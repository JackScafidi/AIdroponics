/*
 * main.cpp  –  ESP32 firmware entry point for Claudroponics
 *
 * MIT License — Copyright (c) 2026 Claudroponics
 *
 * Instantiates all subsystem objects and delegates to:
 *   stepper.h       — dual-axis stepper control (ISR-driven)
 *   pumps.h         — 4 peristaltic pumps
 *   sensors.h       — pH / EC / temperature / water level
 *   load_cell.h     — HX711 harvest weighing
 *   lighting.h      — grow panel (PWM) + inspection LEDs
 *   micro_ros_app.h — micro-ROS node + pub/sub
 *
 * Target: ESP32 DevKit V1, PlatformIO / Arduino framework
 * Flash:  pio run -t upload
 * Agent:  ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200
 */

#include "Arduino.h"
#include "stepper.h"
#include "tmc2209.h"
#include "pumps.h"
#include "sensors.h"
#include "load_cell.h"
#include "lighting.h"
#include "micro_ros_app.h"

// ============================================================================
// Pin Assignments  (adjust to your physical wiring — see esp32_firmware/README.md)
// ============================================================================

// --- Rail transport stepper (AXIS_RAIL) ---
// Defined in stepper.h as RAIL_STEP_PIN=26, RAIL_DIR_PIN=27, RAIL_EN_PIN=14

// --- Z-axis stepper (AXIS_Z) ---
// Defined in stepper.h as Z_STEP_PIN=25, Z_DIR_PIN=33, Z_EN_PIN=32

// --- Servo pins ---
constexpr int TURRET_SERVO_PIN   = 12;  // MG996R turret rotation
constexpr int CUTTER_SERVO_PIN   = 13;  // SG90 blade actuator
constexpr int GRIPPER_SERVO_PIN  = 15;  // SG90 gripper jaw

// --- Peristaltic pumps (MOSFET gate pins) ---
constexpr int PH_UP_PIN          = 16;
constexpr int PH_DOWN_PIN        = 17;
constexpr int NUTRIENT_A_PIN     = 18;
constexpr int NUTRIENT_B_PIN     = 19;

// --- Sensors ---
constexpr int PH_SENSOR_PIN      = 34;  // ADC1_CH6  (input only)
constexpr int EC_SENSOR_PIN      = 35;  // ADC1_CH7  (input only)
constexpr int TEMP_DATA_PIN      =  4;  // DS18B20 OneWire
constexpr int FLOAT_SWITCH_PIN   =  5;  // NC float switch (active LOW)

// --- Load cell (HX711) ---
constexpr int LOAD_CELL_DOUT     = 21;
constexpr int LOAD_CELL_SCK      = 22;

// --- Lighting ---
constexpr int GROW_LED_PIN       = 23;  // PWM (LEDC channel 0)
constexpr int INSPECTION_LED_PIN =  2;  // On-board LED doubles as inspection LED

// --- Limit switches ---
constexpr int RAIL_LIMIT_PIN     = 36;  // VP — rail home switch (active LOW)
constexpr int Z_LIMIT_PIN        = 39;  // VN — Z home switch    (active LOW)

// ============================================================================
// Global subsystem objects  (extern'd in micro_ros_app.cpp)
// ============================================================================
Pumps    g_pumps(PH_UP_PIN, PH_DOWN_PIN, NUTRIENT_A_PIN, NUTRIENT_B_PIN);
Sensors  g_sensors(PH_SENSOR_PIN, EC_SENSOR_PIN, TEMP_DATA_PIN, FLOAT_SWITCH_PIN);
LoadCell g_load_cell(LOAD_CELL_DOUT, LOAD_CELL_SCK);
Lighting g_lighting(GROW_LED_PIN, INSPECTION_LED_PIN);

// ============================================================================
// setup()
// ============================================================================
void setup()
{
    Serial.begin(115200);
    Serial.println("[main] Claudroponics ESP32 firmware starting…");

    // --- Stepper axes ---
    g_rail_axis = {
        .step_pin    = RAIL_STEP_PIN,
        .dir_pin     = RAIL_DIR_PIN,
        .en_pin      = RAIL_EN_PIN,
        .steps_per_mm = STEPPER_DEFAULT_STEPS_PER_MM,
        .max_speed   = STEPPER_DEFAULT_MAX_SPEED_MM_S * STEPPER_DEFAULT_STEPS_PER_MM,
        .acceleration = STEPPER_DEFAULT_ACCEL_MM_S2 * STEPPER_DEFAULT_STEPS_PER_MM,
    };
    g_z_axis = {
        .step_pin    = Z_STEP_PIN,
        .dir_pin     = Z_DIR_PIN,
        .en_pin      = Z_EN_PIN,
        .steps_per_mm = STEPPER_DEFAULT_STEPS_PER_MM,
        .max_speed   = (STEPPER_DEFAULT_MAX_SPEED_MM_S / 2.0f) * STEPPER_DEFAULT_STEPS_PER_MM,
        .acceleration = STEPPER_DEFAULT_ACCEL_MM_S2 * STEPPER_DEFAULT_STEPS_PER_MM,
    };
    stepper_init(&g_rail_axis);
    stepper_init(&g_z_axis);

    // --- Limit switches ---
    pinMode(RAIL_LIMIT_PIN, INPUT_PULLUP);
    pinMode(Z_LIMIT_PIN,    INPUT_PULLUP);

    // --- Homing sequence ---
    Serial.println("[main] Homing Z axis…");
    stepper_home(&g_z_axis, Z_LIMIT_PIN, -1, 200);
    Serial.println("[main] Homing rail axis…");
    stepper_home(&g_rail_axis, RAIL_LIMIT_PIN, -1, 400);
    Serial.println("[main] Homing complete.");

    // --- Peripherals ---
    g_pumps.begin();
    g_sensors.begin();
    g_load_cell.begin();
    g_load_cell.tare();
    g_lighting.begin();

    // --- micro-ROS (blocks until agent connects) ---
    microRosSetup();

    Serial.println("[main] Setup complete. Entering main loop.");
}

// ============================================================================
// loop()
// ============================================================================
void loop()
{
    // Service non-blocking pump timing
    g_pumps.update();

    // Update sensor ADC moving averages + DS18B20 conversion
    g_sensors.update();

    // micro-ROS executor spin (publish sensors, handle commands)
    microRosLoop();

    // Small yield to prevent WDT trips on ESP32
    delay(1);
}
