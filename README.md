# Semantic Mapping — Jetson Orin Nano Setup Guide

Live semantic mapping and localization using **Isaac ROS 3.2**, **nvblox**, and an **Intel RealSense D435i** on a **Jetson Orin Nano 8GB**.

> ⚠️ This guide is specifically for **Isaac ROS 3.2 / ROS 2 Humble / Ubuntu 22.04 / JetPack 6.x**. The current Isaac ROS documentation (4.x) targets Ubuntu 24.04 and Jazzy — do not follow those instructions on this hardware.

---

## Table of Contents

1. [Hardware Requirements](#1-hardware-requirements)
2. [Software Version Reference](#2-software-version-reference)
3. [Verify JetPack Version](#3-verify-jetpack-version)
4. [Set Maximum Performance Mode](#4-set-maximum-performance-mode)
5. [Install Docker Engine](#5-install-docker-engine)
6. [Set Up SSD and Migrate Docker Storage](#6-set-up-ssd-and-migrate-docker-storage)
7. [Generate CDI Spec](#7-generate-cdi-spec)
8. [Install pva-allow-2](#8-install-pva-allow-2)
9. [Add the Isaac ROS Apt Repository](#9-add-the-isaac-ros-apt-repository)
10. [Install Git LFS](#10-install-git-lfs)
11. [Create the Workspace](#11-create-the-workspace)
12. [Clone Required Repositories](#12-clone-required-repositories)
13. [Set Up RealSense udev Rules](#13-set-up-realsense-udev-rules)
14. [Configure Isaac ROS Container for RealSense](#14-configure-isaac-ros-container-for-realsense)
15. [Enter the Docker Container](#15-enter-the-docker-container)
16. [Inside Container: Fix Environment](#16-inside-container-fix-environment)
17. [Inside Container: Install All Dependencies](#17-inside-container-install-all-dependencies)
18. [Inside Container: Build the Workspace](#18-inside-container-build-the-workspace)
19. [Run the nvblox Quickstart Demo](#19-run-the-nvblox-quickstart-demo)
20. [Run Live RealSense Mapping](#20-run-live-realsense-mapping)
21. [Set Up Foxglove Visualization](#21-set-up-foxglove-visualization)
22. [Saving Maps and Recording Bags](#22-saving-maps-and-recording-bags)
23. [Known Bugs and Fixes](#23-known-bugs-and-fixes)
24. [Every Session Checklist](#24-every-session-checklist)

---

## 1. Hardware Requirements

| Component | Requirement |
|---|---|
| Board | Jetson Orin Nano **8GB** (4GB is not recommended — insufficient RAM) |
| Storage | NVMe SSD (strongly recommended — eMMC is too slow and small) |
| Camera | Intel RealSense **D435i** or **D455** (D415 is not supported) |
| USB | USB **3.0** port and cable (required for full camera resolution/framerate) |
| Network | WiFi or Ethernet (for Foxglove remote visualization) |

---

## 2. Software Version Reference

| Software | Version |
|---|---|
| JetPack | 6.1 or 6.2 (R36, REVISION: 4.0) |
| Ubuntu | 22.04 LTS (Jammy) |
| Isaac ROS | **3.2** (`release-3.2` branch) |
| ROS 2 | **Humble** |
| Docker Engine | 27.2.0 or newer |
| RealSense Firmware | 5.16.0.1 |
| librealsense SDK | v2.56.3 |
| realsense-ros driver | 4.51.1 |

---

## 3. Verify JetPack Version

```bash
cat /etc/nv_tegra_release
```

Output must include `R36 (release), REVISION: 4.0`. If it shows `REVISION: 3.0` you are on JetPack 6.0 (Isaac ROS 3.1 only) and must update before continuing.

---

## 4. Set Maximum Performance Mode

```bash
sudo /usr/bin/jetson_clocks
sudo /usr/sbin/nvpmodel -m 0
```

---

## 5. Install Docker Engine

Follow the [official Docker installation guide for Ubuntu](https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository), then additionally install the buildx plugin:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin

# Add your user to the docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify version — must be 27.2.0+
docker --version
```

---

## 6. Set Up SSD and Migrate Docker Storage

If your SSD is not yet formatted and mounted, follow the [NVIDIA Isaac ROS Jetson Storage Setup guide](https://nvidia-isaac-ros.github.io/getting_started/hardware_setup/compute/jetson_storage.html).

This project assumes your SSD is mounted at `/ssd/`.

Migrate Docker's storage to the SSD to avoid filling up eMMC:

```bash
sudo systemctl stop docker

sudo mkdir -p /ssd/docker
sudo rsync -axPS /var/lib/docker/ /ssd/docker/

sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "default-runtime": "nvidia",
    "data-root": "/ssd/docker"
}
EOF

sudo mv /var/lib/docker /var/lib/docker.old
sudo systemctl daemon-reload
sudo systemctl restart docker

# Verify
docker info | grep "Docker Root Dir"
# Expected: Docker Root Dir: /ssd/docker
```

---

## 7. Generate CDI Spec

Required for Docker containers to access GPU and PVA hardware:

```bash
sudo nvidia-ctk cdi generate --mode=csv --output=/etc/cdi/nvidia.yaml
```

---

## 8. Install pva-allow-2

Required for Isaac ROS 3.2 VPI support:

```bash
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo apt-key adv --fetch-key https://repo.download.nvidia.com/jetson/jetson-ota-public.asc
sudo add-apt-repository 'deb https://repo.download.nvidia.com/jetson/common r36.4 main'
sudo apt-get update
sudo apt-get install -y pva-allow-2
```

---

## 9. Add the Isaac ROS Apt Repository

> ⚠️ **Bug warning:** The correct repository path is `/isaac-ros/release-3` — NOT `/isaac-ros/ubuntu/main`. If you see a 404 error for `ubuntu/main`, remove that stale entry first:
> ```bash
> sudo rm -f /etc/apt/sources.list.d/isaac-ros.list
> grep -r "isaac.download.nvidia.com" /etc/apt/  # should return nothing
> ```

Add the correct repository:

```bash
k="/usr/share/keyrings/nvidia-isaac-ros.gpg"
curl -fsSL https://isaac.download.nvidia.com/isaac-ros/repos.key | \
  sudo gpg --dearmor | sudo tee -a $k > /dev/null

# Note: do NOT add "main" at the end - the repo uses a flat structure
sudo tee /etc/apt/sources.list.d/nvidia-isaac-ros.list > /dev/null <<'EOF'
deb [signed-by=/usr/share/keyrings/nvidia-isaac-ros.gpg] https://isaac.download.nvidia.com/isaac-ros/release-3 jammy/
EOF

sudo apt-get update
# Verify: should see "Hit: ... isaac.download.nvidia.com/isaac-ros/release-3 jammy InRelease" with no errors
```

> ⚠️ **Note:** `isaac-ros-cli` (the `isaac-ros activate` command) does **not exist** for Ubuntu 22.04/Humble. That CLI is only available for Isaac ROS 4.x on Ubuntu 24.04. On this setup, the container is launched with `./scripts/run_dev.sh` instead.

---

## 10. Install Git LFS

```bash
sudo apt-get install -y git-lfs
git lfs install --skip-repo
```

---

## 11. Create the Workspace

```bash
mkdir -p /ssd/workspaces/semantic_mapping/src

echo 'export ISAAC_ROS_WS="/ssd/workspaces/semantic_mapping"' >> ~/.bashrc
echo 'xhost +local:root' >> ~/.bashrc
echo 'export DISPLAY=:0' >> ~/.bashrc
echo 'export ROS_DOMAIN_ID=1' >> ~/.bashrc

source ~/.bashrc

# Verify
echo $ISAAC_ROS_WS
# Expected: /ssd/workspaces/semantic_mapping
```

---

## 12. Clone Required Repositories

All clones go into `${ISAAC_ROS_WS}/src` and must use the `release-3.2` branch:

```bash
cd ${ISAAC_ROS_WS}/src

# Core - required first
git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_common.git isaac_ros_common

# nvblox - initialize submodules or nvblox_core will be missing
git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_nvblox.git isaac_ros_nvblox
cd isaac_ros_nvblox
git submodule update --init --recursive
cd ..

# Additional dependencies
git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_image_pipeline.git isaac_ros_image_pipeline
git clone -b release-3.2 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_compression.git isaac_ros_compression

# RealSense driver - pinned to exact version
git clone https://github.com/IntelRealSense/realsense-ros.git -b 4.51.1
```

> ⚠️ **Critical:** Do NOT clone `isaac_ros_nitros` from source. Install it via apt inside the container instead. Building it from source causes a `magic_enum::magic_enum` CMake error that is very difficult to resolve.

---

## 13. Set Up RealSense udev Rules

Run with the camera **unplugged**:

```bash
wget https://raw.githubusercontent.com/IntelRealSense/librealsense/v2.56.3/config/99-realsense-libusb.rules && \
sudo mv 99-realsense-libusb.rules /etc/udev/rules.d/ && \
sudo udevadm control --reload-rules && sudo udevadm trigger && \
echo "Successfully added udev rules"
```

---

## 14. Configure Isaac ROS Container for RealSense

This tells the container build to include the RealSense SDK layer:

```bash
echo "CONFIG_IMAGE_KEY=ros2_humble.realsense" > ~/.isaac_ros_common-config

# Verify
cat ~/.isaac_ros_common-config
# Expected: CONFIG_IMAGE_KEY=ros2_humble.realsense
```

---

## 15. Enter the Docker Container

Plug in your RealSense camera to a USB 3 port **before** running this:

```bash
cd ${ISAAC_ROS_WS}/src/isaac_ros_common && ./scripts/run_dev.sh
```

> The first run will take **15–30 minutes** as it builds the Docker image with RealSense support. Subsequent runs are fast.
>
> You will know you are inside the container when your prompt changes from `drone@jetson` to `admin@jetson`.

---

## 16. Inside Container: Fix Environment

> ⚠️ **Must do every session.** The container resets on restart and does not persist apt installs or environment changes. Always run these at the start of each container session.

```bash
# Source ROS Humble
source /opt/ros/humble/setup.bash

# Manually add /opt/ros/humble to CMAKE_PREFIX_PATH
# (sourcing alone is not enough due to container entrypoint ordering)
export CMAKE_PREFIX_PATH=/opt/ros/humble:$CMAKE_PREFIX_PATH

# Make permanent for this container session
echo "source /opt/ros/humble/setup.bash" > ~/.bashrc
echo "export CMAKE_PREFIX_PATH=/opt/ros/humble:\$CMAKE_PREFIX_PATH" >> ~/.bashrc

# Verify /opt/ros/humble is present
echo $CMAKE_PREFIX_PATH | tr ':' '\n' | grep "opt/ros"
# Must show: /opt/ros/humble
```

---

## 17. Inside Container: Install All Dependencies

Use `rosdep` to install all nvblox and realsense dependencies in one shot instead of chasing them one by one:

```bash
sudo apt-get update
rosdep update

rosdep install -i -r \
  --from-paths /workspaces/isaac_ros-dev/src/isaac_ros_nvblox/ \
  --from-paths /workspaces/isaac_ros-dev/src/realsense-ros/ \
  --rosdistro humble \
  -y
```

Also install Foxglove bridge:

```bash
sudo apt-get install -y ros-humble-foxglove-bridge
```

---

## 18. Inside Container: Build the Workspace

> ⚠️ **The Jetson Orin Nano 8GB will freeze and crash if you build with full parallelism.** Always use these throttled flags.

Enable the `realsense_splitter` package first (only needed once, do on host before entering container):

```bash
# Run this on the HOST before entering container
cd ${ISAAC_ROS_WS}/src/isaac_ros_nvblox/nvblox_examples/realsense_splitter && \
    git update-index --assume-unchanged COLCON_IGNORE && \
    rm COLCON_IGNORE
```

Then inside the container, build with throttled settings:

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

Monitor RAM in a second terminal while building:

```bash
# On the host, in a separate terminal
watch -n 3 free -h
```

The build takes approximately **45–60 minutes** with these settings.

---

## 19. Run the nvblox Quickstart Demo

Download the quickstart rosbag first (run on **host**, outside container):

```bash
sudo apt-get install -y curl jq tar

NGC_ORG="nvidia"
NGC_TEAM="isaac"
NGC_RESOURCE="isaac_ros_nvblox_assets"
NGC_FILENAME="quickstart.tar.gz"
MAJOR_VERSION=3
MINOR_VERSION=2
VERSION_REQ_URL="https://catalog.ngc.nvidia.com/api/resources/versions?orgName=$NGC_ORG&teamName=$NGC_TEAM&name=$NGC_RESOURCE&isPublic=true&pageNumber=0&pageSize=100&sortOrder=CREATED_DATE_DESC"
AVAILABLE_VERSIONS=$(curl -s -H "Accept: application/json" "$VERSION_REQ_URL")
LATEST_VERSION_ID=$(echo $AVAILABLE_VERSIONS | jq -r "
    .recipeVersions[]
    | .versionId as \$v
    | \$v | select(test(\"^\\\\d+\\\\.\\\\d+\\\\.\\\\d+$\"))
    | split(\".\") | {major: .[0]|tonumber, minor: .[1]|tonumber, patch: .[2]|tonumber}
    | select(.major == $MAJOR_VERSION and .minor <= $MINOR_VERSION)
    | \$v
    " | sort -V | tail -n 1
)
if [ -z "$LATEST_VERSION_ID" ]; then
    echo "No version found for Isaac ROS $MAJOR_VERSION.$MINOR_VERSION"
else
    mkdir -p ${ISAAC_ROS_WS}/isaac_ros_assets && \
    FILE_REQ_URL="https://api.ngc.nvidia.com/v2/resources/$NGC_ORG/$NGC_TEAM/$NGC_RESOURCE/versions/$LATEST_VERSION_ID/files/$NGC_FILENAME" && \
    curl -LO --request GET "${FILE_REQ_URL}" && \
    tar -xf ${NGC_FILENAME} -C ${ISAAC_ROS_WS}/isaac_ros_assets && \
    rm ${NGC_FILENAME}
fi
```

Then run inside the container:

```bash
source /opt/ros/humble/setup.bash
source /workspaces/isaac_ros-dev/install/setup.bash

ros2 launch nvblox_examples_bringup isaac_sim_example.launch.py \
  rosbag:=${ISAAC_ROS_WS}/isaac_ros_assets/isaac_ros_nvblox/quickstart \
  navigation:=False
```

This plays back a pre-recorded rosbag — no camera required. You should see a 3D mesh reconstruction in RViz.

---

## 20. Run Live RealSense Mapping

Plug in your D435i to USB 3, enter the container, and run:

```bash
source /opt/ros/humble/setup.bash
source /workspaces/isaac_ros-dev/install/setup.bash

# Verify camera is detected
rs-enumerate-devices

# Launch live mapping (RViz on local display)
ros2 launch nvblox_examples_bringup realsense_example.launch.py

# OR with Foxglove for remote visualization (recommended for headless/remote use)
ros2 launch nvblox_examples_bringup realsense_example.launch.py \
  run_foxglove:=True \
  run_rviz:=False \
  layer_streamer_bandwidth_limit_mbps:=30
```

---

## 21. Set Up Foxglove Visualization

Foxglove lets you visualize the nvblox stream from a **separate device** (laptop, tablet) over WiFi without needing a monitor on the Jetson.

**On your remote device:**
1. Download Foxglove Studio from https://foxglove.dev/download (or use https://studio.foxglove.dev in Chrome)
2. Open Foxglove Studio → click **"Open connection"**
3. Select **"Foxglove WebSocket"**
4. Enter the URL: `ws://<JETSON_IP>:8765`
   - Find your Jetson's IP with: `hostname -I | awk '{print $1}'`
5. Install the **nvblox extension**: Extensions sidebar → search "nvblox" → Install

**Inside the container**, start the Foxglove bridge in a separate terminal:

```bash
source /opt/ros/humble/setup.bash
source /workspaces/isaac_ros-dev/install/setup.bash
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
```

**Topics to add in Foxglove:**
- `/nvblox_node/mesh` — 3D reconstruction mesh
- `/nvblox_node/static_esdf_pointcloud` — 2D distance field slice
- `/camera/color/image_raw` — live camera (avoid over WiFi, high bandwidth)

---

## 22. Saving Maps and Recording Bags

### Save the nvblox Map to Disk

Call this service **while nvblox is running** (in a second terminal inside the container):

```bash
mkdir -p /ssd/workspaces/semantic_mapping/saved_maps

ros2 service call /nvblox_node/save_map \
  nvblox_msgs/srv/FilePath \
  "{file_path: '/ssd/workspaces/semantic_mapping/saved_maps/my_map'}"
```

### Record a Rosbag Without Auto-Deletion

```bash
mkdir -p /ssd/workspaces/semantic_mapping/recordings

ros2 bag record \
  /camera/color/image_raw \
  /camera/depth/image_rect_raw \
  /camera/color/camera_info \
  /camera/depth/camera_info \
  /camera/imu \
  /tf \
  /tf_static \
  --output /ssd/workspaces/semantic_mapping/recordings/session_$(date +%Y%m%d_%H%M%S) \
  --max-bag-size 0 \
  --max-cache-size 0
```

### Replay a Saved Bag Through nvblox

```bash
ros2 launch nvblox_examples_bringup realsense_example.launch.py \
  rosbag:=/ssd/workspaces/semantic_mapping/recordings/<your_bag_folder> \
  run_foxglove:=True \
  run_rviz:=False
```

---

## 23. Known Bugs and Fixes

### Bug: `isaac-ros-cli` package not found
**Cause:** `isaac-ros activate` / `isaac-ros-cli` does not exist for Ubuntu 22.04. It is Isaac ROS 4.x only.
**Fix:** Use `./scripts/run_dev.sh` instead of `isaac-ros activate` for all container operations.

### Bug: 404 on `isaac.download.nvidia.com/isaac-ros/ubuntu/main`
**Cause:** Stale/incorrect apt source entry pointing to a non-existent path.
**Fix:**
```bash
sudo rm -f /etc/apt/sources.list.d/isaac-ros.list
grep -r "isaac.download.nvidia.com" /etc/apt/  # should return nothing
# Then re-add the correct repo from Step 9
```

### Bug: `W: Skipping acquire... component 'main' misspelt`
**Cause:** Isaac ROS release-3 repo uses a flat structure, not a `main` component.
**Fix:** The `.list` entry must end with `jammy/` not `jammy main`. See Step 9.

### Bug: `nvblox_core/cmake/cuda/setup_compute_capability.cmake` not found
**Cause:** `isaac_ros_nvblox` was cloned without initializing git submodules.
**Fix:**
```bash
cd ${ISAAC_ROS_WS}/src/isaac_ros_nvblox
git submodule update --init --recursive
```

### Bug: `magic_enum::magic_enum` target not found
**Cause:** `isaac_ros_nitros` was cloned from source and attempted to build — it requires `magic_enum` which is not available.
**Fix:** Remove `isaac_ros_nitros` from `src/` and install it via apt instead. Never build it from source.
```bash
rm -rf ${ISAAC_ROS_WS}/src/isaac_ros_nitros
# Then install inside container: sudo apt-get install -y ros-humble-isaac-ros-nitros
```

### Bug: `CMAKE_PREFIX_PATH` missing `/opt/ros/humble`
**Cause:** The container entrypoint sources the workspace overlay before ROS, which prevents `/opt/ros/humble` from being added to the path.
**Fix:** Manually export it every session:
```bash
source /opt/ros/humble/setup.bash
export CMAKE_PREFIX_PATH=/opt/ros/humble:$CMAKE_PREFIX_PATH
```

### Bug: Jetson freezes/crashes during `colcon build`
**Cause:** Default colcon uses all CPU cores and RAM simultaneously, overwhelming the Orin Nano.
**Fix:** Always use throttled build flags (see Step 18). Monitor RAM with `watch -n 3 free -h`.

### Bug: apt-installed packages missing after container restart
**Cause:** Docker containers are stateless — apt installs inside the container do not persist.
**Fix:** Always re-run `rosdep install` and apt installs at the start of each container session (Step 17).

---

## 24. Every Session Checklist

Each time you restart the Jetson and want to work on this project, run through this checklist:

**On the host (`drone@jetson`):**
```bash
# 1. Verify swap is active (zram should show ~3.7GB)
free -h

# 2. Set performance mode
sudo /usr/bin/jetson_clocks
sudo /usr/sbin/nvpmodel -m 0

# 3. Plug in RealSense D435i to USB 3

# 4. Enter the container
cd ${ISAAC_ROS_WS}/src/isaac_ros_common && ./scripts/run_dev.sh
```

**Inside the container (`admin@jetson`):**
```bash
# 5. Fix environment
source /opt/ros/humble/setup.bash
export CMAKE_PREFIX_PATH=/opt/ros/humble:$CMAKE_PREFIX_PATH

# 6. Re-install dependencies (lost on container restart)
sudo apt-get update
rosdep update
rosdep install -i -r \
  --from-paths /workspaces/isaac_ros-dev/src/isaac_ros_nvblox/ \
  --from-paths /workspaces/isaac_ros-dev/src/realsense-ros/ \
  --rosdistro humble -y
sudo apt-get install -y ros-humble-foxglove-bridge

# 7. Source the built workspace
source /workspaces/isaac_ros-dev/install/setup.bash

# 8. Verify camera
rs-enumerate-devices
```

---

## Project Goals

- [ ] Live 3D semantic mapping with nvblox + RealSense D435i
- [ ] Visual SLAM / localization with cuVSLAM
- [ ] People segmentation overlay on map
- [ ] Map persistence across sessions
- [ ] Remote visualization via Foxglove
- [ ] Executable scripts for one-command launch of full pipeline

---

## Repository Structure

```
semantic_mapping/
├── src/
│   ├── isaac_ros_common/        ← NVIDIA (gitignored)
│   ├── isaac_ros_nvblox/        ← NVIDIA (gitignored)
│   ├── isaac_ros_image_pipeline/← NVIDIA (gitignored)
│   ├── isaac_ros_compression/   ← NVIDIA (gitignored)
│   └── realsense-ros/           ← Intel  (gitignored)
├── build/                       ← gitignored
├── install/                     ← gitignored
├── log/                         ← gitignored
├── isaac_ros_assets/            ← gitignored
├── saved_maps/                  ← nvblox saved maps
├── recordings/                  ← rosbag recordings (gitignored)
├── scripts/                     ← launch/automation scripts (tracked)
├── config/                      ← custom configs (tracked)
├── README.md
└── .gitignore
```