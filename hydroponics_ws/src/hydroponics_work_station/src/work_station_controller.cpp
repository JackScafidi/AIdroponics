// Copyright (c) 2026 Claudroponics Project
// SPDX-License-Identifier: MIT
//
// work_station_controller.cpp
//
// ROS2 node that drives the harvest work station hardware via micro-ROS ESP32:
//   - Z-axis stepper (vertical positioning)
//   - Turret servo   (tool selection: CUTTER / GRIPPER)
//   - Cutter servo   (blade actuation)
//   - Gripper servo  (open / close / grip-with-force)
//
// Communication with the ESP32 happens over two topics that the micro-ROS
// agent bridges to the MCU firmware:
//   /z_stepper_cmd  (std_msgs/Float64)  -- target Z height in mm
//   /servo_cmd      (std_msgs/String)   -- "channel:angle" pairs
//
// The ESP32 publishes back:
//   /z_position     (std_msgs/Float64)  -- current Z height in mm
//   /harvest_weight (std_msgs/Float64)  -- HX711 load-cell reading in grams

#include <chrono>
#include <cmath>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "std_msgs/msg/float64.hpp"
#include "std_msgs/msg/string.hpp"
#include "std_srvs/srv/trigger.hpp"
#include "std_srvs/srv/set_bool.hpp"

#include "hydroponics_msgs/action/move_z.hpp"
#include "hydroponics_msgs/action/execute_harvest.hpp"
#include "hydroponics_msgs/srv/get_work_station_status.hpp"
#include "hydroponics_msgs/msg/harvest_result.hpp"

using namespace std::chrono_literals;
using namespace std::placeholders;

// ---------------------------------------------------------------------------
// Enumerated states
// ---------------------------------------------------------------------------
enum class ToolType : uint8_t { NONE, CUTTER, GRIPPER };
enum class GripperState : uint8_t { UNKNOWN, OPEN, CLOSED };

enum class HomingState : uint8_t {
  IDLE,
  MOVING_DOWN,      // Moving toward limit switch
  BACKING_OFF,      // Reverse a small amount after switch triggers
  COMPLETE,
  FAILED
};

enum class ZMoveState : uint8_t {
  IDLE,
  MOVING,
  REACHED,
  TIMEOUT,
  ERROR
};

// ---------------------------------------------------------------------------
// Helper: convert enums to human-readable strings
// ---------------------------------------------------------------------------
static const char* tool_to_string(ToolType t)
{
  switch (t) {
    case ToolType::CUTTER:  return "CUTTER";
    case ToolType::GRIPPER: return "GRIPPER";
    default:                return "NONE";
  }
}

static const char* gripper_to_string(GripperState g)
{
  switch (g) {
    case GripperState::OPEN:   return "OPEN";
    case GripperState::CLOSED: return "CLOSED";
    default:                   return "UNKNOWN";
  }
}

// =========================================================================
// WorkStationController -- main ROS2 node
// =========================================================================
class WorkStationController : public rclcpp::Node
{
public:
  using MoveZ          = hydroponics_msgs::action::MoveZ;
  using MoveZGoalH     = rclcpp_action::ServerGoalHandle<MoveZ>;
  using ExecHarvest    = hydroponics_msgs::action::ExecuteHarvest;
  using ExecHarvestGoalH = rclcpp_action::ServerGoalHandle<ExecHarvest>;

  WorkStationController()
  : Node("work_station_controller")
  {
    declare_parameters();
    load_parameters();
    create_publishers();
    create_subscribers();
    create_action_servers();
    create_services();

    status_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(static_cast<int>(1000.0 / publish_rate_hz_)),
      std::bind(&WorkStationController::status_timer_callback, this));

    RCLCPP_INFO(get_logger(),
      "WorkStationController initialised  "
      "[z_max=%.0f mm, safe_z=%.0f mm, rate=%.0f Hz]",
      z_max_travel_mm_, safe_z_height_mm_, publish_rate_hz_);
  }

private:
  // -----------------------------------------------------------------------
  // Parameters
  // -----------------------------------------------------------------------
  // Z-axis
  double z_steps_per_mm_{};
  double z_max_speed_mm_s_{};
  double z_acceleration_mm_s2_{};
  double z_max_travel_mm_{};
  double z_min_position_mm_{};
  // Homing
  double z_homing_speed_mm_s_{};
  double z_homing_backoff_mm_{};
  // Turret servo
  int    turret_servo_channel_{};
  double turret_cutter_angle_deg_{};
  double turret_gripper_angle_deg_{};
  int    turret_move_time_ms_{};
  // Cutter servo
  int    cutter_servo_channel_{};
  double cutter_open_angle_deg_{};
  double cutter_close_angle_deg_{};
  int    cutter_actuate_time_ms_{};
  // Gripper servo
  int    gripper_servo_channel_{};
  double gripper_open_angle_deg_{};
  double gripper_close_angle_deg_{};
  double gripper_grip_angle_deg_{};
  int    gripper_actuate_time_ms_{};
  // Heights
  double default_cut_height_mm_{};
  double grip_height_mm_{};
  double place_height_mm_{};
  double safe_z_height_mm_{};
  // Rate
  double publish_rate_hz_{};

  // -----------------------------------------------------------------------
  // Runtime state (guarded by mutex_)
  // -----------------------------------------------------------------------
  std::mutex mutex_;
  double      current_z_mm_{0.0};
  double      last_weight_grams_{0.0};
  bool        z_homed_{false};
  ToolType    selected_tool_{ToolType::NONE};
  GripperState gripper_state_{GripperState::UNKNOWN};
  HomingState  homing_state_{HomingState::IDLE};
  ZMoveState   z_move_state_{ZMoveState::IDLE};
  double       z_target_mm_{0.0};

  // -----------------------------------------------------------------------
  // ROS2 communication handles
  // -----------------------------------------------------------------------
  rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr  z_stepper_cmd_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr   servo_cmd_pub_;

  rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr z_position_sub_;
  rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr harvest_weight_sub_;

  rclcpp_action::Server<MoveZ>::SharedPtr       move_z_action_;
  rclcpp_action::Server<ExecHarvest>::SharedPtr  exec_harvest_action_;

  rclcpp::Service<std_srvs::srv::SetBool>::SharedPtr     select_tool_srv_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr     execute_cut_srv_;
  rclcpp::Service<std_srvs::srv::SetBool>::SharedPtr     gripper_action_srv_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr     home_z_srv_;
  rclcpp::Service<hydroponics_msgs::srv::GetWorkStationStatus>::SharedPtr status_srv_;

  rclcpp::TimerBase::SharedPtr status_timer_;

  // -----------------------------------------------------------------------
  // Tolerance for considering a Z move complete
  // -----------------------------------------------------------------------
  static constexpr double kZPositionToleranceMm = 0.5;
  static constexpr int    kZMoveTimeoutMs       = 15000;
  static constexpr int    kHomingTimeoutMs       = 20000;

  // =======================================================================
  // Parameter declaration & loading
  // =======================================================================
  void declare_parameters()
  {
    this->declare_parameter("z_steps_per_mm",          400.0);
    this->declare_parameter("z_max_speed_mm_s",         20.0);
    this->declare_parameter("z_acceleration_mm_s2",     50.0);
    this->declare_parameter("z_max_travel_mm",         200.0);
    this->declare_parameter("z_min_position_mm",         0.0);
    this->declare_parameter("z_homing_speed_mm_s",      10.0);
    this->declare_parameter("z_homing_backoff_mm",       2.0);
    this->declare_parameter("turret_servo_channel",        0);
    this->declare_parameter("turret_cutter_angle_deg",   0.0);
    this->declare_parameter("turret_gripper_angle_deg",180.0);
    this->declare_parameter("turret_move_time_ms",       500);
    this->declare_parameter("cutter_servo_channel",        1);
    this->declare_parameter("cutter_open_angle_deg",     0.0);
    this->declare_parameter("cutter_close_angle_deg",   90.0);
    this->declare_parameter("cutter_actuate_time_ms",    300);
    this->declare_parameter("gripper_servo_channel",       2);
    this->declare_parameter("gripper_open_angle_deg",    0.0);
    this->declare_parameter("gripper_close_angle_deg",  70.0);
    this->declare_parameter("gripper_grip_angle_deg",   55.0);
    this->declare_parameter("gripper_actuate_time_ms",   400);
    this->declare_parameter("default_cut_height_mm",    50.0);
    this->declare_parameter("grip_height_mm",           30.0);
    this->declare_parameter("place_height_mm",          25.0);
    this->declare_parameter("safe_z_height_mm",        180.0);
    this->declare_parameter("publish_rate_hz",          10.0);
  }

  void load_parameters()
  {
    z_steps_per_mm_        = this->get_parameter("z_steps_per_mm").as_double();
    z_max_speed_mm_s_      = this->get_parameter("z_max_speed_mm_s").as_double();
    z_acceleration_mm_s2_  = this->get_parameter("z_acceleration_mm_s2").as_double();
    z_max_travel_mm_       = this->get_parameter("z_max_travel_mm").as_double();
    z_min_position_mm_     = this->get_parameter("z_min_position_mm").as_double();
    z_homing_speed_mm_s_   = this->get_parameter("z_homing_speed_mm_s").as_double();
    z_homing_backoff_mm_   = this->get_parameter("z_homing_backoff_mm").as_double();
    turret_servo_channel_  = this->get_parameter("turret_servo_channel").as_int();
    turret_cutter_angle_deg_  = this->get_parameter("turret_cutter_angle_deg").as_double();
    turret_gripper_angle_deg_ = this->get_parameter("turret_gripper_angle_deg").as_double();
    turret_move_time_ms_   = this->get_parameter("turret_move_time_ms").as_int();
    cutter_servo_channel_  = this->get_parameter("cutter_servo_channel").as_int();
    cutter_open_angle_deg_ = this->get_parameter("cutter_open_angle_deg").as_double();
    cutter_close_angle_deg_= this->get_parameter("cutter_close_angle_deg").as_double();
    cutter_actuate_time_ms_= this->get_parameter("cutter_actuate_time_ms").as_int();
    gripper_servo_channel_ = this->get_parameter("gripper_servo_channel").as_int();
    gripper_open_angle_deg_  = this->get_parameter("gripper_open_angle_deg").as_double();
    gripper_close_angle_deg_ = this->get_parameter("gripper_close_angle_deg").as_double();
    gripper_grip_angle_deg_  = this->get_parameter("gripper_grip_angle_deg").as_double();
    gripper_actuate_time_ms_ = this->get_parameter("gripper_actuate_time_ms").as_int();
    default_cut_height_mm_ = this->get_parameter("default_cut_height_mm").as_double();
    grip_height_mm_        = this->get_parameter("grip_height_mm").as_double();
    place_height_mm_       = this->get_parameter("place_height_mm").as_double();
    safe_z_height_mm_      = this->get_parameter("safe_z_height_mm").as_double();
    publish_rate_hz_       = this->get_parameter("publish_rate_hz").as_double();
  }

  // =======================================================================
  // Publishers
  // =======================================================================
  void create_publishers()
  {
    z_stepper_cmd_pub_ = this->create_publisher<std_msgs::msg::Float64>(
      "/z_stepper_cmd", 10);
    servo_cmd_pub_ = this->create_publisher<std_msgs::msg::String>(
      "/servo_cmd", 10);
  }

  // =======================================================================
  // Subscribers
  // =======================================================================
  void create_subscribers()
  {
    z_position_sub_ = this->create_subscription<std_msgs::msg::Float64>(
      "/z_position", 10,
      std::bind(&WorkStationController::on_z_position, this, _1));

    harvest_weight_sub_ = this->create_subscription<std_msgs::msg::Float64>(
      "/harvest_weight", 10,
      std::bind(&WorkStationController::on_harvest_weight, this, _1));
  }

  void on_z_position(const std_msgs::msg::Float64::SharedPtr msg)
  {
    std::lock_guard<std::mutex> lk(mutex_);
    current_z_mm_ = msg->data;

    // Update Z move state when close enough to target
    if (z_move_state_ == ZMoveState::MOVING) {
      if (std::abs(current_z_mm_ - z_target_mm_) <= kZPositionToleranceMm) {
        z_move_state_ = ZMoveState::REACHED;
      }
    }

    // Homing state-machine: position 0.0 from ESP32 means limit switch triggered
    if (homing_state_ == HomingState::MOVING_DOWN && current_z_mm_ <= 0.0) {
      homing_state_ = HomingState::BACKING_OFF;
      publish_z_command(z_homing_backoff_mm_);
    } else if (homing_state_ == HomingState::BACKING_OFF &&
               std::abs(current_z_mm_ - z_homing_backoff_mm_) <= kZPositionToleranceMm)
    {
      homing_state_ = HomingState::COMPLETE;
      z_homed_ = true;
      RCLCPP_INFO(get_logger(), "Z-axis homing complete, position reset to %.1f mm",
                  current_z_mm_);
    }
  }

  void on_harvest_weight(const std_msgs::msg::Float64::SharedPtr msg)
  {
    std::lock_guard<std::mutex> lk(mutex_);
    last_weight_grams_ = msg->data;
    RCLCPP_DEBUG(get_logger(), "Load cell: %.2f g", last_weight_grams_);
  }

  // =======================================================================
  // Low-level command helpers
  // =======================================================================
  void publish_z_command(double height_mm)
  {
    auto msg = std_msgs::msg::Float64();
    msg.data = height_mm;
    z_stepper_cmd_pub_->publish(msg);
  }

  void publish_servo_command(int channel, double angle_deg)
  {
    auto msg = std_msgs::msg::String();
    msg.data = std::to_string(channel) + ":" +
               std::to_string(static_cast<int>(angle_deg));
    servo_cmd_pub_->publish(msg);
    RCLCPP_DEBUG(get_logger(), "Servo cmd: %s", msg.data.c_str());
  }

  // =======================================================================
  // Blocking helpers (used inside action execute callbacks which run in
  // their own threads managed by the action server executor).
  // =======================================================================

  /// Block until z_move_state_ leaves MOVING, or timeout.
  /// Returns true if REACHED, false on TIMEOUT / ERROR.
  bool wait_for_z_reached(int timeout_ms)
  {
    const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);

    while (rclcpp::ok()) {
      {
        std::lock_guard<std::mutex> lk(mutex_);
        if (z_move_state_ == ZMoveState::REACHED) {
          z_move_state_ = ZMoveState::IDLE;
          return true;
        }
        if (z_move_state_ == ZMoveState::ERROR) {
          z_move_state_ = ZMoveState::IDLE;
          return false;
        }
      }
      if (std::chrono::steady_clock::now() >= deadline) {
        std::lock_guard<std::mutex> lk(mutex_);
        z_move_state_ = ZMoveState::TIMEOUT;
        RCLCPP_WARN(get_logger(), "Z move timed out after %d ms", timeout_ms);
        return false;
      }
      std::this_thread::sleep_for(20ms);
    }
    return false;
  }

  /// Command Z to a height and block until arrived.
  bool command_z_blocking(double target_mm, int timeout_ms = kZMoveTimeoutMs)
  {
    // Clamp to valid range
    target_mm = std::clamp(target_mm, z_min_position_mm_, z_max_travel_mm_);

    {
      std::lock_guard<std::mutex> lk(mutex_);
      z_target_mm_   = target_mm;
      z_move_state_  = ZMoveState::MOVING;
    }

    publish_z_command(target_mm);
    RCLCPP_INFO(get_logger(), "Z move commanded to %.1f mm", target_mm);
    return wait_for_z_reached(timeout_ms);
  }

  /// Actuate a servo and sleep for the configured settle time.
  void actuate_servo_blocking(int channel, double angle_deg, int settle_ms)
  {
    publish_servo_command(channel, angle_deg);
    std::this_thread::sleep_for(std::chrono::milliseconds(settle_ms));
  }

  /// Select tool by raising Z to safe height, rotating turret, then returning.
  bool select_tool_blocking(ToolType tool)
  {
    {
      std::lock_guard<std::mutex> lk(mutex_);
      if (selected_tool_ == tool) {
        RCLCPP_INFO(get_logger(), "Tool %s already selected", tool_to_string(tool));
        return true;
      }
    }

    // Move to safe height before turret rotation
    if (!command_z_blocking(safe_z_height_mm_)) {
      RCLCPP_ERROR(get_logger(), "Failed to reach safe Z height for tool change");
      return false;
    }

    double angle = (tool == ToolType::CUTTER)
                   ? turret_cutter_angle_deg_
                   : turret_gripper_angle_deg_;

    actuate_servo_blocking(turret_servo_channel_, angle, turret_move_time_ms_);

    {
      std::lock_guard<std::mutex> lk(mutex_);
      selected_tool_ = tool;
    }
    RCLCPP_INFO(get_logger(), "Tool selected: %s", tool_to_string(tool));
    return true;
  }

  /// Open / close / grip the gripper.
  bool set_gripper_blocking(GripperState target)
  {
    double angle;
    switch (target) {
      case GripperState::OPEN:
        angle = gripper_open_angle_deg_;
        break;
      case GripperState::CLOSED:
        angle = gripper_grip_angle_deg_;  // gentle grip
        break;
      default:
        RCLCPP_WARN(get_logger(), "set_gripper_blocking called with UNKNOWN");
        return false;
    }

    actuate_servo_blocking(gripper_servo_channel_, angle, gripper_actuate_time_ms_);

    {
      std::lock_guard<std::mutex> lk(mutex_);
      gripper_state_ = target;
    }
    RCLCPP_INFO(get_logger(), "Gripper: %s", gripper_to_string(target));
    return true;
  }

  /// Actuate the cutter blade (close then open).
  bool actuate_cutter_blocking()
  {
    {
      std::lock_guard<std::mutex> lk(mutex_);
      if (selected_tool_ != ToolType::CUTTER) {
        RCLCPP_ERROR(get_logger(), "Cannot actuate cutter: tool is %s",
                     tool_to_string(selected_tool_));
        return false;
      }
    }

    RCLCPP_INFO(get_logger(), "Actuating cutter blade");
    // Close blade
    actuate_servo_blocking(cutter_servo_channel_, cutter_close_angle_deg_,
                           cutter_actuate_time_ms_);
    // Re-open blade
    actuate_servo_blocking(cutter_servo_channel_, cutter_open_angle_deg_,
                           cutter_actuate_time_ms_);

    RCLCPP_INFO(get_logger(), "Cutter cycle complete");
    return true;
  }

  /// Run the full homing sequence (blocking).
  bool home_z_blocking()
  {
    RCLCPP_INFO(get_logger(), "Starting Z-axis homing sequence");
    {
      std::lock_guard<std::mutex> lk(mutex_);
      homing_state_ = HomingState::MOVING_DOWN;
      z_homed_ = false;
    }

    // Command Z to 0 at homing speed -- the ESP32 firmware will stop at the
    // limit switch and report position 0.  The state machine in on_z_position
    // handles the back-off automatically.
    publish_z_command(-1.0);  // Negative signals "home" to ESP32 firmware

    const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(kHomingTimeoutMs);

    while (rclcpp::ok()) {
      {
        std::lock_guard<std::mutex> lk(mutex_);
        if (homing_state_ == HomingState::COMPLETE) {
          homing_state_ = HomingState::IDLE;
          return true;
        }
        if (homing_state_ == HomingState::FAILED) {
          homing_state_ = HomingState::IDLE;
          return false;
        }
      }
      if (std::chrono::steady_clock::now() >= deadline) {
        std::lock_guard<std::mutex> lk(mutex_);
        homing_state_ = HomingState::FAILED;
        RCLCPP_ERROR(get_logger(), "Z homing timed out after %d ms", kHomingTimeoutMs);
        return false;
      }
      std::this_thread::sleep_for(20ms);
    }
    return false;
  }

  // =======================================================================
  // Action servers
  // =======================================================================
  void create_action_servers()
  {
    move_z_action_ = rclcpp_action::create_server<MoveZ>(
      this, "move_z",
      std::bind(&WorkStationController::handle_move_z_goal, this, _1, _2),
      std::bind(&WorkStationController::handle_move_z_cancel, this, _1),
      std::bind(&WorkStationController::handle_move_z_accepted, this, _1));

    exec_harvest_action_ = rclcpp_action::create_server<ExecHarvest>(
      this, "execute_harvest",
      std::bind(&WorkStationController::handle_harvest_goal, this, _1, _2),
      std::bind(&WorkStationController::handle_harvest_cancel, this, _1),
      std::bind(&WorkStationController::handle_harvest_accepted, this, _1));
  }

  // -- MoveZ action -------------------------------------------------------
  rclcpp_action::GoalResponse handle_move_z_goal(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const MoveZ::Goal> goal)
  {
    double h = goal->target_height_mm;
    RCLCPP_INFO(get_logger(), "MoveZ goal received: %.1f mm", h);

    if (h < z_min_position_mm_ || h > z_max_travel_mm_) {
      RCLCPP_WARN(get_logger(),
        "MoveZ goal %.1f mm out of range [%.1f, %.1f]",
        h, z_min_position_mm_, z_max_travel_mm_);
      return rclcpp_action::GoalResponse::REJECT;
    }
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handle_move_z_cancel(
    const std::shared_ptr<MoveZGoalH>)
  {
    RCLCPP_INFO(get_logger(), "MoveZ cancel requested");
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handle_move_z_accepted(const std::shared_ptr<MoveZGoalH> goal_handle)
  {
    // Execute in a detached thread so callback group is not blocked.
    std::thread([this, goal_handle]() { execute_move_z(goal_handle); }).detach();
  }

  void execute_move_z(const std::shared_ptr<MoveZGoalH> goal_handle)
  {
    const auto goal = goal_handle->get_goal();
    auto result = std::make_shared<MoveZ::Result>();
    auto feedback = std::make_shared<MoveZ::Feedback>();

    double target = goal->target_height_mm;

    {
      std::lock_guard<std::mutex> lk(mutex_);
      z_target_mm_  = target;
      z_move_state_ = ZMoveState::MOVING;
    }
    publish_z_command(target);

    const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(kZMoveTimeoutMs);

    while (rclcpp::ok()) {
      // Check for cancellation
      if (goal_handle->is_canceling()) {
        // Stop Z by commanding current position
        double cur;
        {
          std::lock_guard<std::mutex> lk(mutex_);
          cur = current_z_mm_;
          z_move_state_ = ZMoveState::IDLE;
        }
        publish_z_command(cur);
        result->success = false;
        result->final_height_mm = cur;
        goal_handle->canceled(result);
        RCLCPP_INFO(get_logger(), "MoveZ canceled at %.1f mm", cur);
        return;
      }

      // Publish feedback
      {
        std::lock_guard<std::mutex> lk(mutex_);
        feedback->current_height_mm = current_z_mm_;

        if (z_move_state_ == ZMoveState::REACHED) {
          z_move_state_ = ZMoveState::IDLE;
          result->success = true;
          result->final_height_mm = current_z_mm_;
          goal_handle->succeed(result);
          RCLCPP_INFO(get_logger(), "MoveZ succeeded at %.1f mm", current_z_mm_);
          return;
        }
      }
      goal_handle->publish_feedback(feedback);

      if (std::chrono::steady_clock::now() >= deadline) {
        std::lock_guard<std::mutex> lk(mutex_);
        z_move_state_ = ZMoveState::IDLE;
        result->success = false;
        result->final_height_mm = current_z_mm_;
        goal_handle->abort(result);
        RCLCPP_ERROR(get_logger(), "MoveZ timed out at %.1f mm", current_z_mm_);
        return;
      }

      std::this_thread::sleep_for(50ms);
    }
  }

  // -- ExecuteHarvest action -----------------------------------------------
  rclcpp_action::GoalResponse handle_harvest_goal(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const ExecHarvest::Goal> goal)
  {
    auto actions_count = goal->plan.actions.size();
    RCLCPP_INFO(get_logger(),
      "ExecuteHarvest goal received: %zu actions (%u cuts, %u replacements)",
      actions_count, goal->plan.total_cuts, goal->plan.total_replacements);

    if (actions_count == 0) {
      RCLCPP_WARN(get_logger(), "Empty harvest plan rejected");
      return rclcpp_action::GoalResponse::REJECT;
    }

    {
      std::lock_guard<std::mutex> lk(mutex_);
      if (!z_homed_) {
        RCLCPP_WARN(get_logger(), "Harvest rejected: Z axis not homed");
        return rclcpp_action::GoalResponse::REJECT;
      }
    }

    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handle_harvest_cancel(
    const std::shared_ptr<ExecHarvestGoalH>)
  {
    RCLCPP_INFO(get_logger(), "ExecuteHarvest cancel requested");
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handle_harvest_accepted(const std::shared_ptr<ExecHarvestGoalH> goal_handle)
  {
    std::thread([this, goal_handle]() { execute_harvest(goal_handle); }).detach();
  }

  void execute_harvest(const std::shared_ptr<ExecHarvestGoalH> goal_handle)
  {
    const auto & plan = goal_handle->get_goal()->plan;
    auto result   = std::make_shared<ExecHarvest::Result>();
    auto feedback = std::make_shared<ExecHarvest::Feedback>();

    const auto & actions = plan.actions;
    double total_weight = 0.0;
    uint8_t action_index = 0;

    for (const auto & action : actions) {
      // Check cancellation
      if (goal_handle->is_canceling()) {
        result->success = false;
        result->total_weight_grams = total_weight;
        goal_handle->canceled(result);
        RCLCPP_INFO(get_logger(), "Harvest canceled after %u actions", action_index);
        recover_to_safe();
        return;
      }

      // Publish progress feedback
      feedback->current_action_index = action_index;
      feedback->total_actions = static_cast<uint8_t>(actions.size());
      feedback->current_action_description =
        action.action_type + " at position " +
        std::to_string(action.position_index) +
        " (z=" + std::to_string(static_cast<int>(action.cut_height_mm)) + " mm)";
      goal_handle->publish_feedback(feedback);

      hydroponics_msgs::msg::HarvestResult action_result;
      action_result.position_index = action.position_index;
      action_result.action_type    = action.action_type;
      action_result.success        = false;
      action_result.weight_grams   = 0.0;

      if (action.action_type == "cut") {
        bool ok = execute_single_cut(action.cut_height_mm);
        action_result.success = ok;

        if (ok) {
          // Read weight from load cell after a brief settle
          std::this_thread::sleep_for(500ms);
          {
            std::lock_guard<std::mutex> lk(mutex_);
            action_result.weight_grams = last_weight_grams_;
          }
          total_weight += action_result.weight_grams;
          RCLCPP_INFO(get_logger(),
            "Cut at position %u complete: %.1f g",
            action.position_index, action_result.weight_grams);
        } else {
          RCLCPP_WARN(get_logger(),
            "Cut at position %u failed, continuing with remaining actions",
            action.position_index);
        }

      } else if (action.action_type == "replace") {
        bool ok = execute_single_replace(action.cut_height_mm);
        action_result.success = ok;
        RCLCPP_INFO(get_logger(), "Replace at position %u: %s",
                    action.position_index, ok ? "success" : "failed");
      } else {
        RCLCPP_WARN(get_logger(),
          "Unknown action type '%s' at index %u, skipping",
          action.action_type.c_str(), action_index);
      }

      action_result.header.stamp = this->now();
      result->results.push_back(action_result);
      action_index++;
    }

    // Return Z to safe height
    recover_to_safe();

    result->success = true;
    result->total_weight_grams = total_weight;
    goal_handle->succeed(result);
    RCLCPP_INFO(get_logger(),
      "Harvest complete: %u actions, total %.1f g",
      action_index, total_weight);
  }

  /// Execute a single cut action: select cutter, move to height, cut, retract.
  bool execute_single_cut(double cut_height_mm)
  {
    // Use plant-profile height, fall back to default
    double height = (cut_height_mm > 0.0) ? cut_height_mm : default_cut_height_mm_;

    if (!select_tool_blocking(ToolType::CUTTER)) {
      return false;
    }
    if (!command_z_blocking(height)) {
      return false;
    }
    if (!actuate_cutter_blocking()) {
      return false;
    }
    // Retract to safe height
    if (!command_z_blocking(safe_z_height_mm_)) {
      RCLCPP_WARN(get_logger(), "Post-cut retract failed");
      // Non-fatal: the cut itself succeeded
    }
    return true;
  }

  /// Execute a single replace action: select gripper, grip, lift.
  bool execute_single_replace(double height_mm)
  {
    double height = (height_mm > 0.0) ? height_mm : grip_height_mm_;

    if (!select_tool_blocking(ToolType::GRIPPER)) {
      return false;
    }
    // Open gripper before descending
    if (!set_gripper_blocking(GripperState::OPEN)) {
      return false;
    }
    // Lower to grip height
    if (!command_z_blocking(height)) {
      return false;
    }
    // Grip
    if (!set_gripper_blocking(GripperState::CLOSED)) {
      return false;
    }
    // Lift
    if (!command_z_blocking(safe_z_height_mm_)) {
      return false;
    }
    return true;
  }

  /// Best-effort return to safe Z and open gripper.
  void recover_to_safe()
  {
    RCLCPP_INFO(get_logger(), "Recovering to safe position");
    command_z_blocking(safe_z_height_mm_);
    set_gripper_blocking(GripperState::OPEN);
  }

  // =======================================================================
  // Services
  // =======================================================================
  void create_services()
  {
    // SelectTool -- SetBool: true = GRIPPER, false = CUTTER
    select_tool_srv_ = this->create_service<std_srvs::srv::SetBool>(
      "select_tool",
      std::bind(&WorkStationController::on_select_tool, this, _1, _2));

    // ExecuteCut -- Trigger
    execute_cut_srv_ = this->create_service<std_srvs::srv::Trigger>(
      "execute_cut",
      std::bind(&WorkStationController::on_execute_cut, this, _1, _2));

    // GripperAction -- SetBool: true = CLOSE/GRIP, false = OPEN
    gripper_action_srv_ = this->create_service<std_srvs::srv::SetBool>(
      "gripper_action",
      std::bind(&WorkStationController::on_gripper_action, this, _1, _2));

    // HomeZ -- Trigger
    home_z_srv_ = this->create_service<std_srvs::srv::Trigger>(
      "home_z",
      std::bind(&WorkStationController::on_home_z, this, _1, _2));

    // GetWorkStationStatus
    status_srv_ = this->create_service<hydroponics_msgs::srv::GetWorkStationStatus>(
      "get_work_station_status",
      std::bind(&WorkStationController::on_get_status, this, _1, _2));
  }

  void on_select_tool(
    const std_srvs::srv::SetBool::Request::SharedPtr request,
    std_srvs::srv::SetBool::Response::SharedPtr response)
  {
    ToolType target = request->data ? ToolType::GRIPPER : ToolType::CUTTER;
    RCLCPP_INFO(get_logger(), "SelectTool service: %s", tool_to_string(target));

    bool ok = select_tool_blocking(target);
    response->success = ok;
    response->message = ok
      ? std::string("Selected ") + tool_to_string(target)
      : "Tool selection failed";
  }

  void on_execute_cut(
    const std_srvs::srv::Trigger::Request::SharedPtr,
    std_srvs::srv::Trigger::Response::SharedPtr response)
  {
    RCLCPP_INFO(get_logger(), "ExecuteCut service called");

    {
      std::lock_guard<std::mutex> lk(mutex_);
      if (selected_tool_ != ToolType::CUTTER) {
        response->success = false;
        response->message = "Cutter not selected. Call SelectTool first.";
        RCLCPP_WARN(get_logger(), "%s", response->message.c_str());
        return;
      }
    }

    bool ok = actuate_cutter_blocking();
    response->success = ok;
    response->message = ok ? "Cut executed" : "Cutter actuation failed";
  }

  void on_gripper_action(
    const std_srvs::srv::SetBool::Request::SharedPtr request,
    std_srvs::srv::SetBool::Response::SharedPtr response)
  {
    GripperState target = request->data ? GripperState::CLOSED : GripperState::OPEN;
    RCLCPP_INFO(get_logger(), "GripperAction service: %s",
                gripper_to_string(target));

    {
      std::lock_guard<std::mutex> lk(mutex_);
      if (selected_tool_ != ToolType::GRIPPER) {
        response->success = false;
        response->message = "Gripper not selected. Call SelectTool first.";
        RCLCPP_WARN(get_logger(), "%s", response->message.c_str());
        return;
      }
    }

    bool ok = set_gripper_blocking(target);
    response->success = ok;
    response->message = ok
      ? std::string("Gripper ") + gripper_to_string(target)
      : "Gripper actuation failed";
  }

  void on_home_z(
    const std_srvs::srv::Trigger::Request::SharedPtr,
    std_srvs::srv::Trigger::Response::SharedPtr response)
  {
    RCLCPP_INFO(get_logger(), "HomeZ service called");
    bool ok = home_z_blocking();
    response->success = ok;
    response->message = ok ? "Z homed successfully" : "Z homing failed";
  }

  void on_get_status(
    const hydroponics_msgs::srv::GetWorkStationStatus::Request::SharedPtr,
    hydroponics_msgs::srv::GetWorkStationStatus::Response::SharedPtr response)
  {
    std::lock_guard<std::mutex> lk(mutex_);
    response->z_position_mm  = current_z_mm_;
    response->selected_tool  = tool_to_string(selected_tool_);
    response->gripper_state  = gripper_to_string(gripper_state_);
  }

  // =======================================================================
  // Periodic status timer
  // =======================================================================
  void status_timer_callback()
  {
    // Lightweight heartbeat log at debug level so operators can confirm the
    // node is alive without flooding the console.
    std::lock_guard<std::mutex> lk(mutex_);
    RCLCPP_DEBUG(get_logger(),
      "Status: z=%.1f mm  tool=%s  gripper=%s  homed=%s",
      current_z_mm_, tool_to_string(selected_tool_),
      gripper_to_string(gripper_state_),
      z_homed_ ? "yes" : "no");
  }
};

// =========================================================================
// main
// =========================================================================
int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<WorkStationController>();

  // Use a multi-threaded executor so that action execution threads can
  // receive subscription callbacks concurrently.
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();

  rclcpp::shutdown();
  return 0;
}
