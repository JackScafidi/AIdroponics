#pragma once
/*
 * lighting.h  –  Grow LED panel (PWM) + inspection LED strip (on/off)
 *
 * Grow panel:  PWM via ESP32 LEDC peripheral, 5 kHz / 8-bit.
 *              Intensity 0–100 % mapped to LEDC duty 0–255.
 * Inspection:  Simple GPIO on/off, typically a relay or logic-level MOSFET.
 */

#ifndef LIGHTING_H
#define LIGHTING_H

#include <stdint.h>
#include "Arduino.h"

#define LEDC_CHANNEL_GROW   0
#define LEDC_FREQ_HZ        5000
#define LEDC_RESOLUTION     8       // bits (0–255)

class Lighting {
public:
    /**
     * @param grow_pwm_pin     GPIO pin for grow panel MOSFET gate (PWM capable)
     * @param inspection_pin   GPIO pin for inspection LED MOSFET/relay
     */
    Lighting(int grow_pwm_pin, int inspection_pin);

    /**
     * Configure LEDC channel and set both outputs to off.
     * Call once during setup().
     */
    void begin();

    /**
     * Set grow panel intensity.
     * @param percent  0–100. Values are clamped.
     */
    void setGrowIntensity(uint8_t percent);

    /** Returns current grow panel intensity (0–100 %). */
    uint8_t getGrowIntensity() const;

    /**
     * Turn inspection LEDs on (true) or off (false).
     * Inspection LEDs should be on only during image capture.
     */
    void setInspectionLight(bool on);

    /** Returns true if inspection light is currently on. */
    bool isInspectionOn() const;

private:
    int     _grow_pin;
    int     _inspection_pin;
    uint8_t _grow_intensity;   // 0–100 %
    bool    _inspection_on;

    static uint8_t _percent_to_duty(uint8_t percent);
};

#endif // LIGHTING_H
