/*
 * sensors.cpp  –  Analog sensor + DS18B20 implementation
 *
 * MIT License — Copyright (c) 2026 Claudroponics
 *
 * pH conversion formula (Gravity analog pH probe):
 *   voltage = (raw_adc / 4095.0) * 3.3
 *   pH = 7.0 + (2.5 - voltage) * 3.5
 *   (Calibration offset added on top)
 *
 * EC conversion formula (Gravity analog EC probe):
 *   voltage = (raw_adc / 4095.0) * 3.3
 *   ec_mS_cm = voltage * ec_factor
 *   Default ec_factor = 0.82 (determined empirically; calibrate with 1413 µS/cm std)
 */

#include "sensors.h"
#include "Arduino.h"

static constexpr float kDefaultEcFactor = 0.82f;

Sensors::Sensors(int ph_pin, int ec_pin, int temp_data_pin, int float_switch_pin)
    : _ph_pin(ph_pin),
      _ec_pin(ec_pin),
      _float_switch_pin(float_switch_pin),
      _one_wire(temp_data_pin),
      _dallas(&_one_wire),
      _buf_idx(0),
      _buf_count(0),
      _ph_offset(0.0f),
      _ec_factor(kDefaultEcFactor),
      _temperature_c(-127.0f),
      _temp_converting(false),
      _temp_request_ms(0)
{
    for (int i = 0; i < SENSOR_ADC_SAMPLES; ++i) {
        _ph_buf[i] = 0.0f;
        _ec_buf[i] = 0.0f;
    }
}

void Sensors::begin()
{
    // Float switch: input with pullup (active LOW = water present)
    pinMode(_float_switch_pin, INPUT_PULLUP);

    // ESP32 ADC pins are input-only — no pinMode needed for ADC channels,
    // but call analogReadResolution to ensure 12-bit
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);  // Full 0–3.3 V range

    _dallas.begin();
    _dallas.setResolution(11);       // 11-bit (~375 ms conversion)
    _dallas.setWaitForConversion(false);
}

void Sensors::update()
{
    uint32_t now = millis();

    // ----- ADC sampling -----
    float ph_raw = static_cast<float>(analogRead(_ph_pin));
    float ec_raw = static_cast<float>(analogRead(_ec_pin));
    _advance_buffer(ph_raw, ec_raw);

    // ----- DS18B20 non-blocking -----
    if (!_temp_converting) {
        _dallas.requestTemperatures();
        _temp_request_ms = now;
        _temp_converting = true;
    } else if ((now - _temp_request_ms) >= TEMP_CONVERSION_MS) {
        float t = _dallas.getTempCByIndex(0);
        if (t > -120.0f) {           // -127 means "not connected"
            _temperature_c = t;
        }
        _temp_converting = false;
    }
}

float Sensors::getPH() const
{
    float avg_raw = _buffer_average(_ph_buf, _buf_count);
    float voltage = (avg_raw / SENSOR_ADC_MAX) * SENSOR_VREF;
    float ph = 7.0f + (2.5f - voltage) * 3.5f;
    return ph + _ph_offset;
}

float Sensors::getEC() const
{
    float avg_raw = _buffer_average(_ec_buf, _buf_count);
    float voltage = (avg_raw / SENSOR_ADC_MAX) * SENSOR_VREF;
    return voltage * _ec_factor;
}

float Sensors::getTemperatureC() const
{
    return _temperature_c;
}

bool Sensors::isWaterLevelOk() const
{
    // NC float switch wired to INPUT_PULLUP: LOW = water present, HIGH = low water
    return (digitalRead(_float_switch_pin) == LOW);
}

void Sensors::calibratePH(float offset)
{
    _ph_offset = offset;
}

void Sensors::calibrateEC(float factor)
{
    if (factor > 0.0f) {
        _ec_factor = factor;
    }
}

float Sensors::getRawPH() const
{
    return _buffer_average(_ph_buf, _buf_count);
}

float Sensors::getRawEC() const
{
    return _buffer_average(_ec_buf, _buf_count);
}

void Sensors::_advance_buffer(float ph_raw, float ec_raw)
{
    _ph_buf[_buf_idx] = ph_raw;
    _ec_buf[_buf_idx] = ec_raw;
    _buf_idx = (_buf_idx + 1) % SENSOR_ADC_SAMPLES;
    if (_buf_count < SENSOR_ADC_SAMPLES) {
        ++_buf_count;
    }
}

float Sensors::_buffer_average(const float* buf, int count) const
{
    if (count == 0) return 0.0f;
    float sum = 0.0f;
    int n = (count < SENSOR_ADC_SAMPLES) ? count : SENSOR_ADC_SAMPLES;
    for (int i = 0; i < n; ++i) {
        sum += buf[i];
    }
    return sum / static_cast<float>(n);
}
