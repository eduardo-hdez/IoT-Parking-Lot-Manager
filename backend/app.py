from flask import Flask, Response
import cv2
import numpy as np
import requests
import time
from threading import Thread, Lock
from ultralytics import YOLO
from dotenv import load_dotenv
import os
from database import init_parking_spaces, insert_parking_event

load_dotenv()

app = Flask(__name__)

ESP32_IP = os.getenv("ESP32_IP")
ESP32_STREAM_URL = os.getenv("ESP32_STREAM_URL")

# Load YOLO model
MODEL_PATH = "./ml_model/runs/detect/parking_detector/weights/best.pt"
model = YOLO(MODEL_PATH)

print(f"Model loaded: {MODEL_PATH}")
print(f"Classes: {model.names}")

CONFIDENCE_THRESHOLD = 0.5

# Parking zones
PARKING_ZONES = [
    [238, 16, 294, 106, 'A1'],
    [167, 15, 224, 106, 'A2'],
    [98, 17, 155, 106, 'A3'],
    [24, 16, 81, 106, 'A4'],
    [20, 141, 78, 229, 'A5'],
    [94, 142, 153, 228, 'A6'],
    [168, 141, 223, 227, 'A7'],
    [241, 141, 298, 226, 'A8'],
]

parking_status = {}
previous_parking_status = {}  # Track previous status for change detection
latest_frame = None
latest_detections = []  # Store latest detections for reuse
frame_lock = Lock()
is_running = True
PROCESS_EVERY_N_FRAMES = 3  # Process every 3rd frame for better performance


def check_parking_zone(detections, zone_coords):
    """
    Check if there are detections within a parking zone
    Returns: ('available', 'occupied', 'obstacle'), confidence, class_name
    """
    x1, y1, x2, y2 = zone_coords
    
    best_detection = None
    best_conf = 0
    
    # Check each detection
    for detection in detections:
        det_x1, det_y1, det_x2, det_y2 = detection[:4]
        det_center_x = (det_x1 + det_x2) / 2
        det_center_y = (det_y1 + det_y2) / 2
        
        # Check if detection center is inside parking zone
        if (x1 <= det_center_x <= x2) and (y1 <= det_center_y <= y2):
            conf = detection[4]
            class_id = int(detection[5])
            class_name = model.names[class_id]
            
            if conf > best_conf:
                best_conf = conf
                best_detection = (class_name, conf)
    
    if best_detection and best_conf > CONFIDENCE_THRESHOLD:
        class_name, conf = best_detection
        
        # Classify based on detected class
        if class_name.lower() in ['car', 'vehicle']:
            return 'occupied', conf, class_name
        else:
            return 'obstacle', conf, class_name
    
    return 'available', 0, None


def analyze_parking(frame):
    """Run YOLO inference on full frame"""
    global parking_status, previous_parking_status
    
    # Run YOLO detection
    results = model(frame, verbose=False, conf=CONFIDENCE_THRESHOLD)
    
    # Extract detections
    detections = []
    if len(results) > 0 and results[0].boxes is not None:
        boxes = results[0].boxes
        for box in boxes:
            detections.append(box.data[0].cpu().numpy())
    
    # Check each parking zone
    temp_status = {}
    for zone in PARKING_ZONES:
        x1, y1, x2, y2, name = zone
        
        status, confidence, class_name = check_parking_zone(
            detections, [x1, y1, x2, y2]
        )
        
        if status == 'occupied':
            display = "Occupied"
        elif status == 'obstacle':
            display = "Obstacle"
        else:
            display = "Available"
        
        temp_status[name] = {
            "status": status,
            "confidence": confidence,
            "display": display,
            "label": class_name
        }
    
    # Detect status changes and insert database events
    for space_name, current_info in temp_status.items():
        current_status = current_info["status"]
        previous_status = previous_parking_status.get(space_name, {}).get("status", "available")
        
        # Only insert event if status has changed
        if current_status != previous_status:
            is_car = None
            if current_status == 'occupied':
                is_car = True
            elif current_status == 'obstacle':
                is_car = False
            
            # Insert the event to database
            try:
                insert_parking_event(space_name, current_status, previous_status, is_car)
            except Exception as error:
                print(f"Error inserting DB event for {space_name}: {error}")
    
    # Update status trackers
    previous_parking_status = temp_status.copy()
    parking_status.update(temp_status)
    return detections


def draw_detections(frame, detections=None):
    """Draw YOLO detections and parking zones"""
    annotated = frame.copy()
    h, w = frame.shape[:2]
    
    # Draw YOLO bounding boxes (optional - for debugging)
    if detections is not None and len(detections) > 0:
        for detection in detections:
            x1, y1, x2, y2 = map(int, detection[:4])
            conf = detection[4]
            class_id = int(detection[5])
            class_name = model.names[class_id]
            
            # Draw detection box (purple for visibility)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 0, 255), 2)
            label = f"{class_name} {conf:.2f}"
            cv2.putText(annotated, label, (x1, y1-5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)
    
    # Draw parking zones
    for zone in PARKING_ZONES:
        x1, y1, x2, y2, name = zone
        status_info = parking_status.get(name, {"status": "available", "display": "Libre"})
        
        # Color based on status
        if status_info["status"] == "occupied":
            color = (0, 0, 255)  # Red
        elif status_info["status"] == "obstacle":
            color = (0, 165, 255)  # Orange
        else:
            color = (0, 255, 0)  # Green
        
        # Draw semi-transparent overlay
        overlay = annotated.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.3, annotated, 0.7, 0, annotated)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        
        # Label text
        conf = status_info.get("confidence", 0)
        if conf > 0:
            label = f"{name}: {status_info['display']} ({conf:.0%})"
        else:
            label = f"{name}: {status_info['display']}"
        
        # Draw label background
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.rectangle(annotated, (x1, y1-th-6), (x1+tw+4, y1), color, -1)
        cv2.putText(annotated, label, (x1+2, y1-3), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    
    # Statistics
    available = sum(1 for s in parking_status.values() if s["status"] == "available")
    occupied = sum(1 for s in parking_status.values() if s["status"] == "occupied")
    obstacles = sum(1 for s in parking_status.values() if s["status"] == "obstacle")
    
    cv2.rectangle(annotated, (2, 2), (280, 25), (0, 0, 0), -1)
    stats_text = f"Available: {available} | Occupied: {occupied} | Obstacles: {obstacles}"
    cv2.putText(annotated, stats_text, (5, 18), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    return annotated


def process_stream():
    """Capture and process ESP32 stream"""
    global latest_frame, latest_detections, is_running
    stream = None
    bytes_data = bytes()
    frame_count = 0
    
    while is_running:
        try:
            if stream is None:
                print(f"Connecting to {ESP32_STREAM_URL}...")
                stream = requests.get(ESP32_STREAM_URL, stream=True, timeout=10)
                bytes_data = bytes()
                print("Connected to ESP32")
            
            for chunk in stream.iter_content(chunk_size=4096):
                if not is_running:
                    break
                    
                bytes_data += chunk
                a = bytes_data.find(b'\xff\xd8')
                b = bytes_data.find(b'\xff\xd9')
                
                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        frame_count += 1
                        
                        # Only run YOLO inference every Nth frame for better performance
                        if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                            start_time = time.time()
                            detections = analyze_parking(frame)
                            latest_detections = detections  # Store for reuse
                            inference_time = (time.time() - start_time) * 1000
                            
                            # Add FPS counter
                            annotated_frame = draw_detections(frame, detections)
                            fps_text = f"Inference: {inference_time:.0f}ms (every {PROCESS_EVERY_N_FRAMES} frames)"
                            cv2.putText(annotated_frame, fps_text, (5, 40), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                        else:
                            # Reuse previous detections for faster rendering
                            annotated_frame = draw_detections(frame, latest_detections)
                            cv2.putText(annotated_frame, "Cached", (5, 40), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                        
                        with frame_lock:
                            latest_frame = annotated_frame
                            
        except Exception as error:
            print(f"Stream error: {error}")
            stream = None
            time.sleep(2)


def generate_frames():
    """Generate frames for web display"""
    global latest_frame
    
    while True:
        with frame_lock:
            if latest_frame is None:
                frame = np.zeros((240, 320, 3), dtype=np.uint8)
                cv2.putText(frame, "Waiting for ESP32...", (40, 120), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            else:
                frame = latest_frame.copy()
        
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.033)


@app.route('/')
def video_feed():
    """Main route - shows only the camera feed"""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("\n" + "="*60)
    print("PARKING SYSTEM WITH YOLO")
    print("="*60)
    print(f"\nModel: {MODEL_PATH}")
    print(f"Classes: {model.names}")
    print(f"ESP32: {ESP32_IP}")
    print(f"Zones: {len(PARKING_ZONES)}")
    print("="*60)
    
    # Initialize database parking spaces
    print("\nInitializing database...")
    if init_parking_spaces():
        print("Database ready")
    else:
        print("Could not connect to database")
    
    # Initialize previous_parking_status with all spaces as 'available'
    for zone in PARKING_ZONES:
        space_name = zone[4]
        previous_parking_status[space_name] = {
            "status": "available",
            "confidence": 0,
            "display": "Available",
            "label": None
        }
    
    print("="*60)
    
    Thread(target=process_stream, daemon=True).start()
    
    print(f"\nCamera feed: http://localhost:5000")
    print("Real-time detection with YOLOv8")
    print("Logging events to database")
        
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)