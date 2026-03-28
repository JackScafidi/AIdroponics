# MIT License
#
# Copyright (c) 2026 Claudroponics
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""mqtt_bridge.py — ROS2 ↔ HiveMQ Cloud MQTT bridge node.

Bridges ROS2 topics to MQTT (for cloud logging and Home Assistant integration)
and routes inbound MQTT commands back to ROS2 services.

Config is loaded from mqtt_config.yaml via ROS2 parameters, with sensitive
credentials optionally overridden by environment variables:
  MQTT_BROKER_URL, MQTT_USERNAME, MQTT_PASSWORD
"""

import json
import os
import ssl
import threading
import time
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from hydroponics_msgs.msg import (
    NutrientStatus,
    TransportStatus,
    LightStatus,
    SystemAlert,
    HarvestResult,
    BehaviorTreeStatus,
    InspectionResult,
)
from hydroponics_msgs.srv import ForceDose, SetGrowLightIntensity


class MqttBridgeNode(Node):
    """Bridges ROS2 topics to/from an MQTT broker (HiveMQ Cloud or compatible)."""

    def __init__(self) -> None:
        super().__init__("mqtt_bridge_node")

        # ------------------------------------------------------------------ #
        # Parameters (loaded from mqtt_config.yaml)
        # ------------------------------------------------------------------ #
        self.declare_parameter("broker_url", "")
        self.declare_parameter("broker_port", 8883)
        self.declare_parameter("use_tls", True)
        self.declare_parameter("username", "")
        self.declare_parameter("password", "")
        self.declare_parameter("topic_prefix", "hydroponics")
        self.declare_parameter("sensor_publish_interval_s", 10.0)
        self.declare_parameter("ha_discovery_enabled", True)
        self.declare_parameter("ha_discovery_prefix", "homeassistant")

        broker_url = (
            os.environ.get("MQTT_BROKER_URL")
            or self.get_parameter("broker_url").value
        )
        broker_port: int = self.get_parameter("broker_port").value
        use_tls: bool = self.get_parameter("use_tls").value
        username: str = (
            os.environ.get("MQTT_USERNAME")
            or self.get_parameter("username").value
        )
        password: str = (
            os.environ.get("MQTT_PASSWORD")
            or self.get_parameter("password").value
        )
        self._prefix: str = self.get_parameter("topic_prefix").value
        self._ha_discovery: bool = self.get_parameter("ha_discovery_enabled").value
        self._ha_prefix: str = self.get_parameter("ha_discovery_prefix").value

        if not broker_url:
            self.get_logger().warn(
                "MQTT broker URL not set. Bridge will not connect. "
                "Set MQTT_BROKER_URL env var or broker_url parameter."
            )

        # ------------------------------------------------------------------ #
        # MQTT client setup
        # ------------------------------------------------------------------ #
        client_id = f"claudroponics_{os.getpid()}"
        self._mqtt = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5)
        self._mqtt.on_connect = self._on_mqtt_connect
        self._mqtt.on_disconnect = self._on_mqtt_disconnect
        self._mqtt.on_message = self._on_mqtt_message

        if username:
            self._mqtt.username_pw_set(username, password)

        if use_tls:
            self._mqtt.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)

        self._broker_url = broker_url
        self._broker_port = broker_port
        self._connected = False
        self._connect_lock = threading.Lock()

        # Start MQTT network loop in a background thread
        self._mqtt.loop_start()

        if broker_url:
            self._try_connect()

        # ------------------------------------------------------------------ #
        # ROS2 service clients
        # ------------------------------------------------------------------ #
        self._force_dose_client = self.create_client(ForceDose, "force_dose")
        self._set_light_client = self.create_client(
            SetGrowLightIntensity, "set_grow_light_intensity"
        )

        # ------------------------------------------------------------------ #
        # ROS2 subscriptions → MQTT publish
        # ------------------------------------------------------------------ #
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=5,
        )
        event_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            depth=10,
        )

        self.create_subscription(
            NutrientStatus, "/hydroponics/nutrient_status",
            self._on_nutrient_status, sensor_qos,
        )
        self.create_subscription(
            TransportStatus, "/hydroponics/transport_status",
            self._on_transport_status, sensor_qos,
        )
        self.create_subscription(
            LightStatus, "/hydroponics/light_status",
            self._on_light_status, sensor_qos,
        )
        self.create_subscription(
            SystemAlert, "/hydroponics/system_alert",
            self._on_system_alert, event_qos,
        )
        self.create_subscription(
            HarvestResult, "/hydroponics/harvest_result",
            self._on_harvest_result, event_qos,
        )
        self.create_subscription(
            BehaviorTreeStatus, "/hydroponics/behavior_tree_status",
            self._on_bt_status, event_qos,
        )
        self.create_subscription(
            InspectionResult, "/hydroponics/inspection_result",
            self._on_inspection_result, event_qos,
        )

        # Reconnect watchdog at 10 s interval
        self.create_timer(10.0, self._reconnect_watchdog)

        self.get_logger().info(
            f"MQTT bridge started → {broker_url}:{broker_port} "
            f"(prefix={self._prefix}, tls={use_tls})"
        )

    # ---------------------------------------------------------------------- #
    # Connection helpers
    # ---------------------------------------------------------------------- #

    def _try_connect(self) -> None:
        with self._connect_lock:
            try:
                self._mqtt.connect_async(self._broker_url, self._broker_port, keepalive=60)
                self.get_logger().info(
                    f"MQTT connecting to {self._broker_url}:{self._broker_port}"
                )
            except Exception as exc:
                self.get_logger().warn(f"MQTT connect failed: {exc}")

    def _reconnect_watchdog(self) -> None:
        if self._broker_url and not self._connected:
            self.get_logger().debug("MQTT not connected, retrying…")
            self._try_connect()

    def _on_mqtt_connect(
        self, client: mqtt.Client, userdata: Any, flags: Dict, rc: int, props: Any = None
    ) -> None:
        if rc == 0:
            self._connected = True
            self.get_logger().info("MQTT connected successfully")
            # Subscribe to inbound command topics
            client.subscribe(f"{self._prefix}/commands/force_dose", qos=1)
            client.subscribe(f"{self._prefix}/commands/set_light_intensity", qos=1)
            if self._ha_discovery:
                self._publish_ha_discovery()
        else:
            self.get_logger().warn(f"MQTT connect refused (rc={rc})")

    def _on_mqtt_disconnect(
        self, client: mqtt.Client, userdata: Any, rc: int, props: Any = None
    ) -> None:
        self._connected = False
        self.get_logger().warn(f"MQTT disconnected (rc={rc})")

    # ---------------------------------------------------------------------- #
    # Inbound MQTT → ROS2
    # ---------------------------------------------------------------------- #

    def _on_mqtt_message(
        self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage
    ) -> None:
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.get_logger().warn(f"MQTT bad payload on {topic}: {exc}")
            return

        if topic == f"{self._prefix}/commands/force_dose":
            self._handle_force_dose(payload)
        elif topic == f"{self._prefix}/commands/set_light_intensity":
            self._handle_set_light(payload)
        else:
            self.get_logger().debug(f"MQTT unhandled topic: {topic}")

    def _handle_force_dose(self, payload: Dict) -> None:
        pump_id = str(payload.get("pump_id", ""))
        amount_ml = float(payload.get("amount_ml", 0.0))
        if not pump_id or amount_ml <= 0:
            self.get_logger().warn(f"force_dose: invalid payload {payload}")
            return
        if not self._force_dose_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn("force_dose: service not available")
            return
        req = ForceDose.Request(pump_id=pump_id, amount_ml=amount_ml)
        self._force_dose_client.call_async(req)
        self.get_logger().info(f"MQTT→ROS2 force_dose: pump={pump_id}, amount={amount_ml}mL")

    def _handle_set_light(self, payload: Dict) -> None:
        intensity = int(payload.get("intensity_percent", 0))
        if not self._set_light_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn("set_grow_light_intensity: service not available")
            return
        req = SetGrowLightIntensity.Request()
        req.intensity_percent = intensity
        self._set_light_client.call_async(req)
        self.get_logger().info(f"MQTT→ROS2 set_light_intensity: {intensity}%")

    # ---------------------------------------------------------------------- #
    # ROS2 → MQTT publish helpers
    # ---------------------------------------------------------------------- #

    def _publish(self, suffix: str, data: Dict, qos: int = 0) -> None:
        if not self._connected:
            return
        topic = f"{self._prefix}/{suffix}"
        payload = json.dumps(data, default=str)
        self._mqtt.publish(topic, payload, qos=qos)

    # ---------------------------------------------------------------------- #
    # ROS2 subscription callbacks → MQTT
    # ---------------------------------------------------------------------- #

    def _on_nutrient_status(self, msg: NutrientStatus) -> None:
        self._publish("sensors/nutrients", {
            "ph": round(msg.ph_current, 3),
            "ec": round(msg.ec_current, 3),
            "temperature_c": round(msg.temperature_c, 2),
            "ph_target": msg.ph_target,
            "ec_target": msg.ec_target,
            "growth_stage": msg.growth_stage,
            "days_since_planting": msg.days_since_planting,
            "a_b_ratio": msg.a_b_ratio,
            "pump_active": list(msg.pump_active),
            "timestamp": time.time(),
        })

    def _on_transport_status(self, msg: TransportStatus) -> None:
        self._publish("system/transport", {
            "current_position": msg.current_position,
            "target_position": msg.target_position,
            "is_moving": msg.is_moving,
            "position_mm": round(msg.position_mm, 1),
            "velocity_mm_s": round(msg.velocity_mm_s, 1),
            "timestamp": time.time(),
        })

    def _on_light_status(self, msg: LightStatus) -> None:
        self._publish("system/lights", {
            "grow_intensity_percent": msg.grow_intensity_percent,
            "schedule_state": msg.schedule_state,
            "inspection_light_on": msg.inspection_light_on,
            "timestamp": time.time(),
        })

    def _on_system_alert(self, msg: SystemAlert) -> None:
        self._publish("alerts", {
            "alert_type": msg.alert_type,
            "severity": msg.severity,
            "message": msg.message,
            "recommended_action": msg.recommended_action,
            "timestamp": time.time(),
        }, qos=1)

    def _on_harvest_result(self, msg: HarvestResult) -> None:
        self._publish("harvests/latest", {
            "position_index": msg.position_index,
            "action_type": msg.action_type,
            "weight_grams": round(msg.weight_grams, 1),
            "success": msg.success,
            "timestamp": time.time(),
        }, qos=1)

    def _on_bt_status(self, msg: BehaviorTreeStatus) -> None:
        self._publish("system/state", {
            "system_state": msg.system_state,
            "active_node_path": msg.active_node_path,
            "running_nodes": list(msg.running_nodes),
            "failed_nodes": list(msg.failed_nodes),
            "timestamp": time.time(),
        })

    def _on_inspection_result(self, msg: InspectionResult) -> None:
        plants_data = []
        for plant in msg.plants:
            plants_data.append({
                "position_index": plant.position_index,
                "status": plant.status,
                "health_state": plant.health_state,
                "canopy_area_cm2": round(plant.canopy_area_cm2, 2),
                "height_cm": round(plant.height_cm, 2),
                "leaf_count": plant.leaf_count,
                "days_since_planted": plant.days_since_planted,
            })
        self._publish("vision/inspection", {
            "scan_number": msg.scan_number,
            "disease_detected": msg.disease_detected,
            "disease_type": msg.disease_type,
            "deficiency_trends": list(msg.deficiency_trends),
            "plants": plants_data,
            "timestamp": time.time(),
        }, qos=1)

    # ---------------------------------------------------------------------- #
    # Home Assistant MQTT discovery
    # ---------------------------------------------------------------------- #

    def _publish_ha_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery payloads for key sensors."""
        device = {
            "identifiers": ["claudroponics_01"],
            "name": "Claudroponics",
            "model": "Prototype v1",
            "manufacturer": "Claudroponics",
        }
        sensors = [
            ("ph", "pH", "mdi:ph", None, "measurement", f"{self._prefix}/sensors/nutrients", "ph"),
            ("ec", "EC", "mdi:water-percent", "mS/cm", "measurement", f"{self._prefix}/sensors/nutrients", "ec"),
            ("temp", "Solution Temp", "mdi:thermometer-water", "°C", "measurement", f"{self._prefix}/sensors/nutrients", "temperature_c"),
        ]
        for uid, name, icon, unit, device_class, state_topic, value_key in sensors:
            config_topic = f"{self._ha_prefix}/sensor/claudroponics_{uid}/config"
            config_payload: Dict[str, Any] = {
                "name": name,
                "unique_id": f"claudroponics_{uid}",
                "icon": icon,
                "state_topic": state_topic,
                "value_template": f"{{{{ value_json.{value_key} }}}}",
                "device": device,
            }
            if unit:
                config_payload["unit_of_measurement"] = unit
            if device_class and device_class != "measurement":
                config_payload["device_class"] = device_class
            self._mqtt.publish(
                config_topic, json.dumps(config_payload), qos=1, retain=True
            )
        self.get_logger().info("Published Home Assistant MQTT discovery configs")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MqttBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
