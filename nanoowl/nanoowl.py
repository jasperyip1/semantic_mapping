import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

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

        # 2. THE NEW LINE: Create the Subscriber
        # We subscribe to the default Realsense color image topic
        self.subscription = self.create_subscription(
            Image,
            '/camera0/color/image_raw',  # This matches the topic from your launch file
            self.image_callback,
            10)

    def image_callback(self, msg):
        try:
            # 1. Convert the ROS Image Message to an OpenCV Image
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            
            # 2. Convert OpenCV Image (BGR) to PIL Image (RGB) for NanoOwl
            cv_image_rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
            pil_image = PIL.Image.fromarray(cv_image_rgb)

            # 3. Run the Prediction
            output = self.predictor.predict(
                image=pil_image, 
                text=["an owl", "a glove"], 
                threshold=0.1
            )
            
            # 4. Print or process the results
            self.get_logger().info(f"Detections: {output}")

        except Exception as e:
            self.get_logger().error(f"Failed to process image: {e}")

def main():
    rclpy.init()
    node = NanoOwlNode()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()