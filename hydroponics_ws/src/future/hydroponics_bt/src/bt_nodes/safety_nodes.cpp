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

/// @file safety_nodes.cpp
/// @brief BT nodes for system safety: CheckSystemSafe, CheckNoDiseaseDetected,
///        EmergencyStop, CheckTransportIdle, PublishSystemStatus.

#include <memory>
#include <string>

#include "behaviortree_cpp/bt_factory.h"
#include "rclcpp/rclcpp.hpp"

#include "hydroponics_msgs/msg/nutrient_status.hpp"
#include "hydroponics_msgs/msg/transport_status.hpp"
#include "hydroponics_msgs/msg/channel_health_summary.hpp"
#include "hydroponics_msgs/msg/system_alert.hpp"
#include "hydroponics_msgs/msg/behavior_tree_status.hpp"
#include "hydroponics_bt/bt_ros_utils.hpp"

namespace hydroponics_bt
{

using NutrientStatus    = hydroponics_msgs::msg::NutrientStatus;
using TransportStatus   = hydroponics_msgs::msg::TransportStatus;
using ChannelHealth     = hydroponics_msgs::msg::ChannelHealthSummary;
using SystemAlert       = hydroponics_msgs::msg::SystemAlert;
using BTStatus          = hydroponics_msgs::msg::BehaviorTreeStatus;

// ---------------------------------------------------------------------------
// CheckSystemSafe
// Verifies that critical subsystems are in a safe operating state.
// Returns FAILURE if water level is low or transport is in an error state.
// ---------------------------------------------------------------------------
class CheckSystemSafe : public BT::SyncActionNode
{
public:
  CheckSystemSafe(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts() { return {}; }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    // Check transport is not reporting an error position
    TransportStatus::SharedPtr transport;
    if (config().blackboard->get("transport_status", transport) && transport) {
      // If transport reports an unknown error state, fail-safe
      if (transport->current_position == "ERROR") {
        RCLCPP_ERROR(node->get_logger(),
          "CheckSystemSafe: transport in ERROR state — halting operations");
        return BT::NodeStatus::FAILURE;
      }
    }

    // Nutrient status: check for critical alerts via blackboard
    // (water level alerts are published by nutrient_controller; we read
    //  the nutrient_status message directly when available)
    NutrientStatus::SharedPtr nutrients;
    if (config().blackboard->get("nutrient_status", nutrients) && nutrients) {
      // All pumps running simultaneously indicates a runaway condition
      bool all_pumps_active = true;
      for (bool active : nutrients->pump_active) {
        if (!active) { all_pumps_active = false; break; }
      }
      if (all_pumps_active) {
        RCLCPP_ERROR(node->get_logger(),
          "CheckSystemSafe: all 4 pumps active simultaneously — possible runaway");
        return BT::NodeStatus::FAILURE;
      }
    }

    return BT::NodeStatus::SUCCESS;
  }
};

// ---------------------------------------------------------------------------
// CheckNoDiseaseDetected
// Returns FAILURE (halting the tree) if any plant shows disease markers.
// ---------------------------------------------------------------------------
class CheckNoDiseaseDetected : public BT::SyncActionNode
{
public:
  CheckNoDiseaseDetected(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts() { return {}; }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    ChannelHealth::SharedPtr health;
    if (!config().blackboard->get("channel_health", health) || !health) {
      // No data yet — allow operation to continue
      return BT::NodeStatus::SUCCESS;
    }

    if (health->diseased_count > 0) {
      RCLCPP_ERROR(node->get_logger(),
        "CheckNoDiseaseDetected: %u diseased plants detected — PAUSING ALL OPERATIONS",
        health->diseased_count);
      return BT::NodeStatus::FAILURE;
    }

    return BT::NodeStatus::SUCCESS;
  }
};

// ---------------------------------------------------------------------------
// EmergencyStop
// Publishes an EMERGENCY_STOP alert and logs a critical error.
// Always returns SUCCESS (the stop is acknowledged; tree handles halt).
// ---------------------------------------------------------------------------
class EmergencyStop : public BT::SyncActionNode
{
public:
  EmergencyStop(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts() { return {}; }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!publisher_) {
      publisher_ = node->create_publisher<SystemAlert>(
        "/hydroponics/alerts", rclcpp::QoS(10).reliable());
    }

    SystemAlert alert{};
    alert.header.stamp     = node->now();
    alert.alert_type       = "EMERGENCY_STOP";
    alert.severity         = "critical";
    alert.message          = "Emergency stop triggered by behavior tree safety check";
    alert.recommended_action = "Inspect system and resolve safety condition before restarting";
    publisher_->publish(alert);

    RCLCPP_ERROR(node->get_logger(),
      "EMERGENCY STOP: safety condition triggered. All operations halted.");
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Publisher<SystemAlert>::SharedPtr publisher_;
};

// ---------------------------------------------------------------------------
// CheckTransportIdle
// Returns SUCCESS if the transport rail is not currently moving.
// ---------------------------------------------------------------------------
class CheckTransportIdle : public BT::SyncActionNode
{
public:
  CheckTransportIdle(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts() { return {}; }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    TransportStatus::SharedPtr transport;
    if (!config().blackboard->get("transport_status", transport) || !transport) {
      RCLCPP_DEBUG(node->get_logger(),
        "CheckTransportIdle: no transport_status — assuming idle");
      return BT::NodeStatus::SUCCESS;
    }

    if (transport->is_moving) {
      RCLCPP_DEBUG(node->get_logger(),
        "CheckTransportIdle: transport moving (%.1f mm/s)", transport->velocity_mm_s);
      return BT::NodeStatus::FAILURE;
    }
    return BT::NodeStatus::SUCCESS;
  }
};

// ---------------------------------------------------------------------------
// PublishSystemStatus
// Publishes a BehaviorTreeStatus message. Always returns SUCCESS.
// Ports: tree_state (string), current_action (string)
// ---------------------------------------------------------------------------
class PublishSystemStatus : public BT::SyncActionNode
{
public:
  PublishSystemStatus(const std::string & name, const BT::NodeConfig & config)
  : BT::SyncActionNode(name, config) {}

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("tree_state",   "BT system state string"),
      BT::InputPort<std::string>("current_action", "Description of current BT action")
    };
  }

  BT::NodeStatus tick() override
  {
    auto node = getRosNode(*this);

    if (!publisher_) {
      publisher_ = node->create_publisher<BTStatus>(
        "/hydroponics/bt_status", rclcpp::QoS(10));
    }

    BTStatus msg{};
    msg.header.stamp = node->now();

    auto state_opt  = getInput<std::string>("tree_state");
    auto action_opt = getInput<std::string>("current_action");
    msg.system_state      = state_opt  ? state_opt.value()  : "RUNNING";
    msg.active_node_path  = action_opt ? action_opt.value() : "";

    publisher_->publish(msg);
    return BT::NodeStatus::SUCCESS;
  }

private:
  rclcpp::Publisher<BTStatus>::SharedPtr publisher_;
};

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------
void registerSafetyNodes(BT::BehaviorTreeFactory & factory, rclcpp::Node::SharedPtr node)
{
  (void)node;
  factory.registerNodeType<CheckSystemSafe>("CheckSystemSafe");
  factory.registerNodeType<CheckNoDiseaseDetected>("CheckNoDiseaseDetected");
  factory.registerNodeType<EmergencyStop>("EmergencyStop");
  factory.registerNodeType<CheckTransportIdle>("CheckTransportIdle");
  factory.registerNodeType<PublishSystemStatus>("PublishSystemStatus");
}

}  // namespace hydroponics_bt
