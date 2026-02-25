import asyncio
import logging
from contextlib import suppress
from pathlib import Path
import sys
from os import getenv

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, Voice
import whisper

from app.speech_recogniser.speach_engine import WhisperResult, transcribe_audio
from app.voice_processing import VoiceProcessingRequest

load_dotenv()

_WHISPER_MODEL = None


def _resolve_models_dir() -> Path:
    env_dir = getenv("WHISPER_CACHE_DIR") or getenv("WHISPER_MODELS_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parent.parent / "whisper_models"


def _get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is not None:
        return _WHISPER_MODEL

    model_name = (getenv("WHISPER_MODEL") or "medium").strip()
    available_models = set(whisper.available_models())
    if model_name not in available_models:
        raise ValueError(
            f"Unsupported WHISPER_MODEL '{model_name}'. "
            f"Allowed: {', '.join(sorted(available_models))}"
        )

    models_dir = _resolve_models_dir()
    models_dir.mkdir(parents=True, exist_ok=True)

    device = (getenv("WHISPER_DEVICE") or "").strip()
    if device:
        _WHISPER_MODEL = whisper.load_model(
            model_name, download_root=str(models_dir), device=device
        )
    else:
        _WHISPER_MODEL = whisper.load_model(model_name, download_root=str(models_dir))
    return _WHISPER_MODEL

async def progress_bar_animation(message: Message, stop_event: asyncio.Event):
    """Animation of a 'thinking' bot"""
    frames = ["[░░░░░░░░░░]", "[▓░░░░░░░░░]", "[▓▓░░░░░░░░]", "[▓▓▓░░░░░░░]", 
              "[▓▓▓▓░░░░░░]", "[▓▓▓▓▓░░░░░]", "[▓▓▓▓▓▓░░░░]", "[▓▓▓▓▓▓▓░░░]"]
    i = 0
    status_msg = await message.answer("Starting processing...")
    
    try:
        while not stop_event.is_set():
            await status_msg.edit_text(f"The processing is working...\n{frames[i % len(frames)]}")
            await asyncio.sleep(0.5)
            i += 1
    except Exception:
        pass
    
    return status_msg

dp = Dispatcher()


def _get_bot_token() -> str:
    token = getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("No BOT_TOKEN provided! Please set it in .env file.")
    return token


def _should_preload_model() -> bool:
    value = (getenv("WHISPER_PRELOAD") or "1").strip().lower()
    return value not in {"0", "false", "no", "off"}

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    await message.answer(f"Hello, {html.bold(message.from_user.full_name)}!")

@dp.message(F.content_type == "voice")
async def voice_handler(message: Message) -> None:
    """
    This handler receives messages with `voice` content type
    """
    voice: Voice = message.voice
    file_info = await message.bot.get_file(voice.file_id)
    file_path = file_info.file_path
    
    local_filename = Path(f"voice_{voice.file_id}.ogg")
    stop_whisper_event = asyncio.Event()
    progress_task = asyncio.create_task(progress_bar_animation(message, stop_whisper_event))
    status_msg = None
    try:
        await message.bot.download_file(file_path, local_filename)

        request_obj = VoiceProcessingRequest(
            file_id=voice.file_id,
            user_id=str(message.from_user.id),
            file_path=local_filename,
            model=_get_whisper_model(),
        )

        voice_transcription: WhisperResult = await asyncio.to_thread(
            transcribe_audio, request_obj
        )

        await message.answer(f"Transcription:\n{voice_transcription.text}")
        await message.answer("Nice voice!")
    except Exception as e:
        logging.error(f"Error processing voice message: {e}")
        await message.answer("Sorry, something went wrong while processing your voice message.")
    finally:
        stop_whisper_event.set()
        with suppress(Exception):
            status_msg = await progress_task
        if status_msg is not None:
            with suppress(Exception):
                await status_msg.delete()
        with suppress(FileNotFoundError):
            local_filename.unlink()
        
@dp.message()
async def echo_handler(message: Message) -> None:
    """
    Handler will forward receive a message back to the sender

    By default, message handler will handle all message types (like a text, photo, sticker etc.)
    """
    try:
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        await message.answer("Nice try!")


async def main() -> None:
    if _should_preload_model():
        logging.info("Preloading Whisper model...")
        _get_whisper_model()
        logging.info("Whisper model loaded.")
    bot = Bot(token=_get_bot_token(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
