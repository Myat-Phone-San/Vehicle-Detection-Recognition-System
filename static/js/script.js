let detectionEnabled = false;

document.getElementById('file-input').addEventListener('change', function(e) {
    let formData = new FormData();
    formData.append('file', e.target.files[0]);

    fetch('/upload_video', {
        method: 'POST',
        body: formData
    }).then(response => response.json())
      .then(data => {
          if(data.status === 'success') {
              document.getElementById('video-stream').src = "/video_feed";
              document.getElementById('ocr-log').innerText = "Media Loaded. Monitoring...";
          }
      });
});

// Controls the "Detect Bounding Box" button logic
document.getElementById('detect-btn').addEventListener('click', function() {
    detectionEnabled = !detectionEnabled;
    
    // UI Visual Feedback
    if(detectionEnabled) {
        this.classList.add('btn-active');
        this.innerText = "🟢 DETECTION ON";
    } else {
        this.classList.remove('btn-active');
        this.innerText = "⚪ DETECT BOUNDING BOX";
    }

    // Inform backend to show/hide boxes in the stream
    fetch('/toggle_detection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: detectionEnabled })
    });
});

document.getElementById('read-btn').addEventListener('click', function() {
    const log = document.getElementById('ocr-log');
    log.innerText = "Processing OCR...";
    
    fetch('/read_plate')
        .then(response => response.json())
        .then(data => {
            log.innerText = `PLATE: ${data.plate}`;
        })
        .catch(err => {
            log.innerText = "Error reading plate.";
        });
});