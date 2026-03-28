/*
 * micro_ros_app.cpp  –  micro-ROS application layer implementation
 *
 * MIT License — Copyright (c) 2026 Claudroponics
 *
 * Requires: micro_ros_arduino library (ESP32 target)
 * Agent command on Raspberry Pi:
 *   ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200
 */

#include "micro_ros_app.h"
#include "pumps.h"
#include "sensors.h"
#include "lighting.h"
#include "stepper.h"

#include <Arduino.h>
#include <micro_ros_arduino.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <std_msgs/msg/string.h>

// ---------------------------------------------------------------------------
// External objects (defined in main.cpp)
// ---------------------------------------------------------------------------
extern Pumps    g_pumps;
extern Sensors  g_sensors;
extern Lighting g_lighting;

// ---------------------------------------------------------------------------
// micro-ROS handles
// ---------------------------------------------------------------------------
static rcl_node_t       g_node;
static rcl_publisher_t  g_sensor_pub;
static rcl_subscription_t g_pump_sub;
static rcl_subscription_t g_light_sub;
static rcl_subscription_t g_stepper_sub;
static rclc_executor_t  g_executor;
static rclc_support_t   g_support;
static rcl_allocator_t  g_allocator;
static rcl_timer_t      g_sensor_timer;

static std_msgs__msg__String g_sensor_msg;
static std_msgs__msg__String g_pump_msg;
static std_msgs__msg__String g_light_msg;
static std_msgs__msg__String g_stepper_msg;

static char g_sensor_buf[256];
static char g_pump_buf[128];
static char g_light_buf[128];
static char g_stepper_buf[128];

static bool g_connected = false;

// ---------------------------------------------------------------------------
// Minimal JSON parser helpers (no heap allocation)
// ---------------------------------------------------------------------------

// Extract int value from JSON string. Returns default_val if key not found.
static int json_get_int(const char* json, const char* key, int default_val)
{
    const char* p = strstr(json, key);
    if (!p) return default_val;
    p = strchr(p, ':');
    if (!p) return default_val;
    ++p;
    while (*p == ' ' || *p == '"') ++p;
    return (int)strtol(p, nullptr, 10);
}

static float json_get_float(const char* json, const char* key, float default_val)
{
    const char* p = strstr(json, key);
    if (!p) return default_val;
    p = strchr(p, ':');
    if (!p) return default_val;
    ++p;
    while (*p == ' ') ++p;
    return strtof(p, nullptr);
}

static bool json_get_bool(const char* json, const char* key, bool default_val)
{
    const char* p = strstr(json, key);
    if (!p) return default_val;
    p = strchr(p, ':');
    if (!p) return default_val;
    ++p;
    while (*p == ' ') ++p;
    if (strncmp(p, "true", 4) == 0)  return true;
    if (strncmp(p, "false", 5) == 0) return false;
    return default_val;
}

// ---------------------------------------------------------------------------
// Subscription callbacks
// ---------------------------------------------------------------------------

static void pump_cmd_callback(const void* msg_in)
{
    const std_msgs__msg__String* msg =
        (const std_msgs__msg__String*)msg_in;
    if (!msg->data.data) return;

    int pump_id    = json_get_int(msg->data.data, "pump_id",    -1);
    int duration   = json_get_int(msg->data.data, "duration_ms", 0);
    float amount   = json_get_float(msg->data.data, "amount_ml", -1.0f);

    if (pump_id < 0 || pump_id >= NUM_PUMPS) return;

    if (amount > 0.0f) {
        g_pumps.doseML(pump_id, amount);
    } else if (duration > 0) {
        g_pumps.dose(pump_id, (uint32_t)duration);
    }
}

static void light_cmd_callback(const void* msg_in)
{
    const std_msgs__msg__String* msg =
        (const std_msgs__msg__String*)msg_in;
    if (!msg->data.data) return;

    const char* json = msg->data.data;

    // Check for grow intensity command
    if (strstr(json, "grow_intensity")) {
        int intensity = json_get_int(json, "grow_intensity", -1);
        if (intensity >= 0 && intensity <= 100) {
            g_lighting.setGrowIntensity((uint8_t)intensity);
        }
    }
    // Check for inspection light command
    if (strstr(json, "inspection_on")) {
        bool on = json_get_bool(json, "inspection_on", false);
        g_lighting.setInspectionLight(on);
    }
}

static void stepper_cmd_callback(const void* msg_in)
{
    const std_msgs__msg__String* msg =
        (const std_msgs__msg__String*)msg_in;
    if (!msg->data.data) return;

    // {"axis": "rail", "target_mm": 500.0}
    float target_mm = json_get_float(msg->data.data, "target_mm", -1.0f);
    if (target_mm < 0.0f) return;

    if (strstr(msg->data.data, "\"rail\"")) {
        int32_t steps = (int32_t)(target_mm * STEPPER_DEFAULT_STEPS_PER_MM);
        stepper_move_to(&g_rail_axis, steps);
    } else if (strstr(msg->data.data, "\"z\"")) {
        int32_t steps = (int32_t)(target_mm * STEPPER_DEFAULT_STEPS_PER_MM);
        stepper_move_to(&g_z_axis, steps);
    }
}

// ---------------------------------------------------------------------------
// Sensor publish timer callback (1 Hz)
// ---------------------------------------------------------------------------
static void sensor_timer_callback(rcl_timer_t* timer, int64_t /*last_call_time*/)
{
    if (!timer) return;

    // Build JSON sensor telemetry
    float ph       = g_sensors.getPH();
    float ec       = g_sensors.getEC();
    float temp     = g_sensors.getTemperatureC();
    bool  water_ok = g_sensors.isWaterLevelOk();
    bool  rail_mov = stepper_is_moving(&g_rail_axis);
    bool  z_mov    = stepper_is_moving(&g_z_axis);
    float rail_pos = (float)g_rail_axis.current_pos / STEPPER_DEFAULT_STEPS_PER_MM;
    float z_pos    = (float)g_z_axis.current_pos    / STEPPER_DEFAULT_STEPS_PER_MM;
    uint8_t grow   = g_lighting.getGrowIntensity();
    bool  insp     = g_lighting.isInspectionOn();

    snprintf(g_sensor_buf, sizeof(g_sensor_buf),
        "{"
        "\"ph\":%.3f,"
        "\"ec\":%.3f,"
        "\"temp_c\":%.2f,"
        "\"water_level_ok\":%s,"
        "\"rail_pos_mm\":%.1f,"
        "\"z_pos_mm\":%.1f,"
        "\"rail_moving\":%s,"
        "\"z_moving\":%s,"
        "\"grow_intensity\":%u,"
        "\"inspection_on\":%s,"
        "\"pump_active\":[%s,%s,%s,%s]"
        "}",
        ph, ec, temp,
        water_ok   ? "true" : "false",
        rail_pos, z_pos,
        rail_mov   ? "true" : "false",
        z_mov      ? "true" : "false",
        grow,
        insp       ? "true" : "false",
        g_pumps.isRunning(0) ? "true" : "false",
        g_pumps.isRunning(1) ? "true" : "false",
        g_pumps.isRunning(2) ? "true" : "false",
        g_pumps.isRunning(3) ? "true" : "false"
    );

    g_sensor_msg.data.data = g_sensor_buf;
    g_sensor_msg.data.size = strlen(g_sensor_buf);
    g_sensor_msg.data.capacity = sizeof(g_sensor_buf);

    rcl_publish(&g_sensor_pub, &g_sensor_msg, nullptr);
}

// ---------------------------------------------------------------------------
// Setup / loop
// ---------------------------------------------------------------------------

static bool try_init_micro_ros()
{
    set_microros_serial_transports(Serial);
    delay(2000);  // Wait for agent

    g_allocator = rcl_get_default_allocator();
    rclc_support_t sup;
    if (rclc_support_init(&sup, 0, nullptr, &g_allocator) != RCL_RET_OK) {
        return false;
    }
    g_support = sup;

    if (rclc_node_init_default(&g_node, "esp32_hydroponics", "", &g_support) != RCL_RET_OK) {
        return false;
    }

    // Publisher: sensor data
    g_sensor_msg.data.data     = g_sensor_buf;
    g_sensor_msg.data.size     = 0;
    g_sensor_msg.data.capacity = sizeof(g_sensor_buf);
    if (rclc_publisher_init_default(
            &g_sensor_pub, &g_node,
            ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
            TOPIC_SENSOR_DATA) != RCL_RET_OK)
    {
        return false;
    }

    // Subscriptions
    g_pump_msg.data.data     = g_pump_buf;
    g_pump_msg.data.size     = 0;
    g_pump_msg.data.capacity = sizeof(g_pump_buf);
    rclc_subscription_init_default(&g_pump_sub, &g_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String), TOPIC_PUMP_CMD);

    g_light_msg.data.data     = g_light_buf;
    g_light_msg.data.size     = 0;
    g_light_msg.data.capacity = sizeof(g_light_buf);
    rclc_subscription_init_default(&g_light_sub, &g_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String), TOPIC_LIGHT_CMD);

    g_stepper_msg.data.data     = g_stepper_buf;
    g_stepper_msg.data.size     = 0;
    g_stepper_msg.data.capacity = sizeof(g_stepper_buf);
    rclc_subscription_init_default(&g_stepper_sub, &g_node,
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String), TOPIC_STEPPER_CMD);

    // 1 Hz sensor publish timer
    rclc_timer_init_default(&g_sensor_timer, &g_support,
        RCL_MS_TO_NS(1000), sensor_timer_callback);

    // Executor: 3 subscriptions + 1 timer = 4 handles
    rclc_executor_init(&g_executor, &g_support.context, 4, &g_allocator);
    rclc_executor_add_timer(&g_executor, &g_sensor_timer);
    rclc_executor_add_subscription(&g_executor, &g_pump_sub,
        &g_pump_msg, pump_cmd_callback, ON_NEW_DATA);
    rclc_executor_add_subscription(&g_executor, &g_light_sub,
        &g_light_msg, light_cmd_callback, ON_NEW_DATA);
    rclc_executor_add_subscription(&g_executor, &g_stepper_sub,
        &g_stepper_msg, stepper_cmd_callback, ON_NEW_DATA);

    g_connected = true;
    return true;
}

void microRosSetup()
{
    Serial.println("[uROS] Connecting to micro-ROS agent…");
    while (!try_init_micro_ros()) {
        Serial.println("[uROS] Agent not found, retrying in 2s…");
        delay(2000);
    }
    Serial.println("[uROS] Connected.");
}

void microRosLoop()
{
    if (!g_connected) {
        // Attempt reconnect
        g_connected = try_init_micro_ros();
        return;
    }

    rcl_ret_t ret = rclc_executor_spin_some(&g_executor, RCL_MS_TO_NS(10));
    if (ret != RCL_RET_OK && ret != RCL_RET_TIMEOUT) {
        // Agent disconnected
        Serial.println("[uROS] Agent disconnected, reconnecting…");
        g_connected = false;
        rcl_publisher_fini(&g_sensor_pub, &g_node);
        rcl_subscription_fini(&g_pump_sub, &g_node);
        rcl_subscription_fini(&g_light_sub, &g_node);
        rcl_subscription_fini(&g_stepper_sub, &g_node);
        rcl_timer_fini(&g_sensor_timer);
        rclc_executor_fini(&g_executor);
        rcl_node_fini(&g_node);
        rclc_support_fini(&g_support);
    }
}

bool microRosConnected()
{
    return g_connected;
}
