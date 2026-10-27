import asyncio
import glob
import html
import json
import logging
import math
import os
import re
import subprocess
import uuid
from typing import Dict, Optional, Tuple

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv
import imageio_ffmpeg
import yt_dlp

from converters import (
    csv_to_excel,
    doc_to_docx,
    docx_to_pdf,
    docx_to_txt,
    excel_to_csv,
    excel_to_pdf,
    image_to_pdf,
    pdf_to_docx,
    pdf_to_txt,
)
from transcriber import transcribe_audio

# .env faylidan o'zgaruvchilarni yuklash
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "DIQQAT: BOT_TOKEN topilmadi! Iltimos, .env fayliga Telegram bot tokeningizni kiriting."
    )

# Logging sozlamalari (Faylga darhol yozish uchun FileHandler)
file_handler = logging.FileHandler("bot.log", mode="a", encoding="utf-8")
stream_handler = logging.StreamHandler()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger(__name__)

# Bot va Dispatcher yaratish (5 daqiqagacha bo'lgan katta fayllarni yuklash uchun timeout=300.0)
session = AiohttpSession(timeout=300.0)
bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Vaqtinchalik fayllar uchun papka
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Yuklangan hujjatlarni vaqtinchalik saqlash lug'ati
pending_documents: Dict[str, dict] = {}

# Havolalarni aniqlash uchun regex
INSTAGRAM_URL_REGEX = re.compile(
    r"(https?://(?:www\.)?instagram\.com/(?:p|reel|reels|tv|share)/[a-zA-Z0-9_\-]+/?(?:\?[^\s]*)?)",
    re.IGNORECASE
)

YOUTUBE_URL_REGEX = re.compile(
    r"(https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?[^\s]+|shorts/[^\s]+|live/[^\s]+|embed/[^\s]+)|youtu\.be/[^\s]+))",
    re.IGNORECASE
)


# Barcha kelayotgan xabarlarni log qilish uchun middleware
@dp.message.outer_middleware()
async def log_all_messages(handler, event: types.Message, data):
    user_id = event.from_user.id if event.from_user else "Unknown"
    user_name = event.from_user.first_name if event.from_user else "Unknown"
    msg_preview = repr(event.text[:80]) if event.text else str(event.content_type)
    logger.info(f"Yangi xabar keldi: User={user_name} (ID:{user_id}), ContentType={event.content_type}, Info={msg_preview}")
    return await handler(event, data)


# Xatoliklarni ushlab qoluvchi handler
@dp.error()
async def global_error_handler(event: types.ErrorEvent):
    logger.exception(f"Kutilmagan tizim xatoligi: {event.exception}")
    try:
        if event.update and event.update.message:
            await event.update.message.answer(
                f"❌ Xatolik yuz berdi: <code>{html.escape(str(event.exception)[:200])}</code>"
            )
    except Exception:
        pass


# ==========================================
# 1-FUNKSIYA: VIDEO YUKLASH (Instagram & YouTube)
# ==========================================

def extract_url_and_platform(text: str) -> Tuple[Optional[str], Optional[str]]:
    insta_match = INSTAGRAM_URL_REGEX.search(text)
    if insta_match:
        return insta_match.group(1).rstrip('.,)>] \n\t'), "Instagram"

    yt_match = YOUTUBE_URL_REGEX.search(text)
    if yt_match:
        return yt_match.group(1).rstrip('.,)>] \n\t'), "YouTube"

    return None, None


def download_media_video(url: str, platform: str, download_id: str) -> Optional[dict]:
    output_template = os.path.join(DOWNLOAD_DIR, f"{download_id}_%(id)s.%(ext)s")

    # YouTube uchun 720p HD (agar 720p bo'lmasa eng yaxshi mavjud sifat)
    format_selector = (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
        "best[height<=720][ext=mp4]/"
        "bestvideo[height<=720]+bestaudio/"
        "best[height<=720]/best"
    )

    ydl_opts = {
        "outtmpl": output_template,
        "format": format_selector,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"]
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Agar kengaytmasi mp4 bo'lib qolgan bo'lsa
            if not os.path.exists(filename):
                mp4_candidate = os.path.splitext(filename)[0] + ".mp4"
                if os.path.exists(mp4_candidate):
                    filename = mp4_candidate
                else:
                    matches = glob.glob(os.path.join(DOWNLOAD_DIR, f"{download_id}_*"))
                    if matches:
                        filename = matches[0]
                    else:
                        return None

            return {
                "file_path": filename,
                "title": info.get("title") or f"{platform} Video",
                "duration": int(info.get("duration") or 0),
                "width": info.get("width"),
                "height": info.get("height"),
            }
    except Exception as e:
        logger.error(f"{platform} dan yuklab olishda xatolik: {e}")
        return None


def split_video_chunks(file_path: str, duration: int, file_size: int, chunk_size: int = 48 * 1024 * 1024) -> list:
    """
    Katta videolarni Telegram limitidan (48 MB) oshmasligi uchun
    qayta render qilmasdan (-c copy) juda tez qismlarga bo'ladi.
    """
    parts_count = math.ceil(file_size / chunk_size)
    if parts_count <= 1 or duration <= 0:
        return [file_path]

    part_duration = duration / parts_count
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    base_name, ext = os.path.splitext(file_path)
    output_files = []

    for i in range(parts_count):
        start_time = i * part_duration
        out_part = f"{base_name}_part{i+1}{ext}"
        cmd = [
            ffmpeg_exe, "-y",
            "-ss", str(start_time),
            "-i", file_path,
            "-t", str(part_duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            out_part
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(out_part) and os.path.getsize(out_part) > 0:
            output_files.append(out_part)

    return output_files if output_files else [file_path]


# ==========================================
# ASOSIY MENYU VA BUYRUQLAR: /start va /help
# ==========================================

def get_main_inline_keyboard() -> InlineKeyboardMarkup:
    """Asosiy menyu uchun inline tugmalar"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 1. Video yuklash (YouTube & Insta)", callback_data="menu:video")],
            [InlineKeyboardButton(text="📄 2. Hujjatlar konvertatsiyasi", callback_data="menu:docs")],
            [InlineKeyboardButton(text="🎙 3. Ovozni matnga o'girish", callback_data="menu:voice")],
            [InlineKeyboardButton(text="ℹ️ 4. Bot haqida va Qo'llanma", callback_data="menu:help")],
        ]
    )


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """Pastki tezkor menyu tugmalari"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Video yuklash"), KeyboardButton(text="📄 Hujjat konvertatsiyasi")],
            [KeyboardButton(text="🎙 Ovozni matnga o'girish"), KeyboardButton(text="ℹ️ Yordam / Menyu")]
        ],
        resize_keyboard=True
    )


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_name = message.from_user.first_name if message.from_user else "Foydalanuvchi"
    welcome_text = (
        f"Assalomu alaykum, <b>{user_name}</b>! 👋\n\n"
        "Men sizning ko'p funksiyali shaxsiy yordamchingizman.\n"
        "Quyidagi bo'limlardan birini tanlang va kerakli xizmatdan foydalaning:"
    )
    # Pastdagi qulay tugmalarni ham yoqamiz
    await message.answer("Bosh menyu ochildi 👇", reply_markup=get_reply_keyboard())
    # Asosiy interaktiv inline menyuni chiqaramiz
    await message.answer(welcome_text, reply_markup=get_main_inline_keyboard())


@dp.callback_query(F.data.startswith("menu:"))
async def handle_menu_callback(callback: CallbackQuery):
    action = callback.data.split(":")[1]

    if action == "video":
        text = (
            "🎬 <b>1. Video yuklash (YouTube & Instagram)</b>\n\n"
            "Bu bo'lim orqali istalgan videoni yuklab olishingiz mumkin:\n"
            "• <b>YouTube:</b> 720p HD sifatda oddiy video va Shorts\n"
            "• <b>Instagram:</b> Reels, Post va barcha videolar\n"
            "• <i>Katta hajmdagi videolar avtomatik qismlarga bo'linib to'liq yuboriladi.</i>\n\n"
            "👉 <b>Qanday ishlatiladi?</b>\n"
            "Shunchaki YouTube yoki Instagram video havolasini menga yuboring!"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Asosiy menyuga qaytish", callback_data="menu:main")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)

    elif action == "docs":
        text = (
            "📄 <b>2. Hujjatlar konvertatsiyasi</b>\n\n"
            "Quyidagi fayl turlarini bir-biriga aylantirishingiz mumkin:\n"
            "• <b>Word (.docx, .doc)</b> ➔ PDF, .docx yoki Matn (.txt)\n"
            "• <b>PDF (.pdf)</b> ➔ Word (.docx) yoki Matn (.txt)\n"
            "• <b>Excel (.xlsx)</b> ➔ PDF yoki CSV\n"
            "• <b>CSV</b> ➔ Excel (.xlsx)\n"
            "• <b>Rasm (JPG, PNG)</b> ➔ PDF\n\n"
            "👉 <b>Qanday ishlatiladi?</b>\n"
            "Hujjat yoki rasm faylini botga yuboring va chiqadigan tugmalar orqali kerakli formatni tanlang!"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Asosiy menyuga qaytish", callback_data="menu:main")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)

    elif action == "voice":
        text = (
            "🎙 <b>3. Ovozni matnga o'girish (Voice-to-Text)</b>\n\n"
            "Ovozli xabarlarni tinglashga imkoniyatingiz yo'qmi?\n"
            "Menga ovozli xabar (Voice) yoki audio fayl (.mp3, .ogg) yuboring — men uni sun'iy intellekt yordamida matn ko'rinishida yozib beraman!\n\n"
            "👉 <b>Qanday ishlatiladi?</b>\n"
            "Hoziroq mikrofoni bosib ovozli xabar yuboring!"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Asosiy menyuga qaytish", callback_data="menu:main")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)

    elif action == "help":
        text = (
            "ℹ️ <b>4. Bot haqida va Qo'llanma</b>\n\n"
            "• 🤖 <b>Bot:</b> @khurshid_media_bot\n"
            "• ⏱ <b>Ishlash vaqti:</b> 24/7 to'xtovsiz\n"
            "• 👥 <b>Foydalanish:</b> Cheklovlarsiz va mutlaqo bepul\n\n"
            "Bosh menyuga qaytish uchun quyidagi tugmani bosing:"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Asosiy menyuga qaytish", callback_data="menu:main")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)

    elif action == "main":
        user_name = callback.from_user.first_name if callback.from_user else "Foydalanuvchi"
        welcome_text = (
            f"Assalomu alaykum, <b>{user_name}</b>! 👋\n\n"
            "Quyidagi funksiyalardan birini tanlang va foydalaning:"
        )
        await callback.message.edit_text(welcome_text, reply_markup=get_main_inline_keyboard())

    await callback.answer()


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Bot bo'limlari:</b>\n"
        "Kerakli xizmatni tanlash uchun quyidagi tugmalardan foydalaning:",
        reply_markup=get_main_inline_keyboard()
    )


# ==========================================
# 3-FUNKSIYA: OVOZLI XABARLARNI MATNGA O'GIRISH
# ==========================================

@dp.message(F.voice | F.audio)
async def handle_voice_message(message: types.Message):
    """
    Ovozli xabar yoki audio kelganda uni matnga o'girish.
    """
    status_msg = await message.reply("🎙 <i>Ovozli xabar tinglanmoqda va matnga o'girilmoqda...</i>")
    audio_obj = message.voice or message.audio

    file_ext = ".ogg" if message.voice else os.path.splitext(audio_obj.file_name or "audio.mp3")[1]
    temp_audio_path = os.path.join(DOWNLOAD_DIR, f"voice_{uuid.uuid4().hex[:8]}{file_ext}")

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

        # Faylni to'g'ridan-to'g'ri yuklab olish (timeout 300 soniya)
        await bot.download(audio_obj, destination=temp_audio_path, timeout=300)

        # Ovozni matnga o'girish (alohida thread'da)
        text, detected_lang = await asyncio.to_thread(transcribe_audio, temp_audio_path)

        if text:
            reply_text = (
                f"📝 <b>Aniqlangan matn:</b>\n\n"
                f"<i>«{html.escape(text)}»</i>\n\n"
                f"🌐 Til: <b>{detected_lang}</b>"
            )
            await status_msg.edit_text(reply_text)
        else:
            await status_msg.edit_text(
                "❌ <b>Ovozni matnga aylantirib bo'lmadi!</b>\n\n"
                "Mumkin bo'lgan sabablar:\n"
                "• Ovoz juda past yoki shovqinli;\n"
                "• So'zlar aniq aytilmagan."
            )

    except Exception as e:
        logger.error(f"Ovozni matnga o'girishda xatolik: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: <code>{str(e)}</code>")

    finally:
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except Exception:
                pass


# ==========================================
# 2-FUNKSIYA: HUJJATLAR KONVERTATSIYASI (Word, Excel, PDF, Rasm)
# ==========================================

@dp.message(F.document)
async def handle_document_upload(message: types.Message):
    """
    Hujjat kelganda formatini tekshirish va foydalanuvchiga konvertatsiya tugmalarini ko'rsatish.
    """
    doc = message.document
    orig_name = doc.file_name or "document"
    ext = os.path.splitext(orig_name)[1].lower()

    supported_exts = [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv"]
    if ext not in supported_exts:
        await message.reply(
            f"⚠️ <b>{ext}</b> formati qo'llab-quvvatlanmaydi.\n\n"
            "Qo'llab-quvvatlanadigan formatlar: <b>PDF, Word (.docx, .doc), Excel (.xlsx), CSV</b>"
        )
        return

    status_msg = await message.reply("📥 Hujjat qabul qilinmoqda...")
    doc_id = uuid.uuid4().hex[:10]
    local_path = os.path.join(DOWNLOAD_DIR, f"{doc_id}_{orig_name}")

    try:
        await bot.download(doc, destination=local_path, timeout=300)

        pending_documents[doc_id] = {
            "path": local_path,
            "orig_name": orig_name,
            "ext": ext,
            "user_id": message.from_user.id
        }

        buttons = []
        if ext == ".pdf":
            buttons.append([InlineKeyboardButton(text="📝 Word ga (.docx)", callback_data=f"conv:pdf_to_docx:{doc_id}")])
            buttons.append([InlineKeyboardButton(text="📄 Matn ko'rinishida (.txt)", callback_data=f"conv:pdf_to_txt:{doc_id}")])
        elif ext == ".doc":
            buttons.append([InlineKeyboardButton(text="📝 Zamonaviy Word ga (.docx)", callback_data=f"conv:doc_to_docx:{doc_id}")])
            buttons.append([InlineKeyboardButton(text="📕 PDF ga (.pdf)", callback_data=f"conv:docx_to_pdf:{doc_id}")])
            buttons.append([InlineKeyboardButton(text="📄 Matn ko'rinishida (.txt)", callback_data=f"conv:docx_to_txt:{doc_id}")])
        elif ext == ".docx":
            buttons.append([InlineKeyboardButton(text="📕 PDF ga (.pdf)", callback_data=f"conv:docx_to_pdf:{doc_id}")])
            buttons.append([InlineKeyboardButton(text="📄 Matn ko'rinishida (.txt)", callback_data=f"conv:docx_to_txt:{doc_id}")])
        elif ext in [".xlsx", ".xls"]:
            buttons.append([InlineKeyboardButton(text="📕 PDF ga (.pdf)", callback_data=f"conv:excel_to_pdf:{doc_id}")])
            buttons.append([InlineKeyboardButton(text="📊 CSV ga (.csv)", callback_data=f"conv:excel_to_csv:{doc_id}")])
        elif ext == ".csv":
            buttons.append([InlineKeyboardButton(text="📊 Excel ga (.xlsx)", callback_data=f"conv:csv_to_excel:{doc_id}")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await status_msg.edit_text(
            f"📄 Hujjat: <b>{html.escape(orig_name)}</b>\n\n"
            "Quyidagilardan qaysi formatga o'tkazmoqchisiz?",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Hujjatni yuklab olishda xatolik: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: <code>{str(e)}</code>")
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


@dp.message(F.photo)
async def handle_photo_upload(message: types.Message):
    """
    Rasm kelganda uni PDF ga o'girish tugmasini chiqarish.
    """
    photo = message.photo[-1]
    status_msg = await message.reply("🖼 Rasm qabul qilindi...")

    photo_id = uuid.uuid4().hex[:10]
    local_path = os.path.join(DOWNLOAD_DIR, f"{photo_id}.jpg")

    try:
        await bot.download(photo, destination=local_path, timeout=300)

        pending_documents[photo_id] = {
            "path": local_path,
            "orig_name": "rasm.jpg",
            "ext": ".jpg",
            "user_id": message.from_user.id
        }

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📕 PDF formatiga aylantirish", callback_data=f"conv:img_to_pdf:{photo_id}")]
        ])

        await status_msg.edit_text(
            "🖼 Rasm qabul qilindi. Uni <b>PDF</b> ga aylantirishni xohlaysizmi?",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Rasmni yuklab olishda xatolik: {e}")
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: <code>{str(e)}</code>")


@dp.callback_query(F.data.startswith("conv:"))
async def handle_conversion_callback(callback: CallbackQuery):
    """
    Foydalanuvchi format tanlaganda konvertatsiyani amalga oshirish.
    """
    data_parts = callback.data.split(":")
    if len(data_parts) != 3:
        await callback.answer("Noto'g'ri so'rov!")
        return

    _, conv_type, doc_id = data_parts
    doc_info = pending_documents.get(doc_id)

    # Agar xotirada bo'lmasa, diskdan qidirish
    input_path = None
    orig_name = "document"

    if doc_info and os.path.exists(doc_info["path"]):
        input_path = doc_info["path"]
        orig_name = doc_info["orig_name"]
    else:
        disk_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{doc_id}_*"))
        if disk_files:
            input_path = disk_files[0]
            orig_name = os.path.basename(input_path).replace(f"{doc_id}_", "")

    if not input_path or not os.path.exists(input_path):
        await callback.answer("⚠️ Fayl topilmadi yoki muddati o'tgan! Qaytadan yuboring.", show_alert=True)
        return

    base_name = os.path.splitext(orig_name)[0]

    await callback.message.edit_text("⏳ <i>Hujjat o'zgartirilmoqda, iltimos kuting...</i>")
    await bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.UPLOAD_DOCUMENT)

    output_path = None
    success = False

    try:
        if conv_type == "pdf_to_docx":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.docx")
            success = await asyncio.to_thread(pdf_to_docx, input_path, output_path)

        elif conv_type == "doc_to_docx":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.docx")
            success = await asyncio.to_thread(doc_to_docx, input_path, output_path)

        elif conv_type == "docx_to_pdf":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.pdf")
            success = await asyncio.to_thread(docx_to_pdf, input_path, output_path)

        elif conv_type == "excel_to_csv":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.csv")
            success = await asyncio.to_thread(excel_to_csv, input_path, output_path)

        elif conv_type == "csv_to_excel":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.xlsx")
            success = await asyncio.to_thread(csv_to_excel, input_path, output_path)

        elif conv_type == "excel_to_pdf":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.pdf")
            success = await asyncio.to_thread(excel_to_pdf, input_path, output_path)

        elif conv_type == "pdf_to_txt":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.txt")
            success = await asyncio.to_thread(pdf_to_txt, input_path, output_path)

        elif conv_type == "docx_to_txt":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.txt")
            success = await asyncio.to_thread(docx_to_txt, input_path, output_path)

        elif conv_type == "img_to_pdf":
            output_path = os.path.join(DOWNLOAD_DIR, f"{base_name}_{doc_id}.pdf")
            success = await asyncio.to_thread(image_to_pdf, input_path, output_path)

        if success and output_path and os.path.exists(output_path):
            doc_file = FSInputFile(output_path)
            await callback.message.reply_document(
                document=doc_file,
                caption=f"✅ <b>Hujjat tayyor!</b>\n🤖 @khurshid_media_bot orqali o'zgartirildi.",
                request_timeout=300
            )
            await callback.message.delete()
        else:
            await callback.message.edit_text(
                "❌ <b>Hujjatni o'zgartirishda xatolik yuz berdi!</b>\n"
                "Fayl buzilgan yoki format mos kelmadi."
            )

    except Exception as e:
        logger.error(f"Konvertatsiyada xatolik: {e}")
        await callback.message.edit_text(f"❌ Xatolik yuz berdi: <code>{str(e)}</code>")

    finally:
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception:
                pass
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        pending_documents.pop(doc_id, None)
        await callback.answer()


# ==========================================
# PASTKI TEZKOR TUGMALAR ISHLOVCHILARI
# ==========================================

@dp.message(F.text == "🎬 Video yuklash")
async def btn_video_handler(message: types.Message):
    await message.reply(
        "🎬 <b>1. Video yuklash:</b>\n\n"
        "Menga YouTube (720p HD) yoki Instagram video havolasini yuboring!\n"
        "<i>Misol: https://youtu.be/... yoki https://instagram.com/reel/...</i>"
    )


@dp.message(F.text == "📄 Hujjat konvertatsiyasi")
async def btn_docs_handler(message: types.Message):
    await message.reply(
        "📄 <b>2. Hujjatlar konvertatsiyasi:</b>\n\n"
        "Menga Word (.docx, .doc), PDF (.pdf), Excel (.xlsx), CSV yoki rasm faylini yuboring va formatni tanlang!"
    )


@dp.message(F.text == "🎙 Ovozni matnga o'girish")
async def btn_voice_handler(message: types.Message):
    await message.reply(
        "🎙 <b>3. Ovozni matnga o'girish:</b>\n\n"
        "Menga ovozli xabar (Voice) yoki audio fayl (.mp3, .ogg) yuboring, uni matnga aylantirib beraman!"
    )


@dp.message(F.text == "ℹ️ Yordam / Menyu")
async def btn_help_handler(message: types.Message):
    await message.reply(
        "Quyidagi funksiyalardan birini tanlang:",
        reply_markup=get_main_inline_keyboard()
    )


# ==========================================
# MATNLI XABARLAR: Video havolalari
# ==========================================

@dp.message(F.text)
async def handle_incoming_text(message: types.Message):
    text = message.text.strip()
    media_url, platform = extract_url_and_platform(text)

    if not media_url:
        await message.reply(
            "Iltimos, video havolasi (Instagram / YouTube), hujjat (Word, Excel, PDF) "
            "yoki ovozli xabar yuboring!\n\n"
            "📖 Batafsil ma'lumot uchun: /help"
        )
        return

    status_msg = await message.reply(
        f"⏳ <b>{platform}</b> videosi yuklab olinmoqda, iltimos kuting..."
    )

    download_id = str(uuid.uuid4())[:8]
    file_path = None
    all_parts = []

    try:
        await bot.send_chat_action(
            chat_id=message.chat.id,
            action=ChatAction.UPLOAD_VIDEO
        )

        downloaded_info = await asyncio.to_thread(
            download_media_video,
            media_url,
            platform,
            download_id
        )

        if not downloaded_info:
            await status_msg.edit_text(
                f"❌ <b>{platform} videosini yuklab bo'lmadi!</b>\n\n"
                "Sabablar:\n"
                "• Havola noto'g'ri yoki video o'chirilgan;\n"
                "• Video yopiq (private) bo'lishi mumkin."
            )
            return

        file_path = downloaded_info.get("file_path")
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Videoni yuklash jarayonida xatolik yuz berdi.")
            return

        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        duration = int(downloaded_info.get("duration") or 0)
        target_limit = 48 * 1024 * 1024

        if file_size > target_limit:
            await status_msg.edit_text(
                f"✂️ <i>Video hajmi katta ({file_size_mb:.1f} MB).\n"
                f"Telegram cheklovi tufayli sifatini yo'qotmagan holda qismlarga bo'linmoqda...</i>"
            )
            all_parts = await asyncio.to_thread(split_video_chunks, file_path, duration, file_size, target_limit)
        else:
            all_parts = [file_path]

        total_parts = len(all_parts)
        await status_msg.edit_text(f"📤 Video yuborilmoqda ({total_parts} ta qism)...")

        raw_title = downloaded_info.get("title") or f"{platform} Video"
        safe_title = html.escape(raw_title[:100])

        for idx, part in enumerate(all_parts, start=1):
            await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)
            caption_text = (
                f"🎬 <b>{platform}:</b> {safe_title}\n"
                f"📺 Sifat: <b>720p HD</b>"
            )
            if total_parts > 1:
                caption_text += f"\n📦 <b>{idx}/{total_parts}-qism</b>"
            caption_text += "\n\n🤖 @khurshid_media_bot orqali yuklandi."

            video_file = FSInputFile(part)
            await message.reply_video(
                video=video_file,
                caption=caption_text,
                supports_streaming=True,
                request_timeout=300
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.exception("Xabarni qayta ishlashda kutilmagan xatolik:")
        try:
            await status_msg.edit_text(f"❌ Xatolik yuz berdi: <code>{str(e)}</code>")
        except Exception:
            await message.reply("❌ Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.")

    finally:
        files_to_clean = set(all_parts + ([file_path] if file_path else []))
        for f in files_to_clean:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

        for leftover in glob.glob(os.path.join(DOWNLOAD_DIR, f"{download_id}_*")):
            try:
                os.remove(leftover)
            except Exception:
                pass


# Har qanday boshqa formatdagi xabarlar uchun catch-all
@dp.message()
async def catch_all_handler(message: types.Message):
    await message.reply(
        "Iltimos, quyidagilardan birini yuboring:\n"
        "1. 🎬 Video havolasi (Instagram yoki YouTube)\n"
        "2. 📄 Hujjat (Word, Excel, PDF, CSV yoki Rasm)\n"
        "3. 🎙 Ovozli xabar (Voice yoki Audio)\n\n"
        "Yordam uchun: /help"
    )


from aiohttp import web


async def _health_check(request):
    return web.Response(text="Khurshid Media Bot 24/7 ishlash rejimida!")


async def start_web_server():
    port = int(os.getenv("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", _health_check)
    app.router.add_get("/health", _health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Cloud Veb-server port {port} da ishga tushirildi.")


async def main():
    logger.info("Bot 24/7 rejimida ishga tushmoqda...")
    # Cloud hostinglar (Render / Koyeb) PORT berganda yoki RENDER muhitida veb-serverni parallel yoqamiz
    if os.getenv("PORT") or os.getenv("RENDER"):
        try:
            await start_web_server()
        except Exception as e:
            logger.warning(f"Veb-serverni ishga tushirishda xatolik: {e}")

    while True:
        try:
            # drop_pending_updates=False qilib, xabarlarni yo'qotmasdan qabul qilamiz
            await bot.delete_webhook(drop_pending_updates=False)
            bot_info = await bot.get_me()
            logger.info(f"✅ Bot muvaffaqiyatli ulandi: @{bot_info.username} (ID: {bot_info.id}). Xabarlar tinglanmoqda...")
            await dp.start_polling(bot)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot to'xtatildi!")
            break
        except Exception as e:
            logger.error(f"Ulanishda uzilish yoki xatolik: {e}. 5 soniyadan so'ng qayta ulanadi...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi!")
