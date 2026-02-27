import asyncio
import logging
from contextlib import suppress
from pathlib import Path
import re
import sys
from os import getenv
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, Voice, CallbackQuery
import whisper
from app.db.base import get_db
from app.db.models import NotionCredential, NotionSetup
from app.services.credential_manager import NotionKeyPipline
from app.services.notion_serviceю import NotionPublisher
from app.speech_recogniser.speach_engine import WhisperResult, transcribe_audio
from app.voice_processing import VoiceProcessingRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db.models import NotionCredential
from services.notion_vault import NotionVault

load_dotenv()

_WHISPER_MODEL = None

# FIXME replace with radishes. Dictionary for tracking statuses (to avoid adding twice) 
pending_confirmations = {}




async def save_to_notion_logic(transcription: str, user_id: int):
    session_local = get_db()
    with session_local as session:
        cred = session.query(NotionCredential).filter_by(user_id=user_id).first()
        if not cred:
            print(f"Error: Key for user {user_id} not found.")
            return

    vault = NotionVault()
    decrypted_key = vault.decrypt_key(cred.encrypted_key)

    title = f"Голосова нотатка: {transcription[:30]}..."

    publisher = NotionPublisher(decrypted_key, cred.database_id)
    try:
        await publisher.create_memo_page(title=title, summary=transcription)
    except Exception as e:
        print(f"Error writing to Notion: {e}")
        
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


def _extract_notion_database_id(text: str) -> str | None:
    if not text:
        return None
    match = re.search(
        r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})",
        text,
    )
    if not match:
        return None
    raw_id = match.group(1)
    return raw_id.replace("-", "").lower()

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

@dp.message(NotionSetup.waiting_for_key)
async def process_notion_key(message: Message, state: FSMContext):
    raw_key = message.text
    tg_id = message.from_user.id
    try:
        await message.delete()
    except Exception as e:
        print(f"Failed to delete message: {e}")
        await message.answer("We were unable to delete your message. Please delete it manually.")

    if not raw_key:
        await message.answer("Надішліть Notion API key текстом.")
        return

    master_key = getenv("MASTER_KEY")
    if not master_key:
        logging.error("MASTER_KEY is not set")
        await message.answer("The server is not configured. Please try again later.")
        return

    try:
        pipeline = NotionKeyPipline(raw_key, master_key)
        pipeline.step_1_sanitize().step_2_validation().step_3_encrypt()
    except RuntimeError as e:
        logging.exception("MASTER_KEY configuration error: %s", e)
        await message.answer("The server is not configured. Please try again later.")
        return
    except ValueError as e:
        await message.answer(str(e))
        return

    with get_db() as session:
        pipeline.save_to_db(
            session,
            user_id=tg_id,
            workspace_name="Default Workspace",
        )

    await state.set_state(NotionSetup.waiting_for_database)
    await message.answer(
       "Great! Now send me the link to the Notion database or its ID."
    )


@dp.message(NotionSetup.waiting_for_database)
async def process_notion_database(message: Message, state: FSMContext):
    raw_text = message.text or ""
    tg_id = message.from_user.id

    database_id = _extract_notion_database_id(raw_text)
    if not database_id:
        await message.answer(
           "Could not find ID. Please send a link to the Notion database or the ID itself."
        )
        return

    with get_db() as session:
        existing = session.query(NotionCredential).filter_by(user_id=tg_id).first()
        if existing:
            existing.database_id = database_id
            existing.workspace_name = existing.workspace_name or "Default Workspace"
        else:
            await message.answer("The key has not been saved yet. Send /start and try again.")
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
                f"Hello! Your Notion is connected (Key ID: {user_cred.id}). You can send voice messages!"
            )
            return

        if user_cred and not user_cred.database_id:
            await message.answer(
                "Great! Now send me the link to the Notion database or its ID."
            )
            await state.set_state(NotionSetup.waiting_for_database)
            return

        await message.answer(
            "Please send your Notion API Key (secret_...)."
        )
        await state.set_state(NotionSetup.waiting_for_key)

async def save_to_notion_placeholder(transcription: str, user_id: int):
    """This is a placeholder function where you would implement the logic to save the transcription to Notion."""
    await asyncio.sleep(1)  # Simulate some processing time
    logging.info(f"Saving to Notion for user {user_id}: {transcription[:30]}...")
    
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
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Accept", callback_data=f"accept_note_{str(message.from_user.id)}")
        kb.button(text="❌ Reject", callback_data=f"reject_note_{str(message.from_user.id)}")
        confirm_msg = await message.answer(
        f"The note is ready:\n\n\"{voice_transcription.text}\"\n\nAdd to Notion? (Auto-save in 10 seconds)",
        reply_markup=kb.as_markup()
    )
        
        note_id = confirm_msg.message_id
        pending_confirmations[note_id] = {
        "text": voice_transcription.text ,
        "user_id": str(message.from_user.id),
        "processed": False
        }
        asyncio.create_task(handle_auto_save(note_id, confirm_msg))
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
 
 #FIXME: This function should be improved to handle multiple notes
async def handle_auto_save(note_id: int, message_obj: Message):
    """A background task that waits 10 seconds and saves if there is no response"""
    await asyncio.sleep(10)
    
    data = pending_confirmations.get(note_id)
    if data and not data["processed"]:
        data["processed"] = True
       # Calling  function
        await save_to_notion_placeholder(data["text"], data["user_id"])
        
       # We update the message so that the user can see that it has been saved automatically.
        await message_obj.edit_text(
            f"✅ Automatically saved in Notion:\n\n\"{data['text']}\"",
            reply_markup=None
        )
        # Deleting from memory
        pending_confirmations.pop(note_id, None)

@dp.callback_query(F.data.startswith("accept_note_"))
async def accept_handler(callback: CallbackQuery):
    note_id = callback.message.message_id
    data = pending_confirmations.get(note_id)
    
    if data and not data["processed"]:
        data["processed"] = True
        await save_to_notion_placeholder(data["text"], data["user_id"])
        await callback.message.edit_text(f"✅ Saved by user:\n\n\"{data['text']}\"")
        await callback.answer("Saved!")
    
    pending_confirmations.pop(note_id, None)
    
@dp.callback_query(F.data.startswith("reject_note_"))
async def reject_handler(callback: CallbackQuery):
    note_id = callback.message.message_id
    
    if note_id in pending_confirmations:
        pending_confirmations[note_id]["processed"] = True
        
        await callback.message.edit_text("❌ The note has been cancelled.")
        
        await callback.answer("Deleted")
        
        # Clearing the memory
        pending_confirmations.pop(note_id, None)
        
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
