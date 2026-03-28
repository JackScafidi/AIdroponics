/*
 * stepper.cpp  –  Trapezoidal-profile stepper driver using esp_timer
 *
 * Each axis gets its own esp_timer periodic callback that fires every
 * STEPPER_TIMER_PERIOD_US microseconds.  Inside the callback the algorithm:
 *
 *   1. Calculates remaining steps and distance needed to decelerate to zero.
 *   2. Decides whether to accelerate, hold max speed, or decelerate.
 *   3. Accumulates fractional step counter (Bresenham-style) so that the
 *      step rate matches the desired speed even at low frequencies.
 *   4. Pulses STEP pin when a whole step is due.
 *
 * Both axes share the same ISR logic via a common helper; the timer callbacks
 * simply pass their respective axis pointers.
 */

#include "stepper.h"

#include <Arduino.h>
#include <esp_timer.h>
#include <math.h>

// ── Global instances ─────────────────────────────────────────────────────────
StepperAxis g_rail_axis = {
    .step_pin      = RAIL_STEP_PIN,
    .dir_pin       = RAIL_DIR_PIN,
    .en_pin        = RAIL_EN_PIN,
    .steps_per_mm  = STEPPER_DEFAULT_STEPS_PER_MM,
    .max_speed     = STEPPER_DEFAULT_MAX_SPEED_MM_S * STEPPER_DEFAULT_STEPS_PER_MM,
    .acceleration  = STEPPER_DEFAULT_ACCEL_MM_S2   * STEPPER_DEFAULT_STEPS_PER_MM,
    .current_pos   = 0,
    .target_pos    = 0,
    .current_speed = 0.0f,
    .moving        = false,
    .dir_positive  = true,
    .steps_to_decel = 0
};

StepperAxis g_z_axis = {
    .step_pin      = Z_STEP_PIN,
    .dir_pin       = Z_DIR_PIN,
    .en_pin        = Z_EN_PIN,
    .steps_per_mm  = STEPPER_DEFAULT_STEPS_PER_MM,
    .max_speed     = STEPPER_DEFAULT_MAX_SPEED_MM_S * STEPPER_DEFAULT_STEPS_PER_MM,
    .acceleration  = STEPPER_DEFAULT_ACCEL_MM_S2   * STEPPER_DEFAULT_STEPS_PER_MM,
    .current_pos   = 0,
    .target_pos    = 0,
    .current_speed = 0.0f,
    .moving        = false,
    .dir_positive  = true,
    .steps_to_decel = 0
};

volatile bool motors_active = false;

// ── Private: per-axis fractional step accumulator ────────────────────────────
static volatile float s_rail_accum = 0.0f;
static volatile float s_z_accum    = 0.0f;

// esp_timer handles
static esp_timer_handle_t s_rail_timer = nullptr;
static esp_timer_handle_t s_z_timer    = nullptr;

// ── Private: tick period in seconds ──────────────────────────────────────────
static constexpr float TICK_S = STEPPER_TIMER_PERIOD_US * 1e-6f;

// ── ISR core logic (runs in timer callback context) ──────────────────────────
static void IRAM_ATTR stepper_tick(StepperAxis *ax, volatile float &accum)
{
    if (!ax->moving) return;

    int32_t remaining = ax->target_pos - ax->current_pos;
    if (remaining == 0) {
        ax->moving        = false;
        ax->current_speed = 0.0f;
        // Update motors_active
        if (!g_rail_axis.moving && !g_z_axis.moving) {
            motors_active = false;
        }
        // Disable driver to reduce heat
        digitalWrite(ax->en_pin, HIGH);
        return;
    }

    // Direction
    bool go_positive = (remaining > 0);
    if (go_positive != ax->dir_positive) {
        ax->dir_positive = go_positive;
        digitalWrite(ax->dir_pin, go_positive ? HIGH : LOW);
    }
    int32_t abs_remaining = go_positive ? remaining : -remaining;

    // Trapezoidal speed calculation
    // Steps needed to decelerate from current_speed to 0:
    //   s = v² / (2·a)
    float decel_steps = (ax->current_speed * ax->current_speed)
                        / (2.0f * ax->acceleration);

    if ((float)abs_remaining <= decel_steps + 1.0f) {
        // Decelerate
        ax->current_speed -= ax->acceleration * TICK_S;
        if (ax->current_speed < 0.0f) ax->current_speed = 0.0f;
    } else {
        // Accelerate or cruise
        ax->current_speed += ax->acceleration * TICK_S;
        if (ax->current_speed > ax->max_speed) {
            ax->current_speed = ax->max_speed;
        }
    }

    // Accumulate fractional steps
    accum += ax->current_speed * TICK_S;

    // Issue whole steps
    while (accum >= 1.0f) {
        accum -= 1.0f;

        // Step pulse (min 2 µs high time per A4988/TMC2209 spec)
        digitalWrite(ax->step_pin, HIGH);
        // ~2 µs delay – nop loop (ESP32 @ 240 MHz ≈ 2 nops per ns)
        volatile int d = 0;
        for (int i = 0; i < 480; i++) { d++; }
        (void)d;
        digitalWrite(ax->step_pin, LOW);

        ax->current_pos += go_positive ? 1 : -1;

        // Re-check after each step
        if (ax->current_pos == ax->target_pos) {
            ax->moving        = false;
            ax->current_speed = 0.0f;
            accum             = 0.0f;
            if (!g_rail_axis.moving && !g_z_axis.moving) {
                motors_active = false;
            }
            digitalWrite(ax->en_pin, HIGH);
            return;
        }
    }
}

// ── Timer callbacks ───────────────────────────────────────────────────────────
static void IRAM_ATTR rail_timer_cb(void */*arg*/)
{
    stepper_tick(&g_rail_axis, s_rail_accum);
}

static void IRAM_ATTR z_timer_cb(void */*arg*/)
{
    stepper_tick(&g_z_axis, s_z_accum);
}

// ── Public API ────────────────────────────────────────────────────────────────
void stepper_init(StepperAxis *axis)
{
    pinMode(axis->step_pin, OUTPUT);
    pinMode(axis->dir_pin,  OUTPUT);
    pinMode(axis->en_pin,   OUTPUT);

    digitalWrite(axis->step_pin, LOW);
    digitalWrite(axis->dir_pin,  LOW);
    digitalWrite(axis->en_pin,   HIGH); // disabled by default (active LOW)

    axis->current_pos   = 0;
    axis->target_pos    = 0;
    axis->current_speed = 0.0f;
    axis->moving        = false;

    // Create the per-axis periodic timer
    esp_timer_create_args_t cfg = {};
    cfg.dispatch_method = ESP_TIMER_ISR;
    cfg.name            = (axis == &g_rail_axis) ? "rail_step" : "z_step";
    cfg.callback        = (axis == &g_rail_axis) ? rail_timer_cb : z_timer_cb;
    cfg.arg             = nullptr;

    esp_timer_handle_t &handle = (axis == &g_rail_axis) ? s_rail_timer : s_z_timer;
    ESP_ERROR_CHECK(esp_timer_create(&cfg, &handle));
    ESP_ERROR_CHECK(esp_timer_start_periodic(handle, STEPPER_TIMER_PERIOD_US));

    Serial.printf("[stepper] axis %s initialised (step=%d dir=%d en=%d)\n",
        cfg.name, axis->step_pin, axis->dir_pin, axis->en_pin);
}

void stepper_move_to(StepperAxis *axis, int32_t target_steps)
{
    if (target_steps == axis->current_pos) return;

    // Enable driver
    digitalWrite(axis->en_pin, LOW);

    // Atomically update target; ISR picks it up on next tick
    axis->target_pos = target_steps;
    axis->moving     = true;
    motors_active    = true;
}

void stepper_home(StepperAxis *axis, int limit_pin, int direction, int32_t backoff_steps)
{
    const float home_speed = axis->max_speed * 0.3f; // 30 % of max

    // Configure limit switch pin
    pinMode(limit_pin, INPUT_PULLUP);

    // Enable driver
    digitalWrite(axis->en_pin, LOW);

    Serial.printf("[stepper] homing axis (limit_pin=%d dir=%d)\n", limit_pin, direction);

    // Phase 1: move toward switch
    bool go_positive = (direction > 0);
    digitalWrite(axis->dir_pin, go_positive ? HIGH : LOW);
    axis->dir_positive  = go_positive;
    axis->current_speed = home_speed;
    axis->moving        = true;
    motors_active       = true;

    // Drive until switch triggers (active LOW)
    while (digitalRead(limit_pin) == HIGH) {
        // Move one step manually at homing speed
        // (We bypass the timer here to keep homing synchronous / simple)
        axis->current_pos += go_positive ? 1 : -1;
        digitalWrite(axis->step_pin, HIGH);
        delayMicroseconds(2);
        digitalWrite(axis->step_pin, LOW);
        // Period = 1 / home_speed in µs
        delayMicroseconds((uint32_t)(1e6f / home_speed));
    }

    axis->moving        = false;
    axis->current_speed = 0.0f;
    if (!g_rail_axis.moving && !g_z_axis.moving) motors_active = false;

    Serial.println("[stepper] limit switch hit – backing off");

    // Phase 2: back off
    int32_t back_target = axis->current_pos + (-direction) * backoff_steps;
    stepper_move_to(axis, back_target);
    while (axis->moving) delay(1);

    // Phase 3: zero position
    axis->current_pos = 0;
    axis->target_pos  = 0;

    digitalWrite(axis->en_pin, HIGH); // disable after homing
    Serial.println("[stepper] homing complete – position zeroed");
}

void stepper_stop(StepperAxis *axis)
{
    axis->target_pos    = axis->current_pos; // stop in place
    axis->moving        = false;
    axis->current_speed = 0.0f;
    if (!g_rail_axis.moving && !g_z_axis.moving) motors_active = false;
    digitalWrite(axis->en_pin, HIGH);
}

bool stepper_is_moving(const StepperAxis *axis)
{
    return axis->moving;
}

// ── Convenience wrappers ──────────────────────────────────────────────────────
void rail_move_to(int32_t steps) { stepper_move_to(&g_rail_axis, steps); }
void z_move_to(int32_t steps)    { stepper_move_to(&g_z_axis,    steps); }

void all_steppers_stop(void)
{
    stepper_stop(&g_rail_axis);
    stepper_stop(&g_z_axis);
}
