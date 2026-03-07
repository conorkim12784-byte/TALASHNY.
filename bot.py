import os, re, json, uuid, logging, asyncio
from datetime import datetime
from time import time

from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from bad_words import BAD_WORDS
from kick_tracker import KickTracker

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#          🔰 نظام السودو
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUDO_FILE = "sudo_db.json"

def _load_sudo():
    try:
        with open(SUDO_FILE) as f: return json.load(f)
    except: return {}

def _save_sudo():
    with open(SUDO_FILE, "w") as f: json.dump(sudo_db, f, indent=2)

sudo_db  = _load_sudo()
warns_db = {}

def is_dev(uid):              return uid == DEVELOPER_ID
def is_sudo(cid, uid):        return uid in sudo_db.get(str(cid), [])
def is_privileged(cid, uid):  return is_dev(uid) or is_sudo(cid, uid)

def rank_label(cid, uid):
    if is_dev(uid):           return "👑 مطور السورس"
    if is_sudo(cid, uid):     return "🔰 مساعد مطور"
    return "🛡️ مشرف"

def get_warns(cid, uid):  return warns_db.get(str(cid), {}).get(str(uid), 0)
def add_warn(cid, uid):
    warns_db.setdefault(str(cid), {}); k=str(uid)
    warns_db[str(cid)][k] = warns_db[str(cid)].get(k, 0) + 1
    return warns_db[str(cid)][k]
def reset_warn(cid, uid): warns_db.get(str(cid), {}).pop(str(uid), None)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           📋 الأوامر
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# كل أمر: "نص": ("action", "level")
# level: "dev" | "priv" | "admin" | "all"
CMDS = {
    # سودو — مطور فقط
    "اضف مساعد":    ("addsudo",    "dev"),
    "شيل مساعد":    ("removesudo", "dev"),
    "المساعدين":    ("sudolist",   "dev"),
    # مشرفين — مطور فقط
    "رفع":          ("promote",    "dev"),
    "ترقية":        ("promote",    "dev"),
    "نزول":         ("demote",     "dev"),
    "عزل":          ("demote",     "dev"),
    # عقوبات — مشرف/سودو/مطور
    "طرد":          ("kick",       "admin"),
    "حظر":          ("ban",        "admin"),
    "فك حظر":       ("unban",      "admin"),
    "كتم":          ("mute",       "admin"),
    "فك كتم":       ("unmute",     "admin"),
    # تحذيرات
    "تحذير":        ("warn",       "admin"),
    "انذار":        ("warn",       "admin"),
    "تحذيرات":      ("warns",      "admin"),
    "مسح تحذيرات": ("resetwarns", "admin"),
    # تثبيت
    "تثبيت":        ("pin",        "admin"),
    "الغاء تثبيت": ("unpin",      "admin"),
    # معلومات — للجميع
    "ايدي":         ("id",         "all"),
    "آيدي":         ("id",         "all"),
    "id":           ("id",         "all"),
    "معلومات":      ("info",       "all"),
    "احصائيات":     ("stats",      "admin"),
    "إحصائيات":     ("stats",      "admin"),
    "تحديث":        ("reload",     "admin"),
    "بينج":         ("ping",       "all"),
    "ping":         ("ping",       "all"),
    "uptime":       ("uptime",     "all"),
    "alive":        ("alive",      "all"),
    # إذاعة — مطور فقط
    "اذاعه":        ("broadcast",  "dev"),
    "اذاعة":        ("broadcast",  "dev"),
    # مساعدة
    "مساعدة":       ("help",       "all"),
    "هلب":          ("help",       "all"),
    "اوامر":        ("help",       "all"),
    "أوامر":        ("help",       "all"),
}

def parse_cmd(text):
    text = text.strip()
    for cmd in sorted(CMDS, key=len, reverse=True):
        if text == cmd or text.startswith(cmd + " "):
            action, level = CMDS[cmd]
            arg = text[len(cmd):].strip() or None
            return action, level, arg
    return None, None, None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           🔧 دوال مساعدة
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_admin(context, cid, uid):
    try:
        m = await context.bot.get_chat_member(cid, uid)
        return m.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except TelegramError: return False

async def resolve(update, context, arg=None):
    msg = update.message
    if msg.reply_to_message:
        u = msg.reply_to_message.from_user
        return u.id, u.full_name
    if not arg: return None, None
    t = arg.split()[0]
    if t.lstrip("-").isdigit():
        uid = int(t)
        try:
            m = await context.bot.get_chat_member(msg.chat_id, uid)
            return uid, m.user.full_name
        except TelegramError: return uid, str(uid)
    uname = t.lstrip("@")
    try:
        m = await context.bot.get_chat_member(msg.chat_id, f"@{uname}")
        return m.user.id, m.user.full_name
    except TelegramError: return None, None

async def del_later(context, cid, mid, delay=5):
    await asyncio.sleep(delay)
    try: await context.bot.delete_message(cid, mid)
    except: pass

def fmt_time(s):
    units = [("أسبوع",604800),("يوم",86400),("ساعة",3600),("دقيقة",60),("ثانية",1)]
    parts = []
    for n, d in units:
        v, s = divmod(int(s), d)
        if v: parts.append(f"{v} {n}")
    return "، ".join(parts) or "0 ثانية"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#      🎛️ الأزرار — بنفس أسلوب السورس
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def kb_start():
    rows = []
    r1 = [InlineKeyboardButton("📋 الأوامر", callback_data="cbcmds")]
    rows.append(r1)
    r2 = []
    if GROUP_SUPPORT:   r2.append(InlineKeyboardButton("👥 جروب الدعم", url=f"https://t.me/{GROUP_SUPPORT}"))
    if UPDATES_CHANNEL: r2.append(InlineKeyboardButton("📣 القناة", url=f"https://t.me/{UPDATES_CHANNEL}"))
    if r2: rows.append(r2)
    if BOT_USERNAME:
        rows.append([InlineKeyboardButton("➕ أضف البوت لجروبك", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")])
    return InlineKeyboardMarkup(rows)

def kb_cmds():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛡️ أوامر الإدارة",   callback_data="cbadmin"),
            InlineKeyboardButton("⚖️ أوامر العقوبات",  callback_data="cbpunish"),
        ],
        [
            InlineKeyboardButton("ℹ️ أوامر المعلومات", callback_data="cbinfo"),
            InlineKeyboardButton("👑 أوامر المطور",     callback_data="cbdev"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="cbstart")],
    ])

def kb_back(to="cbcmds"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=to)]])

# نصوص الصفحات
def txt_start(name):
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 أهلاً <b>{name}</b>!\n"
        f"أنا <b>{BOT_NAME}</b> — بوت إدارة متكامل 🤖\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔹 رفع ونزول المشرفين مع تحديد الصلاحيات\n"
        f"🔹 نظام رتب: مطور ← مساعد ← مشرف\n"
        f"🔹 طرد وحظر وكتم وتحذيرات تلقائية\n"
        f"🔹 فلتر الكلمات المحظورة\n"
        f"🔹 رسايل ترحيب ووداع منسقة\n\n"
        f"👇 اضغط <b>الأوامر</b> عشان تشوف كل حاجة"
    )

TXT_ADMIN = (
    "🛡️ <b>أوامر الإدارة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔹 <b>رفع</b> — رفع مشرف مع اختيار صلاحياته\n"
    "🔹 <b>نزول</b> — نزول مشرف\n"
    "🔹 <b>تثبيت</b> — تثبيت رسالة (رد عليها)\n"
    "🔹 <b>الغاء تثبيت</b> — إلغاء التثبيت\n"
    "🔹 <b>تحديث</b> — تحديث قائمة المشرفين\n\n"
    "🎖 <b>الرتب:</b>\n"
    "👑 مطور السورس — كل الجروبات\n"
    "🔰 مساعد مطور — جروبه بس\n"
    "🛡️ مشرف — أوامر عادية\n\n"
    "📌 <i>رفع ونزول للمطور فقط</i>"
)

TXT_PUNISH = (
    "⚖️ <b>أوامر العقوبات</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔹 <b>طرد</b> — طرد عضو\n"
    "🔹 <b>حظر</b> — حظر نهائي\n"
    "🔹 <b>فك حظر</b> — فك الحظر\n"
    "🔹 <b>كتم</b> — منع من الكتابة\n"
    "🔹 <b>فك كتم</b> — رفع الكتم\n"
    "🔹 <b>تحذير</b> — تحذير (بعد 3 يتحظر تلقائياً)\n"
    "🔹 <b>تحذيرات</b> — عرض تحذيرات عضو\n"
    "🔹 <b>مسح تحذيرات</b> — مسح التحذيرات\n\n"
    "📌 <i>للمشرفين والمساعدين</i>"
)

TXT_INFO = (
    "ℹ️ <b>أوامر المعلومات</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔹 <b>ايدي</b> — ID المستخدم أو الجروب\n"
    "🔹 <b>معلومات</b> — معلومات مفصلة عن عضو\n"
    "🔹 <b>احصائيات</b> — إحصائيات الطرد للمشرفين\n"
    "🔹 <b>بينج</b> — سرعة الاستجابة\n"
    "🔹 <b>uptime</b> — وقت التشغيل\n"
    "🔹 <b>alive</b> — حالة البوت\n\n"
    "📌 <i>متاحة للجميع</i>"
)

TXT_DEV = (
    "👑 <b>أوامر المطور</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔹 <b>رفع / نزول</b> — إدارة المشرفين\n"
    "🔹 <b>اضف مساعد</b> — إضافة مساعد في الجروب\n"
    "🔹 <b>شيل مساعد</b> — إزالة مساعد\n"
    "🔹 <b>المساعدين</b> — قائمة المساعدين\n"
    "🔹 <b>اذاعه</b> — إذاعة لكل الجروبات\n\n"
    "📌 <i>للمطور فقط</i>"
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       📨 Callback Handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
promote_sessions = {}

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    name = q.from_user.first_name

    # ── صفحة الستارت ──
    if data == "cbstart":
        await q.answer("الصفحة الرئيسية")
        txt = txt_start(name)
        try:
            await q.edit_message_text(txt, parse_mode="HTML", reply_markup=kb_start())
        except:
            try: await q.edit_message_caption(caption=txt, parse_mode="HTML", reply_markup=kb_start())
            except: pass
        return

    # ── قائمة الأوامر ──
    if data == "cbcmds":
        await q.answer("قائمة الأوامر")
        await q.edit_message_text(
            "» <b>اضغط على الزر اللي عايز تشوف أوامره!</b>",
            parse_mode="HTML", reply_markup=kb_cmds()
        )
        return

    # ── فئات الأوامر ──
    if data == "cbadmin":
        await q.answer("أوامر الإدارة")
        await q.edit_message_text(TXT_ADMIN, parse_mode="HTML", reply_markup=kb_back())
        return

    if data == "cbpunish":
        await q.answer("أوامر العقوبات")
        await q.edit_message_text(TXT_PUNISH, parse_mode="HTML", reply_markup=kb_back())
        return

    if data == "cbinfo":
        await q.answer("أوامر المعلومات")
        await q.edit_message_text(TXT_INFO, parse_mode="HTML", reply_markup=kb_back())
        return

    if data == "cbdev":
        await q.answer("أوامر المطور")
        await q.edit_message_text(TXT_DEV, parse_mode="HTML", reply_markup=kb_back())
        return

    # ── أزرار الترقية: tgl:sk:perm ──
    if data.startswith("tgl:"):
        _, sk, perm = data.split(":", 2)
        if sk not in promote_sessions:
            await q.answer("❌ انتهت الجلسة، جرب تاني.", show_alert=True)
            return
        s = promote_sessions[sk]
        s["perms"][perm] = not s["perms"].get(perm, False)
        await q.answer()
        await q.edit_message_text(
            _promote_txt(s), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(_promote_kb(sk, s["perms"]))
        )
        return

    if data.startswith("title:"):
        _, sk = data.split(":", 1)
        if sk not in promote_sessions:
            await q.answer("❌ انتهت الجلسة.", show_alert=True)
            return
        promote_sessions[sk]["awaiting_title"] = True
        context.user_data["title_sk"] = sk
        await q.answer("اكتب اللقب في الشات 👇", show_alert=True)
        await q.edit_message_text(
            f"✏️ <b>اكتب اللقب للمشرف {promote_sessions[sk]['name']}</b>\n\n"
            f"📌 أقصى 16 حرف\n"
            f"📌 ابعت <b>لا</b> عشان تشيل اللقب",
            parse_mode="HTML"
        )
        return

    if data.startswith("confirm:"):
        _, sk = data.split(":", 1)
        if sk not in promote_sessions:
            await q.answer("❌ انتهت الجلسة.", show_alert=True)
            return
        await q.answer("جاري الرفع...")
        s = promote_sessions.pop(sk)
        p = s["perms"]
        try:
            await context.bot.promote_chat_member(
                chat_id=s["cid"], user_id=s["uid"],
                can_delete_messages=p.get("delete", False),
                can_restrict_members=p.get("ban", False),
                can_pin_messages=p.get("pin", False),
                can_change_info=p.get("info", False),
                can_promote_members=p.get("add_admins", False),
                can_invite_users=p.get("invite", False),
            )
            title = p.get("title", "").strip()
            if title:
                try:
                    await context.bot.set_chat_administrator_custom_title(s["cid"], s["uid"], custom_title=title)
                except: pass
            plist = ""
            if p.get("delete"):     plist += "🗑 حذف الرسايل\n"
            if p.get("ban"):        plist += "🔨 حظر الأعضاء\n"
            if p.get("pin"):        plist += "📌 تثبيت الرسايل\n"
            if p.get("info"):       plist += "✏️ تغيير المعلومات\n"
            if p.get("add_admins"): plist += "👑 إضافة مشرفين\n"
            if p.get("invite"):     plist += "🔗 الدعوة بلينك\n"
            tlbl = f"\n🏷 اللقب: <b>{title}</b>" if title else ""
            await q.edit_message_text(
                f"✅ <b>تم الرفع بنجاح!</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"👤 <b>{s['name']}</b>{tlbl}\n\n"
                f"📋 <b>الصلاحيات:</b>\n{plist or '— لا يوجد'}",
                parse_mode="HTML"
            )
        except TelegramError as e:
            await q.edit_message_text(f"❌ فشل الرفع:\n<code>{e}</code>", parse_mode="HTML")
        return

    if data.startswith("cancel:"):
        _, sk = data.split(":", 1)
        promote_sessions.pop(sk, None)
        await q.answer("تم الإلغاء")
        await q.edit_message_text("❌ تم إلغاء العملية.")
        return

    await q.answer()

def _promote_txt(s):
    p = s["perms"]
    lines = []
    if p.get("delete"):     lines.append("✅ 🗑 حذف الرسايل")
    if p.get("ban"):        lines.append("✅ 🔨 حظر الأعضاء")
    if p.get("pin"):        lines.append("✅ 📌 تثبيت الرسايل")
    if p.get("info"):       lines.append("✅ ✏️ تغيير المعلومات")
    if p.get("add_admins"): lines.append("✅ 👑 إضافة مشرفين")
    if p.get("invite"):     lines.append("✅ 🔗 الدعوة بلينك")
    ptext = "\n".join(lines) if lines else "— لا يوجد"
    title = p.get("title", "") or "بدون"
    return (
        f"🛡️ <b>رفع مشرف</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 <b>{s['name']}</b>\n"
        f"🏷 اللقب: <b>{title}</b>\n\n"
        f"<b>الصلاحيات المختارة:</b>\n{ptext}\n\n"
        f"اضغط عشان تغير الصلاحيات 👇"
    )

def _promote_kb(sk, p):
    def b(lbl, k):
        icon = "✅" if p.get(k) else "❌"
        return InlineKeyboardButton(f"{icon} {lbl}", callback_data=f"tgl:{sk}:{k}")
    tlbl = f"✏️ اللقب: {p.get('title') or 'بدون'}"
    return [
        [b("🗑 حذف الرسايل","delete"),     b("🔨 حظر الأعضاء","ban")],
        [b("📌 تثبيت الرسايل","pin"),      b("✏️ تغيير المعلومات","info")],
        [b("👑 إضافة مشرفين","add_admins"), b("🔗 الدعوة بلينك","invite")],
        [InlineKeyboardButton(tlbl, callback_data=f"title:{sk}")],
        [
            InlineKeyboardButton("🚀 رفعه مشرف", callback_data=f"confirm:{sk}"),
            InlineKeyboardButton("❌ إلغاء",      callback_data=f"cancel:{sk}"),
        ],
    ]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       🔰 أوامر السودو
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_addsudo(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    cid = update.message.chat_id
    lst = sudo_db.setdefault(str(cid), [])
    if uid not in lst: lst.append(uid); _save_sudo()
    try: chat_title = (await context.bot.get_chat(cid)).title
    except: chat_title = str(cid)
    await update.message.reply_text(
        f"🔰 <b>تم إضافة مساعد مطور</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 <b>{name}</b>\n"
        f"💭 الجروب: <b>{chat_title}</b>\n\n"
        f"📌 صلاحياته في هذا الجروب فقط",
        parse_mode="HTML"
    )

async def cmd_removesudo(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    cid = update.message.chat_id
    lst = sudo_db.get(str(cid), [])
    if uid not in lst:
        return await update.message.reply_text(f"❌ <b>{name}</b> مش مساعد في الجروب ده.", parse_mode="HTML")
    lst.remove(uid); _save_sudo()
    await update.message.reply_text(
        f"✅ <b>تم إزالة المساعد</b>\n━━━━━━━━━━━━━━━━\n👤 <b>{name}</b>",
        parse_mode="HTML"
    )

async def cmd_sudolist(update, context):
    cid   = update.message.chat_id
    sudos = sudo_db.get(str(cid), [])
    if not sudos: return await update.message.reply_text("📋 مفيش مساعدين في الجروب ده.")
    txt = "🔰 <b>مساعدو المطور في هذا الجروب:</b>\n━━━━━━━━━━━━━━━━\n\n"
    for uid in sudos:
        try:
            m = await context.bot.get_chat_member(cid, uid)
            uname = f" @{m.user.username}" if m.user.username else ""
            txt += f"🔰 <b>{m.user.full_name}</b>{uname}\n🆔 <code>{uid}</code>\n\n"
        except: txt += f"🔰 <code>{uid}</code>\n\n"
    await update.message.reply_text(txt, parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       🛡️ Promote / Demote
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_promote(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid:
        return await update.message.reply_text(
            "❌ مش قادر أعرف المستخدم.\n"
            "جرب: رد على رسالته، أو <b>رفع @يوزر</b> أو <b>رفع ID</b>",
            parse_mode="HTML"
        )
    cid = update.message.chat_id
    sk  = uuid.uuid4().hex
    promote_sessions[sk] = {
        "uid": uid, "name": name, "cid": cid, "awaiting_title": False,
        "perms": {"delete":True,"ban":True,"pin":False,"info":False,"add_admins":False,"invite":True,"title":""}
    }
    s = promote_sessions[sk]
    await update.message.reply_text(
        _promote_txt(s), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(_promote_kb(sk, s["perms"]))
    )

async def cmd_demote(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    try:
        await context.bot.promote_chat_member(
            update.message.chat_id, uid,
            can_delete_messages=False, can_restrict_members=False,
            can_pin_messages=False, can_change_info=False,
            can_promote_members=False, can_invite_users=False,
        )
        await update.message.reply_text(
            f"✅ <b>تم النزول</b>\n━━━━━━━━━━━━━━━━\n👤 <b>{name}</b> اتنزل من الإشراف.",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       ⚖️ Kick / Ban / Unban / Mute
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_kick(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    cid = update.message.chat_id; adm = update.message.from_user
    try:
        await context.bot.ban_chat_member(cid, uid)
        await context.bot.unban_chat_member(cid, uid)
        count = tracker.add_action(adm.id, cid, "kick")
        await update.message.reply_text(
            f"👢 <b>تم الطرد</b>\n━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{name}</b>\n👮 <b>{adm.full_name}</b>\n"
            f"📊 عداد المشرف: <b>{count}/{KICK_BAN_LIMIT}</b>",
            parse_mode="HTML"
        )
        if count >= KICK_BAN_LIMIT: await auto_demote(context, adm.id, cid)
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")

async def cmd_ban(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    cid = update.message.chat_id; adm = update.message.from_user
    try:
        await context.bot.ban_chat_member(cid, uid)
        count = tracker.add_action(adm.id, cid, "ban")
        await update.message.reply_text(
            f"🔨 <b>تم الحظر</b>\n━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{name}</b>\n👮 <b>{adm.full_name}</b>\n"
            f"📊 عداد المشرف: <b>{count}/{KICK_BAN_LIMIT}</b>",
            parse_mode="HTML"
        )
        if count >= KICK_BAN_LIMIT: await auto_demote(context, adm.id, cid)
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")

async def cmd_unban(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    try:
        await context.bot.unban_chat_member(update.message.chat_id, uid)
        await update.message.reply_text(f"✅ <b>تم فك الحظر</b>\n━━━━━━━━━━━━━━━━\n👤 <b>{name}</b>", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")

async def cmd_mute(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    try:
        await context.bot.restrict_chat_member(
            update.message.chat_id, uid,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text(f"🔇 <b>تم الكتم</b>\n━━━━━━━━━━━━━━━━\n👤 <b>{name}</b>", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")

async def cmd_unmute(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    try:
        await context.bot.restrict_chat_member(
            update.message.chat_id, uid,
            permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True, can_invite_users=True,
            )
        )
        await update.message.reply_text(f"🔊 <b>تم فك الكتم</b>\n━━━━━━━━━━━━━━━━\n👤 <b>{name}</b>", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       ⚠️ التحذيرات
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_warn(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    cid = update.message.chat_id
    count = add_warn(cid, uid)
    bar   = "🟥" * count + "⬜️" * (MAX_WARNS - count)
    if count >= MAX_WARNS:
        try:
            await context.bot.ban_chat_member(cid, uid)
            reset_warn(cid, uid)
            await update.message.reply_text(
                f"🚫 <b>تم الحظر بسبب التحذيرات</b>\n━━━━━━━━━━━━━━━━\n"
                f"👤 <b>{name}</b>\n⚠️ وصل للحد الأقصى ({MAX_WARNS} تحذيرات)",
                parse_mode="HTML"
            )
        except TelegramError as e:
            await update.message.reply_text(f"❌ فشل الحظر: <code>{e}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"⚠️ <b>تحذير!</b>\n━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{name}</b>\n{bar} <b>{count}/{MAX_WARNS}</b>\n\n"
            f"📌 عند {MAX_WARNS} تحذيرات → حظر تلقائي",
            parse_mode="HTML"
        )

async def cmd_warns(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    count = get_warns(update.message.chat_id, uid)
    bar   = "🟥" * count + "⬜️" * (MAX_WARNS - count)
    await update.message.reply_text(
        f"📊 <b>تحذيرات العضو</b>\n━━━━━━━━━━━━━━━━\n👤 <b>{name}</b>\n{bar} <b>{count}/{MAX_WARNS}</b>",
        parse_mode="HTML"
    )

async def cmd_resetwarns(update, context, arg):
    uid, name = await resolve(update, context, arg)
    if not uid: return await update.message.reply_text("❌ مش قادر أعرف المستخدم.")
    reset_warn(update.message.chat_id, uid)
    await update.message.reply_text(f"✅ <b>تم مسح التحذيرات</b>\n━━━━━━━━━━━━━━━━\n👤 <b>{name}</b>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       📌 Pin / Unpin
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_pin(update, context):
    if not update.message.reply_to_message:
        return await update.message.reply_text("❌ رد على الرسالة اللي عايز تثبتها.")
    try:
        await context.bot.pin_chat_message(update.message.chat_id, update.message.reply_to_message.message_id)
        await update.message.reply_text(
            f"📌 <b>تم التثبيت</b>\n━━━━━━━━━━━━━━━━\n👮 <b>{update.message.from_user.full_name}</b>",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")

async def cmd_unpin(update, context):
    try:
        await context.bot.unpin_chat_message(update.message.chat_id)
        await update.message.reply_text("✅ <b>تم إلغاء التثبيت</b>", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ فشل: <code>{e}</code>", parse_mode="HTML")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       🔄 Auto Demote
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def auto_demote(context, adm_id, cid):
    try:
        m    = await context.bot.get_chat_member(cid, adm_id)
        name = m.user.full_name
        await context.bot.promote_chat_member(
            cid, adm_id,
            can_delete_messages=False, can_restrict_members=False,
            can_pin_messages=False, can_change_info=False,
            can_promote_members=False, can_invite_users=False,
        )
        tracker.reset(adm_id, cid)
        await context.bot.send_message(
            cid,
            f"⚠️ <b>نزول تلقائي</b>\n━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{name}</b> اتنزل تلقائياً\n"
            f"📋 السبب: تجاوز حد الطرد/الحظر ({KICK_BAN_LIMIT} مرة)",
            parse_mode="HTML"
        )
    except TelegramError as e: logger.error(f"auto_demote: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       ℹ️ معلومات
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_id(update, context):
    msg = update.message
    if msg.reply_to_message:
        u = msg.reply_to_message.from_user
        txt = f"👤 <b>معلومات المستخدم</b>\n━━━━━━━━━━━━━━━━\n🔤 <b>{u.full_name}</b>\n🆔 <code>{u.id}</code>\n"
        if u.username: txt += f"🔗 @{u.username}\n"
        txt += f"\n💭 الجروب: <code>{msg.chat_id}</code>"
    else:
        txt = f"👤 ID الخاص بك: <code>{msg.from_user.id}</code>\n💭 ID الجروب: <code>{msg.chat_id}</code>"
    await msg.reply_text(txt, parse_mode="HTML")

async def cmd_info(update, context, arg):
    msg = update.message
    u   = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
    try:
        m  = await context.bot.get_chat_member(msg.chat_id, u.id)
        st = {"administrator":"👮 مشرف","creator":"👑 مالك","member":"👤 عضو",
              "restricted":"🔇 مقيّد","left":"🚪 غادر","kicked":"🔨 محظور"}.get(m.status, m.status)
    except: st = "❓"
    txt = f"👤 <b>معلومات المستخدم</b>\n━━━━━━━━━━━━━━━━\n🔤 <b>{u.full_name}</b>\n🆔 <code>{u.id}</code>\n"
    if u.username: txt += f"🔗 @{u.username}\n"
    txt += (
        f"📋 الحالة: {st}\n"
        f"🎖 الرتبة: {rank_label(msg.chat_id, u.id)}\n"
        f"⚠️ التحذيرات: <b>{get_warns(msg.chat_id, u.id)}/{MAX_WARNS}</b>\n"
        f"🤖 بوت: {'نعم' if u.is_bot else 'لا'}"
    )
    await msg.reply_text(txt, parse_mode="HTML")

async def cmd_stats(update, context):
    cid   = update.message.chat_id
    stats = tracker.get_stats(cid)
    if not stats: return await update.message.reply_text("📊 مفيش إحصائيات لحد دلوقتي.")
    txt = "📊 <b>إحصائيات الطرد/الحظر</b>\n━━━━━━━━━━━━━━━━\n\n"
    for aid, cnt in stats.items():
        try:
            m    = await context.bot.get_chat_member(cid, int(aid))
            name = m.user.full_name
        except: name = f"ID:{aid}"
        bar  = "🟥" * min(cnt,10) + "⬜️" * max(0,10-cnt)
        txt += f"👤 <b>{name}</b>\n{bar} {cnt}/{KICK_BAN_LIMIT}\n\n"
    await update.message.reply_text(txt, parse_mode="HTML")

async def cmd_reload(update, context):
    await update.message.reply_text("✅ <b>تم تحديث قائمة المشرفين</b>", parse_mode="HTML")

async def cmd_ping(update, context):
    t = time()
    m = await update.message.reply_text("🏓 ...")
    d = (time() - t) * 1000
    await m.edit_text(f"🏓 <b>Pong!</b>\n━━━━━━━━━━━━━━━━\n⚡️ <code>{d:.2f} ms</code>", parse_mode="HTML")

async def cmd_uptime(update, context):
    sec = (datetime.utcnow() - START_TIME).total_seconds()
    await update.message.reply_text(
        f"🤖 <b>وقت التشغيل</b>\n━━━━━━━━━━━━━━━━\n⏱ <code>{fmt_time(int(sec))}</code>",
        parse_mode="HTML"
    )

async def cmd_alive(update, context):
    sec      = (datetime.utcnow() - START_TIME).total_seconds()
    bot_info = await context.bot.get_me()
    total_su = sum(len(v) for v in sudo_db.values())
    await update.message.reply_text(
        f"✅ <b>{BOT_NAME} شغال!</b>\n━━━━━━━━━━━━━━━━\n"
        f"🤖 @{bot_info.username}\n"
        f"⏱ {fmt_time(int(sec))}\n"
        f"👑 المطور: <code>{DEVELOPER_ID}</code>\n"
        f"🔰 المساعدين: <b>{total_su}</b>\n"
        f"⚠️ حد الطرد: <b>{KICK_BAN_LIMIT}</b>",
        parse_mode="HTML"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       📡 Broadcast
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_broadcast(update, context, arg):
    msg = update.message
    fwd = msg.reply_to_message
    txt_brc = arg if arg and not fwd else None
    if not fwd and not txt_brc:
        return await msg.reply_text(
            "❌ ارد على رسالة أو اكتب النص بعد الأمر\n"
            "مثال: <code>اذاعه رسالتك هنا</code>",
            parse_mode="HTML"
        )
    sent = failed = 0
    sm   = await msg.reply_text("📡 جاري الإذاعة...")
    for cid_str in list(tracker.data.keys()):
        try:
            cid = int(cid_str)
            if fwd: await context.bot.forward_message(cid, msg.chat_id, fwd.message_id)
            else:   await context.bot.send_message(cid, txt_brc)
            sent += 1; await asyncio.sleep(0.3)
        except: failed += 1
    await sm.edit_text(
        f"📡 <b>تمت الإذاعة</b>\n━━━━━━━━━━━━━━━━\n✅ أُرسلت: <b>{sent}</b>\n❌ فشلت: <b>{failed}</b>",
        parse_mode="HTML"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       📋 Help
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_help(update, context):
    name = update.message.from_user.first_name
    txt  = txt_start(name)
    kb   = kb_start()
    if BOT_PHOTO:
        try:
            await update.message.reply_photo(photo=BOT_PHOTO, caption=txt, parse_mode="HTML", reply_markup=kb)
            return
        except: pass
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       👋 ترحيب / وداع
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg      = update.message
    bot_info = await context.bot.get_me()
    for member in msg.new_chat_members:
        if member.is_bot and member.id == bot_info.id:
            tracker.data.setdefault(str(msg.chat_id), {}); tracker._save()
            txt = (
                f"👋 <b>أهلاً بيكم!</b>\n━━━━━━━━━━━━━━━━\n"
                f"أنا <b>{BOT_NAME}</b> بوت إدارة متكامل 🤖\n\n"
                f"⚙️ ارفعني مشرف بصلاحيات كاملة\n\n"
                f"اكتب <b>أوامر</b> عشان تشوف كل حاجة 🚀"
            )
            rows = []
            if GROUP_SUPPORT:   rows.append([InlineKeyboardButton("💬 جروب الدعم", url=f"https://t.me/{GROUP_SUPPORT}")])
            if UPDATES_CHANNEL: rows.append([InlineKeyboardButton("📣 القناة", url=f"https://t.me/{UPDATES_CHANNEL}")])
            kb = InlineKeyboardMarkup(rows) if rows else None
            try:
                if WELCOME_PHOTO: await context.bot.send_photo(msg.chat_id, WELCOME_PHOTO, caption=txt, parse_mode="HTML", reply_markup=kb)
                else:             await context.bot.send_message(msg.chat_id, txt, parse_mode="HTML", reply_markup=kb)
            except: pass
        elif not member.is_bot:
            mention = f'<a href="tg://user?id={member.id}">{member.full_name}</a>'
            try: chat_title = (await context.bot.get_chat(msg.chat_id)).title
            except: chat_title = "الجروب"
            rows = []
            if GROUP_SUPPORT: rows.append([InlineKeyboardButton("💬 جروب الدعم", url=f"https://t.me/{GROUP_SUPPORT}")])
            kb = InlineKeyboardMarkup(rows) if rows else None
            wtxt = (
                f"🎉 <b>عضو جديد!</b>\n━━━━━━━━━━━━━━━━\n"
                f"👋 أهلاً {mention}!\n"
                f"نورت <b>{chat_title}</b> 🌟\n\n"
                f"اتمنى تبقى معنا دايماً ❤️"
            )
            try:
                sent = await context.bot.send_message(msg.chat_id, wtxt, parse_mode="HTML", reply_markup=kb)
                asyncio.create_task(del_later(context, msg.chat_id, sent.message_id, 300))
            except: pass

async def on_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg    = update.message
    member = msg.left_chat_member
    if not member or member.is_bot: return
    mention = f'<a href="tg://user?id={member.id}">{member.full_name}</a>'
    try:
        sent = await context.bot.send_message(
            msg.chat_id,
            f"👋 <b>وداعاً!</b>\n━━━━━━━━━━━━━━━━\n😢 {mention} غادر\nنتمنى نشوفك تاني 💙",
            parse_mode="HTML"
        )
        asyncio.create_task(del_later(context, msg.chat_id, sent.message_id, 120))
    except: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       🚫 فلتر الكلمات
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def has_bad_word(text):
    n = re.sub(r"\s+", " ", text.lower()).strip()
    return any(re.search(re.escape(w.lower()), n) for w in BAD_WORDS)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       📨 Main Message Handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: return

    text = msg.text.strip()
    uid  = msg.from_user.id
    cid  = msg.chat_id

    # ── انتظار اللقب ──
    if context.user_data.get("title_sk"):
        sk = context.user_data["title_sk"]
        if sk in promote_sessions and promote_sessions[sk].get("awaiting_title"):
            promote_sessions[sk]["perms"]["title"] = "" if text == "لا" else text[:16]
            promote_sessions[sk]["awaiting_title"] = False
            context.user_data.pop("title_sk")
            s = promote_sessions[sk]
            await msg.reply_text(
                _promote_txt(s), parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(_promote_kb(sk, s["perms"]))
            )
            return

    # ── الأوامر ──
    action, level, arg = parse_cmd(text)

    if action:
        # التحقق من الصلاحية
        if level == "dev" and not is_dev(uid):
            m = await msg.reply_text("❌ هذا الأمر للمطور فقط! 👑")
            asyncio.create_task(del_later(context, cid, m.message_id, 5))
            return
        if level == "admin" and not (is_privileged(cid, uid) or await check_admin(context, cid, uid)):
            m = await msg.reply_text("❌ هذا الأمر للمشرفين فقط! 🛡️")
            asyncio.create_task(del_later(context, cid, m.message_id, 5))
            return

        # تنفيذ الأمر
        ACTIONS = {
            "addsudo":    lambda: cmd_addsudo(update, context, arg),
            "removesudo": lambda: cmd_removesudo(update, context, arg),
            "sudolist":   lambda: cmd_sudolist(update, context),
            "promote":    lambda: cmd_promote(update, context, arg),
            "demote":     lambda: cmd_demote(update, context, arg),
            "kick":       lambda: cmd_kick(update, context, arg),
            "ban":        lambda: cmd_ban(update, context, arg),
            "unban":      lambda: cmd_unban(update, context, arg),
            "mute":       lambda: cmd_mute(update, context, arg),
            "unmute":     lambda: cmd_unmute(update, context, arg),
            "warn":       lambda: cmd_warn(update, context, arg),
            "warns":      lambda: cmd_warns(update, context, arg),
            "resetwarns": lambda: cmd_resetwarns(update, context, arg),
            "pin":        lambda: cmd_pin(update, context),
            "unpin":      lambda: cmd_unpin(update, context),
            "id":         lambda: cmd_id(update, context),
            "info":       lambda: cmd_info(update, context, arg),
            "stats":      lambda: cmd_stats(update, context),
            "reload":     lambda: cmd_reload(update, context),
            "ping":       lambda: cmd_ping(update, context),
            "uptime":     lambda: cmd_uptime(update, context),
            "alive":      lambda: cmd_alive(update, context),
            "broadcast":  lambda: cmd_broadcast(update, context, arg),
            "help":       lambda: cmd_help(update, context),
        }
        fn = ACTIONS.get(action)
        if fn: await fn()
        return

    # ── فلتر الكلمات (للأعضاء العاديين فقط) ──
    if is_privileged(cid, uid) or await check_admin(context, cid, uid): return
    if has_bad_word(text):
        try:
            await msg.delete()
            w = await context.bot.send_message(
                cid,
                f"🚫 {msg.from_user.mention_html()} رسالتك اتحذفت بسبب كلمات مخالفة ⚠️",
                parse_mode="HTML"
            )
            asyncio.create_task(del_later(context, cid, w.message_id, 5))
        except TelegramError: pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#           🚀 التشغيل
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_left_member))
    app.add_handler(CallbackQueryHandler(on_callback))
    logger.info(f"✅ {BOT_NAME} شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
