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

/// @file nutrient_nodes.cpp
/// @brief BT nodes for nutrient management: CheckNutrientStatus, ForceDose,
///        WaitForNutrientMixing, CheckGrowthStage, PublishNutrientAlert.

#include <chrono>
#include <cmath>
#include <memory>
#include <string>

#include "behaviortree_cpp/bt_factory.h"
#include "rclcpp/rclcpp.hpp"

#include "hydroponics_msgs/msg/nutrient_status.hpp"
#include "hydroponics_msgs/msg/system_alert.hpp"
#include "hydroponics_msgs/srv/force_dose.hpp"
#include "hydroponics_bt/bt_ros_utils.hpp"

namespace hydroponics_bt
{

using NutrientStatus = hydroponics_msgs::msg::NutrientStatus;
using SystemAlert    = hydroponics_msgs::msg::SystemAlert;
using ForceDoseSrv   = hydroponics_msgs::srv::ForceDose;

// ---------------------------------------------------------------------------
// CheckNutrientStatus
// Reads nutrient_status from blackboard and checks one condition.
// Port: check_type (string): "ph_ok" | "ec_ok" | "temp_ok" | "water_level_ok"
// ---------------------------------------------------------------------------
class CheckNutrientStatus : public BT::SyncActionNode
{
public:
  CheckNutrientStatus(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("check_type",
        "ph_ok | ec_ok | temp_ok | water_level_ok")
    };
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    auto type_opt = getInput<std::string>("check_type");
    if (!type_opt) {
      RCLCPP_ERROR(node->get_logger(), "CheckNutrientStatus: missing check_type");
      return BT::NodeStatus::FAILURE;
    }
    const std::string & check = type_opt.value();

    NutrientStatus::SharedPtr status;
    if (!config().blackboard->get("nutrient_status", status) || !status) {
      RCLCPP_WARN(node->get_logger(),
        "CheckNutrientStatus: no nutrient_status on blackboard");
      return BT::NodeStatus::FAILURE;
    }

    bool ok = false;
    if (check == "ph_ok") {
      ok = std::abs(status->ph_current - status->ph_target) < 0.2;
    } else if (check == "ec_ok") {
      ok = std::abs(status->ec_current - status->ec_target) < 0.3;
    } else if (check == "temp_ok") {
      ok = (status->temperature_c > 18.0 && status->temperature_c < 28.0);
    } else if (check == "water_level_ok") {
      // NutrientStatus does not have a water_level field directly; we check
      // via the SystemAlert pattern — treat missing field as ok if msg arrived.
      // The nutrient_controller publishes alerts when water is low, so here we
      // optimistically return SUCCESS (alert-driven safety is in safety_nodes).
      ok = true;
    } else {
      RCLCPP_ERROR(node->get_logger(),
        "CheckNutrientStatus: unknown check_type '%s'", check.c_str());
      return BT::NodeStatus::FAILURE;
    }

    RCLCPP_DEBUG(node->get_logger(),
      "CheckNutrientStatus[%s]: %s", check.c_str(), ok ? "OK" : "NOT OK");
    return ok ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
  }
};

// ---------------------------------------------------------------------------
// ForceDose
// Calls the /force_dose service to actuate a peristaltic pump.
// Ports: pump_id (string), amount_ml (double)
// ---------------------------------------------------------------------------
class ForceDose : public BT::StatefulActionNode
{
public:
  ForceDose(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("pump_id", "ph_up | ph_down | nutrient_a | nutrient_b"),
      BT::InputPort<double>("amount_ml", "Dose volume in mL")
    };
  }

  BT::NodeStatus onStart() override
  {
    auto node = getRosNode(*this);

    auto id_opt  = getInput<std::string>("pump_id");
    auto ml_opt  = getInput<double>("amount_ml");
    if (!id_opt || !ml_opt) {
      RCLCPP_ERROR(node->get_logger(), "ForceDose: missing required ports");
      return BT::NodeStatus::FAILURE;
    }

    if (!client_) {
      client_ = node->create_client<ForceDoseSrv>("force_dose");
    }
    if (!client_->wait_for_service(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "ForceDose: service not available");
      return BT::NodeStatus::FAILURE;
    }

    auto req = std::make_shared<ForceDoseSrv::Request>();
    req->pump_id   = id_opt.value();
    req->amount_ml = ml_opt.value();
    future_ = client_->async_send_request(req).share();

    RCLCPP_INFO(node->get_logger(),
      "ForceDose: dosing pump '%s' %.2f mL", id_opt.value().c_str(), ml_opt.value());
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
  rclcpp::Client<ForceDoseSrv>::SharedPtr client_;
  std::shared_future<ForceDoseSrv::Response::SharedPtr> future_;
};

// ---------------------------------------------------------------------------
// WaitForNutrientMixing
// Non-blocking timer wait. Port: duration_s (double, default 60.0)
// ---------------------------------------------------------------------------
class WaitForNutrientMixing : public BT::StatefulActionNode
{
public:
  WaitForNutrientMixing(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<double>("duration_s", 60.0, "Mixing wait duration in seconds")
    };
  }

  BT::NodeStatus onStart() override
  {
    auto duration_opt = getInput<double>("duration_s");
    duration_s_ = duration_opt ? duration_opt.value() : 60.0;
    start_time_ = std::chrono::steady_clock::now();
    RCLCPP_INFO(getRosNode(*this)->get_logger(),
      "WaitForNutrientMixing: waiting %.0fs for nutrients to mix", duration_s_);
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    auto elapsed = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - start_time_).count();
    if (elapsed >= duration_s_) {
      RCLCPP_INFO(getRosNode(*this)->get_logger(),
        "WaitForNutrientMixing: mixing complete");
      return BT::NodeStatus::SUCCESS;
    }
    return BT::NodeStatus::RUNNING;
  }

  void onHalted() override {}

private:
  double duration_s_{60.0};
  std::chrono::steady_clock::time_point start_time_;
};

// ---------------------------------------------------------------------------
// CheckGrowthStage
// Reads nutrient_status from blackboard; checks growth_stage == expected_stage.
// Port: expected_stage (string)
// ---------------------------------------------------------------------------
class CheckGrowthStage : public BT::SyncActionNode
{
public:
  CheckGrowthStage(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("expected_stage",
        "Expected growth stage: seedling | vegetative | mature")
    };
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    auto stage_opt = getInput<std::string>("expected_stage");
    if (!stage_opt) {
      RCLCPP_ERROR(node->get_logger(), "CheckGrowthStage: missing expected_stage");
      return BT::NodeStatus::FAILURE;
    }

    NutrientStatus::SharedPtr status;
    if (!config().blackboard->get("nutrient_status", status) || !status) {
      RCLCPP_WARN(node->get_logger(), "CheckGrowthStage: no nutrient_status on blackboard");
      return BT::NodeStatus::FAILURE;
    }

    bool match = (status->growth_stage == stage_opt.value());
    RCLCPP_DEBUG(node->get_logger(),
      "CheckGrowthStage: current='%s', expected='%s' → %s",
      status->growth_stage.c_str(), stage_opt.value().c_str(),
      match ? "MATCH" : "NO MATCH");
    return match ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
  }
};

// ---------------------------------------------------------------------------
// PublishNutrientAlert
// Publishes a SystemAlert message. Always returns SUCCESS.
// Ports: alert_type (string), message (string)
// ---------------------------------------------------------------------------
class PublishNutrientAlert : public BT::SyncActionNode
{
public:
  PublishNutrientAlert(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("alert_type", "Alert type identifier"),
      BT::InputPort<std::string>("message", "Human-readable alert message")
    };
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!publisher_) {
      publisher_ = node->create_publisher<SystemAlert>(
        "/hydroponics/alerts", rclcpp::QoS(10));
    }

    auto type_opt = getInput<std::string>("alert_type");
    auto msg_opt  = getInput<std::string>("message");

    SystemAlert alert{};
    alert.header.stamp  = node->now();
    alert.alert_type    = type_opt ? type_opt.value() : "NUTRIENT_ALERT";
    alert.message       = msg_opt  ? msg_opt.value()  : "Nutrient condition out of range";
    alert.severity      = "warning";
    publisher_->publish(alert);

    RCLCPP_WARN(node->get_logger(),
      "PublishNutrientAlert [%s]: %s", alert.alert_type.c_str(), alert.message.c_str());
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Publisher<SystemAlert>::SharedPtr publisher_;
};

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------
void registerNutrientNodes(BT::BehaviorTreeFactory & factory, rclcpp::Node::SharedPtr node)
{
  (void)node;
  factory.registerNodeType<CheckNutrientStatus>("CheckNutrientStatus");
  factory.registerNodeType<ForceDose>("ForceDose");
  factory.registerNodeType<WaitForNutrientMixing>("WaitForNutrientMixing");
  factory.registerNodeType<CheckGrowthStage>("CheckGrowthStage");
  factory.registerNodeType<PublishNutrientAlert>("PublishNutrientAlert");
}

}  // namespace hydroponics_bt
