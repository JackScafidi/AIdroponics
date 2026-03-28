#!/bin/bash
# Claudroponics Docker entrypoint
# Usage: entrypoint.sh [full|simulation|dashboard|mqtt]
set -e

source /opt/ros/humble/setup.bash
source /hydroponics_ws/install/setup.bash

MODE="${1:-full}"

echo "[entrypoint] Starting Claudroponics in mode: $MODE"
echo "[entrypoint] ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
echo "[entrypoint] DB_PATH=$HYDROPONICS_DB_PATH"

case "$MODE" in

  full)
    # All Python nodes + dashboard; no hardware BT/transport nodes
    exec ros2 launch hydroponics_dashboard dashboard.launch.py &
    exec ros2 launch hydroponics_nutrients  nutrient.launch.py &
    exec ros2 launch hydroponics_lighting   lighting.launch.py &
    exec ros2 launch hydroponics_harvest    harvest.launch.py  &
    exec ros2 launch hydroponics_data       data.launch.py     &
    exec ros2 launch hydroponics_mqtt       mqtt.launch.py     &
    exec ros2 launch hydroponics_vision     vision.launch.py
    ;;

  simulation)
    # Full simulation including mock hardware
    exec ros2 launch hydroponics_bringup simulation.launch.py
    ;;

  dashboard)
    # Dashboard server only (connect to external ROS2 via DDS)
    exec ros2 run hydroponics_dashboard dashboard_server
    ;;

  mqtt)
    # MQTT bridge only
    exec ros2 run hydroponics_mqtt mqtt_bridge
    ;;

  bash)
    exec /bin/bash
    ;;

  *)
    echo "Unknown mode: $MODE"
    echo "Valid modes: full | simulation | dashboard | mqtt | bash"
    exit 1
    ;;
esac
