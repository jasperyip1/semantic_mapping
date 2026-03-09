import pyrealsense2 as rs
import numpy as np
import cv2
import torch
import csv
import os
import threading
from datetime import datetime
from PIL import Image
from transformers import OwlViTProcessor, OwlViTForObjectDetection

print('Loading model...')
processor = OwlViTProcessor.from_pretrained('google/owlvit-base-patch32')
model = OwlViTForObjectDetection.from_pretrained('google/owlvit-base-patch32')
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
use_fp16 = device.type == 'cuda'
model = model.to(device)
if use_fp16:
    model = model.half()
model.eval()
print(f'Running on: {device}')

text_labels = [['person', 'laptop', 'book', 'basketball', 'orange', 'banana',
                'tennis ball', 'water bottle', 'football']]

log_file = 'detections.csv'
write_header = not os.path.exists(log_file)
csv_file = open(log_file, 'a', newline='')
writer = csv.writer(csv_file)
if write_header:
    writer.writerow(['timestamp', 'objects_detected', 'labels_found'])

TP = FP = FN = 0
def precision(): return TP / (TP + FP) if (TP + FP) > 0 else 0.0
def recall(): return TP / (TP + FN) if (TP + FN) > 0 else 0.0

latest_frame = None
latest_detections = []
frame_lock = threading.Lock()
detection_lock = threading.Lock()
running = True

def inference_thread():
    while running:
        with frame_lock:
            frame = latest_frame.copy() if latest_frame is not None else None
        if frame is None:
            continue

        pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        inputs = processor(text=text_labels, images=pil_image, return_tensors='pt')
        if use_fp16:
            inputs = {k: v.half() if v.dtype == torch.float32 else v for k, v in inputs.items()}
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)

        results = processor.post_process_grounded_object_detection(
            outputs=outputs,
            threshold=0.09,
            target_sizes=[pil_image.size[::-1]],
            text_labels=text_labels
        )[0]

        detections = []
        for score, label, box in zip(results['scores'].tolist(),
                                     results['text_labels'], results['boxes'].tolist()):
            detections.append((score, label, [int(v) for v in box]))

        with detection_lock:
            latest_detections.clear()
            latest_detections.extend(detections)

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

try:
    pipeline.start(config)
except Exception as e:
    print(f'ERROR: Could not connect to camera: {e}')
    csv_file.close()
    exit(1)

t = threading.Thread(target=inference_thread, daemon=True)
t.start()

print("Camera running. Press 's' to save | 'q' to quit")

fps_counter = fps_display = 0
fps_time = cv2.getTickCount()

try:
    while True:
        frames = pipeline.wait_for_frames()
        color_frame = frames.get_color_frame()
        if not color_frame:
            continue

        frame_bgr = np.asanyarray(color_frame.get_data())
        with frame_lock:
            latest_frame = frame_bgr.copy()
        display = frame_bgr.copy()

        with detection_lock:
            current_detections = list(latest_detections)

        labels_found = []
        for score, label, box in current_detections:
            cv2.rectangle(display, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
            cv2.putText(display, f'{label}: {score:.2f}', (box[0], box[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            labels_found.append(label)

        object_count = len(current_detections)

        fps_counter += 1
        elapsed = (cv2.getTickCount() - fps_time) / cv2.getTickFrequency()
        if elapsed >= 1.0:
            fps_display = fps_counter
            fps_counter = 0
            fps_time = cv2.getTickCount()

        cv2.putText(display, f'Objects: {object_count}  FPS: {fps_display}',
                    (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 255), 3)
        cv2.putText(display, "Press 's' to save | 'q' to quit", (10, 470),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow('Room Scanner - OWLViT + D435i', display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('s'):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            unique_labels = list(set(labels_found)) if labels_found else ['none']
            writer.writerow([timestamp, object_count, ', '.join(unique_labels)])
            csv_file.flush()
            print(f'[SAVED] {timestamp} — {object_count} object(s): {unique_labels}')
            cv2.putText(display, 'SAVED!', (250, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 5)
            cv2.imshow('Room Scanner - OWLViT + D435i', display)
            cv2.waitKey(500)

finally:
    running = False
    pipeline.stop()
    cv2.destroyAllWindows()
    csv_file.close()
    print('Session ended. Data saved to detections.csv')
