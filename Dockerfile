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

# Smart CPU-only PyTorch installation:
# - For ARM64 (Mac Silicon), pin to 2.2.2 to avoid 3GB CUDA bloat introduced in 2.3+
# - For x86_64 (Windows/Linux), use the official CPU index
RUN arch=$(uname -m) && \
    if [ "$arch" = "aarch64" ]; then \
        pip install --no-cache-dir torch==2.2.2 torchaudio==2.2.2 ; \
    else \
        pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu ; \
    fi

COPY requirements.txt .
RUN pip install --default-timeout=1000 --retries 10 -r requirements.txt

COPY . .

CMD ["python", "-m", "app.main"]