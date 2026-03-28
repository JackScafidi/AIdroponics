# Claudroponics — Scaling Guide

This guide covers how to expand from the single-channel reference design to
larger deployments.

---

## Scaling Axes

| Dimension | Reference | Small Farm | Commercial |
|---|---|---|---|
| Grow channels | 1 | 4 | 16+ |
| Plants per channel | 4 | 4 | 4 |
| Rails | 1 | 1 per channel | 1 per 2–4 channels |
| ROS2 computers | 1 (RPi 5) | 1 (RPi 5 or x86) | 1 per 4 channels |
| ESP32 boards | 1 | 1 per channel | 1 per channel |
| MQTT brokers | HiveMQ Cloud | HiveMQ Cloud | Self-hosted Mosquitto |

---

## Adding a Second Channel (Most Common Case)

### 1. Hardware

- Duplicate the ESP32 + stepper + pump rack for the new channel.
- A single Raspberry Pi 5 can run 2–4 channels.

### 2. Namespacing in ROS2

All nodes accept a `channel` launch argument. Topics are namespaced:
`/channel_0/nutrients/status`, `/channel_1/nutrients/status`, etc.

Edit the bringup launch file:

```python
# full_system.launch.py — add second channel
for ch in range(num_channels):
    nodes += [
        Node(package='hydroponics_nutrients',
             executable='nutrient_controller',
             namespace=f'channel_{ch}',
             parameters=[...]),
        # ... other nodes
    ]
```

### 3. ESP32 Firmware

Each ESP32 publishes to a channel-specific topic. Change `CHANNEL_ID` in
`micro_ros_app.h` before flashing:

```cpp
static constexpr int CHANNEL_ID = 1;  // 0 for first, 1 for second, etc.
```

### 4. Database

The `growth_data` table already has a `channel_id` column. The data pipeline
node accepts a `channel_id` parameter.

### 5. Dashboard

The React frontend's `ChannelOverview` component renders all channels returned
by `/api/channels`. No code changes needed — the backend auto-discovers active
channels from the database.

---

## Multi-Computer Deployment (ROS2 DDS)

For large farms where one RPi cannot handle all channels:

1. All machines must be on the **same LAN** (or use a DDS router).
2. Set the same `ROS_DOMAIN_ID` on all machines:
   ```bash
   export ROS_DOMAIN_ID=42
   ```
3. Run the dashboard server on one machine; all others connect to it.
4. For WAN deployments, use **Zenoh** or **Fast-DDS Discovery Server** to
   avoid multicast issues across subnets.

---

## Redundant Sensing

For commercial deployments, add a second pH/EC meter as a cross-check:

1. Wire second sensors to a second ESP32 on a separate USB port.
2. In `nutrient_controller.py`, subscribe to both `/channel_0/sensors/raw`
   and `/channel_0/sensors/secondary_raw`.
3. Use the median of both readings; alert if they diverge by > 0.3 pH or
   0.2 mS/cm.

---

## Crop Diversification (Multiple Plant Profiles Simultaneously)

To grow different herbs in different channels simultaneously:

1. Each channel's `nutrient_controller` is launched with its own
   `plant_profile` parameter:
   ```bash
   ros2 launch hydroponics_bringup full_system.launch.py \
     channel_0_profile:=basil \
     channel_1_profile:=mint
   ```
2. The BT manager for each channel reads its own profile from
   `/api/plant_profiles/{profile}`.

---

## Water Volume Scaling

Larger reservoirs require adjusting PID gains and dose amounts:

| Reservoir Volume | Recommended Dose (per correction) | PID `ki` multiplier |
|---|---|---|
| 10 L (reference) | pH: 1 mL, EC: 2 mL | 1.0 |
| 30 L | pH: 3 mL, EC: 6 mL | 0.4 |
| 100 L | pH: 8 mL, EC: 20 mL | 0.15 |

Update `dose_ml_per_correction` in `pid_params.yaml`. The PID integrator
is normalised per-milliliter so changing `ki` proportionally is correct.

---

## MQTT Scaling

The default HiveMQ Cloud free tier supports:

- 10 concurrent connections
- 10 GB/month data transfer

For > 4 channels, switch to HiveMQ Cloud Professional or self-host Mosquitto:

```yaml
# mqtt_config.yaml
broker_host: "mosquitto.local"
broker_port: 1883
use_tls: false
```

For self-hosted Mosquitto with TLS, generate certs with:
```bash
openssl req -x509 -newkey rsa:4096 -keyout ca.key -out ca.crt -days 3650
```

---

## Storage Scaling

SQLite works well up to ~5 channels / 2 years of data. Beyond that:

1. Switch `data_pipeline.py` to **PostgreSQL** (change `sqlite3` import to
   `psycopg2`; schema is compatible).
2. Add a Grafana dashboard pointing at PostgreSQL for time-series visualisation
   at scale (the built-in React dashboard is designed for single-operator use).

---

## Hardware BOM per Additional Channel

| Component | Qty | Approx. Cost (USD) |
|---|---|---|
| ESP32-S3 DevKit-C | 1 | $8 |
| TMC2209 stepper driver | 2 | $8 |
| NEMA 17 stepper (rail + Z) | 2 | $24 |
| IRF520 MOSFET + 1N4007 | 4 sets | $4 |
| 12 V peristaltic pump | 4 | $40 |
| pH electrode + BNC | 1 | $20 |
| EC probe | 1 | $15 |
| DS18B20 waterproof | 1 | $5 |
| HX711 + load cell 1 kg | 1 set | $8 |
| LED grow strip (12 V) | 1 m | $12 |
| DWC net pot channel (PVC) | 1 | $30 |
| 10 L reservoir | 1 | $10 |
| Linear rail + belt | 1.5 m | $25 |
| Power supply 12 V 5 A | 1 | $18 |
| **Total per channel** | | **~$227** |
