# AIdroponics — Scaling Guide

V0.1 is a **single-plant validation platform** — one DWC container, one probe,
dual cameras, four peristaltic pumps, one water level sensor. This guide covers
what is needed to grow the platform beyond V0.1.

---

## V0.1 Baseline

| Dimension | V0.1 |
|---|---|
| Plants | 1 |
| DWC containers | 1 |
| Cameras | 2 (RGB IMX477 + NoIR V2) |
| Pumps | 4 (pH Up, pH Down, Nutrient A, Nutrient B) |
| Probe servo | 1 |
| Aeration servo | 1 |
| Water level sensors | 1 |
| Compute | Raspberry Pi CM4 |
| ESP32 boards | 1 |

---

## Scaling to Multiple Plants (V0.2+)

### Same container, more plants

V0.1 uses a single grow site. To add more plants in the same container:

- Vision: the current pipeline measures the entire plant ROI. For multi-plant
  discrimination, add AprilTag fiducials per site and segment per-plant regions
  in `plant_vision_node.py`.
- Dosing: shared reservoir — no changes needed. All plants share the same
  pH/EC target (choose a compatible species mix or grow the same species).
- Dashboard: `PlantMeasurement` will need a `plant_index` field added to the
  message type.

### Multiple independent containers

1. **Namespacing**: all V0.1 nodes are in the root namespace. For multi-container,
   launch each set under a namespace:
   ```python
   # multi_plant.launch.py
   for i in range(num_containers):
       nodes += [
           Node(package='hydroponics_probe',
                executable='probe_arm_node',
                namespace=f'container_{i}',
                parameters=[...]),
           # ... other nodes
       ]
   ```
2. **ESP32**: one ESP32 per container. Set `CONTAINER_ID` in firmware before
   flashing; this namespaces micro-ROS topics automatically.
3. **Cameras**: one CSI pair per container (requires CM4 with dual CSI or a
   USB3 camera for the second container). The V0.1 vision node already supports
   camera index parameters in `v01_system.yaml`.
4. **Dashboard**: the React frontend currently shows a single plant. A future
   `ChannelOverview`-style component would aggregate per-container status.

---

## Multi-Computer Deployment (ROS2 DDS)

For deployments where one CM4 cannot handle all containers:

1. All machines must be on the **same LAN** (or use a DDS router).
2. Set the same `ROS_DOMAIN_ID` on all machines:
   ```bash
   export ROS_DOMAIN_ID=42
   ```
3. Run the dashboard server on one machine; all others connect to it over DDS.
4. For WAN deployments, use **Zenoh** or **Fast-DDS Discovery Server** to avoid
   multicast issues across subnets.

---

## Redundant Sensing

For higher-reliability deployments:

1. Wire a second pH/EC probe to a second ESP32 on a separate USB port.
2. In `dosing_node.py`, subscribe to both `/probe/reading` and
   `/probe/reading_secondary`.
3. Use the median of both readings; alert if they diverge by > 0.3 pH or
   0.2 mS/cm.
4. This prevents false dosing from a fouled or drifted probe.

---

## Crop Diversification

To grow different herbs simultaneously (in separate containers):

Each container's dosing node is launched with its own `plant_profile` parameter:
```bash
ros2 launch hydroponics_bringup multi_container.launch.py \
  container_0_profile:=basil \
  container_1_profile:=mint
```

Plant profiles (pH/EC targets, NDVI thresholds, A:B ratio) are defined in
`hydroponics_bringup/config/plant_library.yaml`.

---

## Reservoir Volume Scaling

The dosing node's explicit-chemistry math scales automatically with reservoir
volume (it takes `reservoir_volume_L` as a parameter). For larger reservoirs,
also increase `min_dose_interval_s` to allow adequate mixing time:

| Reservoir | `reservoir_volume_L` | `min_dose_interval_s` |
|---|---|---|
| 5 L (reference) | 5.0 | 180 |
| 15 L | 15.0 | 300 |
| 30 L | 30.0 | 480 |

Update in `hydroponics_bringup/config/v01_system.yaml`.

---

## MQTT Scaling

The default HiveMQ Cloud free tier supports:
- 10 concurrent connections
- 10 GB/month data transfer

For > 4 containers, switch to HiveMQ Cloud Professional or self-host Mosquitto:

```yaml
# mqtt_config.yaml
broker_host: "mosquitto.local"
broker_port: 1883
use_tls: false
```

---

## Storage Scaling

SQLite works well for a single plant / a few years of data. For larger
deployments:

1. Switch `data_pipeline.py` to **PostgreSQL** (change `sqlite3` to `psycopg2`;
   schema is compatible).
2. Add Grafana pointing at PostgreSQL for time-series visualisation at scale.

---

## Hardware BOM per Additional Container (V0.2+)

| Component | Qty | Approx. Cost (USD) |
|---|---|---|
| ESP32-S3 DevKit-C | 1 | $8 |
| IRF520 MOSFET + 1N4007 | 4 sets | $4 |
| 12 V peristaltic pump | 4 | $40 |
| Probe servo (SG90 or MG90S) | 1 | $6 |
| Aeration servo | 1 | $6 |
| pH electrode + BNC | 1 | $20 |
| EC probe | 1 | $15 |
| DS18B20 waterproof | 1 | $5 |
| Ultrasonic water level (JSN-SR04T) | 1 | $8 |
| Raspberry Pi Camera v2 NoIR + blue gel | 1 | $28 |
| IMX477 camera (RGB) | 1 | $50 |
| LED grow strip (12 V) | 1 m | $12 |
| DWC container (5–15 L) | 1 | $15 |
| Power supply 12 V 5 A | 1 | $18 |
| **Total per additional container** | | **~$235** |
