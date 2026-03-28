# Claudroponics — Calibration Guide

Perform calibrations in this order after initial assembly and whenever
accuracy degrades.

---

## 1. Stepper Motor Calibration (steps/mm)

### Required: ruler or digital calipers

1. Open `hydroponics_transport/config/transport_params.yaml`.
2. Note current `steps_per_mm` (default 80.0 for 2 mm pitch belt, 20-tooth
   pulley, 16 microsteps).
3. Move the carriage to the home position (limit switch).
4. Command a 100 mm move:
   ```bash
   ros2 action send_goal /transport/move hydroponics_msgs/action/MoveToPosition \
     '{target_position_mm: 100.0, speed_mm_s: 20.0}'
   ```
5. Measure actual travel with calipers. If actual = A mm:
   ```
   new_steps_per_mm = current_steps_per_mm × 100 / A
   ```
6. Update `transport_params.yaml`, rebuild, and repeat until error < 0.5 mm.

### Z-axis (same procedure)

Use `work_station_controller/config/work_station_params.yaml` and the
`/work_station/move` action.

---

## 2. pH Probe Calibration

### Required: pH 4.0 and pH 7.0 buffer solutions

The firmware uses a two-point linear map:
```
pH = 7.0 + (2.5 - voltage) × slope
```
Default slope = 3.5 (approximately correct for most electrodes at 25 °C).

1. Rinse probe with distilled water.
2. Immerse in pH 7.0 buffer. Wait 2 minutes.
3. Read the raw ADC voltage from the dashboard sensor gauges (or ROS topic
   `/sensors/raw`). Record as `v7`.
4. Immerse in pH 4.0 buffer. Wait 2 minutes.
5. Record ADC voltage as `v4`.
6. Compute calibrated slope:
   ```
   slope = (7.0 - 4.0) / (v4 - v7)
   ```
7. Update `micro_ros_app.cpp`:
   ```cpp
   static constexpr float PH_SLOPE = <new_slope>;
   static constexpr float PH_MIDPOINT_V = <v7>;
   ```
   Rebuild and flash.

### Verification

Immerse in pH 6.5 buffer; dashboard should read 6.4–6.6.

---

## 3. EC (Electrical Conductivity) Calibration

### Required: 1.413 mS/cm calibration solution (EC standard)

1. Rinse EC probe with distilled water.
2. Immerse in 1.413 mS/cm standard.
3. Read the raw ADC voltage from `/sensors/raw`. Record as `v_cal`.
4. Compute factor:
   ```
   ec_factor = 1.413 / v_cal
   ```
5. Update `micro_ros_app.cpp`:
   ```cpp
   static constexpr float EC_FACTOR = <ec_factor>;
   ```
6. Rebuild and flash.

### Verification

Immerse in 2.76 mS/cm standard; dashboard should read 2.7–2.8.

---

## 4. Load Cell / Harvest Weight Calibration

### Required: known-weight object (e.g., 200 g calibration weight)

1. Mount the harvest basket (empty) and tare:
   ```bash
   ros2 service call /harvest/tare std_srvs/srv/Trigger '{}'
   ```
2. Place the calibration weight in the basket.
3. Read the raw HX711 count from logs or the dashboard.
4. Update `load_cell.cpp`:
   ```cpp
   static constexpr float SCALE_FACTOR = <raw_count> / 200.0f;  // grams
   ```
5. Rebuild and flash.
6. Verify: place known 100 g weight; reading should be 95–105 g.

---

## 5. Camera Position Calibration

### Required: a checkerboard or ruler placed in the grow channel

1. Set the carriage to the INSPECT position.
2. Capture a frame from the overhead camera:
   ```bash
   ros2 run image_view image_view --ros-args -r /image:=/camera/overhead/image_raw
   ```
3. Measure a known physical distance (e.g., 10 cm) in pixel units using an
   image editor.
4. Compute `pixels_per_cm`:
   ```
   pixels_per_cm = pixel_distance / real_distance_cm
   ```
5. Update `vision_params.yaml`:
   ```yaml
   pixels_per_cm: <value>
   ```

### ROI (Region of Interest) Calibration

Verify that the `roi_*` parameters in `vision_params.yaml` match the actual
grow channel boundaries in the camera frame. Adjust if the camera has been
repositioned.

---

## 6. PID Tuning (pH and EC Controllers)

Default gains in `hydroponics_nutrients/config/pid_params.yaml`:

| Parameter | pH | EC |
|---|---|---|
| `kp` | 0.8 | 0.6 |
| `ki` | 0.05 | 0.03 |
| `kd` | 0.1 | 0.05 |

### Ziegler–Nichols Quick-Tune Procedure

1. Set `ki = 0`, `kd = 0`.
2. Increase `kp` until the output oscillates with period T_u and amplitude A_u.
3. Apply:
   ```
   kp = 0.6 × kp_critical
   ki = 2 × kp / T_u
   kd = kp × T_u / 8
   ```
4. Enable anti-windup (`integral_limit` parameter) to prevent integrator
   saturation during large step changes (e.g., fresh reservoir).

### Normal Operating Ranges

| Sensor | Target | Deadband | Dose trigger |
|---|---|---|---|
| pH | 6.0–6.5 | ±0.1 | outside target ± deadband |
| EC | 1.5–2.5 mS/cm | ±0.1 | outside target ± deadband |
| Temp | 18–24 °C | — | alert only |

---

## 7. Harvest Servo / Cutter Calibration

1. Command the servo to the home angle (0°):
   ```bash
   ros2 topic pub /work_station/servo_angle std_msgs/msg/Float32 '{data: 0.0}'
   ```
2. Verify the cutter blade is retracted (safe position).
3. Command to the cut angle (defined in `work_station_params.yaml`):
   ```bash
   ros2 topic pub /work_station/servo_angle std_msgs/msg/Float32 '{data: 90.0}'
   ```
4. Confirm a clean cut motion. Adjust `cut_angle_deg` in the config if needed.
5. Set `home_angle_deg` and `cut_angle_deg` in `work_station_params.yaml`.

---

## Calibration Record

Keep a log of calibration dates and values:

| Date | Component | Old Value | New Value | Notes |
|---|---|---|---|---|
| — | pH slope | 3.5 | — | Factory default |
| — | EC factor | 0.6 | — | Factory default |
| — | Load cell scale | 500.0 | — | Factory default |
