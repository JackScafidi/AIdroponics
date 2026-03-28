# ESP32 Firmware — Claudroponics

Firmware for the ESP32 DevKit V1 that handles all real-time hardware I/O via
micro-ROS over USB serial. The Raspberry Pi 5 running ROS2 communicates with
this firmware through the micro-ROS agent.

---

## Flashing

```bash
# Install PlatformIO CLI (if not already installed)
pip install platformio

# From esp32_firmware/ directory
pio run -t upload
```

On first flash, PlatformIO will download the ESP32 toolchain and micro-ROS
Arduino library automatically. This takes a few minutes.

---

## Starting the micro-ROS Agent (on Raspberry Pi)

```bash
# Install once
sudo apt install ros-humble-micro-ros-agent

# Run the agent (ESP32 connected via USB)
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200
```

The ESP32 will attempt to connect automatically on startup. LED on GPIO2 will
blink during connection and stay on once micro-ROS is established.

---

## Pin Wiring Table

| Function             | ESP32 GPIO | Notes                                     |
|----------------------|------------|-------------------------------------------|
| Rail STEP            | 26         | TMC2209 STEP pin                          |
| Rail DIR             | 27         | TMC2209 DIR pin                           |
| Rail EN              | 14         | TMC2209 EN pin (LOW = enabled)            |
| Z-axis STEP          | 25         | TMC2209 STEP pin                          |
| Z-axis DIR           | 33         | TMC2209 DIR pin                           |
| Z-axis EN            | 32         | TMC2209 EN pin                            |
| Turret servo (MG996R)| 12         | PWM signal (50 Hz)                        |
| Cutter servo (SG90)  | 13         | PWM signal                                |
| Gripper servo (SG90) | 15         | PWM signal                                |
| pH-up pump MOSFET    | 16         | Gate of N-channel MOSFET                  |
| pH-down pump MOSFET  | 17         | Gate of N-channel MOSFET                  |
| Nutrient-A pump      | 18         | Gate of N-channel MOSFET                  |
| Nutrient-B pump      | 19         | Gate of N-channel MOSFET                  |
| pH probe ADC         | 34 (ADC)   | Gravity analog pH — 0–3.3 V (input only)  |
| EC probe ADC         | 35 (ADC)   | Gravity analog EC — 0–3.3 V (input only)  |
| DS18B20 OneWire      | 4          | 4.7 kΩ pull-up to 3.3 V                   |
| Float switch         | 5          | NC type, pull-up; LOW = water present     |
| HX711 DOUT           | 21         |                                           |
| HX711 SCK            | 22         |                                           |
| Grow LED PWM         | 23         | LEDC channel 0, 5 kHz                     |
| Inspection LED       | 2          | On-board LED (also drives MOSFET via buffer) |
| Rail limit switch    | 36 (VP)    | NC, pull-up; LOW = at home end            |
| Z-axis limit switch  | 39 (VN)    | NC, pull-up; LOW = at home end            |

**Power notes:**
- ESP32: 5 V via USB or dedicated 5 V regulator
- Stepper motors, pumps, grow LED: 12 V rail; keep ESP32 3.3 V logic isolated
- Use logic-level N-channel MOSFETs (e.g. IRLZ44N) for all 12 V switching
- TMC2209 UART not used in this firmware (StallGuard optional future feature)

---

## Calibration Procedures

### pH Probe (2-point calibration)

1. Rinse probe in distilled water.
2. Submerge in pH 7.0 buffer. Note the raw ADC value when stable.
3. Submerge in pH 4.0 buffer. Note the raw ADC value when stable.
4. The conversion formula `pH = 7.0 + (2.5 - voltage) * 3.5` is pre-set;
   use `g_sensors.calibratePH(offset)` if the midpoint drifts.
5. Typical offset: ±0.3 pH units.

### EC Probe

1. Prepare 1413 µS/cm (= 1.413 mS/cm) EC standard solution.
2. Submerge probe. Read `g_sensors.getEC()` via serial monitor.
3. Calculate factor: `new_factor = 1.413 / reported_value * current_factor`
4. Update: `g_sensors.calibrateEC(new_factor)`

### Stepper Steps/mm

1. Mark the rail carriage position with tape.
2. Send command `{"axis":"rail","target_mm":100.0}` via MQTT.
3. Measure actual distance moved with calipers.
4. Update `STEPPER_DEFAULT_STEPS_PER_MM` in `stepper.h`:
   `new_steps_mm = current_steps_mm * (100.0 / actual_mm)`

### Load Cell

1. Place collection tray (empty) under the cutter.
2. Call `g_load_cell.tare()` via serial command or power-cycle to auto-tare.
3. Place a known weight (e.g., 100 g calibration mass).
4. Calculate: `factor = known_g / raw_reading`
5. Update: `g_load_cell.setCalibrationFactor(factor)`

### Pump Flow Rate

1. Fill a syringe to a known volume (e.g., 10 mL).
2. Connect syringe outlet to the pump inlet.
3. Run pump for 10 seconds: `g_pumps.dose(pump_id, 10000)`
4. Measure dispensed volume.
5. Update: `g_pumps.calibrate(pump_id, dispensed_mL / 10.0)`
   Typical peristaltic pump: 0.5–2.0 mL/s.

---

## Published MQTT/ROS2 Topics

| Topic                          | Type              | Content                        |
|--------------------------------|-------------------|--------------------------------|
| `/hydroponics/esp32/sensors`   | std_msgs/String   | JSON: pH, EC, temp, etc.       |

## Subscribed Topics

| Topic                            | Type              | JSON fields                     |
|----------------------------------|-------------------|---------------------------------|
| `/hydroponics/esp32/pump_cmd`    | std_msgs/String   | `{pump_id, duration_ms}` or `{pump_id, amount_ml}` |
| `/hydroponics/esp32/light_cmd`   | std_msgs/String   | `{grow_intensity}` or `{inspection_on}` |
| `/hydroponics/esp32/stepper_cmd` | std_msgs/String   | `{axis, target_mm}`             |
