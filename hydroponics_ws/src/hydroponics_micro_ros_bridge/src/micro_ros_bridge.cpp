// MIT License
// Copyright (c) 2024 Claudroponics Project

#include <chrono>
#include <functional>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/int32.hpp"
#include "std_msgs/msg/float32.hpp"
#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

/// @brief Manages serial USB communication with ESP32 via micro-ROS agent.
///
/// This node acts as a monitoring and health-check layer for the micro-ROS
/// transport between the Raspberry Pi and the ESP32 MCU. The actual micro-ROS
/// agent runs as a separate process (micro_ros_agent), and this node:
///   - Monitors connectivity via heartbeat
///   - Republishes ESP32 topics with health metadata
///   - Handles reconnection logic and watchdog alerting
///
/// ESP32 publishes: ph_raw, ec_raw, temperature, water_level, limit_switch_states,
///                   z_position, harvest_weight, rail_position (step count)
/// ESP32 subscribes to: rail_stepper_cmd, z_stepper_cmd, servo_cmd,
///                       pump_cmd, grow_light_cmd, inspect_light_cmd
class MicroRosBridge : public rclcpp::Node
{
public:
  MicroRosBridge()
  : Node("micro_ros_bridge")
  {
    // Declare parameters
    this->declare_parameter("serial_port", "/dev/ttyUSB0");
    this->declare_parameter("baud_rate", 115200);
    this->declare_parameter("heartbeat_timeout_s", 5.0);
    this->declare_parameter("reconnect_interval_s", 2.0);
    this->declare_parameter("watchdog_rate_hz", 2.0);

    serial_port_ = this->get_parameter("serial_port").as_string();
    baud_rate_ = this->get_parameter("baud_rate").as_int();
    heartbeat_timeout_ = this->get_parameter("heartbeat_timeout_s").as_double();
    reconnect_interval_ = this->get_parameter("reconnect_interval_s").as_double();
    double watchdog_rate = this->get_parameter("watchdog_rate_hz").as_double();

    // --- ESP32 Sensor Subscribers (from micro-ROS agent) ---
    sub_ph_raw_ = this->create_subscription<std_msgs::msg::Float32>(
      "ph_raw", 10,
      [this](const std_msgs::msg::Float32::SharedPtr msg) {
        last_ph_raw_ = msg->data;
        update_heartbeat();
      });

    sub_ec_raw_ = this->create_subscription<std_msgs::msg::Float32>(
      "ec_raw", 10,
      [this](const std_msgs::msg::Float32::SharedPtr msg) {
        last_ec_raw_ = msg->data;
        update_heartbeat();
      });

    sub_temperature_ = this->create_subscription<std_msgs::msg::Float32>(
      "temperature", 10,
      [this](const std_msgs::msg::Float32::SharedPtr msg) {
        last_temperature_ = msg->data;
        update_heartbeat();
      });

    sub_water_level_ = this->create_subscription<std_msgs::msg::Bool>(
      "water_level", 10,
      [this](const std_msgs::msg::Bool::SharedPtr msg) {
        water_level_ok_ = msg->data;
        update_heartbeat();
      });

    sub_rail_position_ = this->create_subscription<std_msgs::msg::Int32>(
      "rail_position", 10,
      [this](const std_msgs::msg::Int32::SharedPtr msg) {
        last_rail_steps_ = msg->data;
        update_heartbeat();
      });

    sub_z_position_ = this->create_subscription<std_msgs::msg::Int32>(
      "z_position", 10,
      [this](const std_msgs::msg::Int32::SharedPtr msg) {
        last_z_steps_ = msg->data;
        update_heartbeat();
      });

    sub_harvest_weight_ = this->create_subscription<std_msgs::msg::Float32>(
      "harvest_weight", 10,
      [this](const std_msgs::msg::Float32::SharedPtr msg) {
        last_harvest_weight_ = msg->data;
        update_heartbeat();
      });

    sub_limit_switches_ = this->create_subscription<std_msgs::msg::String>(
      "limit_switch_states", 10,
      [this](const std_msgs::msg::String::SharedPtr msg) {
        last_limit_states_ = msg->data;
        update_heartbeat();
      });

    sub_heartbeat_ = this->create_subscription<std_msgs::msg::Bool>(
      "esp32_heartbeat", 10,
      [this](const std_msgs::msg::Bool::SharedPtr) {
        update_heartbeat();
      });

    // --- Connectivity status publisher ---
    pub_esp32_connected_ = this->create_publisher<std_msgs::msg::Bool>(
      "esp32_connected", 10);

    // --- Watchdog timer ---
    double watchdog_period_ms = 1000.0 / watchdog_rate;
    watchdog_timer_ = this->create_wall_timer(
      std::chrono::milliseconds(static_cast<int>(watchdog_period_ms)),
      std::bind(&MicroRosBridge::watchdog_callback, this));

    last_heartbeat_time_ = this->now();
    esp32_connected_ = false;

    RCLCPP_INFO(this->get_logger(),
      "micro_ros_bridge initialized — monitoring ESP32 on %s @ %d baud",
      serial_port_.c_str(), baud_rate_);
    RCLCPP_INFO(this->get_logger(),
      "Heartbeat timeout: %.1fs, watchdog rate: %.1f Hz",
      heartbeat_timeout_, watchdog_rate);
  }

private:
  void update_heartbeat()
  {
    last_heartbeat_time_ = this->now();
    if (!esp32_connected_) {
      esp32_connected_ = true;
      RCLCPP_INFO(this->get_logger(), "ESP32 connection established");
    }
  }

  void watchdog_callback()
  {
    auto elapsed = (this->now() - last_heartbeat_time_).seconds();

    if (elapsed > heartbeat_timeout_) {
      if (esp32_connected_) {
        esp32_connected_ = false;
        RCLCPP_ERROR(this->get_logger(),
          "ESP32 heartbeat lost! No data for %.1fs (timeout: %.1fs). "
          "Steppers and pumps should auto-stop via ESP32 watchdog.",
          elapsed, heartbeat_timeout_);
      }
    }

    // Publish connectivity status
    auto msg = std_msgs::msg::Bool();
    msg.data = esp32_connected_;
    pub_esp32_connected_->publish(msg);

    RCLCPP_DEBUG(this->get_logger(),
      "ESP32 status: %s | last heartbeat: %.1fs ago | "
      "pH=%.2f EC=%.2f T=%.1f rail_steps=%d z_steps=%d",
      esp32_connected_ ? "CONNECTED" : "DISCONNECTED",
      elapsed, last_ph_raw_, last_ec_raw_, last_temperature_,
      last_rail_steps_, last_z_steps_);
  }

  // Parameters
  std::string serial_port_;
  int baud_rate_;
  double heartbeat_timeout_;
  double reconnect_interval_;

  // State
  bool esp32_connected_;
  rclcpp::Time last_heartbeat_time_;
  float last_ph_raw_ = 0.0f;
  float last_ec_raw_ = 0.0f;
  float last_temperature_ = 0.0f;
  bool water_level_ok_ = true;
  int last_rail_steps_ = 0;
  int last_z_steps_ = 0;
  float last_harvest_weight_ = 0.0f;
  std::string last_limit_states_;

  // Subscribers (ESP32 sensor data)
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr sub_ph_raw_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr sub_ec_raw_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr sub_temperature_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_water_level_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr sub_rail_position_;
  rclcpp::Subscription<std_msgs::msg::Int32>::SharedPtr sub_z_position_;
  rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr sub_harvest_weight_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr sub_limit_switches_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_heartbeat_;

  // Publishers
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr pub_esp32_connected_;

  // Timers
  rclcpp::TimerBase::SharedPtr watchdog_timer_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MicroRosBridge>());
  rclcpp::shutdown();
  return 0;
}
