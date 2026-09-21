FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WHISPER_CACHE_DIR=/app/whisper_models
ENV PYTHONPATH=/app 

COPY requirements.txt .
# We use --extra-index-url to download the CPU-only version of PyTorch.
# This saves ~2.5 GB of downloads and makes the build 10x faster!
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

COPY . .

CMD ["python", "-m", "app.main"]