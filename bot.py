import logging
import re
import json
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from bad_words import BAD_WORDS
from kick_tracker import KickTracker

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
KICK_BAN_LIMIT = 20
tracker = KickTracker()

# المطور الوحيد اللي يقدر يرفع وينزل مشرفين
DEVELOPER_ID = 1923931101

# ==============================
# الأوامر العربية - عدّلها براحتك
# ==============================
COMMANDS = {
    "رفع":       "promote",
    "ترقية":     "promote",
    "نزول":      "demote",
    "عزل":       "demote",
    "طرد":       "kick",
    "حظر":       "ban",
    "احصائيات": "stats",
    "إحصائيات": "stats",
    "مساعدة":   "help",
    "هلب":       "help",
    "اوامر":     "help",
    "أوامر":     "help",
}

# ==============================
# HELPERS
# ==============================

def parse_arabic_command(text: str):
    text = text.strip()
    parts = text.split(None, 1)
    if not parts:
        return None, None
    cmd_word = parts[0].strip()
    arg = parts[1].strip() if len(parts) > 1 else None
    action = COMMANDS.get(cmd_word)
    return action, arg

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

promote_sessions = {}

# ==============================
# PROMOTE
# ==============================

async def handle_promote(update, context, arg):
    if update.message.from_user.id != DEVELOPER_ID:
        await update.message.reply_text("❌ أمر رفع المشرفين متاح للمطور فقط!")
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text(
            "❌ مش قادر أعرف المستخدم.\n"
            "جرب: رد على رسالته، أو <b>رفع @يوزر</b> أو <b>رفع ID</b>",
            parse_mode="HTML"
        )
        return
    chat_id = update.message.chat_id
    session_key = f"{chat_id}_{update.message.from_user.id}"
    promote_sessions[session_key] = {
        "target_id": target_id,
        "target_name": target_name,
        "chat_id": chat_id,
        "permissions": {"delete": True, "ban": True, "pin": False, "info": False, "add_admins": False, "invite": True}
    }
    p = promote_sessions[session_key]["permissions"]

    def btn(label, key):
        icon = "✅" if p.get(key, False) else "❌"
        return InlineKeyboardButton(f"{icon} {label}", callback_data=f"toggle_{session_key}_{key}")

    keyboard = [
        [btn("حذف الرسايل", "delete"), btn("حظر الأعضاء", "ban")],
        [btn("تثبيت الرسايل", "pin"), btn("تغيير المعلومات", "info")],
        [btn("إضافة مشرفين", "add_admins"), btn("الدعوة بلينك", "invite")],
        [
            InlineKeyboardButton("🚀 رفعه مشرف", callback_data=f"confirm_{session_key}"),
            InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{session_key}"),
        ]
    ]
    await update.message.reply_text(
        f"🛡 رفع مشرف: <b>{target_name}</b>\n\nاختار صلاحياته:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def promote_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("toggle_"):
        rest = data[len("toggle_"):]
        last_underscore = rest.rfind("_")
        session_key = rest[:last_underscore]
        perm = rest[last_underscore + 1:]
        if session_key not in promote_sessions:
            await query.edit_message_text("❌ انتهت الجلسة، جرب تاني.")
            return
        session = promote_sessions[session_key]
        session["permissions"][perm] = not session["permissions"].get(perm, False)
        p = session["permissions"]

        def btn(label, key):
            icon = "✅" if p.get(key, False) else "❌"
            return InlineKeyboardButton(f"{icon} {label}", callback_data=f"toggle_{session_key}_{key}")

        keyboard = [
            [btn("حذف الرسايل", "delete"), btn("حظر الأعضاء", "ban")],
            [btn("تثبيت الرسايل", "pin"), btn("تغيير المعلومات", "info")],
            [btn("إضافة مشرفين", "add_admins"), btn("الدعوة بلينك", "invite")],
            [
                InlineKeyboardButton("🚀 رفعه مشرف", callback_data=f"confirm_{session_key}"),
                InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{session_key}"),
            ]
        ]
        await query.edit_message_text(
            f"🛡 رفع مشرف: <b>{session['target_name']}</b>\n\nاختار صلاحياته:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("confirm_"):
        session_key = data[len("confirm_"):]
        if session_key not in promote_sessions:
            await query.edit_message_text("❌ انتهت الجلسة.")
            return
        session = promote_sessions.pop(session_key)
        p = session["permissions"]
        try:
            await context.bot.promote_chat_member(
                chat_id=session["chat_id"],
                user_id=session["target_id"],
                can_delete_messages=p.get("delete", False),
                can_restrict_members=p.get("ban", False),
                can_pin_messages=p.get("pin", False),
                can_change_info=p.get("info", False),
                can_promote_members=p.get("add_admins", False),
                can_invite_users=p.get("invite", False),
            )
            await query.edit_message_text(
                f"✅ تم رفع <b>{session['target_name']}</b> مشرف بنجاح! 🎉",
                parse_mode="HTML"
            )
        except TelegramError as e:
            await query.edit_message_text(f"❌ فشلت العملية: {e}")

    elif data.startswith("cancel_"):
        session_key = data[len("cancel_"):]
        promote_sessions.pop(session_key, None)
        await query.edit_message_text("❌ تم إلغاء العملية.")

# ==============================
# DEMOTE
# ==============================

async def handle_demote(update, context, arg):
    if update.message.from_user.id != DEVELOPER_ID:
        await update.message.reply_text("❌ أمر نزول المشرفين متاح للمطور فقط!")
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    try:
        await context.bot.promote_chat_member(
            chat_id=update.message.chat_id,
            user_id=target_id,
            can_delete_messages=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_change_info=False,
            can_promote_members=False,
            can_invite_users=False,
        )
        await update.message.reply_text(f"✅ تم نزول <b>{target_name}</b> من الإشراف.", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: {e}")

# ==============================
# KICK
# ==============================

async def handle_kick(update, context, arg):
    if not await is_admin(update, context, update.message.from_user.id):
        await update.message.reply_text("❌ أنت مش مشرف!")
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    admin_id = update.message.from_user.id
    chat_id = update.message.chat_id
    try:
        await context.bot.ban_chat_member(chat_id, target_id)
        await context.bot.unban_chat_member(chat_id, target_id)
        count = tracker.add_action(admin_id, chat_id, "kick")
        await update.message.reply_text(
            f"👢 تم طرد <b>{target_name}</b>\n📊 طرد/حظر المشرف ده: {count}/{KICK_BAN_LIMIT}",
            parse_mode="HTML"
        )
        if count >= KICK_BAN_LIMIT:
            await auto_demote(update, context, admin_id, chat_id)
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: {e}")

# ==============================
# BAN
# ==============================

async def handle_ban(update, context, arg):
    if not await is_admin(update, context, update.message.from_user.id):
        await update.message.reply_text("❌ أنت مش مشرف!")
        return
    target_id, target_name = await resolve_target(update, context, arg)
    if not target_id:
        await update.message.reply_text("❌ مش قادر أعرف المستخدم ده.")
        return
    admin_id = update.message.from_user.id
    chat_id = update.message.chat_id
    try:
        await context.bot.ban_chat_member(chat_id, target_id)
        count = tracker.add_action(admin_id, chat_id, "ban")
        await update.message.reply_text(
            f"🔨 تم حظر <b>{target_name}</b>\n📊 طرد/حظر المشرف ده: {count}/{KICK_BAN_LIMIT}",
            parse_mode="HTML"
        )
        if count >= KICK_BAN_LIMIT:
            await auto_demote(update, context, admin_id, chat_id)
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشلت العملية: {e}")

# ==============================
# AUTO DEMOTE
# ==============================

async def auto_demote(update, context, admin_id, chat_id):
    try:
        member = await context.bot.get_chat_member(chat_id, admin_id)
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
            text=f"⚠️ تم نزول المشرف <b>{admin_name}</b> تلقائياً\nالسبب: تجاوز حد الطرد/الحظر ({KICK_BAN_LIMIT} مرة).",
            parse_mode="HTML"
        )
    except TelegramError as e:
        logger.error(f"Auto demote failed: {e}")

# ==============================
# STATS
# ==============================

async def handle_stats(update, context):
    if not await is_admin(update, context, update.message.from_user.id):
        await update.message.reply_text("❌ أنت مش مشرف!")
        return
    chat_id = update.message.chat_id
    stats = tracker.get_stats(chat_id)
    if not stats:
        await update.message.reply_text("📊 مفيش إحصائيات لحد دلوقتي.")
        return
    text = "📊 <b>إحصائيات الطرد/الحظر للمشرفين:</b>\n\n"
    for admin_id, count in stats.items():
        try:
            member = await context.bot.get_chat_member(chat_id, int(admin_id))
            name = member.user.full_name
        except TelegramError:
            name = f"ID: {admin_id}"
        text += f"👤 {name}: {count}/{KICK_BAN_LIMIT}\n"
    await update.message.reply_text(text, parse_mode="HTML")

# ==============================
# HELP
# ==============================

async def handle_help(update, context):
    await update.message.reply_text(
        "🤖 <b>أوامر البوت</b>\n\n"
        "اكتب الأمر في الجروب مباشرةً:\n\n"
        "🔹 <b>رفع</b> أو <b>ترقية</b> — رفع مشرف\n"
        "🔹 <b>نزول</b> أو <b>عزل</b> — نزول مشرف\n"
        "🔹 <b>طرد</b> — طرد عضو\n"
        "🔹 <b>حظر</b> — حظر عضو\n"
        "🔹 <b>احصائيات</b> — إحصائيات الطرد\n\n"
        "📌 <b>طرق الاستخدام:</b>\n"
        "• رد على رسالة الشخص واكتب الأمر\n"
        "• اكتب الأمر + @يوزر — مثال: <code>طرد @ahmed</code>\n"
        "• اكتب الأمر + ID — مثال: <code>حظر 123456789</code>\n\n"
        "🚫 الفلتر شغال تلقائياً على الكلمات المحظورة.",
        parse_mode="HTML"
    )

# ==============================
# BAD WORDS FILTER
# ==============================

def contains_bad_word(text: str) -> bool:
    normalized = re.sub(r'\s+', ' ', text.lower()).strip()
    for word in BAD_WORDS:
        if re.search(re.escape(word.lower()), normalized):
            return True
    return False

# ==============================
# MAIN MESSAGE HANDLER
# ==============================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.message.from_user.id

    # تحقق من الأوامر العربية أولاً
    action, arg = parse_arabic_command(text)

    if action:
        if action == "promote":
            await handle_promote(update, context, arg)
        elif action == "demote":
            await handle_demote(update, context, arg)
        elif action == "kick":
            await handle_kick(update, context, arg)
        elif action == "ban":
            await handle_ban(update, context, arg)
        elif action == "stats":
            await handle_stats(update, context)
        elif action == "help":
            await handle_help(update, context)
        return

    # فلتر الكلمات للأعضاء العاديين فقط
    if await is_admin(update, context, user_id):
        return

    if contains_bad_word(text):
        try:
            await update.message.delete()
            warn_msg = await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=f"⚠️ {update.message.from_user.mention_html()} رسالتك اتحذفت بسبب محتوى مخالف.",
                parse_mode="HTML"
            )
            context.job_queue.run_once(
                lambda ctx: ctx.bot.delete_message(
                    chat_id=update.message.chat_id,
                    message_id=warn_msg.message_id
                ),
                when=5
            )
        except TelegramError as e:
            logger.error(f"Filter error: {e}")

# ==============================
# MAIN
# ==============================

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(promote_callback))
    logger.info("✅ البوت شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
