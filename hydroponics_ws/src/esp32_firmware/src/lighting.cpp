/*
 * lighting.cpp  –  Grow LED panel + inspection LED strip implementation
 *
 * MIT License — Copyright (c) 2026 Claudroponics
 */

#include "lighting.h"
#include "Arduino.h"

Lighting::Lighting(int grow_pwm_pin, int inspection_pin)
    : _grow_pin(grow_pwm_pin),
      _inspection_pin(inspection_pin),
      _grow_intensity(0),
      _inspection_on(false)
{
}

void Lighting::begin()
{
    // Configure LEDC for grow panel
    ledcSetup(LEDC_CHANNEL_GROW, LEDC_FREQ_HZ, LEDC_RESOLUTION);
    ledcAttachPin(_grow_pin, LEDC_CHANNEL_GROW);
    ledcWrite(LEDC_CHANNEL_GROW, 0);  // off at startup

    // Inspection LED: simple GPIO output
    pinMode(_inspection_pin, OUTPUT);
    digitalWrite(_inspection_pin, LOW);
}

void Lighting::setGrowIntensity(uint8_t percent)
{
    // Clamp 0–100
    if (percent > 100) percent = 100;
    _grow_intensity = percent;
    ledcWrite(LEDC_CHANNEL_GROW, _percent_to_duty(percent));
}

uint8_t Lighting::getGrowIntensity() const
{
    return _grow_intensity;
}

void Lighting::setInspectionLight(bool on)
{
    _inspection_on = on;
    digitalWrite(_inspection_pin, on ? HIGH : LOW);
}

bool Lighting::isInspectionOn() const
{
    return _inspection_on;
}

uint8_t Lighting::_percent_to_duty(uint8_t percent)
{
    // Map 0–100 % → 0–255 (8-bit LEDC resolution)
    return static_cast<uint8_t>((static_cast<uint16_t>(percent) * 255u) / 100u);
}
