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
RUN pip install --no-cache-dir -r requirements.txt

COPY guide.pdf /app/guide.pdf
COPY . .

CMD ["python", "-m", "app.main"]