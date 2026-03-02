# Phase 2: VSLAM Pose Forwarding to MAVROS

This guide is a direct continuation of the **Semantic Mapping — Jetson Orin Nano Setup Guide**. It assumes you have already completed the host setup, built the container, and applied the Dockerfile IMU patch *(Step 3 of the previous guide)*.

This workflow bridges the NVIDIA perception stack (Isaac ROS VSLAM) with the flight controller via MAVROS.

---

## Step 1: Start the Perception Stack (Inside Docker)

Launch the RealSense camera, cuVSLAM, and nvblox. To ensure the pose estimates are robust enough for flight, you must explicitly enable the IMU.

Inside your `admin@jetson` container, run:

```bash
ros2 launch nvblox_examples_bringup realsense_example.launch.py \
  run_rviz:=False run_foxglove:=True \
  layer_streamer_bandwidth_limit_mbps:=30 \
  voxel_size:=0.1 \
  enable_imu_fusion:=True
```

> **Note:** cuVSLAM is now broadcasting pose data to `/visual_slam/tracking/vo_pose_covariance`

---

## Step 2: Start the Flight Stack & Pose Relay

Your custom relay script (`mavrospy.launch.py`) will grab the cuVSLAM pose and pipe it directly to `/mavros/vision_pose/pose_cov` for the flight controller to use.

Open a new terminal on your host (or wherever your MAVROS workspace is configured). Ensure you have sourced both ROS 2 Humble and your MAVROS workspace, then launch the script directly from its file path:

```bash
# Example sourcing (modify if your MAVROS workspace is elsewhere)
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash

# Launch the relay and MAVROS connection
ros2 launch /ssd/workspaces/semantic_mapping/vslam/mavrospy.launch.py fcu_url:=/dev/ttyUSB0:921600 pattern:=square
```

> ⚠️ **Flight Controller Check:** If you are flying ArduPilot (ArduCopter), open `/ssd/workspaces/semantic_mapping/vslam/mavrospy.launch.py` and ensure `px4_launch_path` points to `apm.launch`, **not** `px4.launch`.

---

## Step 3: Verify the Connection

Before arming the drone, verify that the coordinate translation is working. Open a new terminal, source ROS 2, and echo the target MAVROS topic:

```bash
ros2 topic echo /mavros/vision_pose/pose_cov
```

If you see a continuous stream of pose data that updates when you physically move the Jetson/camera, your pose forwarding is successfully routing into the flight controller.