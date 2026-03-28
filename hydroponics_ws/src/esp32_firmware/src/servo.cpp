/*
 * servo.cpp  –  ESP32 LEDC-based 3-channel servo driver
 */

#include "servo.h"
#include <Arduino.h>

// ── Static tables ─────────────────────────────────────────────────────────────
static const int s_servo_pins[SERVO_CHANNEL_COUNT] = {
    SERVO_TURRET_PIN,
    SERVO_CUTTER_PIN,
    SERVO_GRIPPER_PIN
};

// Store last commanded angle for read-back
static float s_last_angle[SERVO_CHANNEL_COUNT] = {90.0f, 90.0f, 90.0f};

// ── Conversion helpers ────────────────────────────────────────────────────────

/**
 * Convert microseconds to LEDC duty count.
 *
 * Period = 1 / 50 Hz = 20 000 µs
 * Max duty = 2^16 - 1 = 65535
 * duty = (us / 20000) * 65535
 */
static uint32_t us_to_duty(uint16_t us)
{
    // Clamp
    if (us < SERVO_MIN_US) us = SERVO_MIN_US;
    if (us > SERVO_MAX_US) us = SERVO_MAX_US;

    const uint32_t period_us = 1000000UL / SERVO_FREQ_HZ; // 20000 µs
    const uint32_t max_duty  = (1UL << SERVO_RESOLUTION) - 1;
    return ((uint32_t)us * max_duty) / period_us;
}

// ── Public API ────────────────────────────────────────────────────────────────
void servo_init(void)
{
    for (int ch = 0; ch < SERVO_CHANNEL_COUNT; ch++) {
        // Attach LEDC timer – channel = ch, timer = 0 (shared)
        ledcSetup(ch, SERVO_FREQ_HZ, SERVO_RESOLUTION);
        ledcAttachPin(s_servo_pins[ch], ch);

        // Centre position on startup
        servo_set_angle(ch, 90.0f);

        Serial.printf("[servo] channel %d on pin %d initialised (90°)\n",
                      ch, s_servo_pins[ch]);
    }
}

void servo_set_angle(uint8_t channel, float angle_deg)
{
    if (channel >= SERVO_CHANNEL_COUNT) return;

    // Clamp angle
    if (angle_deg <   0.0f) angle_deg =   0.0f;
    if (angle_deg > 180.0f) angle_deg = 180.0f;

    // Map 0–180° → SERVO_MIN_US – SERVO_MAX_US
    uint16_t us = (uint16_t)(SERVO_MIN_US
                  + (angle_deg / 180.0f) * (SERVO_MAX_US - SERVO_MIN_US));

    servo_set_us(channel, us);
    s_last_angle[channel] = angle_deg;
}

void servo_set_us(uint8_t channel, uint16_t us)
{
    if (channel >= SERVO_CHANNEL_COUNT) return;

    uint32_t duty = us_to_duty(us);
    ledcWrite(channel, duty);

    // Update cached angle from µs
    float angle = ((float)(us - SERVO_MIN_US) / (SERVO_MAX_US - SERVO_MIN_US)) * 180.0f;
    s_last_angle[channel] = angle;
}

float servo_get_angle(uint8_t channel)
{
    if (channel >= SERVO_CHANNEL_COUNT) return 0.0f;
    return s_last_angle[channel];
}
