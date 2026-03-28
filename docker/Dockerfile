# Claudroponics — Docker Image
#
# Packages the ROS2 Python nodes + FastAPI dashboard + React frontend.
# C++ nodes (transport, work_station, micro_ros_bridge, bt_manager) are
# NOT included — they require hardware and are run natively on the RPi 5.
#
# Build:
#   docker build -t claudroponics:latest .
#
# Run (simulation mode — no hardware):
#   docker run --rm -it \
#     -p 8080:8080 \
#     -v /path/to/data:/data \
#     claudroponics:latest simulation
#
# Run (connect to external ROS2 via DDS):
#   docker run --rm -it --network host \
#     -e ROS_DOMAIN_ID=0 \
#     claudroponics:latest

FROM ros:humble-ros-base-jammy AS base

# ─── System dependencies ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-setuptools \
    ros-humble-cv-bridge \
    ros-humble-sensor-msgs \
    ros-humble-std-msgs \
    ros-humble-std-srvs \
    ros-humble-action-msgs \
    libsqlite3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ─── Node.js (for building React frontend) ────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ─── Python dependencies ───────────────────────────────────────────────────────
COPY hydroponics_ws/src/hydroponics_vision/requirements.txt /tmp/vision_reqs.txt
RUN pip3 install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    websockets \
    paho-mqtt \
    ultralytics \
    opencv-python-headless \
    -r /tmp/vision_reqs.txt

# ─── Build React frontend ──────────────────────────────────────────────────────
FROM base AS frontend-builder

WORKDIR /build/frontend
COPY hydroponics_ws/src/hydroponics_dashboard/frontend/package.json .
COPY hydroponics_ws/src/hydroponics_dashboard/frontend/package-lock.json* .
RUN npm ci

COPY hydroponics_ws/src/hydroponics_dashboard/frontend/ .
RUN npm run build

# ─── Build ROS2 workspace ─────────────────────────────────────────────────────
FROM base AS ros-builder

WORKDIR /hydroponics_ws

# Copy only Python packages + message definitions (no C++ packages)
COPY hydroponics_ws/src/hydroponics_msgs/            src/hydroponics_msgs/
COPY hydroponics_ws/src/hydroponics_vision/           src/hydroponics_vision/
COPY hydroponics_ws/src/hydroponics_nutrients/        src/hydroponics_nutrients/
COPY hydroponics_ws/src/hydroponics_lighting/         src/hydroponics_lighting/
COPY hydroponics_ws/src/hydroponics_harvest/          src/hydroponics_harvest/
COPY hydroponics_ws/src/hydroponics_data/             src/hydroponics_data/
COPY hydroponics_ws/src/hydroponics_mqtt/             src/hydroponics_mqtt/
COPY hydroponics_ws/src/hydroponics_dashboard/        src/hydroponics_dashboard/
COPY hydroponics_ws/src/hydroponics_mocks/            src/hydroponics_mocks/

RUN . /opt/ros/humble/setup.sh \
    && rosdep update \
    && rosdep install --from-paths src --ignore-src -r -y \
    && colcon build \
       --packages-select \
         hydroponics_msgs \
         hydroponics_vision \
         hydroponics_nutrients \
         hydroponics_lighting \
         hydroponics_harvest \
         hydroponics_data \
         hydroponics_mqtt \
         hydroponics_dashboard \
         hydroponics_mocks \
       --cmake-args -DCMAKE_BUILD_TYPE=Release

# ─── Final image ──────────────────────────────────────────────────────────────
FROM base AS final

WORKDIR /hydroponics_ws

# Copy built workspace
COPY --from=ros-builder /hydroponics_ws/install/ install/
COPY --from=ros-builder /hydroponics_ws/src/     src/

# Copy built React frontend into dashboard static dir
COPY --from=frontend-builder /build/frontend/dist/ \
    src/hydroponics_dashboard/frontend/dist/

# Copy entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Data volume for SQLite database
VOLUME ["/data"]
ENV HYDROPONICS_DB_PATH=/data/hydroponics.db

# Dashboard port
EXPOSE 8080

# Default environment
ENV ROS_DOMAIN_ID=0
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["full"]
