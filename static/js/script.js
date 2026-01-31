let detectionEnabled = false;

document.getElementById('file-input').addEventListener('change', function(e) {
    let formData = new FormData();
    formData.append('file', e.target.files[0]);
    fetch('/upload_video', { method: 'POST', body: formData })
    .then(res => res.json()).then(data => {
        if(data.status === 'success') {
            document.getElementById('video-stream').src = "/video_feed";
            document.getElementById('ocr-log').innerText = "Media Loaded...";
        }
    });
});

document.getElementById('detect-btn').addEventListener('click', function() {
    detectionEnabled = !detectionEnabled;
    this.innerText = detectionEnabled ? "🟢 DETECTION ACTIVE" : "⚪ DETECT BOUNDING BOX";
    fetch('/toggle_detection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: detectionEnabled })
    });
});

document.getElementById('read-btn').addEventListener('click', function() {
    document.getElementById('ocr-log').innerText = "Processing OCR...";
    fetch('/read_plate').then(res => res.json()).then(data => {
        document.getElementById('ocr-log').innerText = `PLATE: ${data.plate}`;
    });
});
