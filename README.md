# Notion Voice Memo to Action Items

A Telegram bot that receives voice messages, transcribes them locally using [OpenAI Whisper](https://github.com/openai/whisper), and returns the transcription to the user. Designed to eventually extract action items and push them to Notion.

## Features

- Receive voice messages via Telegram
- Transcribe audio locally with Whisper (no external API calls for transcription)
- Show a progress animation while the audio is being processed
- Docker-based deployment with optional model pre-loading

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/)
- A Telegram bot token — create one via [@BotFather](https://t.me/BotFather)

## Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/Artem817/Notion-Voice-Memo-to-Action-Items.git
   cd Notion-Voice-Memo-to-Action-Items
   ```

2. **Create a `.env` file** in the project root:

   ```env
   BOT_TOKEN=your_telegram_bot_token
   ```

   Optional variables:

   | Variable | Default | Description |
   |---|---|---|
   | `WHISPER_MODEL` | `medium` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
   | `WHISPER_DEVICE` | auto | Device to run inference on (`cpu`, `cuda`) |
   | `WHISPER_CACHE_DIR` | `./whisper_models` | Directory for cached model weights |
   | `WHISPER_PRELOAD` | `1` | Pre-load the Whisper model on startup (`1`/`0`) |

3. **Run with Docker Compose**

   ```bash
   docker compose up --build
   ```

   Model weights are stored in `./whisper_models` and audio data in `./data` (both are mounted as volumes so they persist across restarts).

## Running without Docker

```bash
# Install dependencies (Python 3.12+ recommended)
pip install -r requirements.txt

# Start the bot
python -m app.main
```

> **Note:** `ffmpeg` must be installed on the host for Whisper to decode audio files.

## Project Structure

```
app/
  main.py              # Bot entry point and Telegram handlers
  voice_processing.py  # Pydantic model for voice processing requests
  speech_recogniser/   # Whisper transcription logic
  llm_processor/       # LLM integration (in progress)
tests/
  unit/                # Unit tests
```

## Development

Run the unit tests:

```bash
pytest tests/
```

