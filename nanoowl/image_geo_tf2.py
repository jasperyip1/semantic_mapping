import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from vision_msgs.msg import Detection2DArray
from geometry_msgs.msg import PointStamped # NEW: Used for holding 3D coordinates
from cv_bridge import CvBridge
import image_geometry
import numpy as np

# NEW: tf2 imports for coordinate transformations
from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener
import tf2_geometry_msgs 

class ObjectLocatorNode(Node):
    def __init__(self):
        super().__init__('object_locator_node')
        self.bridge = CvBridge()
        
        self.camera_model = image_geometry.PinholeCameraModel()
        self.latest_depth_img = None
        self.camera_info_received = False

        # --- NEW: Initialize tf2 Buffer and Listener ---
        # The buffer stores a rolling history of the robot's VSLAM movements
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        
        # Define the absolute frame you want to lock the object to
        # VSLAM typically uses 'map' or 'odom'. Check your VSLAM tf tree!
        self.target_world_frame = 'map' 
        # -----------------------------------------------

        self.info_sub = self.create_subscription(
            CameraInfo,
            '/camera/color/camera_info', 
            self.info_callback,
            10)

        self.depth_sub = self.create_subscription(
            Image,
            '/camera/aligned_depth_to_color/image_raw',
            self.depth_callback,
            10)

        self.detection_sub = self.create_subscription(
            Detection2DArray,
            '/nanoowl/detections',
            self.detection_callback,
            10)

        self.get_logger().info("Object Locator Node Initialized. Waiting for data...")

    def info_callback(self, msg):
        if not self.camera_info_received:
            self.camera_model.fromCameraInfo(msg)
            self.camera_info_received = True
            self.get_logger().info("Camera Info received and model initialized.")

    def depth_callback(self, msg):
        try:
            self.latest_depth_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        except Exception as e:
            self.get_logger().error(f"Failed to convert depth image: {e}")

    def detection_callback(self, msg):
        if self.latest_depth_img is None or not self.camera_info_received:
            return

        img_height, img_width = self.latest_depth_img.shape

        for detection in msg.detections:
            u = int(detection.bbox.center.position.x)
            v = int(detection.bbox.center.position.y)
            class_id = detection.results[0].hypothesis.class_id

            if not (0 <= u < img_width and 0 <= v < img_height):
                continue

            patch_size = 10
            u_min = max(0, u - patch_size)
            u_max = min(img_width, u + patch_size)
            v_min = max(0, v - patch_size)
            v_max = min(img_height, v + patch_size)

            depth_patch = self.latest_depth_img[v_min:v_max, u_min:u_max]
            valid_depths = depth_patch[depth_patch > 0]

            if valid_depths.size == 0:
                continue

            median_depth_mm = np.median(valid_depths)
            z_meters = float(median_depth_mm) / 1000.0

            ray_normalized = self.camera_model.projectPixelTo3dRay((u, v))
            x_meters = ray_normalized[0] * z_meters
            y_meters = ray_normalized[1] * z_meters

            # --- NEW: TF2 Transformation Logic ---
            
            # 1. Create a PointStamped in the camera's local coordinate frame
            point_camera = PointStamped()
            # CRITICAL: We use the timestamp from the incoming detection message. 
            # This tells tf2 to look up where the robot was in the past when the picture was snapped.
            point_camera.header.stamp = msg.header.stamp
            point_camera.header.frame_id = msg.header.frame_id # Usually 'camera_color_optical_frame'
            
            point_camera.point.x = x_meters
            point_camera.point.y = y_meters
            point_camera.point.z = z_meters

            try:
                # 2. Ask the tf buffer for the transform from the camera to the map
                # timeout ensures we don't wait forever if the tree is broken
                transform = self.tf_buffer.lookup_transform(
                    self.target_world_frame,
                    point_camera.header.frame_id,
                    point_camera.header.stamp,
                    rclpy.duration.Duration(seconds=0.1) 
                )

                # 3. Apply the matrix math to transform the point
                point_world = tf2_geometry_msgs.do_transform_point(point_camera, transform)

                # Output the absolute result!
                self.get_logger().info(
                    f"\n--- ABSOLUTE {class_id.upper()} LOCATION ---\n"
                    f"Frame: {self.target_world_frame}\n"
                    f"X: {point_world.point.x:.3f} m\n"
                    f"Y: {point_world.point.y:.3f} m\n"
                    f"Z: {point_world.point.z:.3f} m\n"
                    f"------------------------------"
                )

            except TransformException as ex:
                self.get_logger().warn(f"Could not transform object to absolute map frame: {ex}")

def main(args=None):
    rclpy.init(args=args)
    node = ObjectLocatorNode()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()