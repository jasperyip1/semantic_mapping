## Spatial Object Locator

This node translates 2D object detections from NanoOWL into 3D world coordinates relative to the Intel RealSense D435i camera. It avoids the high CPU overhead of processing full 3D PointClouds by performing targeted math on the 2D aligned depth image.

### How It Works

1. **Median Patch Extraction (The "Hole" Fix):** Infrared depth sensors often return `0` (unknown) on reflective, transparent, or overly dark surfaces. Instead of blindly trusting the exact center pixel of a bounding box, this node extracts a `20x20` pixel Region of Interest (ROI) around the center. It uses `numpy` to filter out all `0` values and calculates the **median** depth of the remaining valid pixels, ensuring a highly robust distance measurement.
2. **Dynamic Camera Intrinsics:** Instead of hardcoding the RealSense FOV or focal lengths, the node subscribes to the live `/camera/color/camera_info` topic. It feeds this data into `image_geometry.PinholeCameraModel`, which dynamically generates the exact mathematical model of your specific physical lens.
3. **3D Ray Projection:** Once the median depth ($Z$) is found, the node uses the `PinholeCameraModel` to shoot a normalized 3D ray through the 2D pixel coordinate $(u, v)$. By multiplying the $X$ and $Y$ components of this normalized ray by our physical depth ($Z$), we obtain the precise $(X, Y, Z)$ spatial coordinate of the object in meters, relative to the camera lens.
4. **Edge-Case Safety:** Added dynamic bounds-checking to ensure that if an object is detected at the extreme edge of the camera frame, the ROI patch calculation will not attempt to read pixels outside the image array, preventing `IndexError` crashes.

---

## Installation & Setup

To run this ROS 2 node, you need to ensure your environment has the standard ROS 2 vision libraries, Python dependencies, and the Intel RealSense ROS 2 wrapper installed.

The following instructions assume you are using a modern ROS 2 distribution (like Humble, Iron, or Jazzy) on Ubuntu.

### Step 1: Install ROS 2 Vision & Geometry Packages

These are the core ROS 2 libraries used for vision messages, OpenCV image conversions, and the pinhole camera mathematics. Open your terminal and run:

```bash
sudo apt update
sudo apt install ros-$ROS_DISTRO-vision-msgs \
                 ros-$ROS_DISTRO-cv-bridge \
                 ros-$ROS_DISTRO-image-geometry
```

### Step 2: Install Python Dependencies

Ensure that `numpy` and `opencv-python` are installed to process the image matrices and calculate the median depth:

```bash
pip3 install numpy opencv-python
```

### Step 3: Install the Intel RealSense ROS 2 Wrapper

If you haven't already installed the official RealSense drivers, you will need the `realsense2_camera` package to publish the aligned depth topics:

```bash
sudo apt install ros-$ROS_DISTRO-realsense2-camera
```

### Step 4: Launching the RealSense (Crucial)

When you spin up your camera, you must tell the RealSense wrapper to align the depth stream to the color stream. If you skip this, the 2D pixel coordinates from NanoOWL will not match the physical world.

Launch the camera by passing the `align_depth.enable` flag:

```bash
ros2 launch realsense2_camera rs_launch.py align_depth.enable:=true
```

### Step 5: Run the Pipeline

1. Start the NanoOWL node (ensure it is publishing to `/nanoowl/detections`).
2. Start the spatial locator node:

```bash
python3 object_locator_node.py
```