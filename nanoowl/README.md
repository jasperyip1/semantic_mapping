# 🦉 Spatial Object Locator (NanoOWL + Image Geometry + TF2)

This project translates 2D object detections from NVIDIA's NanoOWL into 3D absolute world coordinates. It uses `image_geometry` to calculate depth from an aligned RealSense depth stream and `tf2` to lock those coordinates to an absolute VSLAM map frame (e.g., `map` or `odom`).

### Environment

- **OS:** Ubuntu 22.04
- **ROS 2:** Humble
- **Framework:** Isaac ROS 3.2 (NVBlox)
- **Hardware:** Intel RealSense D435i / D455

---

## 🛠️ 1. Installation & Dependencies

Open your terminal and install the required ROS 2 Humble packages. These handle the vision messages, image conversions, camera mathematics, and spatial transformations.

```bash
sudo apt update
sudo apt install ros-humble-vision-msgs \
                 ros-humble-cv-bridge \
                 ros-humble-image-geometry \
                 ros-humble-tf2-ros \
                 ros-humble-tf2-geometry-msgs
```

Next, ensure you have the required Python libraries for matrix math and image processing:

```bash
pip3 install numpy opencv-python Pillow
```

### Note on NanoOWL

This pipeline assumes you have already installed and built NVIDIA's **NanoOWL** and generated the TensorRT engine (`owlvit-base-patch32-image-encoder.engine`). If you have not, follow the official NVIDIA NanoOWL repository instructions to build the engine for your specific GPU before running this node.

---

## ⚙️ 2. Configuration (CRITICAL)

Because this setup relies on Isaac ROS and NVBlox launch files, you **must** ensure the RealSense camera is publishing an aligned depth stream.

1. Navigate to your `nvblox_examples_bringup` config directory.
2. Open both `realsense_emitter_flashing.yaml` and `realsense_emitter_on.yaml`.
3. Locate the `camera0` parameters and ensure `align_depth.enable` is set to `true`:

```yaml
camera0:
  ros__parameters:
    align_depth:
      enable: true
```

> If this is set to `false`, the locator node will wait indefinitely for the `/camera0/aligned_depth_to_color/image_raw` topic.

---

## 🚀 3. Building the Workspace

1. Place `nanoowl_node.py` and `object_locator_node.py` into the `src` folder of your ROS 2 Python package.

2. Ensure they are marked as executable:

```bash
chmod +x nanoowl_node.py
chmod +x object_locator_node.py
```

3. Update your `setup.py` entry points so ROS 2 knows how to run them:

```python
entry_points={
    'console_scripts': [
        'nanoowl_node = your_package_name.nanoowl_node:main',
        'object_locator_node = your_package_name.object_locator_node:main',
    ],
},
```

4. Navigate to the root of your `colcon_ws` and build:

```bash
colcon build --symlink-install
source install/setup.bash
```

---

## 🏃 4. Running the Pipeline

You will need three separate terminal windows. Make sure to source your workspace in each one: `source install/setup.bash`.

**Terminal 1: Launch the Cameras & VSLAM**

Run your custom NVBlox/RealSense launch file.

```bash
ros2 launch <your_launch_package> <your_launch_file>.py
```

**Terminal 2: Start NanoOWL**

This node subscribes to the RealSense color stream using the `sensor_data` QoS profile and publishes 2D bounding boxes.

```bash
ros2 run <your_package_name> nanoowl_node
```

**Terminal 3: Start the Spatial Locator**

This node subscribes to the NanoOWL detections, the RealSense depth stream, and the camera info. It calculates the 3D position and uses `tf2` to print the absolute map coordinates.

```bash
ros2 run <your_package_name> object_locator_node
```

---

## 🔍 Troubleshooting

- **No output from Locator Node?** Check if the depth topic exists: `ros2 topic hz /camera0/aligned_depth_to_color/image_raw`. If it reports no new messages, double-check your YAML config from Step 2.
- **TF2 Transform Exception?** Ensure your VSLAM system is actively publishing the transform tree from `map` → `camera0_color_optical_frame`. Verify by running `ros2 run tf2_tools view_frames`.
- **NanoOWL Crashing?** Verify that your TensorRT engine path in `nanoowl_node.py` correctly points to where you generated your `.engine` file.