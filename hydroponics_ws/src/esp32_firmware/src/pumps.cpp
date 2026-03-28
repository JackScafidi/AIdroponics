/*
 * pumps.cpp  –  Peristaltic pump driver implementation
 *
 * MIT License — Copyright (c) 2026 Claudroponics
 */

#include "pumps.h"
#include "Arduino.h"
#include <algorithm>

// Default calibration: 1.0 mL/s — update via calibrate() after measuring
static constexpr float kDefaultFlowRate = 1.0f;

Pumps::Pumps(int ph_up_pin, int ph_down_pin, int nutrient_a_pin, int nutrient_b_pin)
{
    _pins[PUMP_PH_UP]      = ph_up_pin;
    _pins[PUMP_PH_DOWN]    = ph_down_pin;
    _pins[PUMP_NUTRIENT_A] = nutrient_a_pin;
    _pins[PUMP_NUTRIENT_B] = nutrient_b_pin;

    for (int i = 0; i < NUM_PUMPS; ++i) {
        _running[i]    = false;
        _start_time[i] = 0;
        _duration[i]   = 0;
        _ml_per_sec[i] = kDefaultFlowRate;
    }
}

void Pumps::begin()
{
    for (int i = 0; i < NUM_PUMPS; ++i) {
        pinMode(_pins[i], OUTPUT);
        digitalWrite(_pins[i], LOW);
    }
}

void Pumps::dose(int pump_id, uint32_t duration_ms)
{
    if (!_valid_id(pump_id)) return;

    // Cancel any running dose before starting a new one
    if (_running[pump_id]) {
        stop(pump_id);
    }

    _running[pump_id]    = true;
    _start_time[pump_id] = millis();
    _duration[pump_id]   = duration_ms;
    digitalWrite(_pins[pump_id], HIGH);
}

void Pumps::stop(int pump_id)
{
    if (!_valid_id(pump_id)) return;
    digitalWrite(_pins[pump_id], LOW);
    _running[pump_id] = false;
}

void Pumps::stopAll()
{
    for (int i = 0; i < NUM_PUMPS; ++i) {
        stop(i);
    }
}

void Pumps::update()
{
    uint32_t now = millis();
    for (int i = 0; i < NUM_PUMPS; ++i) {
        if (_running[i] && (now - _start_time[i]) >= _duration[i]) {
            stop(i);
        }
    }
}

bool Pumps::isRunning(int pump_id) const
{
    if (!_valid_id(pump_id)) return false;
    return _running[pump_id];
}

void Pumps::calibrate(int pump_id, float ml_per_sec)
{
    if (!_valid_id(pump_id)) return;
    if (ml_per_sec > 0.0f) {
        _ml_per_sec[pump_id] = ml_per_sec;
    }
}

void Pumps::doseML(int pump_id, float ml)
{
    if (!_valid_id(pump_id) || ml <= 0.0f) return;

    float flow = _ml_per_sec[pump_id];
    if (flow <= 0.0f) flow = kDefaultFlowRate;

    uint32_t duration_ms = static_cast<uint32_t>((ml / flow) * 1000.0f);
    // Minimum 100 ms pulse to account for pump inertia
    duration_ms = std::max(duration_ms, static_cast<uint32_t>(100));
    dose(pump_id, duration_ms);
}

float Pumps::getFlowRate(int pump_id) const
{
    if (!_valid_id(pump_id)) return 0.0f;
    return _ml_per_sec[pump_id];
}

bool Pumps::_valid_id(int pump_id) const
{
    return (pump_id >= 0 && pump_id < NUM_PUMPS);
}
