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

/// @file transport_nodes.cpp
/// @brief BT nodes for linear-rail transport: TransportTo, WaitForTransport,
///        TransportToPlantIndex.

#include <memory>
#include <string>

#include "behaviortree_cpp/bt_factory.h"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"

#include "hydroponics_msgs/action/transport_to.hpp"
#include "hydroponics_msgs/msg/transport_status.hpp"
#include "hydroponics_bt/bt_ros_utils.hpp"

namespace hydroponics_bt
{

using TransportToAction = hydroponics_msgs::action::TransportTo;
using GoalHandleTransport = rclcpp_action::ClientGoalHandle<TransportToAction>;

// ---------------------------------------------------------------------------
// TransportTo -- StatefulActionNode that sends a TransportTo action goal.
// Ports: target_position (input, string: WORK / GROW / INSPECT / WORK_PLANT_0..3)
// ---------------------------------------------------------------------------
class TransportTo : public BT::StatefulActionNode
{
public:
  TransportTo(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("target_position", "Target rail position")
    };
  }

  BT::NodeStatus onStart() override
  {
    auto node = getRosNode(*this);

    auto expected_target = getInput<std::string>("target_position");
    if (!expected_target) {
      RCLCPP_ERROR(
        node->get_logger(), "TransportTo: missing required input 'target_position'");
      return BT::NodeStatus::FAILURE;
    }
    target_ = expected_target.value();

    // Create action client on first use.
    if (!action_client_) {
      action_client_ = rclcpp_action::create_client<TransportToAction>(
        node, "transport/transport_to");
    }

    if (!action_client_->wait_for_action_server(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "TransportTo: action server not available");
      return BT::NodeStatus::FAILURE;
    }

    auto goal_msg = TransportToAction::Goal();
    goal_msg.target_position = target_;

    auto send_goal_options = rclcpp_action::Client<TransportToAction>::SendGoalOptions();
    send_goal_options.result_callback =
      [this](const GoalHandleTransport::WrappedResult & result) {
        result_received_ = true;
        action_success_ = (result.code == rclcpp_action::ResultCode::SUCCEEDED) &&
          result.result->success;
      };

    result_received_ = false;
    action_success_ = false;
    auto goal_future = action_client_->async_send_goal(goal_msg, send_goal_options);

    RCLCPP_INFO(node->get_logger(), "TransportTo: sending goal -> %s", target_.c_str());
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    auto node = getRosNode(*this);
    rclcpp::spin_some(node);

    if (result_received_) {
      if (action_success_) {
        RCLCPP_INFO(node->get_logger(), "TransportTo: reached %s", target_.c_str());
        return BT::NodeStatus::SUCCESS;
      } else {
        RCLCPP_WARN(node->get_logger(), "TransportTo: failed to reach %s", target_.c_str());
        return BT::NodeStatus::FAILURE;
      }
    }
    return BT::NodeStatus::RUNNING;
  }

  void onHalted() override
  {
    if (action_client_) {
      action_client_->async_cancel_all_goals();
    }
    RCLCPP_INFO(getRosNode(*this)->get_logger(), "TransportTo: halted");
  }

private:
  rclcpp_action::Client<TransportToAction>::SharedPtr action_client_;
  std::string target_;
  bool result_received_{false};
  bool action_success_{false};
};

// ---------------------------------------------------------------------------
// WaitForTransport -- ConditionNode that checks if the rail is stationary.
// Subscribes to transport/status, returns SUCCESS when is_moving == false.
// ---------------------------------------------------------------------------
class WaitForTransport : public BT::ConditionNode
{
public:
  WaitForTransport(const std::string & name, const BT::NodeConfig & config)
  : BT::ConditionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {};
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!sub_) {
      sub_ = node->create_subscription<hydroponics_msgs::msg::TransportStatus>(
        "transport/status", rclcpp::QoS(10),
        [this](const hydroponics_msgs::msg::TransportStatus::SharedPtr msg) {
          latest_moving_ = msg->is_moving;
          received_ = true;
        });
    }

    rclcpp::spin_some(node);

    if (received_ && !latest_moving_) {
      return BT::NodeStatus::SUCCESS;
    }
    return BT::NodeStatus::FAILURE;
  }

private:
  rclcpp::Subscription<hydroponics_msgs::msg::TransportStatus>::SharedPtr sub_;
  bool latest_moving_{true};
  bool received_{false};
};

// ---------------------------------------------------------------------------
// TransportToPlantIndex -- Convenience StatefulActionNode that converts a
// plant index (0..3) into a WORK_PLANT_<n> position string and delegates to
// the TransportTo action.
// Ports: plant_index (input, int)
// ---------------------------------------------------------------------------
class TransportToPlantIndex : public BT::StatefulActionNode
{
public:
  TransportToPlantIndex(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<int>("plant_index", "Plant position index 0-3")
    };
  }

  BT::NodeStatus onStart() override
  {
    auto node = getRosNode(*this);

    auto expected_idx = getInput<int>("plant_index");
    if (!expected_idx) {
      RCLCPP_ERROR(node->get_logger(), "TransportToPlantIndex: missing 'plant_index'");
      return BT::NodeStatus::FAILURE;
    }
    int idx = expected_idx.value();
    if (idx < 0 || idx > 3) {
      RCLCPP_ERROR(node->get_logger(), "TransportToPlantIndex: index %d out of range", idx);
      return BT::NodeStatus::FAILURE;
    }

    target_ = "WORK_PLANT_" + std::to_string(idx);

    if (!action_client_) {
      action_client_ = rclcpp_action::create_client<TransportToAction>(
        node, "transport/transport_to");
    }

    if (!action_client_->wait_for_action_server(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "TransportToPlantIndex: action server unavailable");
      return BT::NodeStatus::FAILURE;
    }

    auto goal_msg = TransportToAction::Goal();
    goal_msg.target_position = target_;

    auto options = rclcpp_action::Client<TransportToAction>::SendGoalOptions();
    options.result_callback =
      [this](const GoalHandleTransport::WrappedResult & result) {
        result_received_ = true;
        action_success_ = (result.code == rclcpp_action::ResultCode::SUCCEEDED) &&
          result.result->success;
      };

    result_received_ = false;
    action_success_ = false;
    action_client_->async_send_goal(goal_msg, options);

    RCLCPP_INFO(
      node->get_logger(), "TransportToPlantIndex: moving to %s", target_.c_str());
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    auto node = getRosNode(*this);
    rclcpp::spin_some(node);

    if (result_received_) {
      if (action_success_) {
        RCLCPP_INFO(node->get_logger(), "TransportToPlantIndex: reached %s", target_.c_str());
        return BT::NodeStatus::SUCCESS;
      } else {
        RCLCPP_WARN(
          node->get_logger(), "TransportToPlantIndex: failed to reach %s", target_.c_str());
        return BT::NodeStatus::FAILURE;
      }
    }
    return BT::NodeStatus::RUNNING;
  }

  void onHalted() override
  {
    if (action_client_) {
      action_client_->async_cancel_all_goals();
    }
  }

private:
  rclcpp_action::Client<TransportToAction>::SharedPtr action_client_;
  std::string target_;
  bool result_received_{false};
  bool action_success_{false};
};

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------
void registerTransportNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<TransportTo>("TransportTo");
  factory.registerNodeType<WaitForTransport>("WaitForTransport");
  factory.registerNodeType<TransportToPlantIndex>("TransportToPlantIndex");
}

}  // namespace hydroponics_bt
