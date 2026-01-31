# Python 3.12 သုံးပါ
FROM python:3.12-slim

# System libraries များ သွင်းခြင်း (OpenCV အတွက် မဖြစ်မနေလိုအပ်)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Requirements သွင်းခြင်း
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ကျန်တဲ့ file အားလုံးကို ကူးယူခြင်း
COPY . .

# Flask run ရန်
CMD ["python", "app.py"]