# Nvblox 3D Mesh Export Guide
### Jetson Orin Nano · Isaac ROS (Humble) · Docker Environment

---

## Overview

This guide documents the full workflow for exporting a colored `.ply` 3D mesh from Isaac ROS `nvblox` on a Jetson Orin Nano. The process involves:
1. Playing back a ROS 2 bag file through the `nvblox_node`
2. Capturing the live `/nvblox_node/mesh` topic with a Python subscriber
3. Saving the accumulated colored point cloud as a `.ply` file
4. Transferring the file from the Docker container to the host desktop

> **Note:** The built-in `save_ply` service (`/nvblox_node/save_ply`) has a known issue where it reports `"No points added, nothing to output"` even when mesh data is visible in RViz. The workaround is to subscribe directly to the mesh topic.

---

## Prerequisites

- Docker container running with Isaac ROS Humble
- ROS 2 workspace sourced inside the container
- Bag file located at a known path (e.g. `/path/to/gym_classroom_map_bag_1_0.db3`)
- Two terminals open inside the Docker container

---

## Step 1: Create the Mesh Recording Script

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

## Step 2: Start the Recording Script

In **Terminal 1**, source your workspace and start the script:

```bash
source install/setup.bash && python3 save_mesh.py
```

You should see:
```
[INFO] [mesh_saver]: Recording mesh... Press Ctrl+C when bag finishes to save.
```

The script will now wait silently until the bag starts publishing mesh data.

---

## Step 3: Play Back the Bag File

In **Terminal 2**, source your workspace and play the bag from the beginning:

```bash
source install/setup.bash
ros2 bag play /path/to/gym_classroom_map_bag_1_0.db3 --start-offset 0
```

Replace `/path/to/` with the actual path to your bag file.

As the bag plays, you will see Terminal 1 logging batches of new vertices accumulating:
```
[INFO] [mesh_saver]: Batch received: +7428 new | Total unique vertices: 7428
[INFO] [mesh_saver]: Batch received: +3201 new | Total unique vertices: 10629
...
```

---

## Step 4: Save the File

When the bag finishes playing, go back to **Terminal 1** and press:

```
Ctrl+C
```

The script will immediately save everything it has accumulated:
```
[INFO] [mesh_saver]: Saving 45320 vertices to /tmp/mesh_from_topic.ply...
[INFO] [mesh_saver]: Done! Saved to /tmp/mesh_from_topic.ply
```

The `.ply` file is now saved inside the Docker container at `/tmp/mesh_from_topic.ply`.

---

## Step 5: Transfer the File to the Host Desktop

Open a terminal **on the Jetson host** (outside the Docker container) and run:

```bash
docker cp $(docker ps -q):/tmp/mesh_from_topic.ply ~/Desktop/mesh_from_topic.ply
```

`docker ps -q` automatically finds the running container ID. The file will appear on your desktop at `~/Desktop/mesh_from_topic.ply`.

---

## Notes & Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `save_ply` returns "No points added" | Known nvblox service bug on Orin Nano | Use the Python subscriber script instead |
| Ctrl+C doesn't stop the script | `rclpy.spin()` blocks signal handling | Use `spin_once()` loop — already in the script above |
| GPU shader warning in RViz | Orin Nano lacks geometry shader support | Cosmetic only, does not affect data capture |
| Vertices missing color (all white) | `block.colors` array is empty for that block | Data issue in the bag; geometry is still correct |
| Script exits before bag finishes | Script ran before nvblox node was ready | Restart script and ensure nvblox node is active first |

---

## File Format

The output `.ply` is an **ASCII colored point cloud** with the following properties per vertex:

```
x y z red green blue
```

It can be opened in:
- **MeshLab** (free, recommended)
- **CloudCompare** (free, good for large scans)
- **Blender** (via the PLY importer)
- **Open3D** (Python, for further processing)