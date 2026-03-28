#pragma once
/*
 * micro_ros_app.h  –  micro-ROS application layer declarations
 *
 * Manages the micro-ROS node lifecycle, executor, publishers,
 * and subscriptions that bridge the ESP32 hardware to ROS2.
 *
 * Topic map:
 *   PUBLISH:
 *     /hydroponics/esp32/sensors  (std_msgs/String — JSON sensor telemetry @ 1 Hz)
 *
 *   SUBSCRIBE:
 *     /hydroponics/esp32/pump_cmd    (std_msgs/String — JSON: {pump_id, duration_ms})
 *     /hydroponics/esp32/light_cmd   (std_msgs/String — JSON: {grow_intensity|inspection_on})
 *     /hydroponics/esp32/stepper_cmd (std_msgs/String — JSON: {axis, target_mm})
 *
 * Usage:
 *   microRosSetup();          // call once in setup()
 *   microRosLoop();           // call every iteration in loop()
 *   microRosConnected();      // query connection state
 */

#ifndef MICRO_ROS_APP_H
#define MICRO_ROS_APP_H

#include <stdbool.h>

// Topic name constants
#define TOPIC_SENSOR_DATA  "/hydroponics/esp32/sensors"
#define TOPIC_PUMP_CMD     "/hydroponics/esp32/pump_cmd"
#define TOPIC_LIGHT_CMD    "/hydroponics/esp32/light_cmd"
#define TOPIC_STEPPER_CMD  "/hydroponics/esp32/stepper_cmd"

/**
 * Initialise micro-ROS transport (USB serial at 115200 baud),
 * create the ROS2 node, publishers, subscriptions, and executor.
 * Blocks until the micro-ROS agent connects (typically < 5 s when
 * the agent is running on the Raspberry Pi).
 */
void microRosSetup();

/**
 * Run one executor spin cycle and service pending UROS callbacks.
 * Must be called from loop() on every iteration.
 */
void microRosLoop();

/**
 * Returns true while the micro-ROS agent connection is active.
 * Drops to false if the serial link is disrupted; microRosLoop()
 * will attempt reconnection automatically.
 */
bool microRosConnected();

#endif // MICRO_ROS_APP_H
