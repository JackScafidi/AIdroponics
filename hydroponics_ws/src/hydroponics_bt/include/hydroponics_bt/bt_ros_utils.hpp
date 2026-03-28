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

#ifndef HYDROPONICS_BT__BT_ROS_UTILS_HPP_
#define HYDROPONICS_BT__BT_ROS_UTILS_HPP_

#include <chrono>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "behaviortree_cpp/bt_factory.h"

namespace hydroponics_bt
{

/// Blackboard key used to store the shared rclcpp::Node pointer.
inline constexpr const char * kNodeKey = "ros_node";

/// Retrieve the shared ROS 2 node from the BT blackboard.
/// Every BT node that needs ROS communication should call this in onStart() or
/// tick().
inline rclcpp::Node::SharedPtr getRosNode(const BT::TreeNode & bt_node)
{
  auto node = bt_node.config().blackboard->get<rclcpp::Node::SharedPtr>(kNodeKey);
  if (!node) {
    throw BT::RuntimeError("ROS 2 node not found on blackboard under key '", kNodeKey, "'");
  }
  return node;
}

/// Spin the ROS node until a future completes or a timeout expires.
/// Returns true if the future finished before the timeout.
template<typename FutureT>
bool spinUntilFuture(
  rclcpp::Node::SharedPtr node,
  FutureT & future,
  std::chrono::milliseconds timeout)
{
  auto start = std::chrono::steady_clock::now();
  while (rclcpp::ok()) {
    rclcpp::spin_some(node);
    if (future.wait_for(std::chrono::milliseconds(1)) == std::future_status::ready) {
      return true;
    }
    if ((std::chrono::steady_clock::now() - start) > timeout) {
      return false;
    }
  }
  return false;
}

}  // namespace hydroponics_bt

#endif  // HYDROPONICS_BT__BT_ROS_UTILS_HPP_
