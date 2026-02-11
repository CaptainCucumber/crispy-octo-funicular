FROM python:3.12-slim

# Install OpenCV system dependencies for video processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app

ENV PORT=8080

CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT} app.main:app"]
