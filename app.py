import cv2
import numpy as np
from flask import Flask, render_template, Response, jsonify, request
from ultralytics import YOLO
import easyocr
import os

app = Flask(__name__)

# Load model and OCR
model_plate = YOLO('best.pt') 
ocr_reader = easyocr.Reader(['en'], gpu=False)

video_source = None
current_frame = None
show_boxes = False 

def generate_frames():
    global current_frame, video_source, show_boxes
    while video_source is not None:
        success, frame = video_source.read()
        if not success: break
        
        current_frame = frame.copy()
        display_frame = frame.copy()

        if show_boxes:
            results = model_plate(display_frame, verbose=False, conf=0.3)[0]
            for box in results.boxes:
                if "car" in model_plate.names[int(box.cls)].lower(): continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
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
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['file']
    file.save("temp_video.mp4")
    if video_source: video_source.release()
    video_source = cv2.VideoCapture("temp_video.mp4")
    return jsonify({"status": "success"})

@app.route('/read_plate', methods=['GET'])
def read_plate():
    global current_frame
    if current_frame is None: return jsonify({"plate": "No media"})
    results = model_plate(current_frame, verbose=False, conf=0.3)[0]
    
    for box in results.boxes:
        if "car" in model_plate.names[int(box.cls)].lower(): continue
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        plate_roi = current_frame[y1:y2, x1:x2]
        if plate_roi.size > 0:
            ocr_res = ocr_reader.readtext(plate_roi)
            text = " ".join([res[1] for res in ocr_res])
            return jsonify({"plate": text if text else "Not clear"})
    
    return jsonify({"plate": "No plate detected"})

if __name__ == '__main__':
    # Hugging Face Spaces အတွက် port 7860 ကို သုံးရပါမယ်
    app.run(host='0.0.0.0', port=7860)
