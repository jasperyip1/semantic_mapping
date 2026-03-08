# Nvblox 3D Mesh Export Guide
### Jetson Orin Nano · Isaac ROS (Humble) · RealSense Camera · Docker Environment

---

## Overview

This guide documents the full workflow for capturing, recording, and exporting a colored `.ply` 3D mesh from Isaac ROS `nvblox` on a Jetson Orin Nano. The process covers two main paths:

- **Part A — Live Hardware Recording:** Using a RealSense camera to capture and record a new map
- **Part B — Bag Playback & PLY Export:** Replaying a recorded bag and exporting the full colored mesh

> **Note:** The built-in `save_ply` service (`/nvblox_node/save_ply`) has a known issue where it reports `"No points added, nothing to output"` even when mesh data is visible in RViz. The workaround documented in Part B bypasses this by subscribing directly to the mesh topic.

---

## Part A — Live Hardware Recording (RealSense Camera)

Use this section when recording a new map from scratch with a physical RealSense camera.

### How It Works

The `realsense_splitter` node is NVIDIA's required middleware for RealSense data. It ensures that Visual SLAM and `nvblox` don't conflict over camera frames — both need depth data but must receive it through separate, managed channels.

---

### A1 — Terminal 1: Launch Visual SLAM

This starts the RealSense driver and NVIDIA's Visual SLAM, which tracks the camera's position in 3D space. Everything else depends on this running first.

```bash
source install/setup.bash
ros2 launch isaac_ros_visual_slam isaac_ros_visual_slam_realsense.launch.py
```

Wait until RViz shows the camera pose is tracking before moving on.

---

### A2 — Terminal 2: Launch Nvblox

This starts the 3D mapping engine that consumes the camera's depth stream and builds the mesh you see in RViz.

```bash
source install/setup.bash
ros2 launch nvblox_examples_bringup realsense_example.launch.py \
  run_rviz:=True run_foxglove:=False \
  voxel_size:=0.1
```

Wait until the mesh begins appearing in RViz before starting the recording.

---

### A3 — Terminal 3: Record the Bag

Once everything is green in RViz, start recording. **Recording the right topics is critical** — if `/tf` or `/tf_static` are missing, the bag will be unusable for mapping during playback.

```bash
source install/setup.bash
ros2 bag record \
  /camera/realsense_splitter_node/output/depth \
  /camera/depth/camera_info \
  /camera/color/image_raw \
  /tf \
  /tf_static \
  -o my_classroom_recording
```

> **Tip:** Walk slowly and steadily. If the camera motion blurs, Visual SLAM is far more likely to fail during playback with a `success=False` error, because the geometry becomes too inconsistent to reconstruct.

Press **Ctrl+C** in Terminal 3 when you are done recording. The bag will be saved to a folder named `my_classroom_recording/` in your current directory.

---

## Part B — Bag Playback & PLY Export

Use this section to replay any recorded bag file and export the full accumulated mesh as a `.ply` file.

---

### B1 — Create the Mesh Recording Script

Run this command inside the Docker container to create `save_mesh.py` in your current directory:

```bash
cat > save_mesh.py << 'EOF'
import rclpy
from rclpy.node import Node
from nvblox_msgs.msg import Mesh

class MeshSaver(Node):
    def __init__(self):
        super().__init__('mesh_saver')
        self.all_vertices = {}
        self.sub = self.create_subscription(
            Mesh, '/nvblox_node/mesh', self.callback, 10)
        self.get_logger().info("Recording mesh... Press Ctrl+C when bag finishes to save.")

    def callback(self, msg):
        new_verts = 0
        for block in msg.blocks:
            has_color = len(block.colors) == len(block.vertices)
            for i, v in enumerate(block.vertices):
                key = (round(v.x, 4), round(v.y, 4), round(v.z, 4))
                if key not in self.all_vertices:
                    if has_color:
                        c = block.colors[i]
                        self.all_vertices[key] = (c.r, c.g, c.b)
                    else:
                        self.all_vertices[key] = (255, 255, 255)
                    new_verts += 1
        self.get_logger().info(
            f"Batch received: +{new_verts} new | Total unique vertices: {len(self.all_vertices)}"
        )

    def save(self):
        output_path = '/tmp/mesh_from_topic.ply'
        verts = list(self.all_vertices.items())
        self.get_logger().info(f"Saving {len(verts)} vertices to {output_path}...")
        with open(output_path, 'w') as f:
            f.write("ply\nformat ascii 1.0\n")
            f.write(f"element vertex {len(verts)}\n")
            f.write("property float x\nproperty float y\nproperty float z\n")
            f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
            f.write("end_header\n")
            for (x, y, z), (r, g, b) in verts:
                f.write(f"{x} {y} {z} {int(r)} {int(g)} {int(b)}\n")
        self.get_logger().info(f"Done! Saved to {output_path}")

def main():
    rclpy.init()
    node = MeshSaver()
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.save()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
EOF
```

---

### B2 — Terminal 1: Start the Recording Script

Source your workspace and start the script. It will wait silently until the bag begins publishing mesh data.

```bash
source install/setup.bash && python3 save_mesh.py
```

Expected output:
```
[INFO] [mesh_saver]: Recording mesh... Press Ctrl+C when bag finishes to save.
```

---

### B3 — Terminal 2: Launch Nvblox and Play the Bag

This single command launches Nvblox, RViz, and plays back the bag all at once. Replace the `rosbag` path with the path to your own recording folder.

```bash
source install/setup.bash
ros2 launch nvblox_examples_bringup realsense_example.launch.py \
  rosbag:=/workspaces/isaac_ros-dev/my_classroom_recording_3
```

> **Note:** Pass the **folder path**, not a `.db3` file. The launch file finds the bag file inside automatically.

As the bag plays, Terminal 1 will log each incoming batch of vertices:
```
[INFO] [mesh_saver]: Batch received: +7428 new | Total unique vertices: 7428
[INFO] [mesh_saver]: Batch received: +3201 new | Total unique vertices: 10629
...
```

---

### B5 — Save the File

When the bag finishes playing, go back to **Terminal 1** and press **Ctrl+C**.

The script will immediately save everything it accumulated:
```
[INFO] [mesh_saver]: Saving 45320 vertices to /tmp/mesh_from_topic.ply...
[INFO] [mesh_saver]: Done! Saved to /tmp/mesh_from_topic.ply
```

---

### B6 — Transfer the File to the Host Desktop

Open a terminal **on the Jetson host** (outside the Docker container) and run:

```bash
docker cp $(docker ps -q):/tmp/mesh_from_topic.ply ~/Desktop/mesh_from_topic.ply
```

`docker ps -q` automatically finds the running container ID. The file will appear on your desktop at `~/Desktop/mesh_from_topic.ply`.

---

## Full Workflow Summary

| Step | What It Does | Command |
|------|-------------|---------|
| 1 | Launch Visual SLAM | `isaac_ros_visual_slam_realsense.launch.py` |
| 2 | Launch Nvblox | `realsense_example.launch.py` |
| 3 | Record Bag | `ros2 bag record ...` |
| 4 | Start mesh capture script | `python3 save_mesh.py` |
| 5 | Launch Nvblox + play bag | `realsense_example.launch.py rosbag:=<path>` |
| 6 | Save on Ctrl+C | Script auto-saves to `/tmp/mesh_from_topic.ply` |
| 7 | Transfer to desktop | `docker cp ... ~/Desktop/` |

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `save_ply` returns "No points added" | Known nvblox service bug on Orin Nano | Use the Python subscriber script in Part B instead |
| Ctrl+C doesn't stop the script | `rclpy.spin()` blocks signal handling | Use `spin_once()` loop — already in the script above |
| GPU shader warning in RViz | Orin Nano lacks geometry shader support | Cosmetic only, does not affect data capture |
| `success=False` during SLAM | Camera motion blur during recording | Re-record walking more slowly and steadily |
| Vertices missing color (all white) | `block.colors` array is empty for that block | Data issue in the bag; geometry is still correct |
| Bag playback produces no mesh | `/tf` or `/tf_static` not recorded | Re-record with all required topics listed in A3 |

---

## Output File Format

The output `.ply` is an **ASCII colored point cloud** with the following properties per vertex:

```
x y z red green blue
```

It can be opened in:
- **MeshLab** (free, recommended)
- **CloudCompare** (free, good for large scans)
- **Blender** (via the PLY importer)
- **Open3D** (Python, for further processing)