#pragma once
/*
 * pumps.h  –  Peristaltic pump driver for nutrient/pH dosing
 *
 * Manages 4 pumps via MOSFET GPIO pins with non-blocking timing,
 * mL-based dosing, and per-pump flow-rate calibration.
 *
 * Pump IDs:
 *   PUMP_PH_UP      = 0  –  pH up solution
 *   PUMP_PH_DOWN    = 1  –  pH down solution
 *   PUMP_NUTRIENT_A = 2  –  Nutrient part A
 *   PUMP_NUTRIENT_B = 3  –  Nutrient part B
 */

#ifndef PUMPS_H
#define PUMPS_H

#include <stdint.h>
#include <stdbool.h>
#include "Arduino.h"

#define NUM_PUMPS 4

typedef enum {
    PUMP_PH_UP      = 0,
    PUMP_PH_DOWN    = 1,
    PUMP_NUTRIENT_A = 2,
    PUMP_NUTRIENT_B = 3
} PumpID;

class Pumps {
public:
    /**
     * @param ph_up_pin       GPIO pin for pH-up pump MOSFET gate
     * @param ph_down_pin     GPIO pin for pH-down pump MOSFET gate
     * @param nutrient_a_pin  GPIO pin for nutrient-A pump MOSFET gate
     * @param nutrient_b_pin  GPIO pin for nutrient-B pump MOSFET gate
     */
    Pumps(int ph_up_pin, int ph_down_pin, int nutrient_a_pin, int nutrient_b_pin);

    /** Configure GPIO pins as outputs and ensure all pumps are off. */
    void begin();

    /**
     * Start a non-blocking timed dose on the specified pump.
     * A previously running dose on the same pump is cancelled first.
     *
     * @param pump_id    Pump to actuate (PumpID enum)
     * @param duration_ms  Duration of the dose in milliseconds
     */
    void dose(int pump_id, uint32_t duration_ms);

    /** Immediately stop a specific pump. */
    void stop(int pump_id);

    /** Immediately stop all pumps. */
    void stopAll();

    /**
     * Service timing — must be called from loop() every iteration.
     * Turns off pumps whose dose duration has elapsed.
     */
    void update();

    /** Returns true while the pump is actively running. */
    bool isRunning(int pump_id) const;

    /**
     * Store the measured flow rate for mL-based dosing.
     * @param pump_id      Pump to calibrate
     * @param ml_per_sec   Measured flow rate in mL/s (typical: 0.5–2.0)
     */
    void calibrate(int pump_id, float ml_per_sec);

    /**
     * Dose a volume in mL, calculated from the stored flow-rate calibration.
     * Falls back to a 1-second pulse if no calibration has been set.
     */
    void doseML(int pump_id, float ml);

    /** Returns the stored flow rate for a pump (mL/s). */
    float getFlowRate(int pump_id) const;

private:
    int      _pins[NUM_PUMPS];
    bool     _running[NUM_PUMPS];
    uint32_t _start_time[NUM_PUMPS];   // millis() when dose started
    uint32_t _duration[NUM_PUMPS];     // requested dose duration (ms)
    float    _ml_per_sec[NUM_PUMPS];   // calibration: mL per second

    bool _valid_id(int pump_id) const;
};

#endif // PUMPS_H
