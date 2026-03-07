import logging
import time
import random
import asyncio
import os
import glob
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   مكتبات التشغيل الصوتي
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    from pyrogram import Client
    from pyrogram.errors import UserAlreadyParticipant, UserNotParticipant
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality, VideoQuality, Update as TgUpdate
    from pytgcalls.types.stream import StreamAudioEnded
    VOICE_ENABLED = True
except ImportError:
    VOICE_ENABLED = False

pyro_app = None
pytgcalls_client = None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           إعدادات البوت
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOKEN        = "5715894811:AAEdH_xnLRq1zoNMvZITgQSpJWn8pPjkb4k"
API_ID       = 21173110
API_HASH     = "71db0c8aae15effc04dcfc636e68c349"
WELCOME_GIF  = "https://i.postimg.cc/wxV3PspQ/1756574872401.gif"
DEVELOPER    = "ძᥲᖇᥱძᥱ᥎Ꭵᥣ"
OWNER_ID     = 1923931101
SESSION_FILE = "/tmp/voice_session.txt"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           قواعد البيانات (الذاكرة)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
admins_db       = {}   # {chat_id: [user_ids]}
auto_responses  = {}   # {chat_id: [{"trigger": x, "response": y}]}
link_filter     = {}   # {chat_id: True/False}
nsfw_filter     = {}
welcome_enabled = {}
welcome_msg     = {}
bot_users       = set()
bot_groups      = set()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   قائمة الانتظار (Queue) - مثل السورس
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUEUE = {}
# {chat_id: [[songname, file_or_url, ref_url, type, quality], ...]}

def add_to_queue(chat_id, songname, file_url, ref_url, media_type, quality):
    if chat_id in QUEUE:
        QUEUE[chat_id].append([songname, file_url, ref_url, media_type, quality])
        return len(QUEUE[chat_id]) - 1
    else:
        QUEUE[chat_id] = [[songname, file_url, ref_url, media_type, quality]]
        return 0

def get_queue(chat_id):
    return QUEUE.get(chat_id, [])

def pop_queue(chat_id):
    if chat_id in QUEUE and QUEUE[chat_id]:
        QUEUE[chat_id].pop(0)
        if not QUEUE[chat_id]:
            QUEUE.pop(chat_id)
        return True
    return False

def clear_queue(chat_id):
    QUEUE.pop(chat_id, None)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   نظام إنشاء الجلسة التلقائي
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
session_setup_state = {}

async def start_session_setup(bot, owner_id: int, trigger_msg=None):
    try:
        await bot.send_message(
            chat_id=owner_id,
            text=(
                "🔐 *إعداد الحساب المساعد للتشغيل الصوتي*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "عشان البوت يشتغل في الدردشة الصوتية، محتاج حساب تليغرام مساعد.\n\n"
                "📱 *ابعتلي رقم التليفون* بالصيغة الدولية:\n"
                "مثال: `+201234567890`\n\n"
                "⚠️ _سيتم استخدام هذا الحساب للانضمام للدردشات الصوتية فقط_"
            ),
            parse_mode="Markdown"
        )
        session_setup_state[owner_id] = {"step": "phone"}
        if trigger_msg:
            await trigger_msg.edit_text("📨 تم إرسال رسالة في خاصك لإعداد الحساب المساعد!")
    except Exception as e:
        if trigger_msg:
            await trigger_msg.edit_text(
                f"❌ مش قادر أبعت في خاصك!\n"
                f"ابدأ محادثة مع البوت أولاً ثم أعد المحاولة.\n\nخطأ: {str(e)[:100]}"
            )

async def handle_session_setup(update, context):
    global pyro_app, pytgcalls_client
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in session_setup_state:
        return False

    state = session_setup_state[user_id]
    step = state.get("step")

    if step == "phone":
        phone = text
        if not phone.startswith("+"):
            await update.message.reply_text("❌ الرقم لازم يبدأ بـ + مثال: `+201234567890`", parse_mode="Markdown")
            return True
        try:
            client = Client("voice_session", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await client.connect()
            sent = await client.send_code(phone)
            state.update({"step": "code", "phone": phone, "client": client, "phone_code_hash": sent.phone_code_hash})
            await update.message.reply_text(
                "✅ تم إرسال كود التحقق على تليغرام!\n\n"
                "🔢 *ابعتلي الكود بمسافة بين كل رقم*\n"
                "مثال: `1 2 3 4 5`",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في الرقم: {str(e)[:150]}")
            session_setup_state.pop(user_id, None)
        return True

    elif step == "code":
        code = text.replace(" ", "").strip()
        client = state.get("client")
        phone = state.get("phone")
        try:
            await client.sign_in(phone, state["phone_code_hash"], code)
            session_string = await client.export_session_string()
            with open(SESSION_FILE, "w") as f:
                f.write(session_string)
            pytgcalls_client = PyTgCalls(client)
            await pytgcalls_client.start()
            _register_call_events()
            pyro_app = client
            session_setup_state.pop(user_id, None)
            await update.message.reply_text(
                "✅ *تم إعداد الحساب المساعد بنجاح!*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🎵 دلوقتي البوت جاهز يشغل موسيقى في الدردشات الصوتية!\n\n"
                "⚡ ارجع للمجموعة وكرر أمر التشغيل.",
                parse_mode="Markdown"
            )
        except Exception as e:
            err = str(e)
            if "PASSWORD_REQUIRED" in err or "two-step" in err.lower():
                state["step"] = "password"
                await update.message.reply_text("🔒 الحساب عنده تحقق بخطوتين\n\n🔑 *ابعتلي كلمة السر:*", parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ كود غلط أو منتهي: {err[:150]}")
                session_setup_state.pop(user_id, None)
        return True

    elif step == "password":
        client = state.get("client")
        try:
            await client.check_password(text)
            session_string = await client.export_session_string()
            with open(SESSION_FILE, "w") as f:
                f.write(session_string)
            pytgcalls_client = PyTgCalls(client)
            await pytgcalls_client.start()
            _register_call_events()
            pyro_app = client
            session_setup_state.pop(user_id, None)
            await update.message.reply_text(
                "✅ *تم إعداد الحساب المساعد بنجاح!*\n🎵 البوت جاهز يشغل موسيقى!",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ كلمة السر غلط: {str(e)[:150]}")
            session_setup_state.pop(user_id, None)
        return True

    return False

async def load_existing_session():
    global pyro_app, pytgcalls_client
    if not VOICE_ENABLED:
        return False
    try:
        if not os.path.exists(SESSION_FILE):
            return False
        with open(SESSION_FILE, "r") as f:
            session_string = f.read().strip()
        if not session_string:
            return False
        client = Client("voice_session", api_id=API_ID, api_hash=API_HASH, session_string=session_string, in_memory=True)
        await client.start()
        pytgcalls_client = PyTgCalls(client)
        await pytgcalls_client.start()
        _register_call_events()
        pyro_app = client
        print("✅ تم تحميل جلسة الحساب المساعد")
        return True
    except Exception as e:
        print(f"⚠️ فشل تحميل الجلسة: {e}")
        return False

def _register_call_events():
    """تسجيل أحداث انتهاء التشغيل والطرد - مثل السورس"""
    if not pytgcalls_client:
        return

    @pytgcalls_client.on_stream_end()
    async def stream_end_handler(_, update: TgUpdate):
        if isinstance(update, StreamAudioEnded):
            chat_id = update.chat_id
            await _play_next(chat_id)

    @pytgcalls_client.on_kicked()
    async def kicked_handler(_, chat_id: int):
        clear_queue(chat_id)

    @pytgcalls_client.on_closed_voice_chat()
    async def closed_vc_handler(_, chat_id: int):
        clear_queue(chat_id)

    @pytgcalls_client.on_left()
    async def left_handler(_, chat_id: int):
        clear_queue(chat_id)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   دوال يوتيوب
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def youtube_search(query: str) -> list:
    loop = asyncio.get_event_loop()
    def _search():
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            return info.get("entries", [])
    return await loop.run_in_executor(None, _search)

async def ytdl_get_url(link: str) -> tuple:
    """يجيب الرابط المباشر للستريم بدون تحميل - زي السورس"""
    loop = asyncio.get_event_loop()
    def _get():
        opts = {
            "quiet": True, "no_warnings": True,
            "format": "best[height<=?720][width<=?1280]",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link, download=False)
            if "entries" in info:
                info = info["entries"][0]
            url = info.get("url", "")
            title = info.get("title", link)
            duration = info.get("duration", 0)
            thumbnail = info.get("thumbnail", "")
            return url, title, int(duration or 0), thumbnail
    return await loop.run_in_executor(None, _get)

async def ytdl_search_and_get(query: str) -> tuple:
    """ابحث في يوتيوب وجيب الرابط المباشر"""
    loop = asyncio.get_event_loop()
    def _get():
        opts = {
            "quiet": True, "no_warnings": True,
            "format": "best[height<=?720][width<=?1280]",
            "default_search": "ytsearch",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)
            if "entries" in info:
                info = info["entries"][0]
            stream_url = info.get("url", "")
            title = info.get("title", query)
            duration = int(info.get("duration", 0) or 0)
            thumbnail = info.get("thumbnail", "")
            webpage_url = info.get("webpage_url", "")
            return stream_url, title, duration, thumbnail, webpage_url
    return await loop.run_in_executor(None, _get)

async def download_audio_file(query: str, output_dir="/tmp") -> tuple:
    """تحميل ملف صوتي للإرسال في الشات"""
    loop = asyncio.get_event_loop()
    def _dl():
        for opts in [
            {"format": "bestaudio/best", "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
             "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
             "quiet": True, "no_warnings": True, "default_search": "ytsearch"},
            {"format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
             "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
             "quiet": True, "no_warnings": True, "default_search": "ytsearch"}
        ]:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(f"ytsearch:{query}", download=True)
                    if "entries" in info:
                        info = info["entries"][0]
                    title = info.get("title", query)
                    duration = int(info.get("duration", 0) or 0)
                    thumbnail = info.get("thumbnail", "")
                    webpage_url = info.get("webpage_url", "")
                    files = (glob.glob(f"{output_dir}/*.mp3") + glob.glob(f"{output_dir}/*.m4a") +
                             glob.glob(f"{output_dir}/*.webm") + glob.glob(f"{output_dir}/*.ogg"))
                    if files:
                        return max(files, key=os.path.getctime), title, duration, thumbnail, webpage_url
            except Exception:
                continue
        return None, query, 0, "", ""
    return await loop.run_in_executor(None, _dl)

async def download_video_file(query: str, output_dir="/tmp") -> tuple:
    """تحميل فيديو للإرسال في الشات"""
    loop = asyncio.get_event_loop()
    def _dl():
        opts = {
            "format": "best[filesize<50M]/best[height<=?720]/best",
            "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
            "quiet": True, "no_warnings": True, "default_search": "ytsearch",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=True)
            if "entries" in info:
                info = info["entries"][0]
            title = info.get("title", query)
            duration = int(info.get("duration", 0) or 0)
            thumbnail = info.get("thumbnail", "")
            webpage_url = info.get("webpage_url", "")
            files = glob.glob(f"{output_dir}/*.mp4") + glob.glob(f"{output_dir}/*.webm") + glob.glob(f"{output_dir}/*.mkv")
            if files:
                return max(files, key=os.path.getctime), title, duration, thumbnail, webpage_url
        return None, query, 0, "", ""
    return await loop.run_in_executor(None, _dl)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   منطق التشغيل في الكول - مثل السورس
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _build_stream(stream_url: str, is_video: bool):
    if is_video:
        return MediaStream(stream_url, audio_quality=AudioQuality.HIGH, video_quality=VideoQuality.SD_480p)
    else:
        return MediaStream(stream_url, audio_quality=AudioQuality.HIGH, video_flags=MediaStream.IGNORE)

async def _ensure_userbot_in_chat(c_bot, chat_id: int):
    """تأكد إن الحساب المساعد موجود في المجموعة - زي السورس"""
    if not pyro_app:
        return False
    try:
        ubot_id = (await pyro_app.get_me()).id
        member = await c_bot.get_chat_member(chat_id, ubot_id)
        if member.status.name.lower() == "banned" or member.status.name.lower() == "kicked":
            await c_bot.unban_chat_member(chat_id, ubot_id)
            link = await c_bot.export_chat_invite_link(chat_id)
            if link.startswith("https://t.me/+"):
                link = link.replace("https://t.me/+", "https://t.me/joinchat/")
            await pyro_app.join_chat(link)
        return True
    except Exception:
        try:
            link = await c_bot.export_chat_invite_link(chat_id)
            if link.startswith("https://t.me/+"):
                link = link.replace("https://t.me/+", "https://t.me/joinchat/")
            await pyro_app.join_chat(link)
            return True
        except UserAlreadyParticipant:
            return True
        except Exception:
            return False

async def _play_next(chat_id: int):
    """شغّل المقطع التالي في القائمة - مثل السورس"""
    pop_queue(chat_id)
    queue = get_queue(chat_id)
    if not queue:
        if pytgcalls_client:
            try:
                await pytgcalls_client.leave_call(chat_id)
            except Exception:
                pass
        return
    next_item = queue[0]
    songname, stream_url, ref_url, media_type, quality = next_item
    try:
        stream = _build_stream(stream_url, media_type == "Video")
        await pytgcalls_client.change_stream(chat_id, stream)
    except Exception:
        await _play_next(chat_id)

async def play_in_call(update, context, query: str, msg, is_video: bool = False):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_mention = f"[{update.effective_user.first_name}](tg://user?id={user_id})"

    if not VOICE_ENABLED:
        await msg.edit_text("⚠️ pyrogram/pytgcalls مش مثبتين في السيرفر.")
        return

    if pytgcalls_client is None:
        if user_id == OWNER_ID or is_admin(user_id, chat_id):
            await start_session_setup(context.bot, OWNER_ID, trigger_msg=msg)
        else:
            await msg.edit_text("⚙️ البوت لسه بيتجهز، تواصل مع الأدمن.")
        return

    try:
        await msg.edit_text(f"🔎 **جاري البحث عن:** {query}\n⏳ لحظة...")

        # جيب الرابط المباشر بدون تحميل (أسرع للستريم)
        stream_url, title, duration, thumbnail, webpage_url = await ytdl_search_and_get(query)

        if not stream_url:
            await msg.edit_text(f"❌ ما لقيتش نتائج لـ: {query}")
            return

        mins, secs = duration // 60, duration % 60
        dur_str = f"{mins}:{secs:02d}"
        media_type = "Video" if is_video else "Audio"

        # تأكد إن الحساب المساعد في المجموعة
        await _ensure_userbot_in_chat(context.bot, chat_id)

        if chat_id in QUEUE:
            # في تشغيل حالي - ضيف للقائمة
            pos = add_to_queue(chat_id, title, stream_url, webpage_url, media_type, 720 if is_video else 0)
            await msg.edit_text(
                f"{'🎬' if is_video else '🎵'} **تمت الإضافة لقائمة الانتظار »** `#{pos}`\n\n"
                f"🏷 **الاسم:** [{title}]({webpage_url})\n"
                f"⏱ **المدة:** `{dur_str}`\n"
                f"🎧 **طلب بواسطة:** {user_mention}",
                parse_mode="Markdown"
            )
        else:
            # مفيش تشغيل - ابدأ مباشرة
            stream = _build_stream(stream_url, is_video)
            await pytgcalls_client.play(chat_id, stream)
            add_to_queue(chat_id, title, stream_url, webpage_url, media_type, 720 if is_video else 0)

            emoji = "🎬" if is_video else "🎵"
            await msg.edit_text(
                f"{emoji} **يشتغل الآن:** [{title}]({webpage_url})\n\n"
                f"⏱ **المدة:** `{dur_str}`\n"
                f"🎧 **طلب بواسطة:** {user_mention}\n\n"
                f"⚡ Developer by {DEVELOPER}",
                reply_markup=player_keyboard(chat_id),
                parse_mode="Markdown"
            )

    except Exception as e:
        err = str(e)
        if "not in" in err.lower() or "GroupCallNotFound" in err or "not found" in err.lower():
            await msg.edit_text("❌ **افتح دردشة صوتية في المجموعة أولاً ثم كرر الأمر**", parse_mode="Markdown")
        elif "SESSION" in err.upper() or "AUTH" in err.upper():
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            global pyro_app, pytgcalls_client
            pyro_app = None; pytgcalls_client = None
            await msg.edit_text("⚠️ انتهت صلاحية الجلسة، جاري إعادة الإعداد...")
            await start_session_setup(context.bot, OWNER_ID)
        else:
            await msg.edit_text(f"🚫 **خطأ في التشغيل:**\n\n`{err[:200]}`", parse_mode="Markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           دوال مساعدة
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def is_admin(user_id, chat_id):
    return user_id == OWNER_ID or user_id in admins_db.get(chat_id, [])

def fmt_duration(secs: int) -> str:
    m, s = secs // 60, secs % 60
    return f"{m}:{s:02d}"

async def safe_edit(q, text=None, caption=None, reply_markup=None, parse_mode=None):
    msg_text = caption or text
    try:
        await q.edit_message_caption(caption=msg_text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            await q.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            await q.message.reply_text(text=msg_text, reply_markup=reply_markup, parse_mode=parse_mode)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           لوحات المفاتيح
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("›: الاوامر :‹", callback_data="commands")],
        [InlineKeyboardButton("›: المطور :‹", callback_data="developer"),
         InlineKeyboardButton("›: لشراء بوت :‹", callback_data="buy")],
        [InlineKeyboardButton("›: لغات البوت :‹", callback_data="languages")],
    ])

def commands_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ أوامر التشغيل", callback_data="cmd_play")],
        [InlineKeyboardButton("🛡️ أوامر الحماية", callback_data="cmd_protection")],
        [InlineKeyboardButton("👑 أوامر الأدمن", callback_data="cmd_admin")],
        [InlineKeyboardButton("🚫 أوامر المنع", callback_data="cmd_filters")],
        [InlineKeyboardButton("💬 أوامر الردود", callback_data="cmd_responses"),
         InlineKeyboardButton("🏅 أوامر الرتب", callback_data="cmd_ranks")],
        [InlineKeyboardButton("🎮 الأوامر الإضافية", callback_data="cmd_extra")],
        [InlineKeyboardButton("العودة", callback_data="back_main")],
    ])

def player_keyboard(chat_id):
    state = QUEUE.get(chat_id, [])
    queue_count = len(state) - 1 if len(state) > 1 else 0
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏸ إيقاف مؤقت", callback_data=f"pause_{chat_id}"),
         InlineKeyboardButton("⏭ تخطي", callback_data=f"skip_{chat_id}")],
        [InlineKeyboardButton("🔇 كتم", callback_data=f"mute_{chat_id}"),
         InlineKeyboardButton("🔊 رفع الكتم", callback_data=f"unmute_{chat_id}")],
        [InlineKeyboardButton(f"📋 القائمة ({queue_count})", callback_data=f"queue_{chat_id}"),
         InlineKeyboardButton("⏹ إيقاف", callback_data=f"stop_{chat_id}")],
    ])

def back_btn(target="commands"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("العودة", callback_data=target)]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           /start
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_users.add(user.id)
    text = (
        f"⚡ اهلا بك عزيزي {user.first_name}\n"
        f"≡ : انا بوت اسمي نقيب\n"
        f"≡ : يمكنني تشغيل الموسيقى في الاتصال\n"
        f"≡ : أدعم تشغيل منصات ‹ يوتيوب › ولخ .\n\n"
        f"⚡ Developer by {DEVELOPER}"
    )
    if update.effective_chat.type == "private":
        await update.message.reply_animation(animation=WELCOME_GIF, caption=text, reply_markup=main_menu_keyboard())
    else:
        bot_groups.add(update.effective_chat.id)
        await update.message.reply_animation(animation=WELCOME_GIF, caption=text, reply_markup=main_menu_keyboard())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           Callbacks - القوائم
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def show_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await safe_edit(q, caption="⚡ اختر قسم الأوامر:", reply_markup=commands_menu_keyboard())

async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    user = q.from_user
    text = (f"⚡ اهلا بك عزيزي {user.first_name}\n≡ : انا بوت اسمي نقيب\n"
            f"≡ : يمكنني تشغيل الموسيقى في الاتصال\n≡ : أدعم تشغيل منصات ‹ يوتيوب › ولخ .\n\n"
            f"⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=main_menu_keyboard())

async def show_developer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await safe_edit(q, caption=f"⚡ المطور: {DEVELOPER}\n━━━━━━━━━━━━━━━━━━\nللتواصل مع المطور اضغط الزر بالأسفل",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("تواصل مع المطور", url="https://t.me/yourusername")],
                                           [InlineKeyboardButton("العودة", callback_data="back_main")]]))

async def show_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await safe_edit(q, caption="⚡ لشراء بوت خاص بك:\n━━━━━━━━━━━━━━━━━━\nتواصل مع المطور للحصول على بوت مخصص",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("تواصل للشراء", url="https://t.me/yourusername")],
                                           [InlineKeyboardButton("العودة", callback_data="back_main")]]))

async def show_languages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await safe_edit(q, caption="⚡ اختر لغة البوت:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),
                                            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
                                           [InlineKeyboardButton("العودة", callback_data="back_main")]]))

async def cmd_play_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (f"اوامر التشغيل ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« شغل [اسم] - تشغيل موسيقى في الكول\n« فيديو [اسم] - تشغيل فيديو في الكول\n"
            "« تشغيل عشوائي - تشغيل أغنية عشوائية\n« بحث [كلمة] - البحث في يوتيوب\n\n"
            "اوامر التنزيل ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« تحميل [اسم] - تحميل فيديو\n« تنزيل [اسم] - تحميل ملف صوتي\n\n"
            "أوامر التحكم ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« ايقاف مؤقت / استكمال / تخطي / ايقاف\n"
            "« كتم / رفع الكتم\n"
            f"« قائمة - عرض قائمة الانتظار\n\n⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_protection_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (f"اوامر الحماية ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« تفعيل الرابط / تعطيل الرابط - فلتر الروابط\n"
            "« تفعيل الترحيب / تعطيل الترحيب - رسالة الترحيب\n"
            "« تفعيل nsfw / تعطيل nsfw - فلتر المحتوى\n\n"
            f"⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (f"اوامر الأدمن ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« كتم @مستخدم - كتم عضو\n« فك الكتم @مستخدم - فك الكتم\n"
            "« حظر @مستخدم - حظر عضو\n« فك الحظر @مستخدم - فك الحظر\n"
            "« طرد البوتات - حذف جميع البوتات\n"
            "« ترقية @مستخدم - ترقية أدمن\n« تنزيل @مستخدم - إزالة صلاحيات\n"
            f"« تحديث الادمن - تحديث قائمة المشرفين\n\n⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_filters_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (f"اوامر الردود التلقائية ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« رد [كلمة] [رد] - إضافة رد تلقائي\n"
            "« حذف الرد [كلمة] - حذف رد\n"
            "« الردود - عرض الردود\n\n"
            f"⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_responses_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (f"اوامر الردود ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« رد [كلمة] [رد] - إضافة رد تلقائي\n"
            "« حذف الرد [كلمة] - حذف رد تلقائي\n"
            "« الردود - قائمة الردود\n\n"
            f"⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_ranks_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (f"اوامر الرتب ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« ترقية @مستخدم - ترقية أدمن\n"
            "« تنزيل @مستخدم - إزالة صلاحيات أدمن\n"
            "« الادمنية - قائمة المشرفين\n\n"
            f"⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_extra_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (f"الأوامر الإضافية ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« فزورة - فزورة عشوائية\n« نكتة - نكتة عشوائية\n"
            "« لو خيروك - سؤال مرح\n« معلومة - معلومة عشوائية\n\n"
            f"⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   Callbacks - التحكم في المشغل
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def player_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = q.data
    chat_id = int(data.split("_", 1)[1])

    if not is_admin(q.from_user.id, chat_id):
        await q.answer("❌ للادمنية فقط", show_alert=True); return

    queue = get_queue(chat_id)
    current = queue[0] if queue else None
    title = current[0] if current else "—"

    if data.startswith("pause_"):
        if pytgcalls_client:
            try:
                await pytgcalls_client.pause_stream(chat_id)
                await q.edit_message_text(
                    f"⏸ **تم الإيقاف المؤقت**\n🎵 {title}\n\n• لاستكمال: اكتب **استكمال**",
                    reply_markup=player_keyboard(chat_id), parse_mode="Markdown")
            except Exception as e:
                await q.answer(f"خطأ: {str(e)[:50]}", show_alert=True)

    elif data.startswith("skip_"):
        if pytgcalls_client and queue:
            try:
                await _play_next(chat_id)
                new_queue = get_queue(chat_id)
                if new_queue:
                    await q.edit_message_text(
                        f"⏭ **تم التخطي**\n🎵 يشتغل الآن: {new_queue[0][0]}\n\n⚡ Developer by {DEVELOPER}",
                        reply_markup=player_keyboard(chat_id), parse_mode="Markdown")
                else:
                    await q.edit_message_text(f"⏹ **انتهت قائمة الانتظار**\n\n⚡ Developer by {DEVELOPER}", parse_mode="Markdown")
            except Exception as e:
                await q.answer(f"خطأ: {str(e)[:50]}", show_alert=True)

    elif data.startswith("mute_"):
        if pytgcalls_client:
            try:
                await pytgcalls_client.mute_stream(chat_id)
                await q.edit_message_text(
                    f"🔇 **تم الكتم**\n🎵 {title}\n\n• لرفع الكتم: اكتب **رفع الكتم**",
                    reply_markup=player_keyboard(chat_id), parse_mode="Markdown")
            except Exception as e:
                await q.answer(f"خطأ: {str(e)[:50]}", show_alert=True)

    elif data.startswith("unmute_"):
        if pytgcalls_client:
            try:
                await pytgcalls_client.unmute_stream(chat_id)
                await q.edit_message_text(
                    f"🔊 **تم رفع الكتم**\n🎵 {title}",
                    reply_markup=player_keyboard(chat_id), parse_mode="Markdown")
            except Exception as e:
                await q.answer(f"خطأ: {str(e)[:50]}", show_alert=True)

    elif data.startswith("stop_"):
        if pytgcalls_client:
            try:
                await pytgcalls_client.leave_call(chat_id)
            except Exception:
                pass
        clear_queue(chat_id)
        await q.edit_message_text(f"⏹ **تم إيقاف التشغيل**\n\n⚡ Developer by {DEVELOPER}", parse_mode="Markdown")

    elif data.startswith("queue_"):
        queue = get_queue(chat_id)
        if not queue:
            await q.answer("❌ القائمة فارغة", show_alert=True); return
        text = "📋 **قائمة الانتظار:**\n━━━━━━━━━━━━━━━━━━\n"
        for i, item in enumerate(queue):
            prefix = "▶️" if i == 0 else f"{i}."
            text += f"{prefix} {item[0][:40]}\n"
        await q.edit_message_text(text, reply_markup=player_keyboard(chat_id), parse_mode="Markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   أوامر الحماية - /commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    try:
        admins = await chat.get_administrators()
        text = "👑 **قائمة المشرفين:**\n━━━━━━━━━━━━━━━━━━\n"
        for a in admins:
            if not a.user.is_bot:
                text += f"• {a.user.mention_html()}\n"
        # تحديث admins_db
        admins_db[chat.id] = [a.user.id for a in admins if not a.user.is_bot]
        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def reload_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        return await update.message.reply_text("❌ للأدمن فقط")
    chat = update.effective_chat
    admins = await chat.get_administrators()
    admins_db[chat.id] = [a.user.id for a in admins if not a.user.is_bot]
    await update.message.reply_text("✅ **تم تحديث قائمة المشرفين!**", parse_mode="Markdown")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ هذا الأمر للأدمن فقط")
    if not update.message.reply_to_message:
        return await update.message.reply_text("↩️ رد على رسالة المستخدم المراد كتمه")
    target = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.restrict_member(
            target.id,
            ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text(f"🔇 **تم كتم** {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ هذا الأمر للأدمن فقط")
    if not update.message.reply_to_message:
        return await update.message.reply_text("↩️ رد على رسالة المستخدم")
    target = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.restrict_member(
            target.id,
            ChatPermissions(
                can_send_messages=True, can_send_other_messages=True,
                can_send_polls=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_add_web_page_previews=True
            )
        )
        await update.message.reply_text(f"🔊 **تم رفع الكتم عن** {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ هذا الأمر للأدمن فقط")
    if not update.message.reply_to_message:
        return await update.message.reply_text("↩️ رد على رسالة المستخدم المراد حظره")
    target = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.ban_member(target.id)
        await update.message.reply_text(f"🚫 **تم حظر** {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ هذا الأمر للأدمن فقط")
    if not update.message.reply_to_message:
        return await update.message.reply_text("↩️ رد على رسالة المستخدم")
    target = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.unban_member(target.id)
        await update.message.reply_text(f"✅ **تم فك حظر** {target.mention_html()}", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def kick_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ هذا الأمر للأدمن فقط")
    msg = await update.message.reply_text("🔍 جاري البحث عن البوتات...")
    try:
        kicked = 0
        async for member in context.bot.get_chat_administrators(chat_id):
            pass
        members = await context.bot.get_chat_administrators(chat_id)
        # نطرد البوتات من الأعضاء العاديين
        await msg.edit_text("⚠️ هذه الوظيفة تحتاج Pyrogram للوصول لقائمة الأعضاء الكاملة")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ هذا الأمر للأدمن فقط")
    if not update.message.reply_to_message:
        return await update.message.reply_text("↩️ رد على رسالة المستخدم المراد ترقيته")
    target = update.message.reply_to_message.from_user
    try:
        await context.bot.promote_chat_member(
            chat_id, target.id,
            can_delete_messages=True, can_restrict_members=True,
            can_pin_messages=True, can_manage_chat=True,
            can_manage_video_chats=True
        )
        admins_db.setdefault(chat_id, [])
        if target.id not in admins_db[chat_id]:
            admins_db[chat_id].append(target.id)
        await update.message.reply_text(f"⭐ **تمت ترقية** {target.mention_html()} **لأدمن**", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ هذا الأمر للأدمن فقط")
    if not update.message.reply_to_message:
        return await update.message.reply_text("↩️ رد على رسالة المستخدم")
    target = update.message.reply_to_message.from_user
    try:
        await context.bot.promote_chat_member(
            chat_id, target.id,
            can_delete_messages=False, can_restrict_members=False,
            can_pin_messages=False, can_manage_chat=False,
            can_manage_video_chats=False
        )
        if chat_id in admins_db and target.id in admins_db[chat_id]:
            admins_db[chat_id].remove(target.id)
        await update.message.reply_text(f"🔽 **تم تنزيل** {target.mention_html()} **من الأدمن**", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   أوامر التشغيل - /commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ للأدمن فقط")
    if chat_id not in QUEUE:
        return await update.message.reply_text("❌ قائمة التشغيل فارغة")
    try:
        await pytgcalls_client.pause_stream(chat_id)
        await update.message.reply_text("⏸ **تم الإيقاف المؤقت**\n\n• لاستكمال: /resume", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"🚫 خطأ:\n\n`{e}`", parse_mode="Markdown")

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ للأدمن فقط")
    if chat_id not in QUEUE:
        return await update.message.reply_text("❌ قائمة التشغيل فارغة")
    try:
        await pytgcalls_client.resume_stream(chat_id)
        await update.message.reply_text("▶️ **تم استكمال التشغيل**", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"🚫 خطأ:\n\n`{e}`", parse_mode="Markdown")

async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ للأدمن فقط")
    if chat_id not in QUEUE:
        return await update.message.reply_text("❌ قائمة التشغيل فارغة")
    await _play_next(chat_id)
    queue = get_queue(chat_id)
    if queue:
        await update.message.reply_text(
            f"⏭ **تم التخطي**\n🎵 يشتغل الآن: {queue[0][0]}",
            reply_markup=player_keyboard(chat_id), parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ **انتهت قائمة الانتظار**", parse_mode="Markdown")

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ للأدمن فقط")
    if chat_id not in QUEUE:
        return await update.message.reply_text("❌ قائمة التشغيل فارغة")
    try:
        if pytgcalls_client:
            await pytgcalls_client.leave_call(chat_id)
        clear_queue(chat_id)
        await update.message.reply_text("⏹ **تم إيقاف التشغيل**", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"🚫 خطأ:\n\n`{e}`", parse_mode="Markdown")

async def cmd_mute_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ للأدمن فقط")
    if chat_id not in QUEUE:
        return await update.message.reply_text("❌ قائمة التشغيل فارغة")
    try:
        await pytgcalls_client.mute_stream(chat_id)
        await update.message.reply_text("🔇 **تم الكتم**\n\n• لرفع الكتم: /unmutecall", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"🚫 خطأ:\n\n`{e}`", parse_mode="Markdown")

async def cmd_unmute_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        return await update.message.reply_text("❌ للأدمن فقط")
    if chat_id not in QUEUE:
        return await update.message.reply_text("❌ قائمة التشغيل فارغة")
    try:
        await pytgcalls_client.unmute_stream(chat_id)
        await update.message.reply_text("🔊 **تم رفع الكتم**", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"🚫 خطأ:\n\n`{e}`", parse_mode="Markdown")

async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    queue = get_queue(chat_id)
    if not queue:
        return await update.message.reply_text("❌ قائمة الانتظار فارغة")
    text = "📋 **قائمة الانتظار:**\n━━━━━━━━━━━━━━━━━━\n"
    for i, item in enumerate(queue):
        prefix = "▶️ يشتغل الآن:" if i == 0 else f"{i}."
        text += f"{prefix} [{item[0][:35]}]({item[2]})\n"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           معالج النصوص الرئيسي
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # ━ الأولوية: إعداد الجلسة في الخاص
    if update.effective_chat.type == "private":
        handled = await handle_session_setup(update, context)
        if handled:
            return

    # ━ تتبع الأعضاء والمجموعات
    bot_users.add(user_id)
    if update.effective_chat.type != "private":
        bot_groups.add(chat_id)

    # ━━ فلتر الروابط
    if link_filter.get(chat_id):
        if is_admin(user_id, chat_id):
            pass
        else:
            import re
            url_pattern = r"(https?://|www\.|t\.me/)[^\s]+"
            if re.search(url_pattern, text, re.IGNORECASE):
                try:
                    await update.message.delete()
                    warn = await update.message.reply_text(
                        f"🚫 {update.effective_user.mention_html()} الروابط ممنوعة في هذه المجموعة!",
                        parse_mode="HTML"
                    )
                    await asyncio.sleep(5)
                    await warn.delete()
                except Exception:
                    pass
                return

    # ━━ أوامر التشغيل في الكول
    if text.startswith("شغل ") or text.startswith("تشغيل "):
        query = text.split(" ", 1)[1].strip()
        msg = await update.message.reply_text(f"🔎 جاري البحث عن: {query}...")
        await play_in_call(update, context, query, msg, is_video=False)

    elif text.startswith("فيديو ") or text.startswith("فيد "):
        query = text.split(" ", 1)[1].strip()
        msg = await update.message.reply_text(f"🔎 جاري البحث عن: {query}...")
        await play_in_call(update, context, query, msg, is_video=True)

    elif text == "تشغيل عشوائي":
        songs = ["Blinding Lights", "Shape of You", "Bohemian Rhapsody", "Stay", "Levitating", "As It Was"]
        song = random.choice(songs)
        msg = await update.message.reply_text(f"🎲 تشغيل عشوائي: {song}...")
        await play_in_call(update, context, song, msg, is_video=False)

    elif text == "ايقاف مؤقت" or text == "توقف":
        if not is_admin(user_id, chat_id): return
        if chat_id not in QUEUE:
            return await update.message.reply_text("❌ مفيش تشغيل حالياً")
        try:
            await pytgcalls_client.pause_stream(chat_id)
            await update.message.reply_text("⏸ **تم الإيقاف المؤقت**", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"🚫 خطأ: `{e}`", parse_mode="Markdown")

    elif text == "استكمال" or text == "كمّل":
        if not is_admin(user_id, chat_id): return
        if chat_id not in QUEUE:
            return await update.message.reply_text("❌ مفيش تشغيل حالياً")
        try:
            await pytgcalls_client.resume_stream(chat_id)
            await update.message.reply_text("▶️ **تم استكمال التشغيل**", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"🚫 خطأ: `{e}`", parse_mode="Markdown")

    elif text == "تخطي" or text == "التالي":
        if not is_admin(user_id, chat_id): return
        if chat_id not in QUEUE:
            return await update.message.reply_text("❌ مفيش تشغيل حالياً")
        await _play_next(chat_id)
        queue = get_queue(chat_id)
        if queue:
            await update.message.reply_text(f"⏭ **تخطي ✓**\n🎵 يشتغل: {queue[0][0]}", reply_markup=player_keyboard(chat_id), parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ انتهت القائمة")

    elif text == "ايقاف" or text == "اسكت":
        if not is_admin(user_id, chat_id): return
        if chat_id not in QUEUE:
            return await update.message.reply_text("❌ مفيش تشغيل حالياً")
        try:
            if pytgcalls_client:
                await pytgcalls_client.leave_call(chat_id)
            clear_queue(chat_id)
            await update.message.reply_text("⏹ **تم إيقاف التشغيل**", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"🚫 خطأ: `{e}`", parse_mode="Markdown")

    elif text == "كتم":
        if not is_admin(user_id, chat_id): return
        if chat_id not in QUEUE:
            return await update.message.reply_text("❌ مفيش تشغيل حالياً")
        try:
            await pytgcalls_client.mute_stream(chat_id)
            await update.message.reply_text("🔇 **تم الكتم**", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"🚫 خطأ: `{e}`", parse_mode="Markdown")

    elif text == "رفع الكتم" or text == "رفع كتم":
        if not is_admin(user_id, chat_id): return
        if chat_id not in QUEUE:
            return await update.message.reply_text("❌ مفيش تشغيل حالياً")
        try:
            await pytgcalls_client.unmute_stream(chat_id)
            await update.message.reply_text("🔊 **تم رفع الكتم**", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"🚫 خطأ: `{e}`", parse_mode="Markdown")

    elif text == "قائمة" or text == "قائمه":
        queue = get_queue(chat_id)
        if not queue:
            return await update.message.reply_text("❌ قائمة الانتظار فارغة")
        t = "📋 **قائمة الانتظار:**\n━━━━━━━━━━━━━━━━━━\n"
        for i, item in enumerate(queue):
            prefix = "▶️" if i == 0 else f"{i}."
            t += f"{prefix} {item[0][:40]}\n"
        await update.message.reply_text(t, parse_mode="Markdown")

    # ━━ أوامر البحث والتنزيل
    elif text.startswith("بحث "):
        query = text[4:].strip()
        msg = await update.message.reply_text(f"🔍 جاري البحث عن: {query}...")
        try:
            results = await youtube_search(query)
            if not results:
                return await msg.edit_text("❌ ما لقيتش نتائج")
            text_out = f"🔍 **نتائج البحث عن:** {query}\n━━━━━━━━━━━━━━━━━━\n"
            buttons = []
            for i, r in enumerate(results[:5], 1):
                title = r.get("title", "بدون عنوان")[:50]
                url = f"https://youtu.be/{r.get('id', '')}"
                duration = int(r.get("duration", 0) or 0)
                text_out += f"{i}️⃣ {title} [{fmt_duration(duration)}]\n"
                buttons.append([InlineKeyboardButton(f"▶️ {title[:30]}", url=url)])
            buttons.append([InlineKeyboardButton("❌ إغلاق", callback_data="close_search")])
            await msg.edit_text(text_out, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ في البحث: {str(e)[:100]}")

    elif text.startswith("تنزيل "):
        query = text[6:].strip()
        msg = await update.message.reply_text(f"🎵 **جاري تنزيل:** {query}\n⏳ يتم التحميل من يوتيوب...", parse_mode="Markdown")
        try:
            filepath, title, duration, thumbnail, webpage_url = await download_audio_file(query)
            if filepath and os.path.exists(filepath):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                await msg.edit_text(f"📤 **جاري رفع الملف:** {title} ({size_mb:.1f}MB)", parse_mode="Markdown")
                with open(filepath, "rb") as af:
                    await update.message.reply_audio(
                        audio=af, title=title, duration=duration,
                        caption=f"🎵 **{title}**\n⏱ {fmt_duration(duration)}\n\n⚡ Developer by {DEVELOPER}",
                        parse_mode="Markdown"
                    )
                await msg.delete()
                os.remove(filepath)
            else:
                await msg.edit_text("❌ فشل التنزيل، جرب مرة تانية")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {str(e)[:150]}")

    elif text.startswith("تحميل "):
        query = text[6:].strip()
        msg = await update.message.reply_text(f"🎬 **جاري تحميل:** {query}\n⏳ يتم التحميل...", parse_mode="Markdown")
        try:
            filepath, title, duration, thumbnail, webpage_url = await download_video_file(query)
            if filepath and os.path.exists(filepath):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                if size_mb > 50:
                    await msg.edit_text(f"❌ الفيديو كبير جداً ({size_mb:.1f}MB)\n• جرب **تنزيل** للصوت فقط")
                    os.remove(filepath)
                    return
                await msg.edit_text(f"📤 **جاري رفع الفيديو:** {title} ({size_mb:.1f}MB)", parse_mode="Markdown")
                with open(filepath, "rb") as vf:
                    await update.message.reply_video(
                        video=vf, duration=duration,
                        caption=f"🎬 **{title}**\n⏱ {fmt_duration(duration)}\n\n⚡ Developer by {DEVELOPER}",
                        parse_mode="Markdown"
                    )
                await msg.delete()
                os.remove(filepath)
            else:
                await msg.edit_text("❌ فشل التحميل، جرب مرة تانية")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {str(e)[:150]}")

    # ━━ أوامر الحماية بالنص
    elif text == "تفعيل الرابط":
        if not is_admin(user_id, chat_id): return
        link_filter[chat_id] = True
        await update.message.reply_text("✅ **تم تفعيل فلتر الروابط**", parse_mode="Markdown")

    elif text == "تعطيل الرابط":
        if not is_admin(user_id, chat_id): return
        link_filter[chat_id] = False
        await update.message.reply_text("❌ **تم تعطيل فلتر الروابط**", parse_mode="Markdown")

    elif text == "تفعيل الترحيب":
        if not is_admin(user_id, chat_id): return
        welcome_enabled[chat_id] = True
        await update.message.reply_text("✅ **تم تفعيل رسالة الترحيب**", parse_mode="Markdown")

    elif text == "تعطيل الترحيب":
        if not is_admin(user_id, chat_id): return
        welcome_enabled[chat_id] = False
        await update.message.reply_text("❌ **تم تعطيل رسالة الترحيب**", parse_mode="Markdown")

    elif text.startswith("رد ") and " " in text[4:]:
        if not is_admin(user_id, chat_id): return
        parts = text[4:].split(" ", 1)
        if len(parts) == 2:
            trigger, response = parts[0], parts[1]
            auto_responses.setdefault(chat_id, [])
            auto_responses[chat_id] = [r for r in auto_responses[chat_id] if r["trigger"] != trigger]
            auto_responses[chat_id].append({"trigger": trigger, "response": response})
            await update.message.reply_text(f"✅ **تم إضافة الرد التلقائي:**\n• عند: `{trigger}`\n• الرد: {response}", parse_mode="Markdown")

    elif text.startswith("حذف الرد "):
        if not is_admin(user_id, chat_id): return
        trigger = text[9:].strip()
        if chat_id in auto_responses:
            auto_responses[chat_id] = [r for r in auto_responses[chat_id] if r["trigger"] != trigger]
        await update.message.reply_text(f"🗑 **تم حذف الرد:** `{trigger}`", parse_mode="Markdown")

    elif text == "الردود":
        responses = auto_responses.get(chat_id, [])
        if not responses:
            return await update.message.reply_text("❌ لا توجد ردود تلقائية")
        t = "📋 **الردود التلقائية:**\n━━━━━━━━━━━━━━━━━━\n"
        for r in responses:
            t += f"• `{r['trigger']}` ← {r['response']}\n"
        await update.message.reply_text(t, parse_mode="Markdown")

    elif text == "تحديث الادمن" or text == "تحديث الإدارة":
        if not is_admin(user_id, chat_id): return
        admins = await update.effective_chat.get_administrators()
        admins_db[chat_id] = [a.user.id for a in admins if not a.user.is_bot]
        await update.message.reply_text("✅ **تم تحديث قائمة المشرفين!**", parse_mode="Markdown")

    # ━━ أوامر الترفيه
    elif text == "فزورة":
        fzawar = [
            ("ما هو الشيء الذي يمشي وليس له أرجل؟", "الوقت"),
            ("ما هو الشيء الذي كلما أخذت منه كبر؟", "الحفرة"),
            ("ما الذي يملك أسنانًا ولا يعض؟", "المشط"),
        ]
        q_text, ans = random.choice(fzawar)
        context.chat_data["fosora_answer"] = ans
        await update.message.reply_text(f"🤔 **فزورة:**\n\n{q_text}\n\n_أرسل إجابتك!_", parse_mode="Markdown")

    elif text == "نكتة":
        jokes = [
            "قال ولد لأبوه: أبوي علمني الكذب!\nقال أبوه: أنا؟! وأنا في مكة!",
            "واحد راح الدكتور قاله: كل ما تمشي تحس بدوخة؟\nقال: ايه، أنا باقعد طول اليوم!",
        ]
        await update.message.reply_text(f"😂 {random.choice(jokes)}")

    elif text == "معلومة":
        facts = [
            "🌟 الشمس تبعد عن الأرض 150 مليون كيلومتر.",
            "🐬 الدلافين تنام بنصف عقلها فقط.",
            "🍯 العسل لا يفسد أبداً - وجدوا عسل عمره 3000 سنة في الأهرامات.",
        ]
        await update.message.reply_text(f"💡 **معلومة:**\n\n{random.choice(facts)}", parse_mode="Markdown")

    else:
        # ردود تلقائية
        if chat_id in auto_responses:
            for item in auto_responses[chat_id]:
                if item["trigger"].lower() in text.lower():
                    await update.message.reply_text(item["response"])
                    break
        # إجابة الفزورة
        if "fosora_answer" in context.chat_data:
            if text.strip().lower() == context.chat_data["fosora_answer"].lower():
                await update.message.reply_text(f"✅ **إجابة صح! 🎉**\nالإجابة: `{context.chat_data['fosora_answer']}`", parse_mode="Markdown")
                del context.chat_data["fosora_answer"]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   أعضاء جدد
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not welcome_enabled.get(chat_id):
        return
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        msg = welcome_msg.get(chat_id, "👋 مرحباً {user} في {chat}! 🎉\n\nنورت المجموعة!")
        msg = msg.replace("{user}", member.mention_html()).replace("{chat}", update.effective_chat.title or "")
        await update.message.reply_animation(animation=WELCOME_GIF, caption=msg, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   تشغيل البوت
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main():
    app = Application.builder().token(TOKEN).build()

    # أوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("kick", kick_bots))
    app.add_handler(CommandHandler("promote", promote_user))
    app.add_handler(CommandHandler("demote", demote_user))
    app.add_handler(CommandHandler("admins", get_admins_cmd))
    app.add_handler(CommandHandler("reload", reload_admins))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("mutecall", cmd_mute_stream))
    app.add_handler(CommandHandler("unmutecall", cmd_unmute_stream))
    app.add_handler(CommandHandler("queue", cmd_queue))

    # Callbacks
    app.add_handler(CallbackQueryHandler(show_commands, pattern="^commands$"))
    app.add_handler(CallbackQueryHandler(show_developer, pattern="^developer$"))
    app.add_handler(CallbackQueryHandler(show_buy, pattern="^buy$"))
    app.add_handler(CallbackQueryHandler(show_languages, pattern="^languages$"))
    app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(cmd_play_cb, pattern="^cmd_play$"))
    app.add_handler(CallbackQueryHandler(cmd_admin_cb, pattern="^cmd_admin$"))
    app.add_handler(CallbackQueryHandler(cmd_protection_cb, pattern="^cmd_protection$"))
    app.add_handler(CallbackQueryHandler(cmd_filters_cb, pattern="^cmd_filters$"))
    app.add_handler(CallbackQueryHandler(cmd_responses_cb, pattern="^cmd_responses$"))
    app.add_handler(CallbackQueryHandler(cmd_ranks_cb, pattern="^cmd_ranks$"))
    app.add_handler(CallbackQueryHandler(cmd_extra_cb, pattern="^cmd_extra$"))
    app.add_handler(CallbackQueryHandler(player_callback,
        pattern="^(pause|skip|stop|mute|unmute|queue)_"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^close_search$"))

    # رسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

    print("⚡ البوت شغال...")

    # تحميل جلسة الحساب المساعد
    if VOICE_ENABLED:
        voice_ok = await load_existing_session()
        if voice_ok:
            print("✅ الحساب المساعد شغال - التشغيل الصوتي جاهز")
        else:
            print("⚠️ مفيش جلسة - البوت هيطلب إعدادها أول ما حد يشغل موسيقى")
    else:
        print("⚠️ pyrogram/pytgcalls مش مثبتين - أوامر الكول معطلة")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
