# Production Dockerfile for Railway.app Deployment
FROM python:3.11-slim

# Install system dependencies including FFmpeg and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create persistent storage directories
RUN mkdir -p storage/clips storage/scripts storage/audio storage/exports storage/temp

# Railway assigns a dynamic PORT environment variable at runtime
ENV PORT=8000
EXPOSE 8000

# Start FastAPI server using dynamic PORT
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
