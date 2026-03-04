# Semantic Mapping — Jetson Orin Nano Setup Guide

Live semantic mapping and localization using **Isaac ROS 3.2**, **nvblox**, and an **Intel RealSense D435i** on a **Jetson Orin Nano 8GB**.

> ⚠️ This guide is specifically for **Isaac ROS 3.2 / ROS 2 Humble / Ubuntu 22.04 / JetPack 6.x**. The current Isaac ROS docs (4.x) target Ubuntu 24.04/Jazzy — do not follow those on this hardware. `isaac-ros activate` and `isaac-ros-cli` do **not exist** on this setup — use `run_dev.sh` instead.

---

## Software Version Reference

| Software | Version |
|---|---|
| JetPack | 6.1 or 6.2 — `R36 (release), REVISION: 4.0` |
| Ubuntu | 22.04 LTS (Jammy) |
| Isaac ROS | **3.2** (`release-3.2` branch) |
| ROS 2 | **Humble** |
| Docker Engine | 27.2.0 or newer |
| RealSense Firmware | **5.13.0.50** |
| librealsense SDK | **v2.55.1** |
| realsense-ros | **4.51.1-isaac** |

> ⚠️ Isaac ROS 4.x docs reference firmware 5.16.0.1 and librealsense 2.56.3 — those are wrong for this setup.

---

## 1. Host Setup (One Time)

### Performance Mode
```bash
sudo /usr/bin/jetson_clocks
sudo /usr/sbin/nvpmodel -m 0
```

### Docker Engine (27.2.0+)
Follow the [official Docker install guide](https://docs.docker.com/engine/install/ubuntu/), then:
```bash
sudo apt-get install -y docker-buildx-plugin
sudo usermod -aG docker $USER
newgrp docker
docker --version  # must be 27.2.0+
```

### Migrate Docker to SSD
```bash
sudo systemctl stop docker
sudo mkdir -p /ssd/docker
sudo rsync -axPS /var/lib/docker/ /ssd/docker/
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
    "runtimes": {
        "nvidia": { "path": "nvidia-container-runtime", "runtimeArgs": [] }
    },
    "default-runtime": "nvidia",
    "data-root": "/ssd/docker"
}
EOF
sudo mv /var/lib/docker /var/lib/docker.old
sudo systemctl daemon-reload && sudo systemctl restart docker
```

### CDI Spec + pva-allow-2
```bash
sudo nvidia-ctk cdi generate --mode=csv --output=/etc/cdi/nvidia.yaml

sudo apt-key adv --fetch-key https://repo.download.nvidia.com/jetson/jetson-ota-public.asc
sudo add-apt-repository 'deb https://repo.download.nvidia.com/jetson/common r36.4 main'
sudo apt-get update && sudo apt-get install -y pva-allow-2
```

### Isaac ROS Apt Repository
```bash
k="/usr/share/keyrings/nvidia-isaac-ros.gpg"
curl -fsSL https://isaac.download.nvidia.com/isaac-ros/repos.key | \
  sudo gpg --dearmor | sudo tee -a $k > /dev/null

sudo tee /etc/apt/sources.list.d/nvidia-isaac-ros.list > /dev/null <<'EOF'
deb [signed-by=/usr/share/keyrings/nvidia-isaac-ros.gpg] https://isaac.download.nvidia.com/isaac-ros/release-3 jammy/
EOF
sudo apt-get update
```

> ⚠️ Do NOT add `main` at the end — the repo uses a flat structure. If you see a 404 for `/ubuntu/main`, remove that stale file: `sudo rm -f /etc/apt/sources.list.d/isaac-ros.list`

### Workspace and Environment
```bash
sudo apt-get install -y git-lfs && git lfs install --skip-repo
mkdir -p /ssd/workspaces/semantic_mapping/src

echo 'export ISAAC_ROS_WS="/ssd/workspaces/semantic_mapping"' >> ~/.bashrc
echo 'xhost +local:root' >> ~/.bashrc
echo 'export DISPLAY=:0' >> ~/.bashrc
echo 'export ROS_DOMAIN_ID=1' >> ~/.bashrc
source ~/.bashrc
```

---

## 2. Clone Repositories

```bash
cd ${ISAAC_ROS_WS}/src

git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_common.git isaac_ros_common

git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_nvblox.git isaac_ros_nvblox
cd isaac_ros_nvblox && git submodule update --init --recursive && cd ..

git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_image_pipeline.git isaac_ros_image_pipeline
git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_compression.git isaac_ros_compression
git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_visual_slam.git isaac_ros_visual_slam
git clone https://github.com/IntelRealSense/realsense-ros.git -b 4.51.1
```

> ⚠️ Do NOT clone `isaac_ros_nitros` from source — it causes a `magic_enum::magic_enum` CMake error. Install via apt inside the container instead.

---

## 3. RealSense Setup

### udev Rules (camera unplugged)
```bash
wget https://raw.githubusercontent.com/IntelRealSense/librealsense/v2.56.3/config/99-realsense-libusb.rules
sudo mv 99-realsense-libusb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### Configure Container Image Key
```bash
echo "CONFIG_IMAGE_KEY=ros2_humble.realsense" > ~/.isaac_ros_common-config
```

### Patch Dockerfile.realsense for IMU Support
JetPack 6 disables the kernel HID driver, breaking the D435i IMU. Fix it by switching to the libuvc backend:

```bash
nano ${ISAAC_ROS_WS}/src/isaac_ros_common/docker/Dockerfile.realsense
```

Find this line:
```dockerfile
chmod +x /opt/realsense/build-librealsense.sh && /opt/realsense/build-librealsense.sh -v ${LIBREALSENSE_SOURCE_VERSION};
```
Change to:
```dockerfile
chmod +x /opt/realsense/build-librealsense.sh && /opt/realsense/build-librealsense.sh -n -j 2 -v ${LIBREALSENSE_SOURCE_VERSION};
```

The Dockerfile already has `LIBREALSENSE_SOURCE_VERSION=v2.55.1` — no other changes needed. The `-n` flag does not affect nvblox or cuVSLAM performance.

### Enable realsense_splitter
```bash
cd ${ISAAC_ROS_WS}/src/isaac_ros_nvblox/nvblox_examples/realsense_splitter
git update-index --assume-unchanged COLCON_IGNORE && rm COLCON_IGNORE
```

---

## 4. Enter the Container

Plug in your D435i to USB 3 first, then:
```bash
cd ${ISAAC_ROS_WS}/src/isaac_ros_common && ./scripts/run_dev.sh
```
First run takes 15–30 minutes. You are inside the container when your prompt shows `admin@jetson`.

---

## 5. Inside Container: Environment (Every Session)

> ⚠️ Docker containers are stateless — run these at the start of every container session.

```bash
source /opt/ros/humble/setup.bash
export CMAKE_PREFIX_PATH=/opt/ros/humble:$CMAKE_PREFIX_PATH
export LD_LIBRARY_PATH=/opt/ros/humble/lib:$LD_LIBRARY_PATH

echo "source /opt/ros/humble/setup.bash" > ~/.bashrc
echo "export CMAKE_PREFIX_PATH=/opt/ros/humble:\$CMAKE_PREFIX_PATH" >> ~/.bashrc
echo "export LD_LIBRARY_PATH=/opt/ros/humble/lib:\$LD_LIBRARY_PATH" >> ~/.bashrc
```

---

## 6. Inside Container: Install Dependencies (Every Session)

```bash
sudo apt-get update -q

sudo apt-get install -y \
  ros-humble-isaac-ros-nitros \
  ros-humble-isaac-ros-managed-nitros \
  ros-humble-isaac-ros-nitros-image-type \
  ros-humble-isaac-ros-nitros-camera-info-type \
  ros-humble-isaac-ros-nitros-pose-cov-stamped-type \
  ros-humble-isaac-ros-nitros-odometry-type \
  ros-humble-isaac-ros-nitros-point-cloud-type \
  ros-humble-isaac-ros-visual-slam \
  ros-humble-foxglove-bridge

sudo rosdep init 2>/dev/null || true
rosdep update
rosdep install -i -r \
  --from-paths /workspaces/isaac_ros-dev/src/isaac_ros_nvblox/ \
  --from-paths /workspaces/isaac_ros-dev/src/realsense-ros/ \
  --rosdistro humble -y \
  --skip-keys="librealsense2"
```

---

## 7. Inside Container: Build (First Time Only)

> ⚠️ Always use `--parallel-workers 1` and `MAKEFLAGS="-j1"` or the Orin Nano will freeze.

```bash
cd /workspaces/isaac_ros-dev

MAKEFLAGS="-j1" nice -n 19 \
colcon build --symlink-install \
  --parallel-workers 1 \
  --cmake-args -DCMAKE_BUILD_PARALLEL_LEVEL=1 \
  --packages-up-to realsense_splitter nvblox_examples_bringup \
  --allow-overriding isaac_ros_common isaac_ros_launch_utils \
    nvblox_examples_bringup nvblox_msgs nvblox_ros \
    nvblox_ros_common nvblox_ros_python_utils nvblox_rviz_plugin

source install/setup.bash
```

Monitor RAM during build in a separate host terminal: `watch -n 3 free -h`

---

## 8. Download Quickstart Assets (Host, Once)

```bash
sudo apt-get install -y curl jq tar
NGC_ORG="nvidia"; NGC_TEAM="isaac"; NGC_RESOURCE="isaac_ros_nvblox_assets"
NGC_FILENAME="quickstart.tar.gz"; MAJOR_VERSION=3; MINOR_VERSION=2
VERSION_REQ_URL="https://catalog.ngc.nvidia.com/api/resources/versions?orgName=$NGC_ORG&teamName=$NGC_TEAM&name=$NGC_RESOURCE&isPublic=true&pageNumber=0&pageSize=100&sortOrder=CREATED_DATE_DESC"
AVAILABLE_VERSIONS=$(curl -s -H "Accept: application/json" "$VERSION_REQ_URL")
LATEST_VERSION_ID=$(echo $AVAILABLE_VERSIONS | jq -r "
    .recipeVersions[]
    | .versionId as \$v
    | \$v | select(test(\"^\\\\d+\\\\.\\\\d+\\\\.\\\\d+$\"))
    | split(\".\") | {major: .[0]|tonumber, minor: .[1]|tonumber, patch: .[2]|tonumber}
    | select(.major == $MAJOR_VERSION and .minor <= $MINOR_VERSION)
    | \$v" | sort -V | tail -n 1)
mkdir -p ${ISAAC_ROS_WS}/isaac_ros_assets
FILE_REQ_URL="https://api.ngc.nvidia.com/v2/resources/$NGC_ORG/$NGC_TEAM/$NGC_RESOURCE/versions/$LATEST_VERSION_ID/files/$NGC_FILENAME"
curl -LO --request GET "${FILE_REQ_URL}"
tar -xf ${NGC_FILENAME} -C ${ISAAC_ROS_WS}/isaac_ros_assets && rm ${NGC_FILENAME}
```

---

## 9. Running nvblox

### Quickstart Demo (Isaac Sim rosbag, no camera needed)
```bash
source /opt/ros/humble/setup.bash
source /workspaces/isaac_ros-dev/install/setup.bash

# With RViz (requires display connected)
ros2 launch nvblox_examples_bringup isaac_sim_example.launch.py \
  rosbag:=${ISAAC_ROS_WS}/isaac_ros_assets/isaac_ros_nvblox/quickstart \
  navigation:=False run_rviz:=True run_foxglove:=False voxel_size:=0.1

# With Foxglove (headless/remote) — connect to ws://<JETSON_IP>:8765
ros2 launch nvblox_examples_bringup isaac_sim_example.launch.py \
  rosbag:=${ISAAC_ROS_WS}/isaac_ros_assets/isaac_ros_nvblox/quickstart \
  navigation:=False run_rviz:=False run_foxglove:=True voxel_size:=0.1
```

### Live RealSense Mapping

```bash
source /opt/ros/humble/setup.bash
source /workspaces/isaac_ros-dev/install/setup.bash

rs-enumerate-devices  # verify camera is detected first
```

Choose one of the two launch modes below:

---

#### Option A — Local RViz (display connected to this machine)

```bash
ros2 launch nvblox_examples_bringup realsense_example.launch.py \
  run_rviz:=True run_foxglove:=False \
  enable_imu_fusion:=False \
  voxel_size:=0.1
```

> Requires a local display (X11 or Wayland). If running inside a Docker container, make sure `DISPLAY` is exported and X forwarding or a host display socket is mounted (e.g. `-e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix`).

---

#### Option B — Foxglove (remote / headless streaming)

```bash
ros2 launch nvblox_examples_bringup realsense_example.launch.py \
  run_rviz:=False run_foxglove:=True \
  enable_imu_fusion:=False \
  layer_streamer_bandwidth_limit_mbps:=30 \
  voxel_size:=0.1
```

> Connect via [Foxglove Studio](https://foxglove.dev) at `ws://<device-ip>:8765`. Useful for Jetson or headless setups where a local display isn't available.

---

> **Notes**
> - `enable_imu_fusion:=False` is required until the `Dockerfile.realsense` IMU patch (Step 3) is applied and the container is rebuilt.
> - `voxel_size:=0.1` reduces GPU memory usage ~8× compared to the default `0.05` — safe to keep for most use cases.

## 10. Foxglove Setup

1. Download [Foxglove Studio](https://foxglove.dev/download) on your laptop
2. Open → **Open connection** → **Foxglove WebSocket**
3. URL: `ws://<JETSON_IP>:8765` (find IP: `hostname -I | awk '{print $1}'`)
4. Install the **nvblox extension**: Extensions sidebar → search "nvblox" → Install
5. Add panel → **3D** → subscribe to `/nvblox_node/mesh`

Start bridge in a separate container terminal:
```bash
source /opt/ros/humble/setup.bash
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
```

---

## 11. Save Map and Record Bags

```bash
# Save nvblox map while it's running (second terminal inside container)
ros2 service call /nvblox_node/save_map \
  nvblox_msgs/srv/FilePath \
  "{file_path: '/ssd/workspaces/semantic_mapping/saved_maps/my_map'}"

# Record rosbag with no size limit or auto-deletion
mkdir -p /ssd/workspaces/semantic_mapping/recordings
ros2 bag record \
  /camera/color/image_raw /camera/depth/image_rect_raw \
  /camera/color/camera_info /camera/depth/camera_info \
  /camera/imu /tf /tf_static \
  --output /ssd/workspaces/semantic_mapping/recordings/session_$(date +%Y%m%d_%H%M%S) \
  --max-bag-size 0 --max-cache-size 0
```

---

## 12. Every Session Checklist

**Host:**
```bash
sudo /usr/bin/jetson_clocks && sudo /usr/sbin/nvpmodel -m 0
free -h  # need 3GB+ available before launching
# Plug in D435i to USB 3
cd ${ISAAC_ROS_WS}/src/isaac_ros_common && ./scripts/run_dev.sh
```

**Container (`admin@jetson`):**
```bash
source /opt/ros/humble/setup.bash
export CMAKE_PREFIX_PATH=/opt/ros/humble:$CMAKE_PREFIX_PATH
export LD_LIBRARY_PATH=/opt/ros/humble/lib:$LD_LIBRARY_PATH

sudo apt-get update -q && sudo apt-get install -y \
  ros-humble-isaac-ros-nitros ros-humble-isaac-ros-managed-nitros \
  ros-humble-isaac-ros-nitros-image-type \
  ros-humble-isaac-ros-nitros-camera-info-type \
  ros-humble-isaac-ros-nitros-pose-cov-stamped-type \
  ros-humble-isaac-ros-nitros-odometry-type \
  ros-humble-isaac-ros-nitros-point-cloud-type \
  ros-humble-isaac-ros-visual-slam ros-humble-foxglove-bridge

source /workspaces/isaac_ros-dev/install/setup.bash
rs-enumerate-devices
```

---

## Known Bugs Quick Reference

| Bug | Fix |
|---|---|
| `isaac-ros-cli` not found | Use `./scripts/run_dev.sh` — CLI is 4.x only |
| 404 on apt repo `/ubuntu/main` | Remove stale list, re-add with `jammy/` not `jammy main` |
| `nvblox_core` CMake error | `git submodule update --init --recursive` inside `isaac_ros_nvblox/` |
| `magic_enum` not found | Remove `src/isaac_ros_nitros/`, install via apt instead |
| `/opt/ros/humble` missing from `CMAKE_PREFIX_PATH` | `export CMAKE_PREFIX_PATH=/opt/ros/humble:$CMAKE_PREFIX_PATH` |
| Jetson freezes during build | Use `--parallel-workers 1` and `MAKEFLAGS="-j1"` |
| D435i IMU not working | Patch `Dockerfile.realsense` with `-n` flag (Step 3) |
| `libisaac_ros_nitros_image_type.so` not found | `sudo apt-get install -y ros-humble-isaac-ros-nitros-image-type` |
| nvblox mesh blank / CUDA out of memory | Add `voxel_size:=0.1` to launch command |
| apt packages gone after container restart | Docker is stateless — re-run Step 6 every session |

---

## Project Goals

- [ ] Live 3D semantic mapping with nvblox + RealSense D435i
- [ ] Visual SLAM / localization with cuVSLAM
- [ ] VIO with D435i IMU (requires Dockerfile.realsense patch + container rebuild)
- [ ] Semantic segmentation overlay on map
- [ ] Map persistence across sessions
- [ ] Remote visualization via Foxglove
- [ ] One-command launch scripts

---

## Repository Structure

```
semantic_mapping/
├── src/
│   ├── isaac_ros_common/         ← NVIDIA (gitignored)
│   ├── isaac_ros_nvblox/         ← NVIDIA (gitignored)
│   ├── isaac_ros_image_pipeline/ ← NVIDIA (gitignored)
│   ├── isaac_ros_compression/    ← NVIDIA (gitignored)
│   ├── isaac_ros_visual_slam/    ← NVIDIA (gitignored)
│   └── realsense-ros/            ← Intel  (gitignored)
├── build/                        ← gitignored
├── install/                      ← gitignored
├── log/                          ← gitignored
├── isaac_ros_assets/             ← gitignored
├── saved_maps/
├── recordings/                   ← gitignored
├── scripts/                      ← your launch scripts (tracked)
├── config/                       ← your configs (tracked)
├── README.md
└── .gitignore
```
