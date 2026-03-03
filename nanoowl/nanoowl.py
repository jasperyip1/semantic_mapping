import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

# --- CHANGED: Added the QoS profile import needed for RealSense cameras ---
from rclpy.qos import qos_profile_sensor_data 

# Import standard ROS 2 vision messages
from vision_msgs.msg import Detection2DArray, Detection2D, BoundingBox2D, ObjectHypothesisWithPose

# NanoOwl Imports
from nanoowl.owl_predictor import OwlPredictor
import PIL.Image
import cv2

class NanoOwlNode(Node):
    def __init__(self):
        super().__init__('nanoowl_node')
        
        # 1. Initialize the NanoOwl Predictor
        self.get_logger().info("Initializing NanoOwl...")
        self.predictor = OwlPredictor(
            "google/owlvit-base-patch32",
            image_encoder_engine="data/owlvit-base-patch32-image-encoder.engine"
        )
        self.bridge = CvBridge()
        self.get_logger().info("NanoOwl Ready.")

        # 2. Image Subscriber 
        # --- CHANGED: Replaced '10' with 'qos_profile_sensor_data' ---
        # This allows the node to accept the Best-Effort video stream from the RealSense
        self.subscription = self.create_subscription(
            Image,
            '/camera/color/image_raw',  
            self.image_callback,
            qos_profile_sensor_data)

        # 3. Detection Publisher
        self.detection_pub = self.create_publisher(
            Detection2DArray, 
            '/nanoowl/detections', 
            10)

        # Storing the text prompts
        self.target_classes = ["an owl", "a glove"]

    def image_callback(self, msg):
        try:
            # 1. Convert ROS Image to PIL Image
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            cv_image_rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
            pil_image = PIL.Image.fromarray(cv_image_rgb)

            # 2. Run the Prediction
            output = self.predictor.predict(
                image=pil_image,
                text=self.target_classes,
                threshold=0.1
            )
            
            # 3. Package the output into ROS 2 Messages
            detection_array_msg = Detection2DArray()
            # Keep original timestamp/frame_id so it aligns temporally with the depth stream
            detection_array_msg.header = msg.header 
            
            # Unpack the NanoOwl output safely
            for box, label_idx, score in zip(output.boxes, output.labels, output.scores):
                detection = Detection2D()
                detection.header = msg.header
                
                # A. Set up the Bounding Box Geometry
                # Convert to standard Python floats to ensure downstream compatibility
                x_min, y_min, x_max, y_max = [float(val) for val in box]
                bbox = BoundingBox2D()
                
                # Calculate centers
                bbox.center.position.x = (x_min + x_max) / 2.0
                bbox.center.position.y = (y_min + y_max) / 2.0
                bbox.size_x = x_max - x_min
                bbox.size_y = y_max - y_min
                
                detection.bbox = bbox
                
                # B. Set up the Class and Score (Hypothesis)
                hypothesis_with_pose = ObjectHypothesisWithPose()
                
                # Get the actual string name from our list using the index
                # Note: Convert label_idx to int if it is a tensor
                class_name = self.target_classes[int(label_idx)] 
                
                hypothesis_with_pose.hypothesis.class_id = class_name
                hypothesis_with_pose.hypothesis.score = float(score)
                
                detection.results.append(hypothesis_with_pose)
                
                # C. Add this detection to our array
                detection_array_msg.detections.append(detection)

            # 4. Publish the final array
            self.detection_pub.publish(detection_array_msg)
            
            # Optional: Print to terminal so you know it's working
            if len(detection_array_msg.detections) > 0:
                self.get_logger().info(f"Published {len(detection_array_msg.detections)} detections.")

        except Exception as e:
            self.get_logger().error(f"Failed to process image: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = NanoOwlNode()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()