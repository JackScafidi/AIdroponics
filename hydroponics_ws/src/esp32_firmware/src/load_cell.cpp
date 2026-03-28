/*
 * load_cell.cpp  –  HX711 load-cell implementation
 *
 * MIT License — Copyright (c) 2026 Claudroponics
 */

#include "load_cell.h"
#include "Arduino.h"

LoadCell::LoadCell(int dout_pin, int sck_pin)
    : _dout_pin(dout_pin),
      _sck_pin(sck_pin),
      _calibration_factor(LOAD_CELL_DEFAULT_CALIBRATION)
{
}

void LoadCell::begin()
{
    _hx711.begin(_dout_pin, _sck_pin);
    // Wait for HX711 to power up (can take up to 500 ms after power-on)
    delay(500);
    _hx711.set_scale(_calibration_factor);
    _hx711.tare(LOAD_CELL_SAMPLES);
}

void LoadCell::tare()
{
    _hx711.tare(LOAD_CELL_SAMPLES);
}

float LoadCell::getWeightGrams()
{
    if (!_hx711.is_ready()) {
        return 0.0f;
    }
    float reading = _hx711.get_units(LOAD_CELL_SAMPLES);
    // Clamp negative noise to zero
    return (reading < 0.0f) ? 0.0f : reading;
}

bool LoadCell::isReady() const
{
    return _hx711.is_ready();
}

void LoadCell::setCalibrationFactor(float factor)
{
    if (factor != 0.0f) {
        _calibration_factor = factor;
        _hx711.set_scale(_calibration_factor);
    }
}

float LoadCell::getCalibrationFactor() const
{
    return _calibration_factor;
}
