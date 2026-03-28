#pragma once
/*
 * sensors.h  –  Analog pH/EC probe + DS18B20 temperature + float switch
 *
 * Reads:
 *   - Gravity analog pH probe    (ADC, 0–4095 on ESP32 12-bit ADC)
 *   - Gravity analog EC probe    (ADC)
 *   - DS18B20 waterproof temp    (OneWire / DallasTemperature)
 *   - Vertical float switch      (GPIO digital input)
 *
 * All ADC readings use a 10-sample moving average to reduce noise.
 * Temperature conversion is non-blocking (750 ms conversion cycle).
 */

#ifndef SENSORS_H
#define SENSORS_H

#include <stdint.h>
#include <stdbool.h>
#include "Arduino.h"
#include <OneWire.h>
#include <DallasTemperature.h>

#define SENSOR_ADC_SAMPLES  10      // Moving average window
#define SENSOR_ADC_MAX      4095.0f // ESP32 12-bit ADC
#define SENSOR_VREF         3.3f    // ADC reference voltage (V)
#define TEMP_CONVERSION_MS  750     // DS18B20 conversion time

class Sensors {
public:
    /**
     * @param ph_pin           ADC GPIO for pH probe (e.g. GPIO34)
     * @param ec_pin           ADC GPIO for EC probe  (e.g. GPIO35)
     * @param temp_data_pin    OneWire data pin for DS18B20 (e.g. GPIO4)
     * @param float_switch_pin Digital GPIO for float switch (active LOW)
     */
    Sensors(int ph_pin, int ec_pin, int temp_data_pin, int float_switch_pin);

    /**
     * Initialise OneWire/DallasTemperature library and configure GPIOs.
     * Call once during setup().
     */
    void begin();

    /**
     * Service sensor reads — call from loop() every iteration.
     * Handles non-blocking DS18B20 timing (requests new conversion every
     * TEMP_CONVERSION_MS ms; reads result when ready).
     */
    void update();

    /** Returns current pH value (0–14), calibration offset applied. */
    float getPH() const;

    /** Returns current EC value in mS/cm, calibration factor applied. */
    float getEC() const;

    /** Returns latest DS18B20 reading in °C (returns -127 if not ready). */
    float getTemperatureC() const;

    /**
     * Returns true when the float switch indicates sufficient water level.
     * Switch is active-LOW (NC type): LOW pin = water present.
     */
    bool isWaterLevelOk() const;

    /**
     * Set a fixed offset added to raw pH readings after conversion.
     * Positive offset raises reported pH.
     */
    void calibratePH(float offset);

    /**
     * Set a multiplicative factor for EC conversion.
     * ec_mS_cm = voltage * factor
     */
    void calibrateEC(float factor);

    /** Raw ADC counts (0–4095), averaged, for diagnostics. */
    float getRawPH() const;
    float getRawEC() const;

private:
    int _ph_pin;
    int _ec_pin;
    int _float_switch_pin;

    OneWire       _one_wire;
    DallasTemperature _dallas;

    // ADC moving-average buffers
    float _ph_buf[SENSOR_ADC_SAMPLES];
    float _ec_buf[SENSOR_ADC_SAMPLES];
    int   _buf_idx;
    int   _buf_count;

    float _ph_offset;    // calibration offset (pH units)
    float _ec_factor;    // calibration factor  (mS/cm per V)

    float _temperature_c;
    bool  _temp_converting;
    uint32_t _temp_request_ms;

    void _advance_buffer(float ph_raw, float ec_raw);
    float _buffer_average(const float* buf, int count) const;
};

#endif // SENSORS_H
