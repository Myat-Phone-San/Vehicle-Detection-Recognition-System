import cv2
import numpy as np
from flask import Flask, render_template, Response, jsonify, request
from ultralytics import YOLO
import easyocr
import os

app = Flask(__name__)

# --- AI Models Initialization ---
# Using 'cpu' explicitly can sometimes prevent memory crashes on Free tiers
model_plate = YOLO('best.pt') 
ocr_reader = easyocr.Reader(['en'], gpu=False)

# Global states
video_source = None
current_frame = None
show_boxes = False # Bounding box is OFF by default

def generate_frames():
    global current_frame, video_source, show_boxes
    while video_source is not None:
        success, frame = video_source.read()
        if not success:
            break
        
        current_frame = frame.copy()
        display_frame = frame.copy()

        # Green bounding box logic: ONLY runs if toggle is enabled
        if show_boxes:
            results = model_plate(display_frame, verbose=False, conf=0.3)[0]
            for box in results.boxes:
                # Filter out detections that aren't license plates if necessary
                if "car" in model_plate.names[int(box.cls)].lower(): continue
                
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                # Draw the green bounding box
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        ret, buffer = cv2.imencode('.jpg', display_frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/toggle_detection', methods=['POST'])
def toggle_detection():
    global show_boxes
    data = request.get_json()
    show_boxes = data.get('enabled', False)
    return jsonify({"status": "success", "detection": show_boxes})

@app.route('/upload_video', methods=['POST'])
def upload_video():
    global video_source
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    save_path = "temp_video.mp4"
    file.save(save_path)
    
    if video_source:
        video_source.release()
    
    video_source = cv2.VideoCapture(save_path)
    return jsonify({"status": "success"})

@app.route('/read_plate', methods=['GET'])
def read_plate():
    global current_frame
    if current_frame is None:
        return jsonify({"plate": "No media active"})

    results = model_plate(current_frame, verbose=False, conf=0.3)[0]
    plates_found = []

    for box in results.boxes:
        if "car" in model_plate.names[int(box.cls)].lower(): continue
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        plate_roi = current_frame[y1:y2, x1:x2]
        
        if plate_roi.size > 0:
            gray = cv2.cvtColor(plate_roi, cv2.COLOR_BGR2GRAY)
            ocr_output = ocr_reader.readtext(gray)
            text = " ".join([res[1].upper() for res in ocr_output if res[2] > 0.2])
            if text.strip():
                plates_found.append(text)

    return jsonify({"plate": ", ".join(plates_found) if plates_found else "NOT DETECTED"})

if __name__ == '__main__':
    # Render requires binding to 0.0.0.0 and the port provided by the environment
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
