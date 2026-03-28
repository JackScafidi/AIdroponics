#pragma once
/*
 * stepper.h  –  Dual-axis stepper motor control (trapezoidal profile)
 *
 * Two axes are defined:
 *   RAIL_AXIS  – horizontal rail (Stepper 1)
 *   Z_AXIS     – vertical Z (Stepper 2)
 *
 * Motion is executed asynchronously by a high-resolution esp_timer ISR.
 * The global flag  motors_active  is set true while any axis is moving so
 * that the ADC subsystem can defer sampling (quiet period).
 */

#ifndef STEPPER_H
#define STEPPER_H

#include <stdint.h>
#include <stdbool.h>

// ── Pin assignments (adjust to your wiring) ────────────────────────────────
// Rail axis
#define RAIL_STEP_PIN       26
#define RAIL_DIR_PIN        27
#define RAIL_EN_PIN         14

// Z axis
#define Z_STEP_PIN          25
#define Z_DIR_PIN           33
#define Z_EN_PIN            32

// Default motion parameters
#define STEPPER_DEFAULT_STEPS_PER_MM   80      // 200 step/rev, 16 microstep, 2mm/rev lead
#define STEPPER_DEFAULT_MAX_SPEED_MM_S 50.0f   // mm/s
#define STEPPER_DEFAULT_ACCEL_MM_S2    200.0f  // mm/s²
#define STEPPER_TIMER_PERIOD_US        50      // ISR tick period in µs

// ── Data types ──────────────────────────────────────────────────────────────
typedef enum {
    AXIS_RAIL = 0,
    AXIS_Z    = 1,
    AXIS_COUNT
} AxisID;

typedef struct {
    // Hardware
    int step_pin;
    int dir_pin;
    int en_pin;

    // Kinematics
    float steps_per_mm;
    float max_speed;       // steps / s
    float acceleration;    // steps / s²

    // Motion state (managed by ISR)
    volatile int32_t  current_pos;   // current position in steps
    volatile int32_t  target_pos;    // target position in steps
    volatile float    current_speed; // current speed  steps / s
    volatile bool     moving;
    volatile bool     dir_positive;

    // Trapezoidal profile helpers
    volatile int32_t  steps_to_decel; // steps remaining when decel must start
} StepperAxis;

// ── Global state ────────────────────────────────────────────────────────────
extern StepperAxis g_rail_axis;
extern StepperAxis g_z_axis;
extern volatile bool motors_active;   // true when any axis is in motion

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Initialise a stepper axis: configure GPIO, disable driver, attach timer ISR.
 * Call once per axis during setup.
 */
void stepper_init(StepperAxis *axis);

/**
 * Command an axis to move to an absolute step position.
 * Returns immediately; motion is handled by the ISR.
 */
void stepper_move_to(StepperAxis *axis, int32_t target_steps);

/**
 * Perform a homing sequence:
 *   1. Move in <direction> until <limit_pin> triggers.
 *   2. Back off <backoff_steps> steps in the opposite direction.
 *   3. Zero current_pos.
 * Blocks until complete.
 *
 * @param axis          Axis to home.
 * @param limit_pin     GPIO pin of the limit switch (active LOW, NC with pullup).
 * @param direction     +1 or -1.
 * @param backoff_steps Steps to retreat after switch triggers.
 */
void stepper_home(StepperAxis *axis, int limit_pin, int direction, int32_t backoff_steps);

/**
 * Immediately stop an axis (no deceleration ramp).
 */
void stepper_stop(StepperAxis *axis);

/**
 * Returns true if the axis is currently executing a move.
 */
bool stepper_is_moving(const StepperAxis *axis);

/**
 * Convenience wrappers that act on the named global instances.
 */
void rail_move_to(int32_t steps);
void z_move_to(int32_t steps);
void all_steppers_stop(void);

#endif // STEPPER_H
