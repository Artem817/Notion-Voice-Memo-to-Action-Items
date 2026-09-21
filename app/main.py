import asyncio
import logging
import re
import sys
import tempfile
from contextlib import suppress
from os import getenv
from pathlib import Path

from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message, Voice
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
import whisper

from app.db.base import get_db, engine, Base
from app.db.models import NotionCredential, NotionSetup
from app.services.credential_manager import NotionKeyPipeline
from app.services.llm_service import GeminiLLMService, ProcessedMemo
from app.services.notion_publisher import (
    NotionCredentialsMissing,
    NotionPublishError,
    NotionPublisher,
)
from app.speech_recogniser.speech_engine import WhisperResult, transcribe_audio
from app.utils import extract_notion_database_id
from app.voice_processing import VoiceProcessingRequest

load_dotenv()

_WHISPER_MODEL = None

pending_confirmations = {}

_llm_service: GeminiLLMService | None = None


def _get_llm_service() -> GeminiLLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = GeminiLLMService()
    return _llm_service


def _get_publisher() -> NotionPublisher:
    master_key = getenv("MASTER_KEY")
    if not master_key:
        raise RuntimeError("MASTER_KEY is not set")
    return NotionPublisher(get_db, master_key)


async def save_to_notion(
    structured_data: ProcessedMemo,
    transcript: str,
    user_id: int,
) -> tuple[bool, str]:
    try:
        publisher = _get_publisher()
    except RuntimeError:
        logging.error("MASTER_KEY is not set")
        return False, "Server not configured. Please try again later."
    try:
        await publisher.publish_from_user_id(
            user_id=user_id,
            title=structured_data.llm_data.title,
            tasks=structured_data.llm_data.tasks,
            transcript=transcript,
            date_value=structured_data.llm_data.task_date_from_user,
            priority=structured_data.llm_data.priority,
        )
    except NotionCredentialsMissing:
        return False, "Notion is not connected. Send /start and connect the database."
    except NotionPublishError as exc:
        logging.exception("Notion publish error: %s", exc)
        return False, "Failed to save note to Notion."
    except Exception as exc:  # pragma: no cover - unexpected error
        logging.exception("Unexpected Notion error: %s", exc)
        return False, "Failed to save note to Notion."

    return True, ""

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


whisper_semaphore = asyncio.Semaphore(1)

async def progress_bar_animation(message: Message, stop_event: asyncio.Event):
    frames = ["[░░░░░░░░░░]", "[▓░░░░░░░░░]", "[▓▓░░░░░░░░]", "[▓▓▓░░░░░░░]"]
    i = 0
    status_msg = await message.answer("Starting processing...")
    
    try:
        while not stop_event.is_set():
            try:
                await status_msg.edit_text(f"Processing...\n{frames[i % len(frames)]}")
            except Exception as e:
                pass 
            await asyncio.sleep(1.5) 
            i += 1
    except asyncio.CancelledError:
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


# If ADMIN_ID is unset, getenv returns None -> int(0) -> 0. 
# User ID 0 doesn't exist, so this safely blocks everyone.
@dp.message(F.from_user.id != int(getenv("ADMIN_ID") or 0))
async def access_denied_handler(message: Message):
    """
    Blocks all messages from users whose ID does not match ADMIN_ID
    """
    await message.answer("Access Restricted\nThis bot is in private test mode. Please contact the administrator.")
    logging.warning("Unauthorized access attempt by %s (ID: %s)", message.from_user.full_name, message.from_user.id)
    return 

@dp.callback_query(F.from_user.id != int(getenv("ADMIN_ID") or 0))
async def access_denied_callback(callback: CallbackQuery):
    await callback.answer("Access denied.", show_alert=True)
    

@dp.message(NotionSetup.waiting_for_key)
async def process_notion_key(message: Message, state: FSMContext):
    raw_key = message.text
    tg_id = message.from_user.id
    try:
        await message.delete()
    except Exception as e:
        logging.warning("Failed to delete message: %s", e)
        await message.answer("Failed to delete your message. Please delete it manually.")

    if not raw_key:
        await message.answer("Send Notion API key as text.")
        return

    master_key = getenv("MASTER_KEY")
    if not master_key:
        logging.error("MASTER_KEY is not set")
        await message.answer("Server not configured. Try again later.")
        return

    try:
        pipeline = NotionKeyPipeline(raw_key, master_key)
        pipeline.step_1_sanitize().step_2_validation().step_3_encrypt()
    except RuntimeError as e:
        logging.exception("MASTER_KEY configuration error: %s", e)
        await message.answer("Server not configured. Try again later.")
        return
    except ValueError as e:
        await message.answer(f"{e}\nPlease try again.")
        # We generally want to keep the user in the waiting_for_key state so they can retry immediately,
        # so we do NOT clear the state here.
        return

    with get_db() as session:
        pipeline.save_to_db(
            session,
            user_id=tg_id,
            workspace_name="Default Workspace",
        )

    await state.set_state(NotionSetup.waiting_for_database)
    await message.answer(
        "Great! Now send the link to the Notion database or its ID."
    )


@dp.message(NotionSetup.waiting_for_database)
async def process_notion_database(message: Message, state: FSMContext):
    raw_text = message.text or ""
    tg_id = message.from_user.id

    database_id = extract_notion_database_id(raw_text)
    if not database_id:
        await message.answer(
            "Failed to find ID. Send the link to the Notion database or the ID itself."
        )
        return

    with get_db() as session:
        existing = session.query(NotionCredential).filter_by(user_id=tg_id).first()
        if existing:
            existing.database_id = database_id
            existing.workspace_name = existing.workspace_name or "Default Workspace"
        else:
            await message.answer("Key not saved yet. Send /start and try again.")
            await state.clear()
            return
        session.commit()

    await message.answer(
        "All done! Don't forget to click Share in Notion and add my integration to this database."
    )
    await state.clear()
        
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    """
    This handler receives messages with `/start` command
    """
    tg_id = message.from_user.id
    with get_db() as session:
        user_cred = session.query(NotionCredential).filter_by(user_id=tg_id).first()

        if user_cred and user_cred.database_id:
            await message.answer(
                f"Hello! Your Notion is connected (Key ID: {user_cred.id}). You can send voice messages."
            )
            return

        if user_cred and not user_cred.database_id:
            await message.answer(
                "Great! Now send the link to the Notion database or its ID."
            )
            await state.set_state(NotionSetup.waiting_for_database)
            return

        await message.answer(
            "Welcome to NotionVoiceMemo! Let's connect your Notion first. For instructions, send /help")
        
        await message.answer(
            "Send your Notion API Key (secret_ or ntn_...)."
        )
        await state.set_state(NotionSetup.waiting_for_key)

@dp.message(F.content_type == "voice")
async def voice_handler(message: Message) -> None:
    """
    This handler receives messages with `voice` content type
    """
    voice: Voice = message.voice
    file_info = await message.bot.get_file(voice.file_id)
    file_path = file_info.file_path
    
    stop_whisper_event = asyncio.Event()
    progress_task = asyncio.create_task(progress_bar_animation(message, stop_whisper_event))
    status_msg = None
    
    # Use a temporary file to avoid leaving orphans in CWD
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        local_filename = Path(tmp.name)
        
    try:
        await message.bot.download_file(file_path, local_filename)

        request_obj = VoiceProcessingRequest(
            file_id=voice.file_id,
            user_id=str(message.from_user.id),
            file_path=local_filename,
            model=_get_whisper_model(),
        )

        async with whisper_semaphore:
            voice_transcription: WhisperResult = await asyncio.to_thread(
                transcribe_audio, request_obj
            )

        try:
            llm_service = _get_llm_service()
            structured_data = await llm_service.structure_transcript(
                voice_transcription.text
            )
        except Exception as e:
            logging.exception("LLM processing failed: %s", e)
            await message.answer("Failed to process transcription via LLM.")
            return

        tasks_preview = "\n".join(
            f"• {task}" for task in structured_data.llm_data.tasks
        )
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Add", callback_data=f"accept_note_{message.from_user.id}")
        kb.button(text="❌ Cancel", callback_data=f"reject_note_{message.from_user.id}")
        confirm_msg = await message.answer(
            "Note ready:\n\n"
            f"{structured_data.llm_data.title}\n"
            f"{tasks_preview}\n\n"
            "Add to Notion? (Autosave in 10 seconds)",
            reply_markup=kb.as_markup(),
        )
        
        await register_auto_save(
            confirm_msg,
            voice_transcription.text,
            structured_data,
            message.from_user.id
        )
    except Exception as e:
        logging.error("Error processing voice message: %s", e)
        await message.answer("An error occurred while processing the voice message.")
    finally:
        stop_whisper_event.set()
        with suppress(Exception):
            status_msg = await progress_task
        if status_msg is not None:
            with suppress(Exception):
                await status_msg.delete()
        with suppress(FileNotFoundError):
            local_filename.unlink()
 
@dp.message(Command("help"))
async def handle_help(message: Message):
    pdf_path = Path(__file__).parent.parent / "guide.pdf" 
    
    try:
        pdf_file = FSInputFile(pdf_path)
        await message.answer_document(
            document=pdf_file,
            caption="NotionVoiceMemo Setup Guide (PDF)\n\nFollow these steps to connect your database."
        )
    except Exception as e:
        logging.error("Failed to send PDF: %s", e)
        await message.answer("Sorry, I couldn't find the guide file.")
        
async def register_auto_save(
    message_obj: Message,
    transcript: str,
    structured_data: ProcessedMemo,
    user_id: int,
):
    """Registers a note for auto-save and starts the timer."""
    note_id = message_obj.message_id
    pending_confirmations[note_id] = {
        "text": transcript,
        "structured": structured_data,
        "user_id": user_id,
        "processed": False,
    }
    
    # Start the background task
    asyncio.create_task(_auto_save_task(note_id, message_obj))


async def _auto_save_task(note_id: int, message_obj: Message):
    """A background task that waits 10 seconds and saves if there is no response"""
    await asyncio.sleep(10)
    
    data = pending_confirmations.get(note_id)
    if data and not data["processed"]:
        data["processed"] = True
        success, error_message = await save_to_notion(
            structured_data=data["structured"],
            transcript=data["text"],
            user_id=data["user_id"],
        )

        if success:
            await message_obj.edit_text(
                "✅ Automatically saved to Notion.",
                reply_markup=None,
            )
        else:
            await message_obj.edit_text(
                f"❌ Failed to save to Notion. {error_message}",
                reply_markup=None,
            )
        # Deleting from memory
        pending_confirmations.pop(note_id, None)

@dp.callback_query(F.data.startswith("accept_note_"))
async def accept_handler(callback: CallbackQuery):
    note_id = callback.message.message_id
    data = pending_confirmations.get(note_id)
    
    if data and not data["processed"]:
        data["processed"] = True
        success, error_message = await save_to_notion(
            structured_data=data["structured"],
            transcript=data["text"],
            user_id=data["user_id"],
        )
        if success:
            await callback.message.edit_text("✅ Saved to Notion.")
            await callback.answer("Saved!")
        else:
            await callback.message.edit_text(f"❌ Failed to save. {error_message}")
            await callback.answer("Error")
    
    pending_confirmations.pop(note_id, None)
    
@dp.callback_query(F.data.startswith("reject_note_"))
async def reject_handler(callback: CallbackQuery):
    note_id = callback.message.message_id
    
    if note_id in pending_confirmations:
        pending_confirmations[note_id]["processed"] = True
        
        await callback.message.edit_text("❌ Note cancelled.")

        await callback.answer("Deleted")
        
        # Clearing the memory
        pending_confirmations.pop(note_id, None)
        
@dp.message()
async def fallback_handler(message: Message) -> None:
    """Handles all unrecognized message types."""
    await message.answer(
        "I only understand voice messages.\n"
        "Send me a voice memo and I'll transcribe it and create a Notion note.\n"
        "Send /help for setup instructions."
    )


async def main() -> None:
    # Auto-create tables (if Alembic is not run manually)
    Base.metadata.create_all(bind=engine)
    
    if _should_preload_model():
        logging.info("Preloading Whisper model...")
        _get_whisper_model()
        logging.info("Whisper model loaded.")
    bot = Bot(token=_get_bot_token(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
