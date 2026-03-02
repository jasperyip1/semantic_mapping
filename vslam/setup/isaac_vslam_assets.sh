#!/bin/bash

# Ensure ISAAC_ROS_WS is set, preventing assets from downloading to the root directory.
# Defaults to standard ~/workspaces/isaac_ros-dev if not set by the Isaac ROS 3.2 CLI.
if [ -z "$ISAAC_ROS_WS" ]; then
  export ISAAC_ROS_WS=~/workspaces/isaac_ros-dev
  echo "Warning: ISAAC_ROS_WS was not set. Defaulting to $ISAAC_ROS_WS"
fi

NGC_ORG="nvidia"
NGC_TEAM="isaac"
PACKAGE_NAME="isaac_ros_visual_slam"
NGC_RESOURCE="isaac_ros_visual_slam_assets"
NGC_FILENAME="quickstart.tar.gz"

# Targeting Isaac ROS 3.2 specifically
MAJOR_VERSION=3
MINOR_VERSION=2

# Check for jq and curl, which are required for the NGC API request
if ! command -v jq &> /dev/null || ! command -v curl &> /dev/null; then
    echo "Error: 'jq' or 'curl' is not installed. Please run: sudo apt-get install -y curl jq"
    exit 1
fi

VERSION_REQ_URL="https://catalog.ngc.nvidia.com/api/resources/versions?orgName=$NGC_ORG&teamName=$NGC_TEAM&name=$NGC_RESOURCE&isPublic=true&pageNumber=0&pageSize=100&sortOrder=CREATED_DATE_DESC"

AVAILABLE_VERSIONS=$(curl -s -H "Accept: application/json" "$VERSION_REQ_URL")

LATEST_VERSION_ID=$(echo "$AVAILABLE_VERSIONS" | jq -r "
    .recipeVersions[]
    | .versionId as \$v
    | \$v | select(test(\"^\\\\d+\\\\.\\\\d+\\\\.\\\\d+$\"))
    | split(\".\") | {major: .[0]|tonumber, minor: .[1]|tonumber, patch: .[2]|tonumber}
    | select(.major == $MAJOR_VERSION and .minor <= $MINOR_VERSION)
    | \$v
    " | sort -V | tail -n 1
)

if [ -z "$LATEST_VERSION_ID" ]; then
    echo "No corresponding version found for Isaac ROS $MAJOR_VERSION.$MINOR_VERSION"
    echo "Found versions:"
    echo "$AVAILABLE_VERSIONS" | jq -r '.recipeVersions[].versionId'
    exit 1
else
    echo "Downloading assets for Isaac ROS version: $LATEST_VERSION_ID"
    mkdir -p "${ISAAC_ROS_WS}/isaac_ros_assets" && \
    FILE_REQ_URL="https://api.ngc.nvidia.com/v2/resources/$NGC_ORG/$NGC_TEAM/$NGC_RESOURCE/versions/$LATEST_VERSION_ID/files/$NGC_FILENAME" && \
    curl -LO --request GET "${FILE_REQ_URL}" && \
    tar -xf "${NGC_FILENAME}" -C "${ISAAC_ROS_WS}/isaac_ros_assets" && \
    rm "${NGC_FILENAME}"
    
    echo "Isaac ROS Visual SLAM assets successfully downloaded and extracted to ${ISAAC_ROS_WS}/isaac_ros_assets!"
fi