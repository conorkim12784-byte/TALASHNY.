import os
import re
import json
import uuid
import logging
import asyncio
from datetime import datetime
from time import time

from telegram import (
    Update, ChatPermissions,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from bad_words import BAD_WORDS
from kick_tracker import KickTracker

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════
#         ⚙️ إعدادات البوت
# ══════════════════════════════════════
BOT_TOKEN       = os.environ.get("BOT_TOKEN", "5715894811:AAEdH_xnLRq1zoNMvZITgQSpJWn8pPjkb4k")
DEVELOPER_ID    = 1923931101
KICK_BAN_LIMIT  = 20
BOT_NAME        = "TALASHNY"
BOT_USERNAME    = "G_FireBot"          # يوزرنيم البوت بدون @
GROUP_SUPPORT   = "D_7_k3"          # يوزرنيم جروب الدعم بدون @
UPDATES_CHANNEL = "FY_TF"          # يوزرنيم قناة التحديثات بدون @
WELCOME_PHOTO   = "https://i.postimg.cc/wxV3PspQ/1756574872401.gif"          # رابط صورة الترحيب (اختياري)
BOT_PHOTO       = "https://i.postimg.cc/wxV3PspQ/1756574872401.gif"          # صورة البوت في رسايل المساعدة (اختياري)

START_TIME = datetime.utcnow()
tracker    = KickTracker()

# ══════════════════════════════════════
#         🔰 نظام الرتب (Sudo)
# ══════════════════════════════════════
# المطور  → صلاحيات كاملة في كل الجروبات
# Sudo    → صلاحيات في الجروب اللي اترفع فيه بس
# مشرف عادي → أوامر الطرد/الحظر/الكتم العادية

SUDO_DB_FILE = "sudo_db.json"

def _load_sudo():
    if os.path.exists(SUDO_DB_FILE):
        try:
            with open(SUDO_DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_sudo(db):
    with open(SUDO_DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

sudo_db = _load_sudo()

def is_sudo(chat_id, user_id):
    return user_id in sudo_db.get(str(chat_id), [])

def add_sudo(chat_id, user_id):
    key = str(chat_id)
    if key not in sudo_db:
        sudo_db[key] = []
    if user_id not in sudo_db[key]:
        sudo_db[key].append(user_id)
    _save_sudo(sudo_db)

def remove_sudo(chat_id, user_id):
    key = str(chat_id)
    if key in sudo_db and user_id in sudo_db[key]:
        sudo_db[key].remove(user_id)
        _save_sudo(sudo_db)

def is_privileged(chat_id, user_id):
    """مطور أو sudo في الجروب ده"""
    return user_id == DEVELOPER_ID or is_sudo(chat_id, user_id)

def rank_label(chat_id, user_id):
    if user_id == DEVELOPER_ID:
        return "👑 مطور السورس"
    if is_sudo(chat_id, user_id):
        return "🔰 مساعد مطور"
    return "🛡️ مشرف"



# ══════════════════════════════════════
#         📋 الأوامر العربية
# ══════════════════════════════════════
COMMANDS = {
    # إدارة الرتب (للمطور)
    "اضف مساعد":     "addsudo",
    "شيل مساعد":     "removesudo",
    "المساعدين":     "sudolist",
    # إدارة المشرفين (للمطور فقط)
    "رفع":           "promote",
    "ترقية":         "promote",
    "نزول":          "demote",
    "عزل":           "demote",
    # عقوبات (للمشرفين)
    "طرد":           "kick",
    "حظر":           "ban",
    "فك حظر":        "unban",
    "كتم":           "mute",
    "فك كتم":        "unmute",
    # تحذيرات
    "تحذير":         "warn",
    "انذار":         "warn",
    "تحذيرات":       "warns",
    "انذارات":       "warns",
    "مسح تحذيرات":   "resetwarns",
    # تثبيت
    "تثبيت":         "pin",
    "الغاء تثبيت":   "unpin",
    # معلومات
    "ايدي":          "id",
    "آيدي":          "id",
    "id":            "id",
    "معلومات":       "info",
    "بروفايل":       "info",
    # إحصائيات
    "احصائيات":      "stats",
    "إحصائيات":      "stats",
    # تحديث
    "تحديث":         "reload",
    "اعاده":         "reload",
    # أخرى
    "بينج":          "ping",
    "ping":          "ping",
    "uptime":        "uptime",
    "وقت التشغيل":   "uptime",
    "alive":         "alive",
    "حي":            "alive",
    # إذاعة (للمطور)
    "اذاعه":         "broadcast",
    "اذاعة":         "broadcast",
    # مساعدة
    "مساعدة":        "help",
    "هلب":           "help",
    "اوامر":         "help",
    "أوامر":         "help",
    "start":         "help",
    "ابدأ":          "help",
}

# ══════════════════════════════════════
#         🔧 دوال مساعدة
# ══════════════════════════════════════

def parse_arabic_command(text: str):
    text = text.strip()
    for cmd in sorted(COMMANDS.keys(), key=len, reverse=True):
        if text == cmd or text.startswith(cmd + " "):
            arg = text[len(cmd):].strip() or None
            return COMMANDS[cmd], arg
    return None, None

async def is_admin(update, context, user_id):
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except TelegramError:
        return False

async def resolve_target(update, context, arg=None):
    msg = update.message
    if msg.reply_to_message:
        user = msg.reply_to_message.from_user
        return user.id, user.full_name
    if not arg:
        return None, None
    target = arg.split()[0]
    if target.lstrip('-').isdigit():
        user_id = int(target)
        try:
            member = await context.bot.get_chat_member(msg.chat_id, user_id)
            return user_id, member.user.full_name
        except TelegramError:
            return user_id, str(user_id)
    username = target.lstrip('@')
    try:
        member = await context.bot.get_chat_member(msg.chat_id, f"@{username}")
        return member.user.id, member.user.full_name
    except TelegramError:
        try:
            chat = await context.bot.get_chat(f"@{username}")
            return chat.id, chat.full_name or chat.username
        except TelegramError:
            return None, None

async def delete_after(context, chat_id, message_id, delay=5):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError:
        pass

def make_session_key():
    return uuid.uuid4().hex

TIME_UNITS = [("أسبوع",604800),("يوم",86400),("ساعة",3600),("دقيقة",60),("ثانية",1)]

def human_time(seconds):
    if seconds == 0:
        return "0 ثانية"
    parts = []
    for unit, div in TIME_UNITS:
        amount, seconds = divmod(int(seconds), div)
        if amount > 0:
            parts.append(f"{amount} {unit}")
    return "، ".join(parts)

# ══════════════════════════════════════
#         🎛️ أزرار الرسايل
# ══════════════════════════════════════

def main_menu_keyboard():
    """الكيبورد الرئيسي"""
    buttons = []
    row = [InlineKeyboardButton("📋 الأوامر", callback_data="cb_commands")]
    if GROUP_SUPPORT:
        row.append(InlineKeyboardButton("👥 جروب الدعم", url=f"https://t.me/{GROUP_SUPPORT}"))
    buttons.append(row)
    row2 = []
    if UPDATES_CHANNEL:
        row2.append(InlineKeyboardButton("📣 القناة", url=f"https://t.me/{UPDATES_CHANNEL}"))
    if BOT_USERNAME:
        row2.append(InlineKeyboardButton("➕ أضف البوت", url=f"https://t.me/{BOT_USERNAME}?startgroup=true"))
    if row2:
        buttons.append(row2)
    return InlineKeyboardMarkup(buttons)

def commands_keyboard():
    """كيبورد الأوامر"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛡 أوامر الإدارة",   callback_data="cb_admin_cmds"),
            InlineKeyboardButton("⚖️ أوامر العقوبات",  callback_data="cb_punish_cmds"),
        ],
        [
            InlineKeyboardButton("ℹ️ أوامر المعلومات", callback_data="cb_info_cmds"),
            InlineKeyboardButton("👑 أوامر المطور",     callback_data="cb_dev_cmds"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="cb_main")],
    ])

def back_keyboard(cb="cb_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=cb)]])

def back_to_commands():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="cb_commands")]])

# ══════════════════════════════════════
#      🎛️ Callback الأزرار الرئيسية
# ══════════════════════════════════════

MAIN_TEXT = lambda name: (
    f"━━━━━━━━━━━━━━━━━━━━\n"
    f"👋 أهلاً <b>{name}</b>!\n"
    f"أنا <b>{BOT_NAME}</b> بوت إدارة متكامل 🤖\n"
    f"━━━━━━━━━━━━━━━━━━━━\n\n"
    f"🔹 رفع ونزول المشرفين مع تحديد الصلاحيات\n"
    f"🔹 طرد وحظر وكتم الأعضاء\n"
    f"🔹 نظام تحذيرات تلقائي\n"
    f"🔹 فلتر الكلمات المحظورة\n"
    f"🔹 رسايل ترحيب ووداع\n\n"
    f"اضغط على <b>الأوامر</b> عشان تشوف كل اللي أقدر أعمله 👇"
)

ADMIN_CMDS_TEXT = (
    "🛡 <b>أوامر الإدارة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔹 <b>رفع</b> — رفع مشرف مع اختيار صلاحياته\n"
    "🔹 <b>نزول</b> — نزول مشرف من الإشراف\n"
    "🔹 <b>تثبيت</b> — تثبيت رسالة\n"
    "🔹 <b>الغاء تثبيت</b> — إلغاء تثبيت الرسالة\n"
    "🔹 <b>تحديث</b> — تحديث قائمة المشرفين\n\n"
    "🎖 <b>الرتب:</b>\n"
    "👑 مطور السورس — صلاحيات كاملة في كل الجروبات\n"
    "🔰 مساعد مطور — صلاحيات في جروبه بس\n"
    "🛡️ مشرف — أوامر الطرد والحظر والكتم\n\n"
    "📌 <i>أوامر رفع ونزول للمطور فقط</i>"
)

PUNISH_CMDS_TEXT = (
    "⚖️ <b>أوامر العقوبات</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔹 <b>طرد</b> — طرد عضو من الجروب\n"
    "🔹 <b>حظر</b> — حظر عضو نهائياً\n"
    "🔹 <b>فك حظر</b> — فك الحظر\n"
    "🔹 <b>كتم</b> — منع عضو من الكتابة\n"
    "🔹 <b>فك كتم</b> — رفع الكتم\n"
    "🔹 <b>تحذير</b> — إعطاء تحذير (بعد 3 تحذيرات يتحظر)\n"
    "🔹 <b>تحذيرات</b> — عرض تحذيرات عضو\n"
    "🔹 <b>مسح تحذيرات</b> — مسح تحذيرات عضو\n\n"
    "📌 <i>جميع الأوامر للمشرفين فقط</i>"
)

INFO_CMDS_TEXT = (
    "ℹ️ <b>أوامر المعلومات</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔹 <b>ايدي</b> — عرض ID المستخدم أو الجروب\n"
    "🔹 <b>معلومات</b> — معلومات مفصلة عن عضو\n"
    "🔹 <b>احصائيات</b> — إحصائيات طرد/حظر المشرفين\n"
    "🔹 <b>بينج</b> — سرعة استجابة البوت\n"
    "🔹 <b>uptime</b> — وقت تشغيل البوت\n"
    "🔹 <b>alive</b> — حالة البوت\n\n"
    "📌 <i>متاحة للجميع</i>"
)

DEV_CMDS_TEXT = (
    "👑 <b>أوامر المطور</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔹 <b>رفع</b> — رفع مشرف\n"
    "🔹 <b>نزول</b> — نزول مشرف\n"
    "🔹 <b>اضف مساعد</b> — إضافة مساعد مطور في الجروب\n"
    "🔹 <b>شيل مساعد</b> — إزالة مساعد مطور\n"
    "🔹 <b>المساعدين</b> — قائمة المساعدين في الجروب\n"
    "🔹 <b>اذاعه</b> — إذاعة رسالة لكل الجروبات\n\n"
    "📌 <i>هذه الأوامر للمطور فقط</i>"
)

async def handle_menu_callback(update, context):
    query = update.callback_query
    await query.answer()
    data  = query.data
    name  = query.from_user.first_name

    if data == "cb_main":
        text = MAIN_TEXT(name)
        kb   = main_menu_keyboard()
        if BOT_PHOTO:
            try:
                await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=kb)
                return
            except TelegramError:
                pass
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

    elif data == "cb_commands":
        await query.edit_message_text(
            f"📋 <b>اختار الفئة اللي عايز تشوف أوامرها:</b>",
            parse_mode="HTML", reply_markup=commands_keyboard()
        )

    elif data == "cb_admin_cmds":
        await query.edit_message_text(ADMIN_CMDS_TEXT, parse_mode="HTML", reply_markup=back_to_commands())

    elif data == "cb_punish_cmds":
        await query.edit_message_text(PUNISH_CMDS_TEXT, parse_mode="HTML", reply_markup=back_to_commands())

    elif data == "cb_info_cmds":
        await query.edit_message_text(INFO_CMDS_TEXT, parse_mode="HTML", reply_markup=back_to_commands())

    elif data == "cb_dev_cmds":
        await query.edit_message_text(DEV_CMDS_TEXT, parse_mode="HTML", reply_markup=back_to_commands())


# ══════════════════════════════════════
#      🔰 إدارة الـ Sudo
# ══════════════════════════════════════

async def handle_addsudo(update, context, arg):
    """إضافة مساعد مطور في جروب معين - للمطور فقط"""
    if update.message.from_user.id != DEVELOPER_ID:
        m = await update.message.reply_text("❌ هذا الأمر للمطور فقط!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    chat_id = update.message.chat_id
    add_sudo(chat_id, target_id)
    try:
        chat = await context.bot.get_chat(chat_id)
        chat_title = chat.title
    except TelegramError:
        chat_title = str(chat_id)
    await update.message.reply_text(
        "🔰 <b>تم إضافة مساعد مطور</b>\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👤 المستخدم: <b>{target_name}</b>\n"
        f"💭 الجروب: <b>{chat_title}</b>\n\n"
        "📌 صلاحياته محدودة بهذا الجروب فقط",
        parse_mode="HTML"
    )

async def handle_removesudo(update, context, arg):
    """إزالة مساعد مطور - للمطور فقط"""
    if update.message.from_user.id != DEVELOPER_ID:
        m = await update.message.reply_text("❌ هذا الأمر للمطور فقط!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    chat_id = update.message.chat_id
    if not is_sudo(chat_id, target_id):
        await update.message.reply_text(f"❌ <b>{target_name}</b> مش مساعد مطور في الجروب ده.", parse_mode="HTML")
        return
    remove_sudo(chat_id, target_id)
    await update.message.reply_text(
        f"✅ <b>تم إزالة المساعد</b>\n━━━━━━━━━━━━━━━━\n👤 المستخدم: <b>{target_name}</b>",
        parse_mode="HTML"
    )

async def handle_sudolist(update, context):
    """قائمة المساعدين في الجروب"""
    if update.message.from_user.id != DEVELOPER_ID:
        m = await update.message.reply_text("❌ هذا الأمر للمطور فقط!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    chat_id = update.message.chat_id
    sudos   = sudo_db.get(str(chat_id), [])
    if not sudos:
        await update.message.reply_text("📋 مفيش مساعدين مطور في الجروب ده.")
        return
    text = "🔰 <b>مساعدو المطور في هذا الجروب:</b>\n━━━━━━━━━━━━━━━━\n\n"
    for uid in sudos:
        try:
            member = await context.bot.get_chat_member(chat_id, uid)
            name   = member.user.full_name
            uname  = f"@{member.user.username}" if member.user.username else ""
            text  += f"🔰 <b>{name}</b> {uname}\n🆔 <code>{uid}</code>\n\n"
        except TelegramError:
            text += f"🔰 <code>{uid}</code>\n\n"
    await update.message.reply_text(text, parse_mode="HTML")


async def handle_promote(update, context, arg):
    if update.message.from_user.id != DEVELOPER_ID:
        m = await update.message.reply_text("❌ أمر رفع المشرفين متاح للمطور فقط!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text(
            "❌ مش قادر أعرف المستخدم.\n"
            "جرب: رد على رسالته، أو <b>رفع @يوزر</b> أو <b>رفع ID</b>",
            parse_mode="HTML"
        )
        return
    chat_id     = update.message.chat_id
    session_key = make_session_key()
    promote_sessions[session_key] = {
        "target_id": target_id, "target_name": target_name,
        "chat_id": chat_id, "awaiting_title": False,
        "permissions": {
            "delete":True,"ban":True,"pin":False,
            "info":False,"add_admins":False,"invite":True,"title":""
        }
    }
    p       = promote_sessions[session_key]["permissions"]
    keyboard= build_promote_keyboard(session_key, p)
    await update.message.reply_text(
        f"🛡 <b>رفع مشرف</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 المستخدم: <b>{target_name}</b>\n\n"
        f"اختار الصلاحيات ثم اضغط رفعه مشرف:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_demote(update, context, arg):
    if update.message.from_user.id != DEVELOPER_ID:
        m = await update.message.reply_text("❌ أمر نزول المشرفين متاح للمطور فقط!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    try:
        await context.bot.promote_chat_member(
            chat_id=update.message.chat_id, user_id=target_id,
            can_delete_messages=False, can_restrict_members=False,
            can_pin_messages=False, can_change_info=False,
            can_promote_members=False, can_invite_users=False,
        )
        await update.message.reply_text(
            f"✅ <b>تم نزول المشرف</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{target_name}</b> اتنزل من الإشراف.",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: {e}")

async def handle_title_input(update, context):
    session_key = context.user_data.get("awaiting_title_session")
    if not session_key or session_key not in promote_sessions:
        return False
    session = promote_sessions[session_key]
    if not session.get("awaiting_title"):
        return False
    text = update.message.text.strip()
    session["permissions"]["title"] = "" if text == "لا" else text[:16]
    session["awaiting_title"] = False
    context.user_data.pop("awaiting_title_session", None)
    p       = session["permissions"]
    keyboard= build_promote_keyboard(session_key, p)
    await update.message.reply_text(
        f"🛡 <b>رفع مشرف</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 المستخدم: <b>{session['target_name']}</b>\n\n"
        f"اختار الصلاحيات ثم اضغط رفعه مشرف:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return True

async def promote_callback(update, context):
    query = update.callback_query
    data  = query.data

    # ---- أزرار القائمة الرئيسية ----
    if data.startswith("cb_"):
        await handle_menu_callback(update, context)
        return

    await query.answer()

    # ---- toggle صلاحية ----
    if data.startswith("tgl."):
        _, session_key, perm = data.split(".", 2)
        if session_key not in promote_sessions:
            await query.edit_message_text("❌ انتهت الجلسة، جرب تاني.")
            return
        session = promote_sessions[session_key]
        session["permissions"][perm] = not session["permissions"].get(perm, False)
        p = session["permissions"]
        await query.edit_message_text(
            f"🛡 <b>رفع مشرف</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 المستخدم: <b>{session['target_name']}</b>\n\n"
            f"اختار الصلاحيات ثم اضغط رفعه مشرف:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(build_promote_keyboard(session_key, p))
        )

    # ---- طلب اللقب ----
    elif data.startswith("title."):
        _, session_key = data.split(".", 1)
        if session_key not in promote_sessions:
            await query.edit_message_text("❌ انتهت الجلسة.")
            return
        promote_sessions[session_key]["awaiting_title"] = True
        context.user_data["awaiting_title_session"] = session_key
        await query.edit_message_text(
            f"✏️ <b>اكتب اللقب للمشرف</b> <b>{promote_sessions[session_key]['target_name']}</b>\n\n"
            f"📌 أقصى 16 حرف\n"
            f"📌 ابعت <b>لا</b> عشان تشيل اللقب",
            parse_mode="HTML"
        )

    # ---- تأكيد الرفع ----
    elif data.startswith("confirm."):
        _, session_key = data.split(".", 1)
        if session_key not in promote_sessions:
            await query.edit_message_text("❌ انتهت الجلسة.")
            return
        session = promote_sessions.pop(session_key)
        p = session["permissions"]
        try:
            await context.bot.promote_chat_member(
                chat_id=session["chat_id"], user_id=session["target_id"],
                can_delete_messages=p.get("delete",False),
                can_restrict_members=p.get("ban",False),
                can_pin_messages=p.get("pin",False),
                can_change_info=p.get("info",False),
                can_promote_members=p.get("add_admins",False),
                can_invite_users=p.get("invite",False),
            )
            title = p.get("title","").strip()
            if title:
                try:
                    await context.bot.set_chat_administrator_custom_title(
                        chat_id=session["chat_id"],
                        user_id=session["target_id"],
                        custom_title=title
                    )
                except TelegramError:
                    pass
            perms_text = ""
            if p.get("delete"):   perms_text += "🗑 حذف الرسايل\n"
            if p.get("ban"):      perms_text += "🔨 حظر الأعضاء\n"
            if p.get("pin"):      perms_text += "📌 تثبيت الرسايل\n"
            if p.get("info"):     perms_text += "✏️ تغيير المعلومات\n"
            if p.get("add_admins"): perms_text += "👑 إضافة مشرفين\n"
            if p.get("invite"):   perms_text += "🔗 الدعوة بلينك\n"
            title_line = f"\n🏷 اللقب: <b>{title}</b>" if title else ""
            await query.edit_message_text(
                f"✅ <b>تم الرفع بنجاح!</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"👤 المشرف: <b>{session['target_name']}</b>{title_line}\n\n"
                f"📋 <b>الصلاحيات:</b>\n{perms_text or '— لا يوجد'}",
                parse_mode="HTML"
            )
        except TelegramError as e:
            await query.edit_message_text(f"❌ فشلت العملية:\n<code>{e}</code>", parse_mode="HTML")

    # ---- إلغاء ----
    elif data.startswith("cancel."):
        _, session_key = data.split(".", 1)
        promote_sessions.pop(session_key, None)
        await query.edit_message_text("❌ تم إلغاء العملية.")

# ══════════════════════════════════════
#      ⚖️ KICK / BAN / UNBAN / MUTE
# ══════════════════════════════════════

async def handle_kick(update, context, arg):
    uid = update.message.from_user.id
    cid = update.message.chat_id
    if not (is_privileged(cid, uid) or await is_admin(update, context, uid)):
        m = await update.message.reply_text("❌ أنت مش مشرف!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    admin_id = update.message.from_user.id
    chat_id  = update.message.chat_id
    try:
        await context.bot.ban_chat_member(chat_id, target_id)
        await context.bot.unban_chat_member(chat_id, target_id)
        count = tracker.add_action(admin_id, chat_id, "kick")
        await update.message.reply_text(
            f"👢 <b>تم الطرد</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 العضو: <b>{target_name}</b>\n"
            f"👮 المشرف: <b>{update.message.from_user.full_name}</b>\n"
            f"📊 عداد الطرد/الحظر: <b>{count}/{KICK_BAN_LIMIT}</b>",
            parse_mode="HTML"
        )
        if count >= KICK_BAN_LIMIT:
            await auto_demote(context, admin_id, chat_id)
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: <code>{e}</code>", parse_mode="HTML")

async def handle_ban(update, context, arg):
    uid = update.message.from_user.id
    cid = update.message.chat_id
    if not (is_privileged(cid, uid) or await is_admin(update, context, uid)):
        m = await update.message.reply_text("❌ أنت مش مشرف!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    admin_id = update.message.from_user.id
    chat_id  = update.message.chat_id
    try:
        await context.bot.ban_chat_member(chat_id, target_id)
        count = tracker.add_action(admin_id, chat_id, "ban")
        await update.message.reply_text(
            f"🔨 <b>تم الحظر</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 العضو: <b>{target_name}</b>\n"
            f"👮 المشرف: <b>{update.message.from_user.full_name}</b>\n"
            f"📊 عداد الطرد/الحظر: <b>{count}/{KICK_BAN_LIMIT}</b>",
            parse_mode="HTML"
        )
        if count >= KICK_BAN_LIMIT:
            await auto_demote(context, admin_id, chat_id)
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: <code>{e}</code>", parse_mode="HTML")

async def handle_unban(update, context, arg):
    uid = update.message.from_user.id
    cid = update.message.chat_id
    if not (is_privileged(cid, uid) or await is_admin(update, context, uid)):
        m = await update.message.reply_text("❌ أنت مش مشرف!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    try:
        await context.bot.unban_chat_member(update.message.chat_id, target_id)
        await update.message.reply_text(
            f"✅ <b>تم فك الحظر</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 العضو: <b>{target_name}</b>",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: <code>{e}</code>", parse_mode="HTML")

async def handle_mute(update, context, arg):
    uid = update.message.from_user.id
    cid = update.message.chat_id
    if not (is_privileged(cid, uid) or await is_admin(update, context, uid)):
        m = await update.message.reply_text("❌ أنت مش مشرف!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    try:
        await context.bot.restrict_chat_member(
            update.message.chat_id, target_id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text(
            f"🔇 <b>تم الكتم</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 العضو: <b>{target_name}</b>\n"
            f"👮 المشرف: <b>{update.message.from_user.full_name}</b>",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: <code>{e}</code>", parse_mode="HTML")

async def handle_unmute(update, context, arg):
    uid = update.message.from_user.id
    cid = update.message.chat_id
    if not (is_privileged(cid, uid) or await is_admin(update, context, uid)):
        m = await update.message.reply_text("❌ أنت مش مشرف!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    try:
        await context.bot.restrict_chat_member(
            update.message.chat_id, target_id,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True, can_invite_users=True,
            )
        )
        await update.message.reply_text(
            f"🔊 <b>تم فك الكتم</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 العضو: <b>{target_name}</b>",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: <code>{e}</code>", parse_mode="HTML")

# ══════════════════════════════════════
#      ⚠️ نظام التحذيرات
# ══════════════════════════════════════

MAX_WARNS = 3
warns_db  = {}   # {chat_id: {user_id: count}}

def get_warns(chat_id, user_id):
    return warns_db.get(str(chat_id), {}).get(str(user_id), 0)

def add_warn(chat_id, user_id):
    chat_id  = str(chat_id)
    user_id  = str(user_id)
    if chat_id not in warns_db:
        warns_db[chat_id] = {}
    warns_db[chat_id][user_id] = warns_db[chat_id].get(user_id, 0) + 1
    return warns_db[chat_id][user_id]

def reset_warns(chat_id, user_id):
    chat_id = str(chat_id)
    user_id = str(user_id)
    if chat_id in warns_db and user_id in warns_db[chat_id]:
        warns_db[chat_id][user_id] = 0

async def handle_warn(update, context, arg):
    uid = update.message.from_user.id
    cid = update.message.chat_id
    if not (is_privileged(cid, uid) or await is_admin(update, context, uid)):
        m = await update.message.reply_text("❌ أنت مش مشرف!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    chat_id = update.message.chat_id
    count   = add_warn(chat_id, target_id)
    warn_bar = "🟥" * count + "⬜️" * (MAX_WARNS - count)
    if count >= MAX_WARNS:
        try:
            await context.bot.ban_chat_member(chat_id, target_id)
            reset_warns(chat_id, target_id)
            await update.message.reply_text(
                f"🚫 <b>تم الحظر بسبب التحذيرات</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"👤 العضو: <b>{target_name}</b>\n"
                f"⚠️ وصل للحد الأقصى ({MAX_WARNS} تحذيرات)",
                parse_mode="HTML"
            )
        except TelegramError as e:
            await update.message.reply_text(f"❌ فشل الحظر: <code>{e}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"⚠️ <b>تحذير!</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 العضو: <b>{target_name}</b>\n"
            f"📊 التحذيرات: {warn_bar} <b>{count}/{MAX_WARNS}</b>\n\n"
            f"📌 عند {MAX_WARNS} تحذيرات سيتم الحظر تلقائياً",
            parse_mode="HTML"
        )

async def handle_warns(update, context, arg):
    if not await is_admin(update, context, update.message.from_user.id):
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    count    = get_warns(update.message.chat_id, target_id)
    warn_bar = "🟥" * count + "⬜️" * (MAX_WARNS - count)
    await update.message.reply_text(
        f"📊 <b>تحذيرات العضو</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 العضو: <b>{target_name}</b>\n"
        f"⚠️ التحذيرات: {warn_bar} <b>{count}/{MAX_WARNS}</b>",
        parse_mode="HTML"
    )

async def handle_resetwarns(update, context, arg):
    if not await is_admin(update, context, update.message.from_user.id):
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    reset_warns(update.message.chat_id, target_id)
    await update.message.reply_text(
        f"✅ <b>تم مسح التحذيرات</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 العضو: <b>{target_name}</b>",
        parse_mode="HTML"
    )

# ══════════════════════════════════════
#      📌 تثبيت الرسائل
# ══════════════════════════════════════

async def handle_pin(update, context, arg):
    uid = update.message.from_user.id
    cid = update.message.chat_id
    if not (is_privileged(cid, uid) or await is_admin(update, context, uid)):
        m = await update.message.reply_text("❌ أنت مش مشرف!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ رد على الرسالة اللي عايز تثبتها.")
        return
    try:
        await context.bot.pin_chat_message(
            update.message.chat_id,
            update.message.reply_to_message.message_id,
            disable_notification=False
        )
        await update.message.reply_text(
            f"📌 <b>تم التثبيت</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👮 بواسطة: <b>{update.message.from_user.full_name}</b>",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: <code>{e}</code>", parse_mode="HTML")

async def handle_unpin(update, context, arg):
    uid = update.message.from_user.id
    cid = update.message.chat_id
    if not (is_privileged(cid, uid) or await is_admin(update, context, uid)):
        m = await update.message.reply_text("❌ أنت مش مشرف!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    try:
        await context.bot.unpin_chat_message(update.message.chat_id)
        await update.message.reply_text("✅ <b>تم إلغاء التثبيت</b>", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: <code>{e}</code>", parse_mode="HTML")

# ══════════════════════════════════════
#      🔄 AUTO DEMOTE
# ══════════════════════════════════════

async def auto_demote(context, admin_id, chat_id):
    try:
        member     = await context.bot.get_chat_member(chat_id, admin_id)
        admin_name = member.user.full_name
        await context.bot.promote_chat_member(
            chat_id=chat_id, user_id=admin_id,
            can_delete_messages=False, can_restrict_members=False,
            can_pin_messages=False, can_change_info=False,
            can_promote_members=False, can_invite_users=False,
        )
        tracker.reset(admin_id, chat_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ <b>نزول تلقائي للمشرف</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"👤 المشرف: <b>{admin_name}</b>\n"
                f"📋 السبب: تجاوز حد الطرد/الحظر ({KICK_BAN_LIMIT} مرة)"
            ),
            parse_mode="HTML"
        )
    except TelegramError as e:
        logger.error(f"Auto demote failed: {e}")

# ══════════════════════════════════════
#      ℹ️ معلومات
# ══════════════════════════════════════

async def handle_id(update, context, arg):
    msg     = update.message
    chat_id = msg.chat_id
    text    = f"💭 <b>معلومات الجروب</b>\n━━━━━━━━━━━━━━━━\n🆔 <code>{chat_id}</code>\n"
    if msg.reply_to_message:
        ru   = msg.reply_to_message.from_user
        text = (
            f"👤 <b>معلومات المستخدم</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🔤 الاسم: <b>{ru.full_name}</b>\n"
            f"🆔 ID: <code>{ru.id}</code>\n"
        )
        if ru.username:
            text += f"🔗 اليوزر: @{ru.username}\n"
        text += f"\n💭 <b>الجروب:</b> <code>{chat_id}</code>"
    await msg.reply_text(text, parse_mode="HTML")

async def handle_info(update, context, arg):
    msg = update.message
    if msg.reply_to_message:
        u = msg.reply_to_message.from_user
    else:
        u = msg.from_user
    try:
        member = await context.bot.get_chat_member(msg.chat_id, u.id)
        status_map = {
            "administrator": "👮 مشرف",
            "creator":       "👑 مالك",
            "member":        "👤 عضو",
            "restricted":    "🔇 مقيّد",
            "left":          "🚪 غادر",
            "kicked":        "🔨 محظور",
        }
        status = status_map.get(member.status, member.status)
    except TelegramError:
        status = "❓ غير معروف"
    text = (
        f"👤 <b>معلومات المستخدم</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🔤 الاسم: <b>{u.full_name}</b>\n"
        f"🆔 ID: <code>{u.id}</code>\n"
    )
    if u.username:
        text += f"🔗 اليوزر: @{u.username}\n"
    text += (
        f"📋 الحالة: {status}\n"
        f"🎖 الرتبة: {rank_label(msg.chat_id, u.id)}\n"
        f"⚠️ التحذيرات: <b>{get_warns(msg.chat_id, u.id)}/{MAX_WARNS}</b>\n"
        f"🤖 بوت: {'نعم' if u.is_bot else 'لا'}"
    )
    await msg.reply_text(text, parse_mode="HTML")

async def handle_ping(update, context):
    start = time()
    m     = await update.message.reply_text("🏓 Pinging...")
    delta = (time() - start) * 1000
    await m.edit_text(
        f"🏓 <b>Pong!</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚡️ السرعة: <code>{delta:.2f} ms</code>",
        parse_mode="HTML"
    )

async def handle_uptime(update, context):
    uptime_sec = (datetime.utcnow() - START_TIME).total_seconds()
    await update.message.reply_text(
        f"🤖 <b>وقت التشغيل</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⏱ شغال منذ: <code>{human_time(int(uptime_sec))}</code>",
        parse_mode="HTML"
    )

async def handle_alive(update, context):
    uptime_sec = (datetime.utcnow() - START_TIME).total_seconds()
    bot_info   = await context.bot.get_me()
    total_sudos = sum(len(v) for v in sudo_db.values())
    await update.message.reply_text(
        f"✅ <b>{BOT_NAME} شغال!</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🤖 البوت: @{bot_info.username}\n"
        f"⏱ وقت التشغيل: <code>{human_time(int(uptime_sec))}</code>\n"
        f"👑 المطور: <code>{DEVELOPER_ID}</code>\n"
        f"🔰 المساعدين: <b>{total_sudos}</b>\n"
        f"⚠️ حد الطرد: <b>{KICK_BAN_LIMIT}</b> مرة",
        parse_mode="HTML"
    )

async def handle_stats(update, context):
    if not await is_admin(update, context, update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    stats   = tracker.get_stats(chat_id)
    if not stats:
        await update.message.reply_text("📊 مفيش إحصائيات لحد دلوقتي.")
        return
    text = "📊 <b>إحصائيات الطرد/الحظر</b>\n━━━━━━━━━━━━━━━━\n\n"
    for admin_id, count in stats.items():
        try:
            member = await context.bot.get_chat_member(chat_id, int(admin_id))
            name   = member.user.full_name
        except TelegramError:
            name = f"ID: {admin_id}"
        bar   = "🟥" * min(count, 10) + "⬜️" * max(0, 10 - count)
        text += f"👤 <b>{name}</b>\n{bar} {count}/{KICK_BAN_LIMIT}\n\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def handle_reload(update, context):
    if not await is_admin(update, context, update.message.from_user.id):
        return
    await update.message.reply_text(
        "✅ <b>تم تحديث قائمة المشرفين</b>",
        parse_mode="HTML"
    )

# ══════════════════════════════════════
#      📡 BROADCAST
# ══════════════════════════════════════

async def handle_broadcast(update, context, arg):
    if update.message.from_user.id != DEVELOPER_ID:
        m = await update.message.reply_text("❌ هذا الأمر للمطور فقط!")
        asyncio.create_task(delete_after(context, update.message.chat_id, m.message_id, 5))
        return
    msg          = update.message
    forward_msg  = msg.reply_to_message if msg.reply_to_message else None
    text_to_send = arg if arg and not forward_msg else None
    if not forward_msg and not text_to_send:
        await msg.reply_text(
            "❌ ارد على رسالة أو اكتب النص بعد الأمر\n"
            "مثال: <code>اذاعه رسالتك هنا</code>",
            parse_mode="HTML"
        )
        return
    sent       = 0
    failed     = 0
    status_msg = await msg.reply_text("📡 جاري الإذاعة...")
    chat_ids   = list(tracker.data.keys())
    if not chat_ids:
        await status_msg.edit_text("⚠️ مفيش جروبات مسجلة للإذاعة.")
        return
    for chat_id_str in chat_ids:
        try:
            cid = int(chat_id_str)
            if forward_msg:
                await context.bot.forward_message(cid, msg.chat_id, forward_msg.message_id)
            else:
                await context.bot.send_message(cid, text_to_send)
            sent += 1
            await asyncio.sleep(0.3)
        except Exception:
            failed += 1
    await status_msg.edit_text(
        f"📡 <b>تمت الإذاعة</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ أُرسلت: <b>{sent}</b> جروب\n"
        f"❌ فشلت: <b>{failed}</b> جروب",
        parse_mode="HTML"
    )

# ══════════════════════════════════════
#      📋 HELP
# ══════════════════════════════════════

async def handle_help(update, context):
    name = update.message.from_user.first_name
    text = MAIN_TEXT(name)
    kb   = main_menu_keyboard()
    if BOT_PHOTO:
        try:
            await update.message.reply_photo(photo=BOT_PHOTO, caption=text, parse_mode="HTML", reply_markup=kb)
            return
        except TelegramError:
            pass
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

# ══════════════════════════════════════
#      👋 رسايل الترحيب والوداع
# ══════════════════════════════════════

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.new_chat_members:
        return
    bot_info = await context.bot.get_me()
    for member in msg.new_chat_members:
        if member.is_bot and member.id == bot_info.id:
            # البوت انضم — سجّل الجروب
            tracker.data.setdefault(str(msg.chat_id), {})
            tracker._save()
            text = (
                f"👋 <b>أهلاً بيكم!</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"أنا <b>{BOT_NAME}</b> بوت إدارة متكامل 🤖\n\n"
                f"⚙️ عشان أشتغل صح:\n"
                f"• ارفعني مشرف بصلاحيات كاملة\n\n"
                f"اكتب <b>أوامر</b> عشان تشوف كل اللي أقدر أعمله 🚀"
            )
            keyboard = []
            if GROUP_SUPPORT:
                keyboard.append([InlineKeyboardButton("💬 جروب الدعم", url=f"https://t.me/{GROUP_SUPPORT}")])
            if UPDATES_CHANNEL:
                keyboard.append([InlineKeyboardButton("📣 قناة التحديثات", url=f"https://t.me/{UPDATES_CHANNEL}")])
            markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            try:
                if WELCOME_PHOTO:
                    await context.bot.send_photo(msg.chat_id, photo=WELCOME_PHOTO, caption=text, parse_mode="HTML", reply_markup=markup)
                else:
                    await context.bot.send_message(msg.chat_id, text, parse_mode="HTML", reply_markup=markup)
            except TelegramError:
                pass
        elif not member.is_bot:
            # عضو جديد
            mention    = f'<a href="tg://user?id={member.id}">{member.full_name}</a>'
            try:
                chat       = await context.bot.get_chat(msg.chat_id)
                chat_title = chat.title
            except TelegramError:
                chat_title = "الجروب"
            keyboard = []
            if GROUP_SUPPORT:
                keyboard.append([InlineKeyboardButton("💬 جروب الدعم", url=f"https://t.me/{GROUP_SUPPORT}")])
            markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            welcome_text = (
                f"🎉 <b>عضو جديد!</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"👋 أهلاً وسهلاً {mention}!\n"
                f"نورت <b>{chat_title}</b> 🌟\n\n"
                f"اتمنى تبقى معنا دايماً ❤️"
            )
            try:
                sent = await context.bot.send_message(msg.chat_id, welcome_text, parse_mode="HTML", reply_markup=markup)
                asyncio.create_task(delete_after(context, msg.chat_id, sent.message_id, delay=300))
            except TelegramError:
                pass

async def farewell_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.left_chat_member:
        return
    member = msg.left_chat_member
    if member.is_bot:
        return
    mention = f'<a href="tg://user?id={member.id}">{member.full_name}</a>'
    try:
        sent = await context.bot.send_message(
            msg.chat_id,
            f"👋 <b>وداعاً!</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"😢 {mention} غادر الجروب\n"
            f"نتمنى نشوفك تاني 💙",
            parse_mode="HTML"
        )
        asyncio.create_task(delete_after(context, msg.chat_id, sent.message_id, delay=120))
    except TelegramError:
        pass

# ══════════════════════════════════════
#      🚫 فلتر الكلمات
# ══════════════════════════════════════

def contains_bad_word(text: str) -> bool:
    normalized = re.sub(r'\s+', ' ', text.lower()).strip()
    for word in BAD_WORDS:
        if re.search(re.escape(word.lower()), normalized):
            return True
    return False

# ══════════════════════════════════════
#      📨 MAIN MESSAGE HANDLER
# ══════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text    = update.message.text.strip()
    user_id = update.message.from_user.id

    # لقب المشرف
    if user_id == DEVELOPER_ID:
        handled = await handle_title_input(update, context)
        if handled:
            return

    # الأوامر
    action, arg = parse_arabic_command(text)
    if action:
        actions = {
            "addsudo":    lambda: handle_addsudo(update, context, arg),
            "removesudo": lambda: handle_removesudo(update, context, arg),
            "sudolist":   lambda: handle_sudolist(update, context),
            "promote":    lambda: handle_promote(update, context, arg),
            "demote":     lambda: handle_demote(update, context, arg),
            "kick":       lambda: handle_kick(update, context, arg),
            "ban":        lambda: handle_ban(update, context, arg),
            "unban":      lambda: handle_unban(update, context, arg),
            "mute":       lambda: handle_mute(update, context, arg),
            "unmute":     lambda: handle_unmute(update, context, arg),
            "warn":       lambda: handle_warn(update, context, arg),
            "warns":      lambda: handle_warns(update, context, arg),
            "resetwarns": lambda: handle_resetwarns(update, context, arg),
            "pin":        lambda: handle_pin(update, context, arg),
            "unpin":      lambda: handle_unpin(update, context, arg),
            "id":         lambda: handle_id(update, context, arg),
            "info":       lambda: handle_info(update, context, arg),
            "ping":       lambda: handle_ping(update, context),
            "uptime":     lambda: handle_uptime(update, context),
            "alive":      lambda: handle_alive(update, context),
            "stats":      lambda: handle_stats(update, context),
            "reload":     lambda: handle_reload(update, context),
            "broadcast":  lambda: handle_broadcast(update, context, arg),
            "help":       lambda: handle_help(update, context),
        }
        if action in actions:
            await actions[action]()
        return

    # فلتر الكلمات للأعضاء فقط
    if await is_admin(update, context, user_id):
        return

    if contains_bad_word(text):
        try:
            await update.message.delete()
            warn_msg = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=(
                    f"🚫 {update.message.from_user.mention_html()}\n"
                    f"رسالتك اتحذفت بسبب محتوى مخالف ⚠️"
                ),
                parse_mode="HTML"
            )
            asyncio.create_task(delete_after(context, update.message.chat_id, warn_msg.message_id, delay=5))
        except TelegramError as e:
            logger.error(f"Filter error: {e}")

# ══════════════════════════════════════
#      🚀 MAIN
# ══════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, farewell_member))
    app.add_handler(CallbackQueryHandler(promote_callback))

    logger.info("✅ البوت شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
