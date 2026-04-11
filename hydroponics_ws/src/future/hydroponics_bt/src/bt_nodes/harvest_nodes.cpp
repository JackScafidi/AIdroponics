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

/// @file harvest_nodes.cpp
/// @brief BT nodes for harvest operations: CheckHarvestNeeded,
///        ExecuteHarvestAction, TransportToPlantIndex, LogHarvestEvent,
///        UpdatePlantState.

#include <chrono>
#include <memory>
#include <string>

#include "behaviortree_cpp/bt_factory.h"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"

#include "hydroponics_msgs/action/execute_harvest.hpp"
#include "hydroponics_msgs/action/transport_to.hpp"
#include "hydroponics_msgs/msg/harvest_plan.hpp"
#include "hydroponics_msgs/msg/harvest_result.hpp"
#include "hydroponics_msgs/msg/plant_position_state.hpp"
#include "hydroponics_bt/bt_ros_utils.hpp"

namespace hydroponics_bt
{

using ExecuteHarvestAction  = hydroponics_msgs::action::ExecuteHarvest;
using GoalHandleHarvest     = rclcpp_action::ClientGoalHandle<ExecuteHarvestAction>;
using TransportToAction     = hydroponics_msgs::action::TransportTo;
using GoalHandleTransport   = rclcpp_action::ClientGoalHandle<TransportToAction>;
using HarvestPlan           = hydroponics_msgs::msg::HarvestPlan;
using HarvestResult         = hydroponics_msgs::msg::HarvestResult;
using PlantPositionState    = hydroponics_msgs::msg::PlantPositionState;

// ---------------------------------------------------------------------------
// CheckHarvestNeeded
// Reads the harvest_plan blackboard key; returns SUCCESS if any actions exist.
// ---------------------------------------------------------------------------
class CheckHarvestNeeded : public BT::SyncActionNode
{
public:
  CheckHarvestNeeded(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts() { return {}; }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);
    HarvestPlan::SharedPtr plan;
    if (!config().blackboard->get("harvest_plan", plan) || !plan) {
      RCLCPP_DEBUG(node->get_logger(), "CheckHarvestNeeded: no harvest_plan on blackboard");
      return BT::NodeStatus::FAILURE;
    }
    if (!plan->actions.empty()) {
      RCLCPP_INFO(node->get_logger(),
        "CheckHarvestNeeded: %zu harvest actions pending (%u cuts, %u replacements)",
        plan->actions.size(), plan->total_cuts, plan->total_replacements);
      return BT::NodeStatus::SUCCESS;
    }
    return BT::NodeStatus::FAILURE;
  }
};

// ---------------------------------------------------------------------------
// ExecuteHarvestAction
// Sends an ExecuteHarvest action goal for a single plant position.
// Ports: plant_index (int), harvest_type (string: "cut" or "replace")
// ---------------------------------------------------------------------------
class ExecuteHarvestActionNode : public BT::StatefulActionNode
{
public:
  ExecuteHarvestActionNode(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<int>("plant_index", "Plant position index (0-3)"),
      BT::InputPort<std::string>("harvest_type", "cut or replace")
    };
  }

  BT::NodeStatus onStart() override
  {
    auto node = getRosNode(*this);

    auto idx_opt  = getInput<int>("plant_index");
    auto type_opt = getInput<std::string>("harvest_type");
    if (!idx_opt || !type_opt) {
      RCLCPP_ERROR(node->get_logger(), "ExecuteHarvestAction: missing required ports");
      return BT::NodeStatus::FAILURE;
    }

    if (!action_client_) {
      action_client_ = rclcpp_action::create_client<ExecuteHarvestAction>(node, "execute_harvest");
    }
    if (!action_client_->wait_for_action_server(std::chrono::seconds(3))) {
      RCLCPP_ERROR(node->get_logger(), "ExecuteHarvestAction: action server not available");
      return BT::NodeStatus::FAILURE;
    }

    // Build a single-action HarvestPlan
    hydroponics_msgs::msg::HarvestAction ha;
    ha.position_index = static_cast<uint8_t>(idx_opt.value());
    ha.action_type = type_opt.value();

    auto goal = ExecuteHarvestAction::Goal{};
    goal.plan.actions.push_back(ha);

    auto send_opts = rclcpp_action::Client<ExecuteHarvestAction>::SendGoalOptions{};
    send_opts.result_callback =
      [this](const GoalHandleHarvest::WrappedResult & wr) {
        result_ = wr;
        done_ = true;
      };

    goal_handle_future_ = action_client_->async_send_goal(goal, send_opts);
    done_ = false;
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    rclcpp::spin_some(getRosNode(*this));

    if (goal_handle_future_.valid() &&
        goal_handle_future_.wait_for(std::chrono::milliseconds(10)) ==
        std::future_status::ready)
    {
      goal_handle_ = goal_handle_future_.get();
      if (!goal_handle_) {
        return BT::NodeStatus::FAILURE;
      }
      goal_handle_future_ = {};
    }

    if (done_) {
      if (result_.code == rclcpp_action::ResultCode::SUCCEEDED && result_.result->success) {
        // Store result on blackboard for LogHarvestEvent
        if (!result_.result->results.empty()) {
          auto r = std::make_shared<HarvestResult>(result_.result->results.front());
          config().blackboard->set("harvest_result", r);
        }
        return BT::NodeStatus::SUCCESS;
      }
      return BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::RUNNING;
  }

  void onHalted() override
  {
    if (goal_handle_) {
      action_client_->async_cancel_goal(goal_handle_);
      goal_handle_.reset();
    }
    done_ = false;
  }

private:
  rclcpp_action::Client<ExecuteHarvestAction>::SharedPtr action_client_;
  std::shared_future<GoalHandleHarvest::SharedPtr> goal_handle_future_;
  GoalHandleHarvest::SharedPtr goal_handle_;
  GoalHandleHarvest::WrappedResult result_;
  bool done_{false};
};

// ---------------------------------------------------------------------------
// TransportToPlantIndex
// Sends a TransportTo action with position_name = "WORK_PLANT_<index>".
// Port: plant_index (int)
// ---------------------------------------------------------------------------
class TransportToPlantIndex : public BT::StatefulActionNode
{
public:
  TransportToPlantIndex(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<int>("plant_index", "Plant position index (0-3)")
    };
  }

  BT::NodeStatus onStart() override
  {
    auto node = getRosNode(*this);
    auto idx_opt = getInput<int>("plant_index");
    if (!idx_opt) {
      RCLCPP_ERROR(node->get_logger(), "TransportToPlantIndex: missing plant_index");
      return BT::NodeStatus::FAILURE;
    }

    std::string pos = "WORK_PLANT_" + std::to_string(idx_opt.value());

    if (!action_client_) {
      action_client_ = rclcpp_action::create_client<TransportToAction>(node, "transport_to");
    }
    if (!action_client_->wait_for_action_server(std::chrono::seconds(3))) {
      RCLCPP_ERROR(node->get_logger(), "TransportToPlantIndex: action server not available");
      return BT::NodeStatus::FAILURE;
    }

    auto goal = TransportToAction::Goal{};
    goal.target_position = pos;

    auto send_opts = rclcpp_action::Client<TransportToAction>::SendGoalOptions{};
    send_opts.result_callback =
      [this](const GoalHandleTransport::WrappedResult & wr) {
        result_ = wr;
        done_ = true;
      };

    goal_handle_future_ = action_client_->async_send_goal(goal, send_opts);
    done_ = false;
    RCLCPP_INFO(node->get_logger(), "TransportToPlantIndex: moving to %s", pos.c_str());
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    rclcpp::spin_some(getRosNode(*this));

    if (goal_handle_future_.valid() &&
        goal_handle_future_.wait_for(std::chrono::milliseconds(10)) ==
        std::future_status::ready)
    {
      goal_handle_ = goal_handle_future_.get();
      if (!goal_handle_) { return BT::NodeStatus::FAILURE; }
      goal_handle_future_ = {};
    }

    if (done_) {
      return (result_.code == rclcpp_action::ResultCode::SUCCEEDED)
        ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::RUNNING;
  }

  void onHalted() override
  {
    if (goal_handle_) {
      action_client_->async_cancel_goal(goal_handle_);
      goal_handle_.reset();
    }
    done_ = false;
  }

private:
  rclcpp_action::Client<TransportToAction>::SharedPtr action_client_;
  std::shared_future<GoalHandleTransport::SharedPtr> goal_handle_future_;
  GoalHandleTransport::SharedPtr goal_handle_;
  GoalHandleTransport::WrappedResult result_;
  bool done_{false};
};

// ---------------------------------------------------------------------------
// LogHarvestEvent
// Reads harvest_result from blackboard and publishes to /hydroponics/harvest_events.
// Always returns SUCCESS.
// ---------------------------------------------------------------------------
class LogHarvestEvent : public BT::SyncActionNode
{
public:
  LogHarvestEvent(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts() { return {}; }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!publisher_) {
      publisher_ = node->create_publisher<HarvestResult>(
        "/hydroponics/harvest_events", rclcpp::QoS(10));
    }

    HarvestResult::SharedPtr result;
    if (config().blackboard->get("harvest_result", result) && result) {
      publisher_->publish(*result);
      RCLCPP_INFO(node->get_logger(),
        "LogHarvestEvent: plant %u, type=%s, weight=%.1fg",
        result->position_index, result->action_type.c_str(), result->weight_grams);
    } else {
      RCLCPP_WARN(node->get_logger(), "LogHarvestEvent: no harvest_result on blackboard");
    }
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Publisher<HarvestResult>::SharedPtr publisher_;
};

// ---------------------------------------------------------------------------
// UpdatePlantState
// Publishes a PlantPositionState update for a given plant index.
// Ports: plant_index (int), new_state (string)
// ---------------------------------------------------------------------------
class UpdatePlantState : public BT::SyncActionNode
{
public:
  UpdatePlantState(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<int>("plant_index", "Plant position index (0-3)"),
      BT::InputPort<std::string>("new_state", "New plant state (e.g. HARVESTED)")
    };
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    auto idx_opt   = getInput<int>("plant_index");
    auto state_opt = getInput<std::string>("new_state");
    if (!idx_opt || !state_opt) {
      RCLCPP_ERROR(node->get_logger(), "UpdatePlantState: missing required ports");
      return BT::NodeStatus::FAILURE;
    }

    if (!publisher_) {
      publisher_ = node->create_publisher<PlantPositionState>(
        "/hydroponics/plant_state_update", rclcpp::QoS(10));
    }

    PlantPositionState msg{};
    msg.position_index = static_cast<uint8_t>(idx_opt.value());
    msg.status = state_opt.value();
    publisher_->publish(msg);

    RCLCPP_INFO(node->get_logger(),
      "UpdatePlantState: plant %d → %s",
      idx_opt.value(), state_opt.value().c_str());
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Publisher<PlantPositionState>::SharedPtr publisher_;
};

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------
void registerHarvestNodes(BT::BehaviorTreeFactory & factory, rclcpp::Node::SharedPtr node)
{
  (void)node;
  factory.registerNodeType<CheckHarvestNeeded>("CheckHarvestNeeded");
  factory.registerNodeType<ExecuteHarvestActionNode>("ExecuteHarvestAction");
  factory.registerNodeType<TransportToPlantIndex>("TransportToPlantIndex");
  factory.registerNodeType<LogHarvestEvent>("LogHarvestEvent");
  factory.registerNodeType<UpdatePlantState>("UpdatePlantState");
}

}  // namespace hydroponics_bt
