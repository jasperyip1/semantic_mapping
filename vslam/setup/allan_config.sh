#!/bin/bash

# In Isaac ROS 3.2 (ROS 2 Jazzy), the default rosbag format is .mcap instead of .db3.
# The script now looks for both format types to ensure backwards compatibility.
BAG_DIR="/home/analysis/imu_rosbag"
BAG_FILE=$(find "$BAG_DIR" -maxdepth 1 -type f \( -name "*.mcap" -o -name "*.db3" \) | head -n 1)

# Check if a bag file was found
if [ -z "$BAG_FILE" ]; then
  echo "No .mcap or .db3 file found in $BAG_DIR"
  exit 1
fi

echo "Found rosbag file: $BAG_FILE"

# Define workspace directory explicitly for easier configuration
WORKSPACE_DIR=~/ros2_ws
CONFIG_FILE="$WORKSPACE_DIR/src/allan_ros2/config/config.yaml"

# Overwrite the config.yaml file with the found bag path
cat << EOF > "$CONFIG_FILE"
allan_node:
  ros__parameters:
     topic: /camera/imu
     bag_path: $BAG_FILE
     msg_type: ros
     publish_rate: 200
     sample_rate: 200
EOF

echo "Configuration file updated successfully at $CONFIG_FILE"

# Change directory to the ros2 workspace
cd "$WORKSPACE_DIR" || { echo "Failed to change directory to $WORKSPACE_DIR"; exit 1; }

# Build the allan_ros2 package
# Added --symlink-install, which is the recommended default for ROS 2 Jazzy development
echo "Building allan_ros2 package..."
colcon build --packages-select allan_ros2 --symlink-install
if [ $? -ne 0 ]; then
    echo "Build failed."
    exit 1
fi

# Source the workspace
echo "Sourcing the workspace..."
source "$WORKSPACE_DIR/install/setup.bash"

echo "Build and source complete."