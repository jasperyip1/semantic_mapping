import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from vision_msgs.msg import Detection2DArray  # Standard ROS 2 message for bounding boxes
from cv_bridge import CvBridge
import image_geometry
import numpy as np

class ObjectLocatorNode(Node):
    def __init__(self):
        super().__init__('object_locator_node')
        self.bridge = CvBridge()
        
        # 1. Initialize the Camera Model from image_geometry
        self.camera_model = image_geometry.PinholeCameraModel()
        self.latest_depth_img = None

        # 2. Subscribe to the Camera Info
        self.info_sub = self.create_subscription(
            CameraInfo,
            '/camera0/color/camera_info',
            self.info_callback,
            10)

        # 3. Subscribe to the Aligned Depth Image (CRITICAL for Realsense)
        self.depth_sub = self.create_subscription(
            Image,
            '/camera0/aligned_depth_to_color/image_raw',
            self.depth_callback,
            10)

        # 4. Subscribe to the detections coming from your NanoOwl Node
        self.detection_sub = self.create_subscription(
            Detection2DArray,
            '/nanoowl/detections',  # You will need to make NanoOwl publish to this
            self.detection_callback,
            10)

        self.get_logger().info("Object Locator Node Ready. Waiting for data...")

    def info_callback(self, msg):
        # Update the camera model with intrinsic parameters
        self.camera_model.fromCameraInfo(msg)

    def depth_callback(self, msg):
        try:
            # Convert ROS Depth Image to OpenCV format (usually 16-bit unsigned for Realsense)
            self.latest_depth_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        except Exception as e:
            self.get_logger().error(f"Failed to convert depth image: {e}")

    def detection_callback(self, msg):
        if self.latest_depth_img is None or not self.camera_model.cameraInfo:
            self.get_logger().warn("Waiting for depth image and camera info to initialize...")
            return

        for detection in msg.detections:
            # Get the center (u, v) pixel of the bounding box
            u = int(detection.bbox.center.position.x)
            v = int(detection.bbox.center.position.y)

            height, width = self.latest_depth_img.shape
            
            # Ensure coordinates are within image bounds
            if u < 0 or u >= width or v < 0 or v >= height:
                continue

            # RealSense depth is typically reported in millimeters (16-bit)
            depth_mm = self.latest_depth_img[v, u]
            
            # Depth of 0 means the camera couldn't read the distance (too close/far/reflective)
            if depth_mm == 0:
                self.get_logger().warn(f"Depth is 0 at pixel ({u}, {v}). Cannot determine 3D location.")
                continue

            # Convert depth to meters
            depth_m = float(depth_mm) / 1000.0

            # Generate a normalized 3D ray through the pixel
            ray_normalized = self.camera_model.projectPixelTo3dRay((u, v))

            # Scale the ray by the actual depth to get the final 3D point (X, Y, Z)
            # Realsense Camera Frame: X is right, Y is down, Z is forward
            x = ray_normalized[0] * depth_m
            y = ray_normalized[1] * depth_m
            z = depth_m

            # You can extract a class ID or label if you published it from NanoOwl
            class_id = detection.results[0].hypothesis.class_id 
            
            self.get_logger().info(
                f"Object detected at -> X: {x:.3f}m, Y: {y:.3f}m, Z: {z:.3f}m (Distance: {depth_m:.3f}m)"
            )

def main(args=None):
    rclpy.init(args=args)
    node = ObjectLocatorNode()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()