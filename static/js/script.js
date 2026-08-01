let detectionEnabled = false;
let currentPlateResult = "";
let currentMediaType = "none";

// Initialize Camera
document.getElementById('cam-btn').addEventListener('click', function() {
    document.getElementById('ocr-log').innerText = "Connecting...";
    resetCropPreview();
    fetch('/start_camera', { method: 'POST' })
    .then(res => res.json()).then(data => {
        if(data.status === 'success') {
            currentMediaType = "webcam";
            document.getElementById('video-stream').src = "/video_feed?" + new Date().getTime();
            document.getElementById('ocr-log').innerText = "WEBCAM ACTIVE";
        }
    });
});

// Process File Upload Handler
document.getElementById('file-input').addEventListener('change', function(e) {
    if(e.target.files.length === 0) return;
    
    let formData = new FormData();
    formData.append('file', e.target.files[0]);
    document.getElementById('ocr-log').innerText = "Loading Media...";
    resetCropPreview();
    
    fetch('/upload_media', { method: 'POST', body: formData })
    .then(res => res.json()).then(data => {
        if(data.status === 'success') {
            currentMediaType = data.type;
            if (data.type === 'image') {
                document.getElementById('video-stream').src = "/get_image?" + new Date().getTime();
            } else {
                document.getElementById('video-stream').src = "/video_feed?" + new Date().getTime();
            }
            document.getElementById('ocr-log').innerText = `MEDIA: ${data.type.toUpperCase()}`;
        }
    }).catch(err => {
        document.getElementById('ocr-log').innerText = "Upload failed.";
    });
});

// Toggle Bounding Box
document.getElementById('detect-btn').addEventListener('click', function() {
    detectionEnabled = !detectionEnabled;
    this.innerText = detectionEnabled ? "🟢 BOX ACTIVE" : "⚪ BOX ACTIVE";
    fetch('/toggle_detection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: detectionEnabled })
    }).then(() => {
        if (currentMediaType === 'image') {
            document.getElementById('video-stream').src = "/get_image?" + new Date().getTime();
        }
    });
});

// Show Cropped License Plate Image
document.getElementById('crop-btn').addEventListener('click', function() {
    if (currentMediaType === "none") {
        alert("Please load an image or webcam feed first.");
        return;
    }
    showCroppedPlate();
});

function showCroppedPlate() {
    const cropBox = document.getElementById('crop-preview-box');
    const cropImg = document.getElementById('cropped-plate-img');
    cropImg.src = "/get_cropped_plate?" + new Date().getTime();
    cropBox.style.display = "flex";
}

// Read Plate String OCR
document.getElementById('read-btn').addEventListener('click', function() {
    const log = document.getElementById('ocr-log');
    log.innerText = "SCANNING...";
    log.classList.remove('active-plate');
    
    // Display cropped plate on top
    showCroppedPlate();

    fetch('/read_plate').then(res => res.json()).then(data => {
        currentPlateResult = data.plate;
        log.innerText = data.plate;
        if (!data.plate.includes("Not detected")) {
            log.classList.add('active-plate');
        }
    });
});

// Verify Against Excel Database Records
document.getElementById('verify-btn').addEventListener('click', function() {
    const display = document.getElementById('info-display');
    
    if(!currentPlateResult || currentPlateResult.includes("Not detected") || currentPlateResult.includes("No media")) {
        alert("Please run OCR recognition before verifying status.");
        return;
    }

    display.innerHTML = "<div class='placeholder-text'>Searching Database Records...</div>";
    
    fetch('/verify_car', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate: currentPlateResult })
    })
    .then(res => res.json())
    .then(data => {
        if(data.status === 'valid') {
            let infoHtml = `<div class="status-badge valid">✓ REGISTERED VEHICLE</div><div class="db-grid">`;
            
            for (const [key, value] of Object.entries(data.data)) {
                if (key.toLowerCase().startsWith('sn')) continue;
                infoHtml += `
                    <div class="grid-item">
                        <span class="item-label">${key}</span>
                        <span class="item-value">${value}</span>
                    </div>`;
            }
            
            infoHtml += `</div>`;
            display.innerHTML = infoHtml;
        } else {
            display.innerHTML = `
                <div class="status-badge invalid">✕ NOT FOUND / UNREGISTERED</div>
                <div class="placeholder-text">No matching record found for ${currentPlateResult}</div>`;
        }
    });
});

function resetCropPreview() {
    const cropBox = document.getElementById('crop-preview-box');
    const cropImg = document.getElementById('cropped-plate-img');
    cropBox.style.display = "none";
    cropImg.src = "";
}

// Clear / Reset System Event Handler
document.getElementById('clear-btn').addEventListener('click', function() {
    fetch('/clear_system', { method: 'POST' }).then(() => {
        currentMediaType = "none";
        currentPlateResult = "";
        detectionEnabled = false;
        
        document.getElementById('video-stream').src = "";
        const log = document.getElementById('ocr-log');
        log.innerText = "READY...";
        log.classList.remove('active-plate');
        
        document.getElementById('info-display').innerHTML = "<div class='placeholder-text'>Run Database Check to display owner details...</div>";
        document.getElementById('detect-btn').innerText = "⚪ BOX ACTIVE";
        document.getElementById('file-input').value = "";
        resetCropPreview();
    });
});
