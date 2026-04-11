# AIdroponics V0.1 — Calibration Guide

Perform calibrations in this order after initial assembly and whenever
accuracy degrades.

---

## 1. pH Probe Calibration

### Required: pH 4.0 and pH 7.0 buffer solutions

The ESP32 firmware uses a two-point linear map:
```
pH = 7.0 + (2.5 - voltage) × slope
```
Default slope = 3.5 (approximately correct for most electrodes at 25 °C).

1. Rinse probe with distilled water.
2. Immerse in pH 7.0 buffer. Wait 2 minutes.
3. Read the raw ADC voltage from the dashboard Sensors page (or ROS topic
   `/probe/reading` → raw voltage field). Record as `v7`.
4. Immerse in pH 4.0 buffer. Wait 2 minutes.
5. Record ADC voltage as `v4`.
6. Compute calibrated slope:
   ```
   slope = (7.0 - 4.0) / (v4 - v7)
   ```
7. Update `esp32_firmware/src/sensors.cpp`:
   ```cpp
   static constexpr float PH_SLOPE      = <new_slope>;
   static constexpr float PH_MIDPOINT_V = <v7>;
   ```
   Rebuild and flash via PlatformIO.

### Verification

Immerse in pH 6.5 buffer; dashboard Sensors page should read 6.4–6.6.

### pH Target (per plant profile)

Default targets are defined in `hydroponics_bringup/config/plant_library.yaml`.
Basil ideal range: 5.5–6.5. The dosing node uses the midpoint as its target.

---

## 2. EC (Electrical Conductivity) Calibration

### Required: 1.413 mS/cm calibration solution

1. Rinse EC probe with distilled water.
2. Immerse in 1.413 mS/cm standard.
3. Read the raw ADC voltage from the dashboard or `/probe/reading`. Record as `v_cal`.
4. Compute factor:
   ```
   ec_factor = 1.413 / v_cal
   ```
5. Update `esp32_firmware/src/sensors.cpp`:
   ```cpp
   static constexpr float EC_FACTOR = <ec_factor>;
   ```
6. Rebuild and flash.

### Verification

Immerse in 2.76 mS/cm standard; dashboard should read 2.7–2.8 mS/cm.

---

## 3. Temperature Sensor Calibration

The DS18B20 is factory-calibrated to ±0.5 °C. No firmware adjustment is
normally needed.

To verify: immerse in ice water (0 °C) — reading should be −0.5 to +0.5 °C.

If offset correction is needed, add to `esp32_firmware/src/sensors.cpp`:
```cpp
static constexpr float TEMP_OFFSET_C = <offset>;
```

---

## 4. AprilTag / Vision Scale Calibration

The vision node uses an AprilTag placed in the grow container to convert pixel
measurements to real-world centimetres.

### Required: AprilTag (36h11 family, 50 mm × 50 mm printed at known size)

1. Print the AprilTag from `docs/apriltag_50mm.pdf` at exactly 50 mm side length.
   Laminate it; mount it flat on the reservoir wall or grow tray edge.
2. Confirm tag size in `hydroponics_bringup/config/v01_system.yaml`:
   ```yaml
   vision:
     apriltag_size_mm: 50.0
   ```
3. Trigger a vision capture from the dashboard Controls page (requires auth).
4. Check the `PlantMeasurement` topic or Inspection page — `canopy_area_cm2`
   should be reasonable for the plant size.

### ROI Calibration

If the camera has been moved, verify `roi_*` parameters in `v01_system.yaml`
match the actual grow area visible in the frame. The ROI is used for HSV
segmentation before NDVI calculation.

---

## 5. Water Level Sensor Calibration

### Required: ruler or measuring tape

The water level node maps ultrasonic sensor distance readings to a percentage.
Two reference points are required: empty (0%) and full (100%).

1. Fill the reservoir to the marked "full" line. Trigger a water level reading:
   ```bash
   ros2 topic echo /water/level --once
   ```
   Note the raw `distance_cm` value. Record as `dist_full`.
2. Empty the reservoir to the minimum safe level. Repeat. Record as `dist_empty`.
3. Update `hydroponics_bringup/config/v01_system.yaml`:
   ```yaml
   water:
     sensor_distance_empty_cm: <dist_empty>
     sensor_distance_full_cm: <dist_full>
   ```

### Top-off Threshold

`topoff_threshold_percent` (default 60%) is when the pump activates.
`topoff_target_percent` (default 90%) is the fill target.
Both are in `v01_system.yaml`.

---

## 6. Dosing Chemistry Verification

The dosing node uses explicit math rather than PID. After initial setup, verify
the dose calculations are producing correct corrections.

### Procedure

1. Mix a fresh reservoir at known volume (e.g. 10 L at pH 7.5, EC 0.5 mS/cm).
2. Trigger a probe cycle from the dashboard.
3. The dosing node should automatically correct pH down and EC up.
4. After the correction cycle completes (~5–10 min for mixing), trigger another
   probe cycle and check that pH and EC are within target range.

### Tuning Dose Amounts

If corrections overshoot, reduce `dose_ml_per_unit_error` in `v01_system.yaml`:
```yaml
dosing:
  ph_dose_ml_per_unit:  1.2   # reduce if overshooting pH
  ec_dose_ml_per_unit:  2.0   # reduce if overshooting EC
  max_dose_ml:          10.0  # hard cap per single dose
  min_dose_interval_s:  300   # minimum gap between doses on same pump
```

---

## 7. NDVI Baseline Calibration

NDVI readings vary with lighting conditions and camera exposure. Establish a
baseline on a known-healthy plant.

1. With a healthy plant (or a green reference card) in the container, trigger
   a vision capture.
2. Note the `mean_ndvi` from the Inspection page or `/ndvi/reading` topic.
   A healthy basil plant in good lighting should read ≥ 0.35.
3. If readings are consistently low (< 0.2) despite healthy plants, check:
   - Blue gel is properly seated on the NoIR camera lens
   - Both CSI cameras are focused correctly
   - Lighting is on during capture (the light controller should auto-enable)
4. NDVI thresholds per plant are defined in `plant_library.yaml`:
   ```yaml
   ndvi:
     healthy_min: 0.3
     warning_threshold: 0.2
     critical_threshold: 0.1
   ```

---

## Calibration Record

Keep a log of calibration dates and values:

| Date | Component | Old Value | New Value | Notes |
|---|---|---|---|---|
| — | pH slope | 3.5 | — | Factory default |
| — | EC factor | 0.6 | — | Factory default |
| — | AprilTag size | 50 mm | — | Factory default |
| — | Water level full | — | — | Site-specific |
| — | Water level empty | — | — | Site-specific |
