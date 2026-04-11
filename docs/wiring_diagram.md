# AIdroponics V0.1 — Wiring Diagram & Pin Reference

## ESP32 Pin Assignments

```
ESP32-S3 DevKit-C (38-pin)
───────────────────────────

PUMP MOSFETs (IRF520 or IRLZ44N, logic-level)
  GPIO 22  →  pH Up pump gate
  GPIO 23  →  pH Down pump gate
  GPIO 25  →  Nutrient A pump gate
  GPIO 26  →  Nutrient B pump gate
             (drain → pump motor, source → GND, flyback diode across motor)

SERVO MOTORS
  GPIO 21  →  Probe arm servo PWM (50 Hz, 1000–2000 µs)
  GPIO 19  →  Aeration servo PWM  (50 Hz, 1000–2000 µs)
             (servo power: 5 V rail, NOT 3.3 V)

SENSORS
  GPIO 34  →  pH probe analog (ADC1_CH6, 0–3.3 V after voltage divider)
  GPIO 35  →  EC probe analog  (ADC1_CH7)
  GPIO 18  →  DS18B20 temperature (1-Wire + 4.7 kΩ pull-up to 3.3 V)
  GPIO 27  →  JSN-SR04T trigger (ultrasonic water level)
  GPIO 14  →  JSN-SR04T echo   (ultrasonic water level)

WATER TOP-OFF PUMP
  GPIO 15  →  Top-off pump MOSFET gate (same circuit as nutrient pumps)

LIGHTING
  GPIO 12  →  Grow panel PWM (LEDC CH0, 5 kHz, 8-bit → MOSFET gate)

MICRO-ROS
  USB      →  micro-ROS serial transport (115200 baud, via USB CDC)
             (no extra wiring needed on ESP32-S3 DevKit)
```

## Full Wiring Schematic (Text)

```
12 V DC Supply
├── Buck converter (5 V / 3 A)  ──→ ESP32 5 V rail, servos
├── Buck converter (3.3 V / 1 A) ──→ ESP32 3.3 V rail, DS18B20, JSN-SR04T
└── 12 V rail                   ──→ pump motors, grow light driver, top-off pump

pH / EC Analog Front-End
  pH probe    → BNC connector → op-amp buffer (TL071) → voltage divider
                → ESP32 GPIO 34 (range 0–3.3 V maps to pH 4–10)
  EC probe    → signal generator / bridge circuit → rectifier → LPF
                → ESP32 GPIO 35 (0–3.3 V maps to 0–4 mS/cm)
  Both inputs need 100 nF decoupling cap to GND at ESP32 pin.

Pump MOSFET Circuit (×5: pH Up, pH Down, Nutrient A, Nutrient B, Top-off)
  Gate    ← 10 kΩ ← ESP32 GPIO
  Gate    ← 10 kΩ pull-down to GND   (keeps FET off during ESP32 boot)
  Drain   → pump motor (+)
  Source  → GND
  1N4007 diode: cathode → Drain, anode → Source  (flyback protection)
  Pump motor (−) → 12 V

Servo Circuit (×2: probe arm, aeration)
  Signal  ← ESP32 GPIO (3.3 V PWM — most servos accept this level)
  Power   → 5 V rail (NOT 3.3 V regulator; servos draw transient current spikes)
  GND     → common GND

JSN-SR04T Ultrasonic (waterproof water level sensor)
  Trigger → ESP32 GPIO 27 (10 µs pulse)
  Echo    ← ESP32 GPIO 14 (3.3 V — JSN-SR04T is 3.3 V compatible)
  VCC     → 3.3 V or 5 V (check module variant)
  GND     → GND

Grow Light PWM Driver
  ESP32 GPIO 12 → gate of IRLZ44N
  Drain → grow LED strip (−)
  Source → GND
  LED strip (+) → 12 V (or 24 V, match strip rating)
```

## Raspberry Pi CM4 Connections

```
Raspberry Pi CM4 (on Compute Module IO Board or custom carrier)
├── CSI-2 port 0  → IMX477 (Raspberry Pi HQ Camera, RGB) — overhead
├── CSI-2 port 1  → Raspberry Pi Camera V2 NoIR (+ Wratten 47B blue gel)
│                  mounted at same overhead position, co-aligned with port 0
├── USB-A         → ESP32 USB-C (micro-ROS serial transport)
├── Ethernet      → LAN / router (dashboard access + HiveMQ cloud)
└── USB-C power   → 5 V / 5 A
```

### Dual Camera Alignment

Both cameras must be mounted side-by-side or stacked at the same height
pointing directly down at the plant. They do not need to be pixel-perfect
aligned — the AprilTag calibration compensates for minor positional offsets.
The blue gel is taped directly over the V2 NoIR lens; this blocks the red
channel and makes the red channel of the captured image approximate NIR.

## LED Status Indicator

```
Raspberry Pi CM4 GPIO (via GPIO header or carrier board)
  GPIO_STATUS → 220 Ω → Green LED  → GND   (healthy / info)
  GPIO_WARN   → 220 Ω → Yellow LED → GND   (warning)
  GPIO_CRIT   → 220 Ω → Red LED   → GND   (critical / alert)
```

Update GPIO pin numbers in `hydroponics_bringup/config/v01_system.yaml`:
```yaml
led:
  gpio_green:  17
  gpio_yellow: 27
  gpio_red:    22
```

## Safety Notes

1. **Ground the 12 V supply chassis** to ESP32 GND. A floating ground causes
   erratic ADC readings on the pH and EC probes.

2. **Do not connect pump motor power** to the same regulator output as the
   ESP32 logic. Motors cause voltage spikes that reset the MCU.

3. **pH probe calibration** should be done with pump circuits powered (motors
   running causes EM interference that can shift readings by ±0.1 pH if not
   accounted for during calibration).

4. **Servo inrush**: if the 5 V rail sags when servos move, add a 470 µF
   electrolytic capacitor across the servo power pins. Voltage sag causes
   micro-ROS disconnects.

5. **JSN-SR04T mounting**: the sensor must point straight down at the water
   surface. Tilt > 15° causes erratic readings. Mount it centrally over the
   reservoir opening, away from the aeration diffuser.

6. **NoIR camera gel**: replace the blue gel if it becomes wet, faded, or
   creased — degraded gel reduces NDVI accuracy. Keep spares (Wratten 47B
   is the correct filter; 47 also works).
