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

/// @file work_station_nodes.cpp
/// @brief BT nodes for the harvest work station: Z-axis movement, tool
///        selection, cut execution, gripper control, and Z homing.

#include <chrono>
#include <memory>
#include <string>

#include "behaviortree_cpp/bt_factory.h"
#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "std_srvs/srv/trigger.hpp"
#include "std_srvs/srv/set_bool.hpp"

#include "hydroponics_msgs/action/move_z.hpp"
#include "hydroponics_bt/bt_ros_utils.hpp"

namespace hydroponics_bt
{

using MoveZAction = hydroponics_msgs::action::MoveZ;
using GoalHandleMoveZ = rclcpp_action::ClientGoalHandle<MoveZAction>;

// ---------------------------------------------------------------------------
// MoveZAction -- StatefulActionNode that sends a MoveZ action goal.
// Ports: height_mm (input, double) -- target Z height in millimetres.
// ---------------------------------------------------------------------------
class MoveZAction_ : public BT::StatefulActionNode
{
public:
  MoveZAction_(const std::string & name, const BT::NodeConfig & config)
  : BT::StatefulActionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<double>("height_mm", "Target Z height in millimetres")
    };
  }

  BT::NodeStatus onStart() override
  {
    auto node = getRosNode(*this);

    auto expected_height = getInput<double>("height_mm");
    if (!expected_height) {
      RCLCPP_ERROR(node->get_logger(), "MoveZAction: missing required input 'height_mm'");
      return BT::NodeStatus::FAILURE;
    }
    target_height_ = expected_height.value();

    if (!action_client_) {
      action_client_ = rclcpp_action::create_client<MoveZAction>(
        node, "work_station/move_z");
    }

    if (!action_client_->wait_for_action_server(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "MoveZAction: action server not available");
      return BT::NodeStatus::FAILURE;
    }

    auto goal_msg = MoveZAction::Goal();
    goal_msg.target_height_mm = target_height_;

    auto options = rclcpp_action::Client<MoveZAction>::SendGoalOptions();
    options.result_callback =
      [this](const GoalHandleMoveZ::WrappedResult & result) {
        result_received_ = true;
        action_success_ = (result.code == rclcpp_action::ResultCode::SUCCEEDED) &&
          result.result->success;
      };

    result_received_ = false;
    action_success_ = false;
    action_client_->async_send_goal(goal_msg, options);

    RCLCPP_INFO(
      node->get_logger(), "MoveZAction: moving to %.1f mm", target_height_);
    return BT::NodeStatus::RUNNING;
  }

  BT::NodeStatus onRunning() override
  {
    auto node = getRosNode(*this);
    rclcpp::spin_some(node);

    if (result_received_) {
      if (action_success_) {
        RCLCPP_INFO(
          node->get_logger(), "MoveZAction: reached %.1f mm", target_height_);
        return BT::NodeStatus::SUCCESS;
      } else {
        RCLCPP_WARN(
          node->get_logger(), "MoveZAction: failed to reach %.1f mm", target_height_);
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
    RCLCPP_INFO(getRosNode(*this)->get_logger(), "MoveZAction: halted");
  }

private:
  rclcpp_action::Client<MoveZAction>::SharedPtr action_client_;
  double target_height_{0.0};
  bool result_received_{false};
  bool action_success_{false};
};

// ---------------------------------------------------------------------------
// SelectToolAction -- SyncActionNode that calls the select_tool service.
// The work_station_controller uses std_srvs/SetBool: true = GRIPPER,
// false = CUTTER.
// Ports: tool (input, string: "CUTTER" or "GRIPPER")
// ---------------------------------------------------------------------------
class SelectToolAction : public BT::SyncActionNode
{
public:
  SelectToolAction(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("tool", "Tool to select: CUTTER or GRIPPER")
    };
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    auto expected_tool = getInput<std::string>("tool");
    if (!expected_tool) {
      RCLCPP_ERROR(node->get_logger(), "SelectToolAction: missing required input 'tool'");
      return BT::NodeStatus::FAILURE;
    }
    const std::string & tool_str = expected_tool.value();

    bool use_gripper = false;
    if (tool_str == "GRIPPER") {
      use_gripper = true;
    } else if (tool_str == "CUTTER") {
      use_gripper = false;
    } else {
      RCLCPP_ERROR(
        node->get_logger(),
        "SelectToolAction: unknown tool '%s', expected CUTTER or GRIPPER",
        tool_str.c_str());
      return BT::NodeStatus::FAILURE;
    }

    if (!client_) {
      client_ = node->create_client<std_srvs::srv::SetBool>("select_tool");
    }

    if (!client_->wait_for_service(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "SelectToolAction: service not available");
      return BT::NodeStatus::FAILURE;
    }

    auto request = std::make_shared<std_srvs::srv::SetBool::Request>();
    request->data = use_gripper;

    auto future = client_->async_send_request(request);
    if (!spinUntilFuture(node, future, std::chrono::milliseconds(3000))) {
      RCLCPP_ERROR(node->get_logger(), "SelectToolAction: service call timed out");
      return BT::NodeStatus::FAILURE;
    }

    auto result = future.get();
    if (!result->success) {
      RCLCPP_WARN(
        node->get_logger(),
        "SelectToolAction: service returned failure for tool '%s'", tool_str.c_str());
      return BT::NodeStatus::FAILURE;
    }

    RCLCPP_INFO(node->get_logger(), "SelectToolAction: selected %s", tool_str.c_str());
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Client<std_srvs::srv::SetBool>::SharedPtr client_;
};

// ---------------------------------------------------------------------------
// ExecuteCutAction -- SyncActionNode that calls the execute_cut Trigger service.
// No ports.
// ---------------------------------------------------------------------------
class ExecuteCutAction : public BT::SyncActionNode
{
public:
  ExecuteCutAction(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {};
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!client_) {
      client_ = node->create_client<std_srvs::srv::Trigger>("execute_cut");
    }

    if (!client_->wait_for_service(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "ExecuteCutAction: service not available");
      return BT::NodeStatus::FAILURE;
    }

    auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
    auto future = client_->async_send_request(request);

    if (!spinUntilFuture(node, future, std::chrono::milliseconds(5000))) {
      RCLCPP_ERROR(node->get_logger(), "ExecuteCutAction: service call timed out");
      return BT::NodeStatus::FAILURE;
    }

    auto result = future.get();
    if (!result->success) {
      RCLCPP_WARN(
        node->get_logger(), "ExecuteCutAction: cut failed -- %s", result->message.c_str());
      return BT::NodeStatus::FAILURE;
    }

    RCLCPP_INFO(node->get_logger(), "ExecuteCutAction: cut executed successfully");
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr client_;
};

// ---------------------------------------------------------------------------
// GripperOpenAction -- SyncActionNode: calls gripper_action service with
// data = false (open). Uses std_srvs/SetBool where false = OPEN.
// No ports.
// ---------------------------------------------------------------------------
class GripperOpenAction : public BT::SyncActionNode
{
public:
  GripperOpenAction(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {};
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!client_) {
      client_ = node->create_client<std_srvs::srv::SetBool>("gripper_action");
    }

    if (!client_->wait_for_service(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "GripperOpenAction: service not available");
      return BT::NodeStatus::FAILURE;
    }

    auto request = std::make_shared<std_srvs::srv::SetBool::Request>();
    request->data = false;  // false = OPEN

    auto future = client_->async_send_request(request);
    if (!spinUntilFuture(node, future, std::chrono::milliseconds(3000))) {
      RCLCPP_ERROR(node->get_logger(), "GripperOpenAction: service call timed out");
      return BT::NodeStatus::FAILURE;
    }

    auto result = future.get();
    if (!result->success) {
      RCLCPP_WARN(
        node->get_logger(), "GripperOpenAction: failed -- %s", result->message.c_str());
      return BT::NodeStatus::FAILURE;
    }

    RCLCPP_INFO(node->get_logger(), "GripperOpenAction: gripper opened");
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Client<std_srvs::srv::SetBool>::SharedPtr client_;
};

// ---------------------------------------------------------------------------
// GripperCloseAction -- SyncActionNode: calls gripper_action service with
// data = true (close/grip). Uses std_srvs/SetBool where true = CLOSE.
// No ports.
// ---------------------------------------------------------------------------
class GripperCloseAction : public BT::SyncActionNode
{
public:
  GripperCloseAction(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {};
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!client_) {
      client_ = node->create_client<std_srvs::srv::SetBool>("gripper_action");
    }

    if (!client_->wait_for_service(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "GripperCloseAction: service not available");
      return BT::NodeStatus::FAILURE;
    }

    auto request = std::make_shared<std_srvs::srv::SetBool::Request>();
    request->data = true;  // true = CLOSE / GRIP

    auto future = client_->async_send_request(request);
    if (!spinUntilFuture(node, future, std::chrono::milliseconds(3000))) {
      RCLCPP_ERROR(node->get_logger(), "GripperCloseAction: service call timed out");
      return BT::NodeStatus::FAILURE;
    }

    auto result = future.get();
    if (!result->success) {
      RCLCPP_WARN(
        node->get_logger(), "GripperCloseAction: failed -- %s", result->message.c_str());
      return BT::NodeStatus::FAILURE;
    }

    RCLCPP_INFO(node->get_logger(), "GripperCloseAction: gripper closed");
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Client<std_srvs::srv::SetBool>::SharedPtr client_;
};

// ---------------------------------------------------------------------------
// HomeZAction -- SyncActionNode: calls the home_z Trigger service.
// No ports.
// ---------------------------------------------------------------------------
class HomeZAction : public BT::SyncActionNode
{
public:
  HomeZAction(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config)
  {}

  static BT::PortsList providedPorts()
  {
    return {};
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!client_) {
      client_ = node->create_client<std_srvs::srv::Trigger>("home_z");
    }

    if (!client_->wait_for_service(std::chrono::seconds(2))) {
      RCLCPP_ERROR(node->get_logger(), "HomeZAction: service not available");
      return BT::NodeStatus::FAILURE;
    }

    auto request = std::make_shared<std_srvs::srv::Trigger::Request>();
    auto future = client_->async_send_request(request);

    if (!spinUntilFuture(node, future, std::chrono::milliseconds(10000))) {
      RCLCPP_ERROR(node->get_logger(), "HomeZAction: homing timed out");
      return BT::NodeStatus::FAILURE;
    }

    auto result = future.get();
    if (!result->success) {
      RCLCPP_WARN(
        node->get_logger(), "HomeZAction: homing failed -- %s", result->message.c_str());
      return BT::NodeStatus::FAILURE;
    }

    RCLCPP_INFO(node->get_logger(), "HomeZAction: Z axis homed");
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Client<std_srvs::srv::Trigger>::SharedPtr client_;
};

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------
void registerWorkStationNodes(BT::BehaviorTreeFactory & factory)
{
  factory.registerNodeType<MoveZAction_>("MoveZ");
  factory.registerNodeType<SelectToolAction>("SelectTool");
  factory.registerNodeType<ExecuteCutAction>("ExecuteCut");
  factory.registerNodeType<GripperOpenAction>("GripperOpen");
  factory.registerNodeType<GripperCloseAction>("GripperClose");
  factory.registerNodeType<HomeZAction>("HomeZ");
}

}  // namespace hydroponics_bt
