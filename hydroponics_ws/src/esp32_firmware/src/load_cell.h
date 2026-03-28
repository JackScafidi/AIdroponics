#pragma once
/*
 * load_cell.h  –  HX711 load-cell interface for harvest weighing
 *
 * Wraps the HX711 library to provide a simple mL-to-grams interface
 * with tare support and a calibration factor.
 *
 * Typical usage:
 *   LoadCell lc(DOUT, SCK);
 *   lc.begin();
 *   lc.tare();                    // zero the scale
 *   float g = lc.getWeightGrams(); // read weight
 */

#ifndef LOAD_CELL_H
#define LOAD_CELL_H

#include "Arduino.h"
#include <HX711.h>

#define LOAD_CELL_DEFAULT_CALIBRATION 420.0f  // raw units per gram (tune at calibration)
#define LOAD_CELL_SAMPLES             5        // averages per reading

class LoadCell {
public:
    /**
     * @param dout_pin  HX711 DOUT pin
     * @param sck_pin   HX711 SCK pin
     */
    LoadCell(int dout_pin, int sck_pin);

    /**
     * Initialise the HX711 library.
     * Call once during setup(). Blocks ~500 ms to power-stabilise.
     */
    void begin();

    /**
     * Tare the scale — captures the current offset as the zero reference.
     * Call with the collection tray in place but empty.
     * Blocks for a short reading cycle.
     */
    void tare();

    /**
     * Returns the net weight in grams above the tared zero.
     * Returns 0.0 if the HX711 is not ready.
     */
    float getWeightGrams();

    /**
     * Returns true when a new reading is available (HX711 DATA low).
     */
    bool isReady() const;

    /**
     * Update the calibration factor.
     * factor = (known_weight_grams) / (raw_reading - tare_raw)
     * Measure with a known mass and call this once.
     */
    void setCalibrationFactor(float factor);

    /** Returns the currently stored calibration factor. */
    float getCalibrationFactor() const;

private:
    HX711 _hx711;
    int   _dout_pin;
    int   _sck_pin;
    float _calibration_factor;
};

#endif // LOAD_CELL_H
