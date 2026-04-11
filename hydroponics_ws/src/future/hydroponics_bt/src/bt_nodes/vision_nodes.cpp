// MIT License
//
// Copyright (c) 2026 Claudroponics
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

/// @file vision_nodes.cpp
/// @brief BT nodes for vision inspection pipeline: TriggerInspection,
///        CheckPlantMaturity, CheckPlantHealth, CheckChannelDeficiency,
///        SetInspectionLight.

#include <chrono>
#include <memory>
#include <string>

#include "behaviortree_cpp/bt_factory.h"
#include "rclcpp/rclcpp.hpp"

#include "hydroponics_msgs/msg/inspection_result.hpp"
#include "hydroponics_msgs/msg/channel_health_summary.hpp"
#include "hydroponics_msgs/srv/trigger_inspection.hpp"
#include "hydroponics_msgs/srv/set_inspection_light.hpp"
#include "hydroponics_bt/bt_ros_utils.hpp"

namespace hydroponics_bt
{

using InspectionResult  = hydroponics_msgs::msg::InspectionResult;
using ChannelHealth     = hydroponics_msgs::msg::ChannelHealthSummary;
using TriggerInspSrv    = hydroponics_msgs::srv::TriggerInspection;
using SetLightSrv       = hydroponics_msgs::srv::SetInspectionLight;

// ---------------------------------------------------------------------------
// TriggerInspection
// Calls the /trigger_inspection service and waits for a success response.
// ---------------------------------------------------------------------------
class TriggerInspection : public BT::StatefulActionNode
{
public:
  TriggerInspection(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config) {}

  static BT::PortsList providedPorts() { return {}; }

  BT::NodeStatus onStart() override
  {
    auto node = getRosNode(*this);
    if (!client_) {
      client_ = node->create_client<TriggerInspSrv>("trigger_inspection");
    }
    if (!client_->wait_for_service(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "TriggerInspection: service not available");
      return BT::NodeStatus::FAILURE;
    }
    auto req = std::make_shared<TriggerInspSrv::Request>();
    future_ = client_->async_send_request(req).share();
    start_time_ = node->now();
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    auto node = getRosNode(*this);
    rclcpp::spin_some(node);
    if (future_.wait_for(std::chrono::milliseconds(10)) == std::future_status::ready) {
      auto result = future_.get();
      if (result->success) {
        RCLCPP_INFO(node->get_logger(), "TriggerInspection: scan #%u complete", result->scan_number);
        return BT::NodeStatus::SUCCESS;
      }
      RCLCPP_WARN(node->get_logger(), "TriggerInspection: service returned failure");
      return BT::NodeStatus::FAILURE;
    }
    // 30 second timeout
    auto elapsed = (node->now() - start_time_).seconds();
    if (elapsed > 30.0) {
      RCLCPP_ERROR(node->get_logger(), "TriggerInspection: timed out after 30s");
      return BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::RUNNING;
  }

  void onHalted() override
  {
    future_ = {};
  }

private:
  rclcpp::Client<TriggerInspSrv>::SharedPtr client_;
  std::shared_future<TriggerInspSrv::Response::SharedPtr> future_;
  rclcpp::Time start_time_;
};

// ---------------------------------------------------------------------------
// CheckPlantMaturity
// Reads the inspection_result from the blackboard and checks whether the
// plant at plant_index has maturity_state == "mature".
// ---------------------------------------------------------------------------
class CheckPlantMaturity : public BT::SyncActionNode
{
public:
  CheckPlantMaturity(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<int>("plant_index", "Plant position index (0-3)")
    };
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    auto idx_opt = getInput<int>("plant_index");
    if (!idx_opt) {
      RCLCPP_ERROR(node->get_logger(), "CheckPlantMaturity: missing plant_index");
      return BT::NodeStatus::FAILURE;
    }
    int idx = idx_opt.value();

    InspectionResult::SharedPtr result;
    if (!config().blackboard->get("inspection_result", result) || !result) {
      RCLCPP_WARN(node->get_logger(), "CheckPlantMaturity: no inspection_result on blackboard");
      return BT::NodeStatus::FAILURE;
    }

    if (idx < 0 || static_cast<size_t>(idx) >= result->plants.size()) {
      RCLCPP_ERROR(node->get_logger(), "CheckPlantMaturity: plant_index %d out of range", idx);
      return BT::NodeStatus::FAILURE;
    }

    const auto & plant = result->plants[static_cast<size_t>(idx)];
    if (plant.status == "MATURE") {
      RCLCPP_DEBUG(node->get_logger(), "CheckPlantMaturity: plant %d is mature", idx);
      return BT::NodeStatus::SUCCESS;
    }
    return BT::NodeStatus::FAILURE;
  }
};

// ---------------------------------------------------------------------------
// CheckPlantHealth
// Returns SUCCESS if the plant at plant_index has no disease detected.
// ---------------------------------------------------------------------------
class CheckPlantHealth : public BT::SyncActionNode
{
public:
  CheckPlantHealth(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<int>("plant_index", "Plant position index (0-3)")
    };
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    auto idx_opt = getInput<int>("plant_index");
    if (!idx_opt) {
      RCLCPP_ERROR(node->get_logger(), "CheckPlantHealth: missing plant_index");
      return BT::NodeStatus::FAILURE;
    }
    int idx = idx_opt.value();

    InspectionResult::SharedPtr result;
    if (!config().blackboard->get("inspection_result", result) || !result) {
      RCLCPP_WARN(node->get_logger(), "CheckPlantHealth: no inspection_result on blackboard");
      return BT::NodeStatus::FAILURE;
    }

    if (idx < 0 || static_cast<size_t>(idx) >= result->plants.size()) {
      RCLCPP_ERROR(node->get_logger(), "CheckPlantHealth: plant_index %d out of range", idx);
      return BT::NodeStatus::FAILURE;
    }

    const auto & plant = result->plants[static_cast<size_t>(idx)];
    if (plant.health_state == "disease_fungal" || plant.health_state == "disease_bacterial") {
      RCLCPP_WARN(node->get_logger(),
        "CheckPlantHealth: plant %d has disease: %s", idx, plant.health_state.c_str());
      return BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::SUCCESS;
  }
};

// ---------------------------------------------------------------------------
// CheckChannelDeficiency
// Returns SUCCESS if deficiency_prevalence > 0.5 (channel-wide deficiency trend).
// ---------------------------------------------------------------------------
class CheckChannelDeficiency : public BT::SyncActionNode
{
public:
  CheckChannelDeficiency(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts() { return {}; }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    ChannelHealth::SharedPtr health;
    if (!config().blackboard->get("channel_health", health) || !health) {
      RCLCPP_WARN(node->get_logger(), "CheckChannelDeficiency: no channel_health on blackboard");
      return BT::NodeStatus::FAILURE;
    }

    if (health->deficiency_prevalence > 0.5) {
      RCLCPP_INFO(node->get_logger(),
        "CheckChannelDeficiency: deficiency prevalent (%.0f%% affected, primary: %s)",
        health->deficiency_prevalence * 100.0, health->primary_deficiency.c_str());
      return BT::NodeStatus::SUCCESS;
    }
    return BT::NodeStatus::FAILURE;
  }
};

// ---------------------------------------------------------------------------
// SetInspectionLight
// Calls the /set_inspection_light service to turn the inspection LEDs on/off.
// Port: light_on (bool)
// ---------------------------------------------------------------------------
class SetInspectionLight : public BT::StatefulActionNode
{
public:
  SetInspectionLight(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<bool>("light_on", "true to enable inspection LEDs, false to disable")
    };
  }

  BT::NodeStatus onStart() override
  {
    auto node = getRosNode(*this);

    auto on_opt = getInput<bool>("light_on");
    if (!on_opt) {
      RCLCPP_ERROR(node->get_logger(), "SetInspectionLight: missing light_on port");
      return BT::NodeStatus::FAILURE;
    }

    if (!client_) {
      client_ = node->create_client<SetLightSrv>("set_inspection_light");
    }
    if (!client_->wait_for_service(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "SetInspectionLight: service not available");
      return BT::NodeStatus::FAILURE;
    }

    auto req = std::make_shared<SetLightSrv::Request>();
    req->on = on_opt.value();
    future_ = client_->async_send_request(req).share();
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    rclcpp::spin_some(getRosNode(*this));
    if (future_.wait_for(std::chrono::milliseconds(10)) == std::future_status::ready) {
      return future_.get()->success ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::RUNNING;
  }

  void onHalted() override { future_ = {}; }

private:
  rclcpp::Client<SetLightSrv>::SharedPtr client_;
  std::shared_future<SetLightSrv::Response::SharedPtr> future_;
};

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------
void registerVisionNodes(BT::BehaviorTreeFactory & factory, rclcpp::Node::SharedPtr node)
{
  auto bb = BT::Blackboard::create();
  bb->set(kNodeKey, node);

  BT::NodeConfig cfg;
  cfg.blackboard = bb;

  factory.registerNodeType<TriggerInspection>("TriggerInspection");
  factory.registerNodeType<CheckPlantMaturity>("CheckPlantMaturity");
  factory.registerNodeType<CheckPlantHealth>("CheckPlantHealth");
  factory.registerNodeType<CheckChannelDeficiency>("CheckChannelDeficiency");
  factory.registerNodeType<SetInspectionLight>("SetInspectionLight");
}

}  // namespace hydroponics_bt
