# MIT License
# Copyright (c) 2024 Claudroponics Project
#
# Entry point for the hydroponics dashboard server.
# Starts the RosBridge ROS2 node in a background thread, then launches
# a Uvicorn / FastAPI server on 0.0.0.0:8080.

from __future__ import annotations

import logging
import os
import signal
import threading
from pathlib import Path
from typing import Optional

import rclpy
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hydroponics_dashboard.ros_bridge import RosBridge
from hydroponics_dashboard.api_routes import router as api_router, set_ros_bridge

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"


def create_app(bridge: RosBridge) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Claudroponics Dashboard API",
        version="1.0.0",
        description="REST + WebSocket API for the Claudroponics hydroponic system",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Allow all origins in development; in production the Nginx proxy handles CORS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Inject the RosBridge instance into the routes module.
    set_ros_bridge(bridge)

    # REST + WebSocket routes under /api and /ws.
    app.include_router(api_router)

    # Serve the compiled React build from the /static directory.
    # Mount at "/" last so it acts as a catch-all for the SPA.
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
        logger.info("Serving React SPA from %s", STATIC_DIR)
    else:
        logger.warning(
            "Static directory %s not found – React SPA will not be served. "
            "Run `npm run build` inside the frontend directory.",
            STATIC_DIR,
        )

    return app


# ---------------------------------------------------------------------------
# ROS spin thread
# ---------------------------------------------------------------------------


class _RosThread(threading.Thread):
    """Spins the rclpy executor for the RosBridge node in a daemon thread."""

    def __init__(self, bridge: RosBridge) -> None:
        super().__init__(name="ros-spin", daemon=True)
        self._bridge = bridge
        self._executor = rclpy.executors.MultiThreadedExecutor(num_threads=4)
        self._executor.add_node(bridge)

    def run(self) -> None:
        logger.info("ROS spin thread started.")
        try:
            self._executor.spin()
        except Exception as exc:  # noqa: BLE001
            logger.error("ROS executor error: %s", exc)
        finally:
            logger.info("ROS spin thread stopped.")

    def shutdown(self) -> None:
        self._executor.shutdown(timeout_sec=2.0)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_ros_thread: Optional[_RosThread] = None
_bridge: Optional[RosBridge] = None


def main() -> None:
    """Initialise ROS2, start the FastAPI server, and handle graceful shutdown."""
    global _ros_thread, _bridge

    # ---- ROS2 initialisation -----------------------------------------------
    rclpy.init()
    _bridge = RosBridge()

    _ros_thread = _RosThread(_bridge)
    _ros_thread.start()

    # ---- FastAPI / Uvicorn --------------------------------------------------
    app = create_app(_bridge)

    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "8080"))

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config)

    # ---- Shutdown handler ---------------------------------------------------
    def _shutdown(signum: int, frame: object) -> None:
        logger.info("Shutdown signal received (sig=%d), stopping…", signum)
        server.should_exit = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Starting Claudroponics Dashboard on http://%s:%d", host, port)
    try:
        server.run()
    finally:
        logger.info("Uvicorn stopped. Shutting down ROS2…")
        if _ros_thread is not None:
            _ros_thread.shutdown()
        if _bridge is not None:
            _bridge.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        logger.info("Clean shutdown complete.")


if __name__ == "__main__":
    main()
