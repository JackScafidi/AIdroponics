// Copyright (c) 2026 Claudroponics Project
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

#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "std_msgs/msg/int32.hpp"
#include "hydroponics_msgs/msg/transport_status.hpp"
#include "hydroponics_msgs/action/transport_to.hpp"

using namespace std::chrono_literals;
using namespace std::placeholders;

// ---------------------------------------------------------------------------
// TransportController -- linear-rail motion controller
// ---------------------------------------------------------------------------
//
// Coordinates stepper movement via micro-ROS on an ESP32.  The ESP32 is
// responsible for real-time pulse generation; this node owns the trajectory
// planning, position bookkeeping, homing logic, and action-server interface.
//
// Topic contract with the ESP32 firmware:
//   /rail_stepper_cmd  (pub  Int32)  -- target step count sent to ESP32
//   /rail_position     (sub  Int32)  -- current step count reported by ESP32
//   /limit_switch_states (sub Int32) -- bitmask; bit 0 = home limit switch
// ---------------------------------------------------------------------------

class TransportController : public rclcpp::Node
{
public:
  using TransportTo = hydroponics_msgs::action::TransportTo;
  using TransportToGoalHandle = rclcpp_action::ServerGoalHandle<TransportTo>;
  using TransportStatus = hydroponics_msgs::msg::TransportStatus;

  TransportController()
  : Node("transport_controller")
  {
    declare_parameters();
    load_parameters();

    // Publishers
    status_pub_ = this->create_publisher<TransportStatus>(
      "/transport_status", rclcpp::QoS(10));
    stepper_cmd_pub_ = this->create_publisher<std_msgs::msg::Int32>(
      "/rail_stepper_cmd", rclcpp::QoS(10));

    // Subscribers
    rail_position_sub_ = this->create_subscription<std_msgs::msg::Int32>(
      "/rail_position", rclcpp::QoS(10),
      std::bind(&TransportController::rail_position_callback, this, _1));

    limit_switch_sub_ = this->create_subscription<std_msgs::msg::Int32>(
      "/limit_switch_states", rclcpp::QoS(10),
      std::bind(&TransportController::limit_switch_callback, this, _1));

    // Action server
    action_server_ = rclcpp_action::create_server<TransportTo>(
      this,
      "TransportTo",
      std::bind(&TransportController::handle_goal, this, _1, _2),
      std::bind(&TransportController::handle_cancel, this, _1),
      std::bind(&TransportController::handle_accepted, this, _1));

    // Periodic status publisher & motion tick
    double rate_hz = this->get_parameter("publish_rate_hz").as_double();
    if (rate_hz <= 0.0) {
      RCLCPP_WARN(this->get_logger(), "publish_rate_hz <= 0, defaulting to 10 Hz");
      rate_hz = 10.0;
    }
    auto period = std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::duration<double>(1.0 / rate_hz));
    timer_ = this->create_wall_timer(period,
      std::bind(&TransportController::timer_callback, this));

    RCLCPP_INFO(this->get_logger(),
      "Transport controller initialised  --  %zu named positions loaded, "
      "%.1f steps/mm, max %.1f mm/s",
      named_positions_.size(), steps_per_mm_, max_speed_mm_s_);
  }

private:
  // -----------------------------------------------------------------------
  //  Parameter declaration & loading
  // -----------------------------------------------------------------------

  void declare_parameters()
  {
    this->declare_parameter<double>("steps_per_mm", 80.0);
    this->declare_parameter<double>("max_speed_mm_s", 50.0);
    this->declare_parameter<double>("acceleration_mm_s2", 100.0);
    this->declare_parameter<double>("deceleration_mm_s2", 100.0);

    this->declare_parameter<double>("min_position_mm", 0.0);
    this->declare_parameter<double>("max_position_mm", 1100.0);

    this->declare_parameter<double>("homing_speed_mm_s", 20.0);
    this->declare_parameter<double>("homing_backoff_mm", 5.0);
    this->declare_parameter<int>("home_direction", -1);

    this->declare_parameter<bool>("stallguard_enabled", false);
    this->declare_parameter<int>("stallguard_threshold", 50);

    this->declare_parameter<double>("publish_rate_hz", 10.0);

    // Named positions are loaded as individual parameters under the
    // "positions" prefix.  Declare defaults that match the YAML.
    this->declare_parameter<double>("positions.WORK", 50.0);
    this->declare_parameter<double>("positions.WORK_PLANT_0", 50.0);
    this->declare_parameter<double>("positions.WORK_PLANT_1", 177.0);
    this->declare_parameter<double>("positions.WORK_PLANT_2", 304.0);
    this->declare_parameter<double>("positions.WORK_PLANT_3", 431.0);
    this->declare_parameter<double>("positions.GROW", 500.0);
    this->declare_parameter<double>("positions.INSPECT", 1050.0);
  }

  void load_parameters()
  {
    steps_per_mm_       = this->get_parameter("steps_per_mm").as_double();
    max_speed_mm_s_     = this->get_parameter("max_speed_mm_s").as_double();
    acceleration_mm_s2_ = this->get_parameter("acceleration_mm_s2").as_double();
    deceleration_mm_s2_ = this->get_parameter("deceleration_mm_s2").as_double();
    min_position_mm_    = this->get_parameter("min_position_mm").as_double();
    max_position_mm_    = this->get_parameter("max_position_mm").as_double();
    homing_speed_mm_s_  = this->get_parameter("homing_speed_mm_s").as_double();
    homing_backoff_mm_  = this->get_parameter("homing_backoff_mm").as_double();
    home_direction_     = this->get_parameter("home_direction").as_int();

    // Load named positions
    const std::vector<std::string> position_names = {
      "WORK", "WORK_PLANT_0", "WORK_PLANT_1", "WORK_PLANT_2",
      "WORK_PLANT_3", "GROW", "INSPECT"
    };
    for (const auto & name : position_names) {
      double mm = this->get_parameter("positions." + name).as_double();
      named_positions_[name] = mm;
      RCLCPP_DEBUG(this->get_logger(), "Position '%s' = %.1f mm", name.c_str(), mm);
    }
  }

  // -----------------------------------------------------------------------
  //  Subscriber callbacks
  // -----------------------------------------------------------------------

  void rail_position_callback(const std_msgs::msg::Int32::SharedPtr msg)
  {
    std::lock_guard<std::mutex> lock(state_mutex_);
    current_step_count_ = msg->data;
    last_position_update_ = this->now();
    position_known_ = true;

    RCLCPP_DEBUG(this->get_logger(), "Rail position update: %d steps (%.2f mm)",
      current_step_count_, steps_to_mm(current_step_count_));
  }

  void limit_switch_callback(const std_msgs::msg::Int32::SharedPtr msg)
  {
    std::lock_guard<std::mutex> lock(state_mutex_);
    bool home_pressed = (msg->data & 0x01) != 0;

    if (home_pressed && !home_limit_active_) {
      RCLCPP_INFO(this->get_logger(), "Home limit switch ACTIVATED");
    } else if (!home_pressed && home_limit_active_) {
      RCLCPP_INFO(this->get_logger(), "Home limit switch released");
    }
    home_limit_active_ = home_pressed;
  }

  // -----------------------------------------------------------------------
  //  Action server callbacks
  // -----------------------------------------------------------------------

  rclcpp_action::GoalResponse handle_goal(
    const rclcpp_action::GoalUUID & /*uuid*/,
    std::shared_ptr<const TransportTo::Goal> goal)
  {
    const std::string & target = goal->target_position;
    RCLCPP_INFO(this->get_logger(), "TransportTo goal received: '%s'", target.c_str());

    // Special case: HOME is always accepted (triggers homing sequence)
    if (target == "HOME") {
      if (is_moving_) {
        RCLCPP_WARN(this->get_logger(),
          "Rejecting HOME goal -- transport is already moving");
        return rclcpp_action::GoalResponse::REJECT;
      }
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    }

    // Validate named position
    if (named_positions_.find(target) == named_positions_.end()) {
      RCLCPP_ERROR(this->get_logger(),
        "Rejecting goal: unknown position '%s'", target.c_str());
      return rclcpp_action::GoalResponse::REJECT;
    }

    if (!is_homed_) {
      RCLCPP_ERROR(this->get_logger(),
        "Rejecting goal: rail is not homed -- send HOME first");
      return rclcpp_action::GoalResponse::REJECT;
    }

    if (is_moving_) {
      RCLCPP_WARN(this->get_logger(),
        "Rejecting goal: transport is already executing a move");
      return rclcpp_action::GoalResponse::REJECT;
    }

    double target_mm = named_positions_.at(target);
    if (target_mm < min_position_mm_ || target_mm > max_position_mm_) {
      RCLCPP_ERROR(this->get_logger(),
        "Rejecting goal: position %.1f mm is outside travel limits [%.1f, %.1f]",
        target_mm, min_position_mm_, max_position_mm_);
      return rclcpp_action::GoalResponse::REJECT;
    }

    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handle_cancel(
    const std::shared_ptr<TransportToGoalHandle> /*goal_handle*/)
  {
    RCLCPP_WARN(this->get_logger(), "TransportTo cancel requested");
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handle_accepted(const std::shared_ptr<TransportToGoalHandle> goal_handle)
  {
    // Execute in a detached thread so the action server stays responsive.
    std::thread{std::bind(&TransportController::execute_goal, this, _1),
                goal_handle}.detach();
  }

  // -----------------------------------------------------------------------
  //  Goal execution (runs in its own thread)
  // -----------------------------------------------------------------------

  void execute_goal(const std::shared_ptr<TransportToGoalHandle> goal_handle)
  {
    const std::string & target_name = goal_handle->get_goal()->target_position;
    RCLCPP_INFO(this->get_logger(), "Executing transport to '%s'", target_name.c_str());

    auto result = std::make_shared<TransportTo::Result>();

    // ----- HOME sequence ---------------------------------------------------
    if (target_name == "HOME") {
      execute_homing(goal_handle, result);
      return;
    }

    // ----- Normal move -----------------------------------------------------
    double target_mm = named_positions_.at(target_name);
    int32_t target_steps = mm_to_steps(target_mm);

    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      target_position_name_ = target_name;
      target_step_count_ = target_steps;
      is_moving_ = true;
    }

    // Publish the target to the ESP32
    publish_stepper_cmd(target_steps);

    // Build the trapezoidal profile to estimate progress
    double start_mm, total_distance_mm;
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      start_mm = steps_to_mm(current_step_count_);
      total_distance_mm = std::abs(target_mm - start_mm);
    }

    if (total_distance_mm < 0.1) {
      // Already at target
      RCLCPP_INFO(this->get_logger(), "Already at '%s'", target_name.c_str());
      std::lock_guard<std::mutex> lock(state_mutex_);
      is_moving_ = false;
      current_position_name_ = target_name;
      result->success = true;
      result->final_position = target_name;
      result->message = "Already at target position";
      goal_handle->succeed(result);
      return;
    }

    RCLCPP_INFO(this->get_logger(),
      "Moving %.1f mm -> %.1f mm (delta %.1f mm, %d steps)",
      start_mm, target_mm, total_distance_mm, target_steps);

    // Poll until arrival or cancellation
    rclcpp::Rate rate(20);  // 20 Hz polling
    const double arrival_tolerance_mm = 0.5;
    const auto move_timeout = 60s;
    const auto move_start = this->now();

    while (rclcpp::ok()) {
      // Check for cancellation
      if (goal_handle->is_canceling()) {
        RCLCPP_WARN(this->get_logger(), "TransportTo cancelled during move");
        // Command stop at current position
        int32_t stop_step;
        {
          std::lock_guard<std::mutex> lock(state_mutex_);
          stop_step = current_step_count_;
          is_moving_ = false;
          current_position_name_ = "TRANSIT";
          target_position_name_ = "";
        }
        publish_stepper_cmd(stop_step);
        result->success = false;
        result->final_position = "TRANSIT";
        result->message = "Move cancelled by client";
        goal_handle->canceled(result);
        return;
      }

      // Check timeout
      if ((this->now() - move_start) > move_timeout) {
        RCLCPP_ERROR(this->get_logger(),
          "Move to '%s' timed out after 60 s", target_name.c_str());
        int32_t stop_step;
        {
          std::lock_guard<std::mutex> lock(state_mutex_);
          stop_step = current_step_count_;
          is_moving_ = false;
          current_position_name_ = "TRANSIT";
          target_position_name_ = "";
        }
        publish_stepper_cmd(stop_step);
        result->success = false;
        result->final_position = "TRANSIT";
        result->message = "Move timed out";
        goal_handle->abort(result);
        return;
      }

      // Compute and publish feedback
      double current_mm;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        current_mm = steps_to_mm(current_step_count_);
      }
      double remaining = std::abs(target_mm - current_mm);
      double progress = (total_distance_mm > 0.0)
        ? std::clamp((1.0 - remaining / total_distance_mm) * 100.0, 0.0, 100.0)
        : 100.0;

      auto feedback = std::make_shared<TransportTo::Feedback>();
      feedback->progress_percent = progress;
      feedback->current_position_mm = current_mm;
      goal_handle->publish_feedback(feedback);

      // Check arrival
      if (remaining <= arrival_tolerance_mm) {
        RCLCPP_INFO(this->get_logger(),
          "Arrived at '%s' (%.2f mm, error %.2f mm)",
          target_name.c_str(), current_mm, remaining);
        break;
      }

      rate.sleep();
    }

    // Finalise
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      is_moving_ = false;
      current_position_name_ = target_name;
      target_position_name_ = "";
    }

    result->success = true;
    result->final_position = target_name;
    result->message = "Transport complete";
    goal_handle->succeed(result);
  }

  // -----------------------------------------------------------------------
  //  Homing sequence
  // -----------------------------------------------------------------------

  void execute_homing(
    const std::shared_ptr<TransportToGoalHandle> goal_handle,
    std::shared_ptr<TransportTo::Result> result)
  {
    RCLCPP_INFO(this->get_logger(), "Beginning homing sequence");

    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      is_moving_ = true;
      is_homed_ = false;
      target_position_name_ = "HOME";
      current_position_name_ = "TRANSIT";
    }

    // Phase 1: Drive toward home limit switch at homing speed.
    //
    // We command a large negative step target so the ESP32 drives continuously
    // in the home direction.  The limit-switch interrupt on the ESP32 will
    // stop the motor, but we also monitor the switch state here.
    const int32_t homing_step_target =
      static_cast<int32_t>(home_direction_ * max_position_mm_ * steps_per_mm_ * 1.5);
    publish_stepper_cmd(homing_step_target);

    RCLCPP_INFO(this->get_logger(),
      "Homing phase 1: driving toward limit switch (target %d steps)",
      homing_step_target);

    rclcpp::Rate rate(20);
    const auto homing_timeout = 45s;
    const auto phase_start = this->now();

    while (rclcpp::ok()) {
      if (goal_handle->is_canceling()) {
        abort_homing(goal_handle, result, "Homing cancelled by client");
        return;
      }
      if ((this->now() - phase_start) > homing_timeout) {
        abort_homing(goal_handle, result,
          "Homing timed out waiting for limit switch");
        return;
      }

      bool switch_hit;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        switch_hit = home_limit_active_;
      }

      // Publish feedback
      auto feedback = std::make_shared<TransportTo::Feedback>();
      feedback->progress_percent = switch_hit ? 50.0 : 25.0;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        feedback->current_position_mm = steps_to_mm(current_step_count_);
      }
      goal_handle->publish_feedback(feedback);

      if (switch_hit) {
        RCLCPP_INFO(this->get_logger(), "Homing phase 1 complete: limit switch hit");
        break;
      }
      rate.sleep();
    }

    // Phase 2: Back off the switch by homing_backoff_mm.
    int32_t backoff_steps =
      static_cast<int32_t>(homing_backoff_mm_ * steps_per_mm_);
    int32_t backoff_target = -home_direction_ * backoff_steps;  // opposite direction
    publish_stepper_cmd(backoff_target);

    RCLCPP_INFO(this->get_logger(),
      "Homing phase 2: backing off %d steps", backoff_steps);

    // Wait for the switch to release
    const auto backoff_start = this->now();
    while (rclcpp::ok()) {
      if (goal_handle->is_canceling()) {
        abort_homing(goal_handle, result, "Homing cancelled during backoff");
        return;
      }
      if ((this->now() - backoff_start) > 10s) {
        abort_homing(goal_handle, result,
          "Homing backoff timed out -- limit switch stuck?");
        return;
      }

      bool switch_active;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        switch_active = home_limit_active_;
      }

      auto feedback = std::make_shared<TransportTo::Feedback>();
      feedback->progress_percent = 75.0;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        feedback->current_position_mm = steps_to_mm(current_step_count_);
      }
      goal_handle->publish_feedback(feedback);

      if (!switch_active) {
        RCLCPP_INFO(this->get_logger(),
          "Homing phase 2 complete: switch released after backoff");
        break;
      }
      rate.sleep();
    }

    // Phase 3: Slowly re-approach the switch for a precise zero reference.
    int32_t slow_approach_target =
      static_cast<int32_t>(home_direction_ * homing_backoff_mm_ * steps_per_mm_ * 2.0);
    publish_stepper_cmd(slow_approach_target);

    RCLCPP_INFO(this->get_logger(), "Homing phase 3: slow re-approach");

    const auto approach_start = this->now();
    while (rclcpp::ok()) {
      if (goal_handle->is_canceling()) {
        abort_homing(goal_handle, result, "Homing cancelled during re-approach");
        return;
      }
      if ((this->now() - approach_start) > 10s) {
        abort_homing(goal_handle, result,
          "Homing re-approach timed out -- mechanical issue?");
        return;
      }

      bool switch_hit;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        switch_hit = home_limit_active_;
      }

      auto feedback = std::make_shared<TransportTo::Feedback>();
      feedback->progress_percent = 90.0;
      {
        std::lock_guard<std::mutex> lock(state_mutex_);
        feedback->current_position_mm = steps_to_mm(current_step_count_);
      }
      goal_handle->publish_feedback(feedback);

      if (switch_hit) {
        break;
      }
      rate.sleep();
    }

    // Phase 4: Zero the step counter and mark homed.
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      current_step_count_ = 0;
      target_step_count_ = 0;
      is_homed_ = true;
      is_moving_ = false;
      position_known_ = true;
      current_position_name_ = "HOME";
      target_position_name_ = "";
    }

    // Command zero position so ESP32 resets its counter
    publish_stepper_cmd(0);

    RCLCPP_INFO(this->get_logger(),
      "Homing complete -- step counter zeroed, position origin set");

    auto feedback = std::make_shared<TransportTo::Feedback>();
    feedback->progress_percent = 100.0;
    feedback->current_position_mm = 0.0;
    goal_handle->publish_feedback(feedback);

    result->success = true;
    result->final_position = "HOME";
    result->message = "Homing complete";
    goal_handle->succeed(result);
  }

  void abort_homing(
    const std::shared_ptr<TransportToGoalHandle> goal_handle,
    std::shared_ptr<TransportTo::Result> result,
    const std::string & reason)
  {
    RCLCPP_ERROR(this->get_logger(), "Homing aborted: %s", reason.c_str());

    // Stop the motor at whatever position it is in now
    int32_t stop_step;
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      stop_step = current_step_count_;
      is_moving_ = false;
      target_position_name_ = "";
    }
    publish_stepper_cmd(stop_step);

    result->success = false;
    result->final_position = "UNKNOWN";
    result->message = reason;

    if (goal_handle->is_canceling()) {
      goal_handle->canceled(result);
    } else {
      goal_handle->abort(result);
    }
  }

  // -----------------------------------------------------------------------
  //  Timer callback: publish status and enforce software limits
  // -----------------------------------------------------------------------

  void timer_callback()
  {
    std::lock_guard<std::mutex> lock(state_mutex_);

    // Compute instantaneous velocity from position deltas
    double current_mm = steps_to_mm(current_step_count_);
    auto now = this->now();
    double velocity_mm_s = 0.0;

    if (prev_timer_stamp_.nanoseconds() > 0) {
      double dt = (now - prev_timer_stamp_).seconds();
      if (dt > 0.0) {
        velocity_mm_s = (current_mm - prev_position_mm_) / dt;
      }
    }
    prev_timer_stamp_ = now;
    prev_position_mm_ = current_mm;

    // Software travel-limit enforcement
    if (is_homed_ && position_known_) {
      if (current_mm < min_position_mm_ - 1.0) {
        RCLCPP_ERROR(this->get_logger(),
          "SOFTWARE LIMIT: position %.1f mm < min %.1f mm -- commanding stop",
          current_mm, min_position_mm_);
        publish_stepper_cmd_unlocked(current_step_count_);
        is_moving_ = false;
      }
      if (current_mm > max_position_mm_ + 1.0) {
        RCLCPP_ERROR(this->get_logger(),
          "SOFTWARE LIMIT: position %.1f mm > max %.1f mm -- commanding stop",
          current_mm, max_position_mm_);
        publish_stepper_cmd_unlocked(current_step_count_);
        is_moving_ = false;
      }
    }

    // Resolve current position name from mm
    if (!is_moving_ && is_homed_) {
      current_position_name_ = resolve_position_name(current_mm);
    }

    // Build and publish status message
    TransportStatus status;
    status.header.stamp = now;
    status.header.frame_id = "transport_rail";
    status.current_position = current_position_name_;
    status.target_position = target_position_name_;
    status.is_moving = is_moving_;
    status.position_mm = current_mm;
    status.velocity_mm_s = velocity_mm_s;

    status_pub_->publish(status);
  }

  // -----------------------------------------------------------------------
  //  Helpers
  // -----------------------------------------------------------------------

  double steps_to_mm(int32_t steps) const
  {
    return static_cast<double>(steps) / steps_per_mm_;
  }

  int32_t mm_to_steps(double mm) const
  {
    return static_cast<int32_t>(std::round(mm * steps_per_mm_));
  }

  /// Publish a target step command to the ESP32.  Thread-safe (acquires no
  /// additional locks -- call from code that does NOT hold state_mutex_).
  void publish_stepper_cmd(int32_t target_steps)
  {
    auto msg = std_msgs::msg::Int32();
    msg.data = target_steps;
    stepper_cmd_pub_->publish(msg);
    RCLCPP_DEBUG(this->get_logger(), "Stepper cmd -> %d steps", target_steps);
  }

  /// Variant for use inside code that already holds state_mutex_.
  void publish_stepper_cmd_unlocked(int32_t target_steps)
  {
    auto msg = std_msgs::msg::Int32();
    msg.data = target_steps;
    stepper_cmd_pub_->publish(msg);
  }

  /// Find the named position closest to the given mm value (within 2 mm).
  /// Returns "TRANSIT" if no named position is close enough.
  std::string resolve_position_name(double mm) const
  {
    constexpr double snap_tolerance_mm = 2.0;
    std::string best_name = "TRANSIT";
    double best_dist = snap_tolerance_mm;

    for (const auto & [name, pos_mm] : named_positions_) {
      double d = std::abs(mm - pos_mm);
      if (d < best_dist) {
        best_dist = d;
        best_name = name;
      }
    }
    return best_name;
  }

  // -----------------------------------------------------------------------
  //  Member data
  // -----------------------------------------------------------------------

  // ROS interfaces
  rclcpp::Publisher<TransportStatus>::SharedPtr status_pub_;
  rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr stepper_cmd_pub_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr rail_position_sub_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr limit_switch_sub_;
  rclcpp_action::Server<TransportTo>::SharedPtr action_server_;
  rclcpp::TimerBase::SharedPtr timer_;

  // Configuration
  double steps_per_mm_{80.0};
  double max_speed_mm_s_{50.0};
  double acceleration_mm_s2_{100.0};
  double deceleration_mm_s2_{100.0};
  double min_position_mm_{0.0};
  double max_position_mm_{1100.0};
  double homing_speed_mm_s_{20.0};
  double homing_backoff_mm_{5.0};
  int64_t home_direction_{-1};
  std::unordered_map<std::string, double> named_positions_;

  // State -- guarded by state_mutex_
  std::mutex state_mutex_;
  int32_t current_step_count_{0};
  int32_t target_step_count_{0};
  bool position_known_{false};
  bool is_homed_{false};
  bool is_moving_{false};
  bool home_limit_active_{false};
  std::string current_position_name_{"UNKNOWN"};
  std::string target_position_name_;
  rclcpp::Time last_position_update_{0, 0, RCL_ROS_TIME};

  // For velocity estimation
  rclcpp::Time prev_timer_stamp_{0, 0, RCL_ROS_TIME};
  double prev_position_mm_{0.0};
};

// ===========================================================================
//  main
// ===========================================================================

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<TransportController>();
  RCLCPP_INFO(node->get_logger(), "Transport controller node starting");

  rclcpp::spin(node);

  RCLCPP_INFO(node->get_logger(), "Transport controller shutting down");
  rclcpp::shutdown();
  return 0;
}
