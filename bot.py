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
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality, VideoQuality
    VOICE_ENABLED = True
except ImportError:
    VOICE_ENABLED = False

pyro_app = None
pytgcalls_client = None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   دوال يوتيوب الحقيقية
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def youtube_search(query: str) -> list:
    loop = asyncio.get_event_loop()
    def _search():
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            return info.get("entries", [])
    return await loop.run_in_executor(None, _search)

async def download_audio(query: str, output_dir="/tmp") -> tuple:
    loop = asyncio.get_event_loop()
    def _download():
        # أولاً نحاول مع ffmpeg لتحويل لـ mp3
        ydl_opts_ffmpeg = {
            "format": "bestaudio/best",
            "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch",
        }
        # إذا ffmpeg مش موجود نحمّل الصوت مباشرة بدون تحويل
        ydl_opts_noffmpeg = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch",
        }
        for ydl_opts in [ydl_opts_ffmpeg, ydl_opts_noffmpeg]:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch:{query}", download=True)
                    if "entries" in info:
                        info = info["entries"][0]
                    title = info.get("title", query)
                    files = (glob.glob(f"{output_dir}/*.mp3") +
                             glob.glob(f"{output_dir}/*.m4a") +
                             glob.glob(f"{output_dir}/*.webm") +
                             glob.glob(f"{output_dir}/*.ogg"))
                    if files:
                        return max(files, key=os.path.getctime), title
            except Exception:
                continue
        return None, query
    return await loop.run_in_executor(None, _download)

async def download_video(query: str, output_dir="/tmp") -> tuple:
    loop = asyncio.get_event_loop()
    def _download():
        ydl_opts = {
            "format": "best[filesize<50M]/best",
            "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=True)
            if "entries" in info:
                info = info["entries"][0]
            title = info.get("title", query)
            files = glob.glob(f"{output_dir}/*.mp4") + glob.glob(f"{output_dir}/*.webm")
            if files:
                return max(files, key=os.path.getctime), title
            return None, title
    return await loop.run_in_executor(None, _download)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           إعدادات البوت
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOKEN = "5715894811:AAEdH_xnLRq1zoNMvZITgQSpJWn8pPjkb4k"
API_ID = 21173110
API_HASH = "71db0c8aae15effc04dcfc636e68c349"
PHONE = "+201008967492"
WELCOME_GIF = "https://i.postimg.cc/wxV3PspQ/1756574872401.gif"
DEVELOPER = "ძᥲᖇᥱძᥱ᥎Ꭵᥣ"
OWNER_ID = 1923931101  # ضع ID الأدمن هنا بعد أول تشغيل

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def safe_edit(q, text=None, caption=None, reply_markup=None, parse_mode=None):
    """يحاول يعدل الكابشن، وإذا فشل يعدل النص العادي"""
    msg_text = caption or text
    try:
        await safe_edit(q, caption=msg_text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            await q.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            await q.message.reply_text(text=msg_text, reply_markup=reply_markup, parse_mode=parse_mode)



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           قواعد البيانات
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
admins_db = {}
auto_responses = {}
link_filter = {}
nsfw_filter = {}
welcome_enabled = {}
welcome_msg = {}
bot_users = set()
bot_groups = set()
active_calls = {}   # {chat_id: {"playing": True, "paused": False, "loop": False, "title": ""}}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   تهيئة عميل Pyrogram + PyTgCalls
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def init_voice_client():
    global pyro_app, pytgcalls_client
    if not VOICE_ENABLED:
        return False
    try:
        pyro_app = Client(
            "voice_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            phone_number=PHONE,
            in_memory=True
        )
        await pyro_app.start()
        pytgcalls_client = PyTgCalls(pyro_app)
        await pytgcalls_client.start()
        return True
    except Exception as e:
        logging.error(f"فشل تهيئة الكول: {e}")
        return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   دالة التشغيل الحقيقي في الكول
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def play_in_call(update, context, query: str, msg, is_video: bool = False):
    chat_id = update.effective_chat.id
    
    if not VOICE_ENABLED or pytgcalls_client is None:
        await msg.edit_text(
            "⚠️ ميزة التشغيل في الكول تحتاج إعداد حساب مساعد (Userbot)\n"
            "تأكد من إضافة pyrogram و pytgcalls في requirements.txt وتشغيل الحساب المساعد أولاً"
        )
        return

    try:
        # تحميل الصوت/الفيديو
        if is_video:
            filepath, title = await download_video(query)
        else:
            filepath, title = await download_audio(query)

        if not filepath or not os.path.exists(filepath):
            await msg.edit_text(f"❌ فشل تحميل: {query}")
            return

        await msg.edit_text(f"{'🎬' if is_video else '🎵'} {'جاري رفع الفيديو' if is_video else 'جاري التشغيل'}: {title}\n⚡ Developer by {DEVELOPER}")

        # الانضمام للكول وتشغيل الملف
        if is_video:
            stream = MediaStream(
                filepath,
                audio_quality=AudioQuality.HIGH,
                video_quality=VideoQuality.SD_480p
            )
        else:
            stream = MediaStream(
                filepath,
                audio_quality=AudioQuality.HIGH,
                video_flags=MediaStream.IGNORE
            )

        active = active_calls.get(chat_id)
        if active:
            # إذا في تشغيل حالي - غير المقطع
            await pytgcalls_client.change_stream(chat_id, stream)
        else:
            # انضم للكول وابدأ التشغيل
            await pytgcalls_client.play(chat_id, stream)

        active_calls[chat_id] = {"playing": True, "paused": False, "loop": False, "title": title, "file": filepath}

        await msg.edit_text(
            f"{'🎬' if is_video else '🎵'} يشتغل الآن: {title}\n\n⚡ Developer by {DEVELOPER}",
            reply_markup=player_keyboard(chat_id)
        )

    except Exception as e:
        err = str(e)
        if "not in" in err.lower() or "GroupCallNotFound" in err or "not found" in err.lower():
            await msg.edit_text("❌ البوت مش في دردشة صوتية - افتح كول أولاً ثم اكتب الأمر")
        else:
            await msg.edit_text(f"❌ خطأ في التشغيل: {err[:150]}")
        # تنظيف الملف لو فيه
        try:
            fp = active_calls.get(chat_id, {}).get("file")
            if fp and os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass


def is_admin(user_id, chat_id):
    return user_id == OWNER_ID or user_id in admins_db.get(chat_id, [])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           لوحات المفاتيح
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("›: الاوامر :‹", callback_data="commands")],
        [InlineKeyboardButton("›: قناة البوت :‹", url="https://t.me/yourchannel")],
        [InlineKeyboardButton("›: اضف البوت الى مجموعتك :‹", url="https://t.me/yourbot?startgroup=true")],
        [InlineKeyboardButton("›: المطور :‹", callback_data="developer"), InlineKeyboardButton("›: لشراء بوت :‹", callback_data="buy")],
        [InlineKeyboardButton("›: لغات البوت :‹", callback_data="languages")],
    ])

def commands_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ أوامر التشغيل", callback_data="cmd_play")],
        [InlineKeyboardButton("🛡️ أوامر الحماية", callback_data="cmd_protection")],
        [InlineKeyboardButton("👑 أوامر الأدمن", callback_data="cmd_admin")],
        [InlineKeyboardButton("🚫 أوامر المنع", callback_data="cmd_filters")],
        [InlineKeyboardButton("💬 أوامر الردود", callback_data="cmd_responses"), InlineKeyboardButton("🏅 أوامر الرتب", callback_data="cmd_ranks")],
        [InlineKeyboardButton("🎮 الأوامر الإضافية", callback_data="cmd_extra")],
        [InlineKeyboardButton("العودة", callback_data="back_main")],
    ])

def player_keyboard(chat_id):
    state = active_calls.get(chat_id, {})
    paused = state.get("paused", False)
    looping = state.get("loop", False)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏸ ايقاف مؤقت" if not paused else "▶️ استكمال", callback_data=f"pause_{chat_id}"),
            InlineKeyboardButton("⏭ تخطي", callback_data=f"skip_{chat_id}"),
        ],
        [
            InlineKeyboardButton("🔁 تكرار: " + ("✅" if looping else "❌"), callback_data=f"loop_{chat_id}"),
            InlineKeyboardButton("⏹ ايقاف", callback_data=f"stop_{chat_id}"),
        ],
    ])

def back_btn(target="commands"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("العودة", callback_data=target)]])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           /start
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_users.add(user.id)
    if update.effective_chat.type != "private":
        bot_groups.add(update.effective_chat.id)
    text = (
        f"⚡ اهلا بك عزيزي {user.first_name}\n"
        f"≡ : انا بوت اسمي نقيب\n"
        f"≡ : يمكنني تشغيل الموسيقى في الاتصال\n"
        f"≡ : ادعم تشغيل منصات ‹ يوتيوب › ولخ .\n\n"
        f"⚡ Developer by {DEVELOPER}"
    )
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
            f"≡ : يمكنني تشغيل الموسيقى في الاتصال\n≡ : ادعم تشغيل منصات ‹ يوتيوب › ولخ .\n\n"
            f"⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=main_menu_keyboard())

async def show_developer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await safe_edit(q, caption=f"⚡ المطور: {DEVELOPER}\n━━━━━━━━━━━━━━━━━━\nللتواصل مع المطور اضغط الزر بالأسفل",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("تواصل مع المطور", url="https://t.me/yourusername")],[InlineKeyboardButton("العودة", callback_data="back_main")]]))

async def show_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await safe_edit(q, caption="⚡ لشراء بوت خاص بك:\n━━━━━━━━━━━━━━━━━━\nتواصل مع المطور للحصول على بوت مخصص",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("تواصل للشراء", url="https://t.me/yourusername")],[InlineKeyboardButton("العودة", callback_data="back_main")]]))

async def show_languages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await safe_edit(q, caption="⚡ اختر لغة البوت:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],[InlineKeyboardButton("العودة", callback_data="back_main")]]))

async def cmd_play_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = ("اوامر التشغيل ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« شغل [اسم] - تشغيل موسيقى في الكول\n« فيديو [اسم] - تشغيل فيديو في الكول\n"
            "« تشغيل عشوائي - تشغيل أغنية عشوائية\n« بحث [كلمة] - البحث في يوتيوب\n"
            "« تحميل [اسم] - تحميل فيديو\n« تنزيل [اسم] - تحميل ملف صوتي\n\n"
            "اوامر التحكم ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« ايقاف مؤقت / استكمال\n« تخطي - تخطي الأغنية\n"
            "« ايقاف / اسكت - وقف التشغيل\n« تكرار / كررها - تكرار الحالي\n"
            f"« تمرير [ثواني] - تغيير الوقت\n\n⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_protection_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = ("اوامر الحمايه ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« كتم - الغاء كتم - مسح المكتومين\n« تقيد - الغاء تقيد\n"
            "« حظر - الغاء حظر - مسح المحظورين\n« مسح + عدد - مسح الرسائل\n\n"
            "« المشرفين - قايمة المشرفين\n« البوتات - قايمة البوتات\n"
            "« طرد البوتات - حذف البوتات\n\n"
            "« تعين اسم - تعين اسم المجموعه\n« تعين صوره - صورة المجموعه\n"
            "« تفعيل/تعطيل الترحيب\n« رفع مشرف - تنزيل مشرف\n\n"
            f"⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = ("اوامر الأدمن ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "- المستخدمين ؛ قائمه مستخدمين البوت\n- المجموعات ؛ قائمه مجموعات البوت\n"
            "- الاحصائيات ؛ عدد المستخدمين والمجموعات\n"
            "- تفعيل/تعطيل الاشتراك الإجباري\n"
            "- تفعيل/تعطيل سجل التشغيل\n"
            f"- قسم الترويج ؛ إعلان عن مميزات البوت\n\n⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_filters_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = ("اوامر المنع ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "« منع الروابط - فتح الروابط\n« منع الاسائله - فتح الاسائله\n"
            f"« منع الاباحي - فتح الاباحي\n« منع التوجيه - فتح التوجيه\n\n⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_responses_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = ("اوامر الردود ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "استخدام: اضف رد [الكلمة] [الرد]\n\n"
            "- اضف رد عام → رد في جميع المحادثات\n"
            f"- اضف رد متعدد → رد عشوائي من عدة ردود\n\n⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_ranks_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = ("اوامر الرتب ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "- اضف رتبه → انشاء رتبه جديده\n- حذف رتبه → حذف رتبه موجوده\n"
            f"- ترقيه + اسم الرتبه → اضافه صلاحيات\n- عزل + اسم الرتبه → ازاله صلاحيات\n\n⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

async def cmd_extra_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = ("الاوامر الإضافية ⚡:\n━━━━━━━━━━━━━━━━━━\n"
            "• صراحه » اسئلة صراحه\n• فزوره » فزوره وتحلها\n"
            "• تحدي » تحديات مسليه\n• لو خيروك » اختار من اتنين\n"
            f"• امثله » امثله معروفه\n• اسئله » اسئله متنوعه\n\n⚡ Developer by {DEVELOPER}")
    await safe_edit(q, caption=text, reply_markup=back_btn())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   Callbacks - التحكم في المشغل
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def player_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    chat_id = int(data.split("_")[1])

    if not is_admin(q.from_user.id, chat_id):
        await q.answer("❌ للادمنية فقط", show_alert=True)
        return

    state = active_calls.get(chat_id, {})

    if data.startswith("pause_"):
        if state.get("paused"):
            state["paused"] = False
            status = "▶️ تم استكمال التشغيل"
            if VOICE_ENABLED and pytgcalls_client:
                try: await pytgcalls_client.resume_stream(chat_id)
                except Exception: pass
        else:
            state["paused"] = True
            status = "⏸ تم ايقاف التشغيل مؤقتاً"
            if VOICE_ENABLED and pytgcalls_client:
                try: await pytgcalls_client.pause_stream(chat_id)
                except Exception: pass
        active_calls[chat_id] = state
        await q.edit_message_text(f"{status}\n🎵 {state.get('title','')}", reply_markup=player_keyboard(chat_id))

    elif data.startswith("skip_"):
        state["playing"] = False
        active_calls[chat_id] = state
        if VOICE_ENABLED and pytgcalls_client:
            try: await pytgcalls_client.leave_call(chat_id)
            except Exception: pass
        active_calls.pop(chat_id, None)
        await q.edit_message_text(f"⏭ تم تخطي الأغنية\n\n⚡ Developer by {DEVELOPER}")

    elif data.startswith("loop_"):
        state["loop"] = not state.get("loop", False)
        active_calls[chat_id] = state
        await q.edit_message_text(
            f"🔁 التكرار: {'✅ مفعل' if state['loop'] else '❌ معطل'}\n🎵 {state.get('title','')}",
            reply_markup=player_keyboard(chat_id))

    elif data.startswith("stop_"):
        if VOICE_ENABLED and pytgcalls_client:
            try: await pytgcalls_client.leave_call(chat_id)
            except Exception: pass
        # تنظيف الملف
        fp = state.get("file")
        if fp and os.path.exists(fp):
            try: os.remove(fp)
            except Exception: pass
        active_calls.pop(chat_id, None)
        await q.edit_message_text(f"⏹ تم ايقاف التشغيل\n\n⚡ Developer by {DEVELOPER}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   أوامر الحماية
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def get_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    admins = await chat.get_administrators()
    text = "👑 قائمة المشرفين:\n━━━━━━━━━━━━━━━━━━\n"
    for a in admins:
        text += f"• {a.user.mention_html()}\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        await update.message.reply_text("❌ هذا الأمر للادمنية فقط"); return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ رد على رسالة المستخدم المراد كتمه"); return
    target = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(target.id, ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"🔇 تم كتم {target.mention_html()}", parse_mode="HTML")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        await update.message.reply_text("❌ هذا الأمر للادمنية فقط"); return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ رد على رسالة المستخدم"); return
    target = update.message.reply_to_message.from_user
    await update.effective_chat.restrict_member(target.id, ChatPermissions(can_send_messages=True, can_send_other_messages=True, can_send_polls=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_add_web_page_previews=True))
    await update.message.reply_text(f"🔊 تم الغاء كتم {target.mention_html()}", parse_mode="HTML")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        await update.message.reply_text("❌ هذا الأمر للادمنية فقط"); return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ رد على رسالة المستخدم المراد حظره"); return
    target = update.message.reply_to_message.from_user
    await update.effective_chat.ban_member(target.id)
    await update.message.reply_text(f"🚫 تم حظر {target.mention_html()}", parse_mode="HTML")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        await update.message.reply_text("❌ هذا الأمر للادمنية فقط"); return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ رد على رسالة المستخدم"); return
    target = update.message.reply_to_message.from_user
    await update.effective_chat.unban_member(target.id)
    await update.message.reply_text(f"✅ تم الغاء حظر {target.mention_html()}", parse_mode="HTML")

async def kick_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        await update.message.reply_text("❌ هذا الأمر للادمنية فقط"); return
    admins = await update.effective_chat.get_administrators()
    admin_ids = {a.user.id for a in admins}
    kicked = 0
    async for member in update.effective_chat.get_members():
        if member.user.is_bot and member.user.id not in admin_ids:
            await update.effective_chat.ban_member(member.user.id)
            await update.effective_chat.unban_member(member.user.id)
            kicked += 1
    await update.message.reply_text(f"🤖 تم طرد {kicked} بوت")

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        await update.message.reply_text("❌ هذا الأمر للادمنية فقط"); return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ رد على رسالة المستخدم"); return
    target = update.message.reply_to_message.from_user
    await update.effective_chat.promote_member(
        target.id,
        can_delete_messages=True,
        can_restrict_members=True,
        can_pin_messages=True,
        can_invite_users=True
    )
    await update.message.reply_text(f"⬆️ تم رفع {target.mention_html()} مشرف", parse_mode="HTML")

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        await update.message.reply_text("❌ هذا الأمر للادمنية فقط"); return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ رد على رسالة المستخدم"); return
    target = update.message.reply_to_message.from_user
    await update.effective_chat.promote_member(target.id)
    await update.message.reply_text(f"⬇️ تم تنزيل {target.mention_html()} من المشرفين", parse_mode="HTML")

async def delete_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(update.effective_user.id, chat_id):
        await update.message.reply_text("❌ هذا الأمر للادمنية فقط"); return
    count = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    count = min(count, 100)
    msg_id = update.message.message_id
    deleted = 0
    for i in range(msg_id, msg_id - count - 1, -1):
        try:
            await context.bot.delete_message(chat_id, i)
            deleted += 1
        except:
            pass
    m = await update.message.reply_text(f"🗑 تم مسح {deleted} رسالة")
    await asyncio.sleep(3)
    try: await m.delete()
    except: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   الأوامر الإضافية
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SARA7A = [
    "ايه اكتر حاجه بتخليك تحس بالوحده؟",
    "لو قدرت تغير حاجه في نفسك ايه هتكون؟",
    "ايه اصعب قرار اتخدته في حياتك؟",
    "مين الشخص اللي اتمنيت تعيش معاه أكتر؟",
    "ايه اكبر غلطه عملتها وندمت عليها؟",
    "ايه اللي بيخليك تصحى كل يوم؟",
    "لو عندك يوم واحد تعيشه زي ما انت عايز هتعمل ايه؟",
]
FOSORA = [
    ("ما بيت ولا خيمه وساكنه في القمه ؟", "النجمه"),
    ("بياخد ويدي ما بياخدش ويمشي ؟", "الصوت"),
    ("كلما زاد نقص ؟", "العمر"),
    ("طول عمرها واقفه وما بتتعبش ؟", "الشجره"),
    ("بتاكل وما بتشبعش ؟", "النار"),
]
TAHADI = [
    "اعمل 20 ضغطه في دقيقه 💪",
    "قول كلمه واحده بس لمدة ساعه 🤐",
    "اكتب اسمك بإيدك التانيه ✍️",
    "اقلد شخص في الشات لمدة 5 دقايق 😂",
    "ابعت صورة سيلفي دلوقتي 📸",
]
AMSAL = [
    "اللي مات مات ومن عاش يتأمل",
    "الصاحب وقت الضيق",
    "أكل العيش مش سهل",
    "البعيد عن العين بعيد عن القلب",
    "اللي يتجوز أمي أقوله عمي",
]
LO_KHAROUK = [
    ("المال", "الصحة"),
    ("الشهرة", "السعادة"),
    ("الحكمة", "الجمال"),
    ("الحرية", "الأمان"),
    ("الحب", "النجاح"),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   معالج الرسائل النصية
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # ━ فلتر الروابط
    if link_filter.get(chat_id) and ("t.me" in text or "http" in text):
        if not is_admin(user_id, chat_id):
            try: await update.message.delete()
            except: pass
            m = await update.message.reply_text("🚫 الروابط ممنوعة في هذه المجموعة")
            await asyncio.sleep(5)
            try: await m.delete()
            except: pass
            return

    # ━ شغل / تشغيل
    if text.startswith("شغل ") or text.startswith("تشغيل "):
        query = text.split(" ", 1)[1]
        msg = await update.message.reply_text(f"🎵 جاري تشغيل: {query}\n⏳ يتم التحميل من يوتيوب...")
        await play_in_call(update, context, query, msg, is_video=False)

    elif text.startswith("فيد ") or text.startswith("فيديو "):
        query = text.split(" ", 1)[1]
        msg = await update.message.reply_text(f"🎬 جاري تشغيل فيديو: {query}\n⏳ يتم التحميل...")
        await play_in_call(update, context, query, msg, is_video=True)

    elif text == "تشغيل عشوائي":
        songs = ["Blinding Lights", "Shape of You", "Bohemian Rhapsody", "Stay", "Levitating"]
        song = random.choice(songs)
        msg = await update.message.reply_text(f"🎲 تشغيل عشوائي: {song}\n⏳ يتم التحميل...")
        await play_in_call(update, context, song, msg, is_video=False)

    elif text.startswith("بحث "):
        query = text[4:]
        msg = await update.message.reply_text(f"🔍 جاري البحث عن: {query}...")
        try:
            results = await youtube_search(query)
            if not results:
                await msg.edit_text("❌ مافيش نتائج")
                return
            text_out = f"🔍 نتائج البحث عن: **{query}**\n━━━━━━━━━━━━━━━━━━\n"
            buttons = []
            for i, r in enumerate(results[:5], 1):
                title = r.get("title", "بدون عنوان")[:50]
                url = f"https://youtu.be/{r.get('id','')}"
                duration = int(r.get("duration", 0) or 0)
                mins = duration // 60
                secs = duration % 60
                text_out += f"{i}️⃣ {title} [{mins}:{secs:02d}]\n"
                buttons.append([InlineKeyboardButton(f"▶️ {title[:30]}", url=url)])
            buttons.append([InlineKeyboardButton("العودة", callback_data="back_main")])
            await msg.edit_text(text_out, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ في البحث: {str(e)[:100]}")

    elif text.startswith("تحميل "):
        query = text[6:]
        msg = await update.message.reply_text(f"🎬 جاري تحميل: {query}\n⏳ يتم البحث في يوتيوب...")
        try:
            filepath, title = await download_video(query)
            if filepath and os.path.exists(filepath):
                size_mb = os.path.getsize(filepath) / (1024*1024)
                if size_mb > 50:
                    await msg.edit_text(f"❌ الفيديو كبير جداً ({size_mb:.1f}MB) - جرب تنزيل بدل تحميل للصوت فقط")
                    os.remove(filepath)
                    return
                await msg.edit_text(f"📤 جاري رفع الفيديو: {title} ({size_mb:.1f}MB)")
                with open(filepath, 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption=f"🎬 {title}\n\n⚡ Developer by {DEVELOPER}"
                    )
                await msg.delete()
                os.remove(filepath)
            else:
                await msg.edit_text("❌ فشل التحميل، جرب مرة تانية")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {str(e)[:150]}")

    elif text.startswith("تنزيل "):
        query = text[6:]
        msg = await update.message.reply_text(f"🎵 جاري تنزيل: {query}\n⏳ يتم البحث في يوتيوب...")
        try:
            filepath, title = await download_audio(query)
            if filepath and os.path.exists(filepath):
                await msg.edit_text(f"📤 جاري رفع الملف: {title}")
                with open(filepath, 'rb') as audio_file:
                    await update.message.reply_audio(
                        audio=audio_file,
                        title=title,
                        caption=f"🎵 {title}\n\n⚡ Developer by {DEVELOPER}"
                    )
                await msg.delete()
                os.remove(filepath)
            else:
                await msg.edit_text("❌ فشل التنزيل، جرب مرة تانية")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {str(e)[:150]}")

    elif text == "ايقاف مؤقت":
        if is_admin(user_id, chat_id) and chat_id in active_calls:
            active_calls[chat_id]["paused"] = True
            await update.message.reply_text("⏸ تم ايقاف التشغيل مؤقتاً", reply_markup=player_keyboard(chat_id))

    elif text == "استكمال":
        if is_admin(user_id, chat_id) and chat_id in active_calls:
            active_calls[chat_id]["paused"] = False
            await update.message.reply_text("▶️ تم استكمال التشغيل", reply_markup=player_keyboard(chat_id))

    elif text == "تخطي":
        if is_admin(user_id, chat_id):
            active_calls.pop(chat_id, None)
            await update.message.reply_text(f"⏭ تم تخطي الأغنية\n\n⚡ Developer by {DEVELOPER}")

    elif text in ["ايقاف", "اسكت"]:
        if is_admin(user_id, chat_id):
            active_calls.pop(chat_id, None)
            await update.message.reply_text(f"⏹ تم ايقاف التشغيل\n\n⚡ Developer by {DEVELOPER}")

    elif text in ["تكرار", "كررها"]:
        if is_admin(user_id, chat_id) and chat_id in active_calls:
            active_calls[chat_id]["loop"] = not active_calls[chat_id].get("loop", False)
            state = "✅ مفعل" if active_calls[chat_id]["loop"] else "❌ معطل"
            await update.message.reply_text(f"🔁 التكرار: {state}")

    elif text.startswith("تمرير ") or text.startswith("مرر "):
        parts = text.split()
        sec = parts[1] if len(parts) > 1 else "0"
        await update.message.reply_text(f"⏩ تم التمرير إلى: {sec} ثانية\n\n⚡ Developer by {DEVELOPER}")

    elif text == "بنج":
        t = time.time()
        msg = await update.message.reply_text("🏓 جاري القياس...")
        ms = round((time.time()-t)*1000)
        await msg.edit_text(f"🏓 بنج!\n⚡ سرعة الاستجابة: {ms}ms\n\n⚡ Developer by {DEVELOPER}")

    elif text == "سورس":
        await update.message.reply_animation(
            animation=WELCOME_GIF,
            caption=(f"⚡ معلومات البوت:\n━━━━━━━━━━━━━━━━━━\n"
                     f"🤖 اسم البوت: نقيب\n👨‍💻 المطور: {DEVELOPER}\n"
                     f"👥 المستخدمين: {len(bot_users)}\n💬 المجموعات: {len(bot_groups)}\n\n"
                     f"⚡ Developer by {DEVELOPER}")
        )

    elif text == "المشرفين":
        await get_admins(update, context)

    elif text == "كتم":
        await mute_user(update, context)

    elif text == "الغاء كتم":
        await unmute_user(update, context)

    elif text == "حظر":
        await ban_user(update, context)

    elif text == "الغاء حظر":
        await unban_user(update, context)

    elif text == "رفع مشرف":
        await promote_user(update, context)

    elif text == "تنزيل مشرف":
        await demote_user(update, context)

    elif text == "طرد البوتات":
        await kick_bots(update, context)

    elif text.startswith("مسح "):
        parts = text.split()
        context.args = [parts[1]] if len(parts) > 1 else ["1"]
        await delete_messages(update, context)

    elif text == "منع الروابط":
        if is_admin(user_id, chat_id):
            link_filter[chat_id] = True
            await update.message.reply_text("🚫 تم تفعيل منع الروابط")

    elif text == "فتح الروابط":
        if is_admin(user_id, chat_id):
            link_filter[chat_id] = False
            await update.message.reply_text("✅ تم فتح الروابط")

    elif text == "منع الاباحي":
        if is_admin(user_id, chat_id):
            nsfw_filter[chat_id] = True
            await update.message.reply_text("🚫 تم تفعيل منع المحتوى الإباحي")

    elif text == "فتح الاباحي":
        if is_admin(user_id, chat_id):
            nsfw_filter[chat_id] = False
            await update.message.reply_text("✅ تم فتح المحتوى")

    elif text == "تفعيل الترحيب":
        if is_admin(user_id, chat_id):
            welcome_enabled[chat_id] = True
            await update.message.reply_text("✅ تم تفعيل رسالة الترحيب")

    elif text == "تعطيل الترحيب":
        if is_admin(user_id, chat_id):
            welcome_enabled[chat_id] = False
            await update.message.reply_text("❌ تم تعطيل رسالة الترحيب")

    elif text.startswith("اضف رد "):
        if is_admin(user_id, chat_id):
            parts = text[7:].split(" ", 1)
            if len(parts) == 2:
                if chat_id not in auto_responses:
                    auto_responses[chat_id] = []
                auto_responses[chat_id].append({"trigger": parts[0], "response": parts[1]})
                await update.message.reply_text(f"✅ تم إضافة الرد على: {parts[0]}")
            else:
                await update.message.reply_text("⚡ استخدام: اضف رد [الكلمة] [الرد]")

    elif text == "الاحصائيات":
        if user_id == OWNER_ID:
            await update.message.reply_text(
                f"📊 الاحصائيات:\n━━━━━━━━━━━━━━━━━━\n"
                f"👥 المستخدمين: {len(bot_users)}\n💬 المجموعات: {len(bot_groups)}\n\n"
                f"⚡ Developer by {DEVELOPER}"
            )

    elif text == "صراحه":
        await update.message.reply_text(f"🎯 سؤال صراحة:\n\n{random.choice(SARA7A)}\n\n⚡ Developer by {DEVELOPER}")

    elif text == "فزوره":
        f, a = random.choice(FOSORA)
        context.chat_data["fosora_answer"] = a
        await update.message.reply_text(f"🧩 الفزورة:\n\n{f}\n\nاكتب اجابتك...")

    elif text == "تحدي":
        await update.message.reply_text(f"💪 التحدي:\n\n{random.choice(TAHADI)}\n\n⚡ Developer by {DEVELOPER}")

    elif text == "امثله":
        await update.message.reply_text(f"📖 مثل:\n\n{random.choice(AMSAL)}\n\n⚡ Developer by {DEVELOPER}")

    elif text == "لو خيروك":
        a, b = random.choice(LO_KHAROUK)
        await update.message.reply_text(
            f"🤔 لو خيروك:\n\n{a} أم {b}؟\n\n⚡ Developer by {DEVELOPER}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(a, callback_data="lo_a"), InlineKeyboardButton(b, callback_data="lo_b")]])
        )

    else:
        # ردود تلقائية
        if chat_id in auto_responses:
            for item in auto_responses[chat_id]:
                if item["trigger"].lower() in text.lower():
                    await update.message.reply_text(item["response"])
                    break

        # إجابة الفزورة
        if "fosora_answer" in context.chat_data:
            if text.strip() == context.chat_data["fosora_answer"]:
                await update.message.reply_text(f"✅ إجابة صح! 🎉 الإجابة: {context.chat_data['fosora_answer']}")
                del context.chat_data["fosora_answer"]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   أعضاء جدد
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not welcome_enabled.get(chat_id):
        return
    for member in update.message.new_chat_members:
        msg = welcome_msg.get(chat_id, "👋 مرحباً {user} في {chat}! 🎉\n\nنورت المجموعة!")
        msg = msg.replace("{user}", member.mention_html()).replace("{chat}", update.effective_chat.title or "")
        await update.message.reply_animation(animation=WELCOME_GIF, caption=msg, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           تشغيل البوت
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import asyncio

async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))
    app.add_handler(CommandHandler("kick", kick_bots))
    app.add_handler(CommandHandler("promote", promote_user))
    app.add_handler(CommandHandler("demote", demote_user))

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
    app.add_handler(CallbackQueryHandler(player_callback, pattern="^(pause|skip|loop|stop)_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

    print("⚡ البوت شغال...")
    # تهيئة الحساب المساعد للتشغيل الصوتي
    if VOICE_ENABLED:
        voice_ok = await init_voice_client()
        if voice_ok:
            print("✅ الحساب المساعد شغال - التشغيل الصوتي جاهز")
        else:
            print("⚠️ فشل تشغيل الحساب المساعد - أوامر الكول مش هتشتغل")
    else:
        print("⚠️ pyrogram/pytgcalls مش مثبتين - أوامر الكول معطلة")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
