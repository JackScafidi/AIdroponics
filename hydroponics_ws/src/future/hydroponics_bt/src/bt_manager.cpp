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

/// @file bt_manager.cpp
/// @brief Main BT manager node: loads the XML behavior tree, ticks at 10 Hz,
///        publishes BehaviorTreeStatus, and exposes the shared rclcpp::Node to
///        all BT nodes via the blackboard.

#include <chrono>
#include <memory>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "behaviortree_cpp/bt_factory.h"
#include "behaviortree_cpp/loggers/bt_cout_logger.h"
#include "ament_index_cpp/get_package_share_directory.hpp"

#include "hydroponics_msgs/msg/behavior_tree_status.hpp"
#include "hydroponics_bt/bt_ros_utils.hpp"

// Forward declarations -- each node file registers its nodes with the factory.
namespace hydroponics_bt
{
void registerTransportNodes(BT::BehaviorTreeFactory & factory);
void registerWorkStationNodes(BT::BehaviorTreeFactory & factory);
void registerVisionNodes(BT::BehaviorTreeFactory & factory);
void registerHarvestNodes(BT::BehaviorTreeFactory & factory);
void registerNutrientNodes(BT::BehaviorTreeFactory & factory);
void registerSafetyNodes(BT::BehaviorTreeFactory & factory);
}  // namespace hydroponics_bt

namespace
{

/// Recursively collect node names that are in the given status.
void collectNodesByStatus(
  const BT::Tree & tree,
  BT::NodeStatus target,
  std::vector<std::string> & out)
{
  for (const auto & subtree : tree.subtrees) {
    for (const auto & node : subtree->nodes) {
      if (node->status() == target) {
        out.push_back(node->name());
      }
    }
  }
}

/// Return the deepest RUNNING node path as a slash-separated string.
std::string activeNodePath(const BT::Tree & tree)
{
  std::string deepest;
  for (const auto & subtree : tree.subtrees) {
    for (const auto & node : subtree->nodes) {
      if (node->status() == BT::NodeStatus::RUNNING) {
        deepest = node->name();
      }
    }
  }
  return deepest;
}

/// Map overall tree status to a human-readable system state string.
std::string systemStateString(BT::NodeStatus root_status, bool first_tick)
{
  if (first_tick) {
    return "STARTUP";
  }
  switch (root_status) {
    case BT::NodeStatus::RUNNING: return "RUNNING";
    case BT::NodeStatus::SUCCESS: return "RUNNING";   // tree succeeded one cycle
    case BT::NodeStatus::FAILURE: return "ERROR";
    default: return "STARTUP";
  }
}

}  // namespace

class BtManager : public rclcpp::Node
{
public:
  BtManager()
  : Node("bt_manager")
  {
    // ---- Parameters -------------------------------------------------------
    this->declare_parameter<std::string>("tree_xml_path", "");
    this->declare_parameter<double>("tick_rate_hz", 10.0);

    std::string xml_path = this->get_parameter("tree_xml_path").as_string();
    double tick_rate = this->get_parameter("tick_rate_hz").as_double();

    // Resolve default tree path relative to package share directory.
    if (xml_path.empty()) {
      // Fallback: look for installed tree next to the executable.
      xml_path = std::string(
        ament_index_cpp::get_package_share_directory("hydroponics_bt") +
        "/trees/main_tree.xml");
    }

    RCLCPP_INFO(this->get_logger(), "Loading behavior tree from: %s", xml_path.c_str());
    RCLCPP_INFO(this->get_logger(), "Tick rate: %.1f Hz", tick_rate);

    // ---- BT Factory -------------------------------------------------------
    hydroponics_bt::registerTransportNodes(factory_);
    hydroponics_bt::registerWorkStationNodes(factory_);
    hydroponics_bt::registerVisionNodes(factory_);
    hydroponics_bt::registerHarvestNodes(factory_);
    hydroponics_bt::registerNutrientNodes(factory_);
    hydroponics_bt::registerSafetyNodes(factory_);

    // ---- Blackboard -------------------------------------------------------
    auto blackboard = BT::Blackboard::create();
    blackboard->set<rclcpp::Node::SharedPtr>(
      hydroponics_bt::kNodeKey,
      std::shared_ptr<rclcpp::Node>(this, [](rclcpp::Node *) {}));

    // Seed blackboard with default values used by various BT nodes.
    blackboard->set<double>("inspection_interval_hours", 48.0);
    blackboard->set<bool>("inspection_due", false);
    blackboard->set<bool>("disease_detected", false);
    blackboard->set<bool>("harvest_needed", false);
    blackboard->set<bool>("deficiency_detected", false);
    blackboard->set<bool>("all_healthy", true);
    blackboard->set<int>("current_plan_index", 0);
    blackboard->set<bool>("system_paused", false);

    // ---- Load Tree --------------------------------------------------------
    tree_ = factory_.createTreeFromFile(xml_path, blackboard);
    logger_ = std::make_unique<BT::StdCoutLogger>(tree_);

    // ---- Publisher --------------------------------------------------------
    status_pub_ = this->create_publisher<hydroponics_msgs::msg::BehaviorTreeStatus>(
      "bt/status", rclcpp::QoS(10));

    // ---- Timer at configured tick rate ------------------------------------
    auto period = std::chrono::duration<double>(1.0 / tick_rate);
    tick_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      std::bind(&BtManager::tickCallback, this));
  }

private:
  void tickCallback()
  {
    // Tick the tree once.
    BT::NodeStatus status = tree_.tickOnce();

    // Build and publish status message.
    auto msg = hydroponics_msgs::msg::BehaviorTreeStatus();
    msg.header.stamp = this->now();
    msg.system_state = systemStateString(status, first_tick_);
    msg.active_node_path = activeNodePath(tree_);

    collectNodesByStatus(tree_, BT::NodeStatus::RUNNING, msg.running_nodes);
    collectNodesByStatus(tree_, BT::NodeStatus::FAILURE, msg.failed_nodes);

    status_pub_->publish(msg);

    first_tick_ = false;

    // If the tree reached SUCCESS, the full cycle completed. For a continuously
    // running system we leave the tree in place -- the ReactiveSequence will
    // re-evaluate on the next tick.
    if (status == BT::NodeStatus::FAILURE) {
      RCLCPP_ERROR(this->get_logger(), "Behavior tree returned FAILURE");
    }
  }

  BT::BehaviorTreeFactory factory_;
  BT::Tree tree_;
  std::unique_ptr<BT::StdCoutLogger> logger_;
  rclcpp::Publisher<hydroponics_msgs::msg::BehaviorTreeStatus>::SharedPtr status_pub_;
  rclcpp::TimerBase::SharedPtr tick_timer_;
  bool first_tick_{true};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<BtManager>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
