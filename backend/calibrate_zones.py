import cv2
import requests
import numpy as np
from dotenv import load_dotenv
import os

load_dotenv()

ESP32_IP = os.getenv("ESP32_IP")
url = os.getenv("ESP32_STREAM_URL")

zones = []
drawing = False
start_point = None
temp_rect = None

def mouse_callback(event, x, y, flags, param):
    global drawing, start_point, zones, temp_rect
    
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        start_point = (x, y)
    
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            temp_rect = (start_point[0], start_point[1], x, y)
    
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        zone_name = f"Zona-{len(zones)+1}"
        zones.append([start_point[0], start_point[1], x, y, zone_name])
        print(f"✓ {zone_name} agregada")
        start_point = None
        temp_rect = None

print("\n" + "="*50)
print("ZONE CALIBRATOR")
print("="*50)
print("1. Click and drag to define zones")
print("2. Press 's' to see coordinates")
print("3. Press 'q' to exit")
print("="*50 + "\n")

try:
    print("Connecting...")
    stream = requests.get(url, stream=True, timeout=10)
    bytes_data = bytes()
    
    window_name = "Zone Calibrator"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, mouse_callback)
    
    print("Connected - Draw the zones\n")
    
    while True:
        bytes_data += stream.raw.read(2048)
        
        a = bytes_data.find(b'\xff\xd8')
        b = bytes_data.find(b'\xff\xd9')
        
        if a != -1 and b != -1:
            jpg = bytes_data[a:b+2]
            bytes_data = bytes_data[b+2:]
            
            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            
            if frame is not None:
                display = frame.copy()
                
                for zone in zones:
                    cv2.rectangle(display, (zone[0], zone[1]), (zone[2], zone[3]), (0, 255, 0), 2)
                    cv2.putText(display, zone[4], (zone[0]+5, zone[1]+15), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                
                if temp_rect:
                    cv2.rectangle(display, (temp_rect[0], temp_rect[1]), 
                                (temp_rect[2], temp_rect[3]), (0, 0, 255), 2)
                
                cv2.putText(display, f"Zones: {len(zones)}", (10, 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
                
                cv2.imshow(window_name, display)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            print("\n" + "="*50)
            print("PARKING_ZONES = [")
            for zone in zones:
                print(f"    {zone},")
            print("]")
            print("="*50 + "\n")
        elif key == ord('r'):
            zones = []
            print("Reset\n")
    
    cv2.destroyAllWindows()
    
except Exception as error:
    print(f"Error: {error}")