import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from vision_msgs.msg import Detection2DArray
from cv_bridge import CvBridge
import image_geometry
import numpy as np
import cv2

class ObjectLocatorNode(Node):
    def __init__(self):
        super().__init__('object_locator_node')
        self.bridge = CvBridge()
        
        # 1. Initialize the Camera Model
        self.camera_model = image_geometry.PinholeCameraModel()
        self.latest_depth_img = None
        self.camera_info_received = False

        # 2. Subscribe to the Camera Info
        self.info_sub = self.create_subscription(
            CameraInfo,
            '/camera/color/camera_info', # Check your specific Realsense topic name
            self.info_callback,
            10)

        # 3. Subscribe to the Aligned Depth Image
        self.depth_sub = self.create_subscription(
            Image,
            '/camera/aligned_depth_to_color/image_raw',
            self.depth_callback,
            10)

        # 4. Subscribe to the NanoOwl Detections
        self.detection_sub = self.create_subscription(
            Detection2DArray,
            '/nanoowl/detections',
            self.detection_callback,
            10)

        self.get_logger().info("Object Locator Node Initialized. Waiting for data...")

    def info_callback(self, msg):
        # We only need to set this once, but it's fine if it updates
        if not self.camera_info_received:
            self.camera_model.fromCameraInfo(msg)
            self.camera_info_received = True
            self.get_logger().info("Camera Info received and model initialized.")

    def depth_callback(self, msg):
        try:
            # Realsense depth is 16-bit unsigned integer (mm)
            self.latest_depth_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        except Exception as e:
            self.get_logger().error(f"Failed to convert depth image: {e}")

    def detection_callback(self, msg):
        if self.latest_depth_img is None or not self.camera_info_received:
            self.get_logger().warn("Waiting for depth image and camera info...")
            return

        img_height, img_width = self.latest_depth_img.shape

        for detection in msg.detections:
            # 1. Extract center pixel coordinates from the detection
            u = int(detection.bbox.center.position.x)
            v = int(detection.bbox.center.position.y)
            class_id = detection.results[0].hypothesis.class_id

            # Ensure center is inside the image bounds
            if not (0 <= u < img_width and 0 <= v < img_height):
                self.get_logger().warn(f"Detection {class_id} center out of bounds.")
                continue

            # 2. Define a Region of Interest (ROI) around the center
            # Let's use a 20x20 pixel patch (10 pixels in each direction)
            patch_size = 10
            
            # Safely calculate bounding box for the patch to avoid edge crashes
            u_min = max(0, u - patch_size)
            u_max = min(img_width, u + patch_size)
            v_min = max(0, v - patch_size)
            v_max = min(img_height, v + patch_size)

            # 3. Extract the depth patch
            depth_patch = self.latest_depth_img[v_min:v_max, u_min:u_max]

            # 4. Filter out zeros (invalid depth readings)
            valid_depths = depth_patch[depth_patch > 0]

            if valid_depths.size == 0:
                self.get_logger().warn(f"No valid depth data found for {class_id} at ({u}, {v}).")
                continue

            # 5. Calculate the median depth of the valid pixels
            median_depth_mm = np.median(valid_depths)
            z_meters = float(median_depth_mm) / 1000.0

            # 6. Use image_geometry to shoot a ray through the pixel
            # projectPixelTo3dRay returns a normalized 3D vector [X, Y, Z] where Z = 1.0
            
            ray_normalized = self.camera_model.projectPixelTo3dRay((u, v))

            # 7. Scale the normalized ray by our actual measured depth
            x_meters = ray_normalized[0] * z_meters
            y_meters = ray_normalized[1] * z_meters

            # Output the result
            self.get_logger().info(
                f"\n--- Object Found ---\n"
                f"Class: {class_id}\n"
                f"Pixel: (u: {u}, v: {v})\n"
                f"3D Position (Camera Frame):\n"
                f"  X (Right):   {x_meters:.3f} m\n"
                f"  Y (Down):    {y_meters:.3f} m\n"
                f"  Z (Forward): {z_meters:.3f} m\n"
                f"--------------------"
            )

def main(args=None):
    rclpy.init(args=args)
    node = ObjectLocatorNode()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()