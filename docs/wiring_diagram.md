# Claudroponics — Wiring Diagram & Pin Reference

## ESP32 Pin Assignments

```
ESP32-S3 DevKit-C (38-pin)
───────────────────────────

STEPPER MOTORS (TMC2209 via UART)
  GPIO 17  →  UART TX → TMC2209 PDN_UART (all drivers share bus, unique addresses)
  GPIO 16  →  UART RX ← TMC2209 PDN_UART
  GPIO 4   →  X-AXIS STEP
  GPIO 5   →  X-AXIS DIR
  GPIO 6   →  X-AXIS ENABLE (active LOW)
  GPIO 7   →  Z-AXIS STEP
  GPIO 8   →  Z-AXIS DIR
  GPIO 9   →  Z-AXIS ENABLE (active LOW)

SERVO (FUTABA S3003 or equivalent)
  GPIO 21  →  SERVO PWM (50 Hz, 1000–2000 µs)
             (servo power: 5 V rail, NOT 3.3 V)

PUMP MOSFETs (IRF520 or IRLZ44N, logic-level)
  GPIO 22  →  pH Up pump gate
  GPIO 23  →  pH Down pump gate
  GPIO 25  →  Nutrient A pump gate
  GPIO 26  →  Nutrient B pump gate
             (drain → pump motor, source → GND, flyback diode across motor)

SENSORS
  GPIO 34  →  pH probe analog (ADC1_CH6, 0–3.3 V after voltage divider)
  GPIO 35  →  EC probe analog  (ADC1_CH7)
  GPIO 18  →  DS18B20 temperature (1-Wire + 4.7 kΩ pull-up to 3.3 V)

LOAD CELL (HX711 module)
  GPIO 32  →  HX711 DOUT (data)
  GPIO 33  →  HX711 SCK  (clock)
             (HX711 powered from 3.3 V)

LIGHTING
  GPIO 12  →  Grow panel PWM (LEDC CH0, 5 kHz, 8-bit → MOSFET gate)
  GPIO 13  →  Inspection LEDs (GPIO on/off → relay or MOSFET)

MICRO-ROS
  USB      →  micro-ROS serial transport (115200 baud, via USB CDC)
             (no extra wiring needed on ESP32-S3 DevKit)
```

## Full Wiring Schematic (Text)

```
12 V DC Supply
├── Buck converter (5 V/3 A)  ──→ ESP32 5 V rail, servo, HX711
├── Buck converter (3.3 V/1 A) ──→ ESP32 3.3 V rail, DS18B20, TMC2209 logic
└── 12 V rail                 ──→ TMC2209 VM, pump motors, grow light driver

TMC2209 Wiring (×2, one per axis)
  VM       → 12 V
  GND      → GND
  VIO      → 3.3 V
  PDN_UART → 1 kΩ → ESP32 TX17; also → 10 kΩ pull-up → 3.3 V
  STEP     → ESP32 GPIO 4 (X) or 7 (Z)
  DIR      → ESP32 GPIO 5 (X) or 8 (Z)
  EN       → ESP32 GPIO 6 (X) or 9 (Z)   [LOW = enabled]
  M0, M1   → GND (256 microstep via UART)
  OA1/OA2  → Stepper coil A
  OB1/OB2  → Stepper coil B

pH / EC Analog Front-End
  pH probe    → BNC connector → op-amp buffer (TL071) → voltage divider
                → ESP32 GPIO 34 (range 0–3.3 V maps to pH 4–10)
  EC probe    → signal generator / bridge circuit → rectifier → LPF
                → ESP32 GPIO 35 (0–3.3 V maps to 0–4 mS/cm)
  Both inputs need 100 nF decoupling cap to GND at ESP32 pin.

Pump MOSFET Circuit (×4, identical)
  Gate    ← 10 kΩ ← ESP32 GPIO
  Gate    ← 10 kΩ pull-down to GND   (keeps FET off during ESP32 boot)
  Drain   → pump motor (+)
  Source  → GND
  1N4007 diode: cathode → Drain, anode → Source  (flyback protection)
  Pump motor (−) → 12 V

Grow Light PWM Driver
  ESP32 GPIO 12 → gate of IRLZ44N
  Drain → grow LED strip (−)
  Source → GND
  LED strip (+) → 12 V (or 24 V, match strip rating)
```

## Raspberry Pi 5 Connections

```
RPi 5
├── USB-A  → ESP32 USB-C (micro-ROS serial)
├── CSI-2  → Camera 1 (overhead, Raspberry Pi Camera Module 3)
├── USB-A  → Camera 2 (30° side, USB UVC webcam or second RPi cam via USB HAT)
├── Ethernet → LAN / router (for dashboard access + HiveMQ cloud)
└── USB-C  → Power (5 V / 5 A recommended for RPi 5)
```

## Safety Notes

1. **Ground the 12 V supply chassis** to ESP32 GND. A floating ground causes
   erratic ADC readings on the pH and EC probes.

2. **Do not connect pump motor power** to the same regulator output as the
   ESP32 logic. Motors cause voltage spikes that reset the MCU.

3. **pH probe calibration** should be done with the probe immersed in buffer
   solution with the pump circuits powered (motors running causes EM
   interference that shifts readings by ±0.1 pH if not accounted for).

4. **Load cell zeroing**: Always tare the load cell with the harvest basket
   empty and mounted before starting a grow cycle.

5. **TMC2209 current limit**: Set `RMS_CURRENT` in firmware to ≤ 70% of the
   stepper motor's rated current. Overdriving causes overheating on long moves.
