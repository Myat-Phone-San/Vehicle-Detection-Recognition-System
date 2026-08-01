import os
import cv2
import re
import threading
import numpy as np
import pandas as pd
from flask import Flask, render_template, Response, jsonify, request, send_file
import io
from ultralytics import YOLO
import easyocr

app = Flask(__name__)

frame_lock = threading.Lock()

# Load Models
model_plate = YOLO('best.pt') 
ocr_reader = easyocr.Reader(['en'], gpu=False)

DB_PATH = 'Car_List_MinDaMa_overall.xlsx'
video_source = None
current_frame = None
show_boxes = False 
media_type = 'none'

def get_db():
    if os.path.exists(DB_PATH):
        try:
            xls = pd.ExcelFile(DB_PATH)
            all_dfs = []
            for sheet in xls.sheet_names:
                df = pd.read_excel(DB_PATH, sheet_name=sheet)
                if 'Car No.' not in df.columns and 'Car Number' not in df.columns and 'Room No.' not in df.columns:
                    df = pd.read_excel(DB_PATH, sheet_name=sheet, header=1)
                all_dfs.append(df)
            combined_df = pd.concat(all_dfs, ignore_index=True) if len(all_dfs) > 1 else all_dfs[0]
            return combined_df
        except Exception as e:
            print(f"Error reading Excel database: {e}")
    return None

def get_best_plate_crop(image):
    results = model_plate(image, verbose=False, conf=0.45)[0]
    if len(results.boxes) == 0:
        return None

    best_box = None
    max_conf = -1.0

    for box in results.boxes:
        conf = float(box.conf[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        w_box, h_box = x2 - x1, y2 - y1
        aspect_ratio = w_box / float(h_box) if h_box > 0 else 0

        if 1.8 <= aspect_ratio <= 4.2:
            if conf > max_conf:
                max_conf = conf
                best_box = (x1, y1, x2, y2)

    if best_box is None:
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf > max_conf:
                max_conf = conf
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                best_box = (x1, y1, x2, y2)

    if best_box is None:
        return None

    x1, y1, x2, y2 = best_box
    h_img, w_img = image.shape[:2]
    padding = 5
    x1_pad = max(0, x1 - padding)
    y1_pad = max(0, y1 - padding)
    x2_pad = min(w_img, x2 + padding)
    y2_pad = min(h_img, y2 + padding)

    return image[y1_pad:y2_pad, x1_pad:x2_pad]

def preprocess_and_read_plate(crop_img):
    if crop_img is None or crop_img.size == 0: 
        return "Not detected"

    h, w = crop_img.shape[:2]
    # Separating top and bottom areas more accurately for Myanmar License Plates
    top_part = crop_img[0:int(h * 0.5), 0:w]
    bottom_part = crop_img[int(h * 0.3):h, 0:w]

    def process_sub_img(img):
        resized = cv2.resize(img, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        filtered = cv2.bilateralFilter(gray, 11, 17, 17)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        return clahe.apply(filtered)

    top_processed = process_sub_img(top_part)
    bot_processed = process_sub_img(bottom_part)

    res_top = ocr_reader.readtext(top_processed, detail=0, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-')
    res_bot = ocr_reader.readtext(bot_processed, detail=0, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-')

    top_text = " ".join(res_top).upper()
    bot_text = " ".join(res_bot).upper()

    noise_words = ["HONDA", "INSIGHT", "TOYOTA", "SUZUKI", "CARRY", "PROBOX", "NISSAN", "FIT", "JUSGM", "QOLIL", "AUDI", "CHANGAN", "DEEPAL", "COROLLA", "FIELDER"]
    for word in noise_words:
        top_text = top_text.replace(word, "")
        bot_text = bot_text.replace(word, "")

    combined_text = f"{top_text} {bot_text}"

    # Region/City Code Detection from top text or combined text
    city_code = "YGN"
    if re.search(r'\b(NPW|NPT)\b', combined_text): 
        city_code = "NPW"
    elif re.search(r'\b(MDY|MOY|MDV|MAY)\b', combined_text): 
        city_code = "MDY"
    elif re.search(r'\b(AYY|AVY|AAY)\b', combined_text): 
        city_code = "AYY"
    elif re.search(r'\b(BGO|3GO|8GO)\b', combined_text): 
        city_code = "BGO"
    elif re.search(r'\b(SHN|SHAN)\b', combined_text): 
        city_code = "SHN"
    elif re.search(r'\b(YGN|YON|YCN|VGN)\b', combined_text): 
        city_code = "YGN"

    # Improved Prefix and Digits Extraction (e.g., handling '6G-7763' or '6G 7763')
    prefix = ""
    digits = ""

    # Flexible regex to catch alphanumeric prefixes like '6G', '2C', etc., followed by optional hyphen and 4 digits
    match_plate = re.search(r'([A-Z0-9]{1,3})[-]?(\d{4})', bot_text)
    if match_plate:
        prefix = match_plate.group(1)
        digits = match_plate.group(2)
    else:
        match_plate_comb = re.search(r'([A-Z0-9]{1,3})[-]?(\d{4})', combined_text)
        if match_plate_comb:
            prefix = match_plate_comb.group(1)
            digits = match_plate_comb.group(2)
        else:
            digits_match = re.findall(r'\b\d{4}\b', bot_text)
            if digits_match:
                digits = digits_match[-1]
            
            pfx_match = re.search(r'\b([A-Z0-9]{2,3})\b', bot_text)
            if pfx_match:
                prefix = pfx_match.group(1)

    # Correct common OCR confusions in Myanmar plate prefixes (1 <-> I, 6 <-> G)
    def correct_prefix(pfx):
        pfx = pfx.upper().strip()
        pfx = re.sub(r'[^A-Z0-9]', '', pfx)
        if len(pfx) >= 2:
            chars = list(pfx)
            # Position 0 should be a digit (0-9)
            if chars[0] in ['I', 'L', '|', '!']:
                chars[0] = '1'
            elif chars[0] in ['G', 'b']:
                chars[0] = '6'
            elif chars[0] == 'O':
                chars[0] = '0'
            elif chars[0] == 'Z':
                chars[0] = '2'
            elif chars[0] == 'S':
                chars[0] = '5'
                
            # Position 1 should be a letter (A-Z)
            if chars[1] in ['6', 'b', 'o']:
                chars[1] = 'G'
            elif chars[1] == '0':
                chars[1] = 'D'
            elif chars[1] in ['1', '|']:
                chars[1] = 'I'
            elif chars[1] == '2':
                chars[1] = 'Z'
            elif chars[1] == '5':
                chars[1] = 'S'
            return "".join(chars)
        return pfx

    if prefix:
        prefix = correct_prefix(prefix)

    if prefix and digits:
        return f"{city_code} {prefix}-{digits}"
    elif digits:
        return f"{city_code} {digits}"

    return "Not detected"

def draw_single_best_box(img):
    results = model_plate(img, verbose=False, conf=0.45)[0]
    if len(results.boxes) == 0:
        return img

    best_box = None
    max_conf = -1.0

    for box in results.boxes:
        conf = float(box.conf[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        bw, bh = x2 - x1, y2 - y1
        aspect = bw / float(bh) if bh > 0 else 0

        if 1.8 <= aspect <= 4.2:
            if conf > max_conf:
                max_conf = conf
                best_box = (x1, y1, x2, y2)

    if best_box is None and len(results.boxes) > 0:
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf > max_conf:
                max_conf = conf
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                best_box = (x1, y1, x2, y2)

    if best_box is not None:
        x1, y1, x2, y2 = best_box
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)

    return img

@app.route('/')
def index():
    return render_template('index.html')

def generate_frames():
    global current_frame, video_source, show_boxes, media_type
    while media_type in ['video', 'webcam']:
        if video_source is not None and video_source.isOpened():
            success, frame = video_source.read()
            if not success:
                if media_type == 'video':
                    video_source.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    break
            with frame_lock:
                current_frame = frame.copy()
                display_frame = frame.copy()

            if show_boxes:
                display_frame = draw_single_best_box(display_frame)

            ret, buffer = cv2.imencode('.jpg', display_frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            cv2.waitKey(30)
        else:
            break

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_image')
def get_image():
    global current_frame, show_boxes
    with frame_lock:
        if current_frame is None:
            return "No image", 400
        display_frame = current_frame.copy()

    if show_boxes:
        display_frame = draw_single_best_box(display_frame)

    _, buffer = cv2.imencode('.jpg', display_frame)
    return send_file(io.BytesIO(buffer.tobytes()), mimetype='image/jpeg')

@app.route('/get_cropped_plate')
def get_cropped_plate():
    global current_frame
    with frame_lock:
        if current_frame is None:
            return "No frame loaded", 400
        processing_img = current_frame.copy()

    roi = get_best_plate_crop(processing_img)
    if roi is None or roi.size == 0:
        return "No plate region detected", 404

    roi_resized = cv2.resize(roi, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    _, buffer = cv2.imencode('.jpg', roi_resized)
    return send_file(io.BytesIO(buffer.tobytes()), mimetype='image/jpeg')

@app.route('/start_camera', methods=['POST'])
def start_camera():
    global video_source, media_type
    if video_source: 
        video_source.release()
    video_source = cv2.VideoCapture(0) 
    media_type = 'webcam'
    return jsonify({"status": "success"})

@app.route('/upload_media', methods=['POST'])
def upload_media():
    global video_source, current_frame, media_type
    if 'file' not in request.files: 
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files['file']
    filename = file.filename.lower()
    
    if filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
        if video_source: 
            video_source.release()
            video_source = None
            
        file_bytes = np.frombuffer(file.read(), np.uint8)
        with frame_lock:
            current_frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        media_type = 'image'
        return jsonify({"status": "success", "type": "image"})
        
    elif filename.endswith(('.mp4', '.avi', '.mov', '.mkv')):
        temp_path = "temp_video.mp4"
        file.save(temp_path)
        
        if video_source: 
            video_source.release()
        video_source = cv2.VideoCapture(temp_path)
        media_type = 'video'
        return jsonify({"status": "success", "type": "video"})
        
    return jsonify({"error": "Unsupported file format"}), 400

@app.route('/toggle_detection', methods=['POST'])
def toggle_detection():
    global show_boxes
    data = request.get_json()
    show_boxes = data.get('enabled', False)
    return jsonify({"status": "success", "active": show_boxes})

@app.route('/clear_system', methods=['POST'])
def clear_system():
    global video_source, current_frame, show_boxes, media_type
    if video_source:
        video_source.release()
        video_source = None
    with frame_lock:
        current_frame = None
    show_boxes = False
    media_type = 'none'
    return jsonify({"status": "cleared"})

@app.route('/read_plate', methods=['GET'])
def read_plate():
    global current_frame
    
    with frame_lock:
        if current_frame is None:
            return jsonify({"plate": "No media frame loaded"})
        processing_img = current_frame.copy()
        
    roi = get_best_plate_crop(processing_img)
    if roi is not None and roi.size > 0:
        final_plate_str = preprocess_and_read_plate(roi)
        return jsonify({"plate": final_plate_str})

    return jsonify({"plate": "Not detected"})

@app.route('/verify_car', methods=['POST'])
def verify_car():
    detected_plate = request.json.get('plate', '')
    det_digits = "".join(re.findall(r'\d+', detected_plate))
    det_suffix = det_digits[-4:] if len(det_digits) >= 4 else None

    if not det_suffix:
        return jsonify({"status": "invalid", "message": "Clear character matching error"})

    df = get_db()
    if df is None: 
        return jsonify({"status": "error", "message": "Database lookup failed"})

    car_col = None
    for col in df.columns:
        if 'car' in str(col).lower():
            car_col = col
            break
    if not car_col:
        car_col = df.columns[-1]

    match_row = None
    
    for _, row in df.iterrows():
        db_car_no = str(row[car_col])
        db_digits = "".join(re.findall(r'\d+', db_car_no))
        if db_digits and db_digits.endswith(det_suffix):
            match_row = row.to_dict()
            break

    if match_row:
        clean_data = {}
        for k, v in match_row.items():
            if str(k).strip().lower() in ['sn', 'sn.', 's/n', 'sr. no.', 'sr no']:
                continue
                
            if pd.notna(v) and str(v).strip() != "":
                if isinstance(v, float) and v.is_integer():
                    clean_data[str(k)] = str(int(v))
                else:
                    clean_data[str(k)] = str(v)
        return jsonify({"status": "valid", "data": clean_data})
        
    return jsonify({"status": "unregistered", "message": "Record log not found"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860, debug=True)
