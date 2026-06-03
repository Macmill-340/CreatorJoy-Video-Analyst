FROM python:3.13-slim

# Install ffmpeg (needed by yt-dlp for audio extraction)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT