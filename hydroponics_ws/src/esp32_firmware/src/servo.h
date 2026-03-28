#pragma once
/*
 * servo.h  –  3-channel servo control via ESP32 LEDC peripheral
 *
 * Channels:
 *   SERVO_TURRET  (LEDC channel 0)  – rotary turret
 *   SERVO_CUTTER  (LEDC channel 1)  – cutting mechanism
 *   SERVO_GRIPPER (LEDC channel 2)  – gripper / end-effector
 *
 * All servos use:
 *   Frequency   : 50 Hz  (20 ms period)
 *   Resolution  : 16 bits  (0 – 65535)
 *   Pulse range : 500 µs – 2500 µs  (0° – 180°)
 */

#ifndef SERVO_H
#define SERVO_H

#include <stdint.h>

// ── Pin assignments ──────────────────────────────────────────────────────────
#define SERVO_TURRET_PIN    18
#define SERVO_CUTTER_PIN    19
#define SERVO_GRIPPER_PIN   21

// ── LEDC parameters ──────────────────────────────────────────────────────────
#define SERVO_FREQ_HZ       50
#define SERVO_RESOLUTION    16          // bits
#define SERVO_MIN_US        500         // µs – pulse at 0°
#define SERVO_MAX_US        2500        // µs – pulse at 180°

// Channel IDs (map to LEDC channels 0–2)
#define SERVO_TURRET        0
#define SERVO_CUTTER        1
#define SERVO_GRIPPER       2
#define SERVO_CHANNEL_COUNT 3

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * Initialise all servo LEDC channels and output pins.
 * Centres all servos (90°) on startup.
 */
void servo_init(void);

/**
 * Set servo position by angle.
 * @param channel  SERVO_TURRET / SERVO_CUTTER / SERVO_GRIPPER
 * @param angle_deg  0 – 180 degrees
 */
void servo_set_angle(uint8_t channel, float angle_deg);

/**
 * Set servo position directly in microseconds.
 * @param channel  SERVO_TURRET / SERVO_CUTTER / SERVO_GRIPPER
 * @param us       Pulse width in microseconds (500 – 2500)
 */
void servo_set_us(uint8_t channel, uint16_t us);

/**
 * Read back the last commanded angle for a channel.
 */
float servo_get_angle(uint8_t channel);

#endif // SERVO_H
