"""
بات تلگرامی جنگ جهانی (World War Bot) - نسخه‌ی دکمه‌ای
-----------------------------------------------------------
همه‌چیز با دکمه کار می‌کنه، نه دستورات اسلش (فقط /start برای شروع لازمه چون
تلگرام همیشه به یک نقطه‌ی ورود نیاز داره).

قابلیت‌ها:
- هر بازیکن یک کشور با منابع (پول، نفت، آهن، طلا) و جمعیت دلخواه (توسط ادمین) داره
- تجهیزات نظامی متنوع: موشک‌های مختلف، جنگنده‌های مختلف، نیروی زمینی (سرباز ساده/ویژه، تانک)
- ساخت شهر و معدن (طلا/آهن/نفت) با اسم دلخواه بازیکن، با سقف مشخص
- سیستم سود روزانه: ادمین با زدن یک دکمه، بر اساس شهر/معدن‌های هر بازیکن بهش سود می‌ده
  (بدون محدودیت تعداد دفعات برای ادمین)
- حمله بین بازیکنان بر اساس مجموع قدرت تجهیزاتشون

معماری کانفیگ‌محور: برای اضافه کردن هر واحد جدید (مثلاً نیروی دریایی در آینده)
فقط کافیه به دیکشنری UNITS یا BUILDINGS یک آیتم جدید اضافه کنید؛ بقیه‌ی کد
(ساخت، نمایش وضعیت، محاسبه‌ی قدرت حمله) به‌صورت خودکار باهاش کار می‌کنه.

راه‌اندازی: فایل README.md رو ببینید.
"""

import os
import logging
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
#                        تنظیمات کلی
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()} or {0}

DB_PATH = os.path.join(os.path.dirname(__file__), "game.db")

RESOURCE_NAMES = {"money": "پول", "oil": "نفت", "iron": "آهن", "gold": "طلا"}
RESOURCE_EMOJI = {"money": "💰", "oil": "🛢", "iron": "⚙️", "gold": "🥇"}

# منابع اولیه‌ی هر کشور جدید (پول طبق خواسته‌ی شما ۱۰ میلیون، بقیه بالانس‌شده)
DEFAULT_START = {"money": 10_000_000, "oil": 50_000, "iron": 60_000, "gold": 20_000}

# ------------------------------------------------------------
# تجهیزات نظامی -- برای افزودن واحد جدید فقط یک خط اینجا اضافه کنید
# ------------------------------------------------------------
UNITS = {
    "missile": {
        "v2": {"name": "موشک وی-۲", "emoji": "🚀", "cost": {"money": 50_000, "oil": 2_000}, "attack": 8, "defense": 3},
        "scud": {"name": "موشک اسکاد", "emoji": "🚀", "cost": {"money": 80_000, "oil": 3_000}, "attack": 10, "defense": 3},
        "sejjil": {"name": "موشک سجیل", "emoji": "🚀", "cost": {"money": 150_000, "oil": 4_000}, "attack": 15, "defense": 4},
        "iskander": {"name": "موشک اسکندر", "emoji": "🚀", "cost": {"money": 300_000, "oil": 6_000}, "attack": 22, "defense": 6},
        "tomahawk": {"name": "موشک تاماهاوک", "emoji": "🚀", "cost": {"money": 500_000, "oil": 8_000}, "attack": 30, "defense": 8},
    },
    "fighter": {
        "f5": {"name": "جنگنده اف-۵", "emoji": "✈️", "cost": {"money": 200_000, "iron": 5_000}, "attack": 10, "defense": 8},
        "mig29": {"name": "جنگنده میگ-۲۹", "emoji": "✈️", "cost": {"money": 400_000, "iron": 8_000}, "attack": 16, "defense": 12},
        "su27": {"name": "جنگنده سوخو-۲۷", "emoji": "✈️", "cost": {"money": 600_000, "iron": 10_000}, "attack": 20, "defense": 15},
        "f16": {"name": "جنگنده اف-۱۶", "emoji": "✈️", "cost": {"money": 700_000, "iron": 12_000}, "attack": 18, "defense": 14},
        "su35": {"name": "جنگنده سوخو-۳۵", "emoji": "✈️", "cost": {"money": 900_000, "iron": 14_000}, "attack": 25, "defense": 18},
        "f22": {"name": "جنگنده اف-۲۲", "emoji": "✈️", "cost": {"money": 1_500_000, "iron": 20_000}, "attack": 35, "defense": 25},
    },
    "ground": {
        "soldier": {"name": "سرباز ساده", "emoji": "🪖", "cost": {"money": 1_000, "gold": 10}, "attack": 1, "defense": 1},
        "special_soldier": {"name": "سرباز ویژه", "emoji": "🎖", "cost": {"money": 5_000, "gold": 50}, "attack": 3, "defense": 2},
        "tank": {"name": "تانک", "emoji": "🛡", "cost": {"money": 100_000, "gold": 500}, "attack": 12, "defense": 10},
    },
    # نیروی دریایی و هر دسته‌ی جدید دیگه رو بعداً همینجا اضافه می‌کنیم
}
CATEGORY_NAMES = {"missile": "🚀 موشک‌ها", "fighter": "✈️ جنگنده‌ها", "ground": "🪖 نیروی زمینی"}

# لیست مسطح از همه‌ی واحدها برای دسترسی سریع
FLAT_UNITS = {}
for _cat, _items in UNITS.items():
    for _key, _info in _items.items():
        FLAT_UNITS[_key] = {**_info, "category": _cat}

# ------------------------------------------------------------
# ساختمان‌ها: شهر و معدن‌ها -- برای واحد جدید فقط یک خط اضافه کنید
# ------------------------------------------------------------
BUILDINGS = {
    "city": {"name": "شهر", "emoji": "🏙", "cost": {"money": 800_000}, "cap": 3, "profit": {"money": 200_000}},
    "mine_gold": {"name": "معدن طلا", "emoji": "🥇", "cost": {"money": 250_000}, "cap": 5, "profit": {"gold": 2_000}},
    "mine_iron": {"name": "معدن آهن", "emoji": "⚙️", "cost": {"money": 250_000}, "cap": 5, "profit": {"iron": 10_000}},
    "mine_oil": {"name": "معدن نفت", "emoji": "🛢", "cost": {"money": 300_000}, "cap": 5, "profit": {"oil": 10_000}},
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ============================================================
#                          دیتابیس
# ============================================================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            country TEXT NOT NULL,
            population INTEGER NOT NULL,
            money INTEGER NOT NULL,
            oil INTEGER NOT NULL,
            iron INTEGER NOT NULL,
            gold INTEGER NOT NULL,
            alive INTEGER NOT NULL DEFAULT 1,
            created_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS player_units (
            user_id INTEGER NOT NULL,
            unit_key TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, unit_key)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS player_buildings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            btype TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT
        )"""
    )
    conn.commit()
    conn.close()


def get_player(user_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row


def get_units(user_id: int) -> dict:
    conn = db()
    rows = conn.execute(
        "SELECT unit_key, quantity FROM player_units WHERE user_id=? AND quantity>0", (user_id,)
    ).fetchall()
    conn.close()
    return {r["unit_key"]: r["quantity"] for r in rows}


def get_buildings(user_id: int) -> list:
    conn = db()
    rows = conn.execute(
        "SELECT btype, name FROM player_buildings WHERE user_id=? ORDER BY id", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_buildings(user_id: int, btype: str) -> int:
    conn = db()
    n = conn.execute(
        "SELECT COUNT(*) c FROM player_buildings WHERE user_id=? AND btype=?", (user_id, btype)
    ).fetchone()["c"]
    conn.close()
    return n


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def fmt(n: int) -> str:
    return f"{n:,}"


# ============================================================
#                     مدیریت وضعیت (pending action)
# ============================================================
def set_pending(context: ContextTypes.DEFAULT_TYPE, action: str, **extra):
    context.user_data["pending"] = {"action": action, **extra}


def get_pending(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get("pending")


def clear_pending(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending", None)


# ============================================================
#                          کیبوردها
# ============================================================
BTN_STATUS = "🌍 وضعیت کشور من"
BTN_ATTACK = "⚔️ حمله"
BTN_BUILD_MIL = "🎖 ساخت نظامی"
BTN_BUILD_CITY = "🏙 ساخت شهر/معدن"
BTN_HELP = "📜 راهنما"
BTN_REQUEST_COUNTRY = "📩 درخواست کشور"
BTN_ADMIN_PANEL = "👑 پنل مدیریت"
BTN_CANCEL = "❌ لغو"


def main_menu(user_id: int) -> ReplyKeyboardMarkup:
    p = get_player(user_id)
    rows = []
    if p:
        rows.append([BTN_STATUS, BTN_ATTACK])
        rows.append([BTN_BUILD_MIL, BTN_BUILD_CITY])
    else:
        rows.append([BTN_REQUEST_COUNTRY])
    rows.append([BTN_HELP])
    if is_admin(user_id):
        rows.append([BTN_ADMIN_PANEL])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)


def units_category_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(CATEGORY_NAMES[c], callback_data=f"cat:{c}")] for c in UNITS]
    return InlineKeyboardMarkup(rows)


def units_list_kb(category: str) -> InlineKeyboardMarkup:
    rows = []
    for key, info in UNITS[category].items():
        cost_text = " + ".join(f"{fmt(v)} {RESOURCE_NAMES[k]}" for k, v in info["cost"].items())
        label = f"{info['emoji']} {info['name']} ({cost_text})"
        rows.append([InlineKeyboardButton(label, callback_data=f"unit:{key}")])
    rows.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="cat_back")])
    return InlineKeyboardMarkup(rows)


def buildings_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for key, info in BUILDINGS.items():
        n = count_buildings(user_id, key)
        cost_text = " + ".join(f"{fmt(v)} {RESOURCE_NAMES[k]}" for k, v in info["cost"].items())
        label = f"{info['emoji']} {info['name']} ({n}/{info['cap']}) - {cost_text}"
        rows.append([InlineKeyboardButton(label, callback_data=f"build:{key}")])
    return InlineKeyboardMarkup(rows)


def admin_panel_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📥 درخواست‌های در انتظار", callback_data="admin:pending")],
        [InlineKeyboardButton("💰 اعمال سود روزانه برای همه", callback_data="admin:profit")],
        [InlineKeyboardButton("🎁 افزودن منبع به بازیکن", callback_data="admin:give")],
        [InlineKeyboardButton("📋 لیست بازیکنان", callback_data="admin:list")],
        [InlineKeyboardButton("🗑 حذف بازیکن", callback_data="admin:remove")],
    ]
    return InlineKeyboardMarkup(rows)


def resource_choice_kb(prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{RESOURCE_EMOJI[k]} {v}", callback_data=f"{prefix}:{k}")] for k, v in RESOURCE_NAMES.items()]
    rows.append([InlineKeyboardButton(f"{'👥'} جمعیت", callback_data=f"{prefix}:population")])
    return InlineKeyboardMarkup(rows)


# ============================================================
#                          /start
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_pending(context)
    user_id = update.effective_user.id
    p = get_player(user_id)
    if p:
        text = f"خوش برگشتی فرمانده‌ی {p['country']}! از دکمه‌های پایین استفاده کن."
    else:
        text = (
            "به بازی جنگ جهانی خوش اومدی! 🌍\n"
            "برای اینکه کشور بگیری، روی «📩 درخواست کشور» بزن."
        )
    await update.message.reply_text(text, reply_markup=main_menu(user_id))


# ============================================================
#                     نمایش وضعیت کشور
# ============================================================
async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    p = get_player(user_id)
    if not p:
        await update.message.reply_text("هنوز کشوری نداری.", reply_markup=main_menu(user_id))
        return
    if not p["alive"]:
        await update.message.reply_text(f"💀 کشور {p['country']} نابود شده است.", reply_markup=main_menu(user_id))
        return

    text = (
        f"🌍 *{p['country']}*\n"
        f"👥 جمعیت: {fmt(p['population'])}\n"
        f"💰 پول: {fmt(p['money'])}\n"
        f"🛢 نفت: {fmt(p['oil'])}\n"
        f"⚙️ آهن: {fmt(p['iron'])}\n"
        f"🥇 طلا: {fmt(p['gold'])}\n"
    )

    units = get_units(user_id)
    if units:
        text += "\n*🪖 تجهیزات نظامی:*\n"
        for key, qty in units.items():
            info = FLAT_UNITS[key]
            text += f"{info['emoji']} {info['name']}: {qty}\n"
    else:
        text += "\nهنوز هیچ تجهیزات نظامی نساختی.\n"

    buildings = get_buildings(user_id)
    if buildings:
        text += "\n*🏙 شهرها و معادن:*\n"
        for b in buildings:
            info = BUILDINGS[b["btype"]]
            text += f"{info['emoji']} {b['name']} ({info['name']})\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(user_id))


# ============================================================
#                          راهنما
# ============================================================
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (
        "📜 *راهنمای بازی*\n\n"
        f"{BTN_STATUS} — دیدن منابع، جمعیت، تجهیزات و شهر/معدن‌های خودت\n"
        f"{BTN_BUILD_MIL} — ساخت موشک، جنگنده یا نیروی زمینی\n"
        f"{BTN_BUILD_CITY} — ساخت شهر یا معدن (طلا/آهن/نفت) با اسم دلخواه\n"
        f"{BTN_ATTACK} — حمله به یک بازیکن دیگه با دادن آیدی عددیش\n\n"
        "برای گرفتن کشور، از دکمه‌ی «📩 درخواست کشور» استفاده کن؛ درخواستت برای ادمین ارسال می‌شه."
    )
    if is_admin(user_id):
        text += (
            "\n\n👑 *پنل مدیریت (فقط شما):*\n"
            "از دکمه‌ی «👑 پنل مدیریت» می‌تونی درخواست‌های کشور رو تایید/رد کنی، "
            "سود روزانه بدی، به بازیکنان منبع اضافه کنی، لیستشون رو ببینی یا حذفشون کنی."
        )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu(user_id))


# ============================================================
#                     درخواست کشور (بازیکن)
# ============================================================
async def request_country_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if get_player(user_id):
        await update.message.reply_text("تو از قبل یک کشور داری!", reply_markup=main_menu(user_id))
        return
    pending = context.bot_data.setdefault("pending_requests", {})
    if user_id in pending:
        await update.message.reply_text("درخواستت قبلاً ثبت شده، منتظر تایید ادمین باش.", reply_markup=main_menu(user_id))
        return
    set_pending(context, "await_country_name")
    await update.message.reply_text("اسمی که می‌خوای برای کشورت باشه رو بفرست:", reply_markup=cancel_menu())


async def handle_country_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "بدون‌نام"
    country_name = text.strip()
    if not country_name:
        await update.message.reply_text("اسم نامعتبره، دوباره بفرست:")
        return
    pending_requests = context.bot_data.setdefault("pending_requests", {})
    pending_requests[user_id] = {"country_name": country_name, "username": username}
    clear_pending(context)
    await update.message.reply_text(
        "✅ درخواستت برای ادمین ارسال شد. به‌محض تایید بهت خبر می‌دیم.",
        reply_markup=main_menu(user_id),
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ تایید", callback_data=f"approve:{user_id}"),
                InlineKeyboardButton("❌ رد", callback_data=f"reject:{user_id}"),
            ]
        ]
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"📩 درخواست کشور جدید\n"
                    f"بازیکن: @{username} (`{user_id}`)\n"
                    f"نام کشور پیشنهادی: {country_name}"
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
            )
        except Exception:
            pass


# ============================================================
#                        ساخت نظامی
# ============================================================
async def build_mil_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_player(user_id):
        await update.message.reply_text("اول باید کشور داشته باشی.", reply_markup=main_menu(user_id))
        return
    await update.message.reply_text("کدوم دسته از تجهیزات رو می‌خوای بسازی؟", reply_markup=units_category_kb())


async def build_city_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_player(user_id):
        await update.message.reply_text("اول باید کشور داشته باشی.", reply_markup=main_menu(user_id))
        return
    await update.message.reply_text("کدوم رو می‌خوای بسازی؟", reply_markup=buildings_kb(user_id))


async def attack_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    p = get_player(user_id)
    if not p or not p["alive"]:
        await update.message.reply_text("کشوری نداری یا کشورت نابود شده.", reply_markup=main_menu(user_id))
        return
    set_pending(context, "await_attack_target")
    await update.message.reply_text("آیدی عددی بازیکنی که می‌خوای بهش حمله کنی رو بفرست:", reply_markup=cancel_menu())


# ============================================================
#                   هندلر متن (منو + ورودی‌های چندمرحله‌ای)
# ============================================================
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # دکمه‌های منوی اصلی همیشه اول چک می‌شن (حتی وسط یک ورودی چندمرحله‌ای، برای خروج راحت)
    if text == BTN_CANCEL:
        clear_pending(context)
        await update.message.reply_text("لغو شد.", reply_markup=main_menu(user_id))
        return
    if text == BTN_STATUS:
        clear_pending(context)
        await show_status(update, context)
        return
    if text == BTN_HELP:
        clear_pending(context)
        await show_help(update, context)
        return
    if text == BTN_REQUEST_COUNTRY:
        clear_pending(context)
        await request_country_start(update, context)
        return
    if text == BTN_BUILD_MIL:
        clear_pending(context)
        await build_mil_start(update, context)
        return
    if text == BTN_BUILD_CITY:
        clear_pending(context)
        await build_city_start(update, context)
        return
    if text == BTN_ATTACK:
        clear_pending(context)
        await attack_start(update, context)
        return
    if text == BTN_ADMIN_PANEL and is_admin(user_id):
        clear_pending(context)
        await update.message.reply_text("پنل مدیریت:", reply_markup=admin_panel_kb())
        return

    pending = get_pending(context)
    if not pending:
        await update.message.reply_text("از دکمه‌های پایین استفاده کن 🙂", reply_markup=main_menu(user_id))
        return

    action = pending["action"]

    if action == "await_country_name":
        await handle_country_name(update, context, text)

    elif action == "await_attack_target":
        await do_attack(update, context, text)

    elif action == "await_build_qty":
        await do_build_unit(update, context, text, pending["unit_key"])

    elif action == "await_building_name":
        await do_build_building(update, context, text, pending["btype"])

    elif action == "await_admin_population":
        await do_approve_with_population(update, context, text, pending["target_user_id"], pending["country_name"])

    elif action == "await_admin_give_userid":
        await ask_give_resource_type(update, context, text)

    elif action == "await_admin_give_amount":
        await do_give_resource(update, context, text, pending["target_user_id"], pending["resource"])

    elif action == "await_admin_remove_userid":
        await do_remove_player(update, context, text)

    else:
        await update.message.reply_text("متوجه نشدم، از دکمه‌ها استفاده کن.", reply_markup=main_menu(user_id))


# ============================================================
#                       اجرای ساخت واحد
# ============================================================
async def do_build_unit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, unit_key: str):
    user_id = update.effective_user.id
    clear_pending(context)
    try:
        count = int(text.strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("عدد نامعتبره.", reply_markup=main_menu(user_id))
        return

    info = FLAT_UNITS[unit_key]
    p = get_player(user_id)
    total_cost = {k: v * count for k, v in info["cost"].items()}
    for res, amount in total_cost.items():
        if p[res] < amount:
            await update.message.reply_text(
                f"منابع کافی نیست. برای {count} {info['name']} به {fmt(amount)} {RESOURCE_NAMES[res]} نیاز داری.",
                reply_markup=main_menu(user_id),
            )
            return

    conn = db()
    set_clause = ", ".join(f"{k}={k}-?" for k in total_cost)
    conn.execute(f"UPDATE players SET {set_clause} WHERE user_id=?", (*total_cost.values(), user_id))
    conn.execute(
        """INSERT INTO player_units (user_id, unit_key, quantity) VALUES (?,?,?)
           ON CONFLICT(user_id, unit_key) DO UPDATE SET quantity=quantity+excluded.quantity""",
        (user_id, unit_key, count),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ {count} {info['emoji']} {info['name']} ساخته شد.", reply_markup=main_menu(user_id))


# ============================================================
#                     اجرای ساخت شهر/معدن
# ============================================================
async def do_build_building(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, btype: str):
    user_id = update.effective_user.id
    clear_pending(context)
    name = text.strip()
    if not name:
        await update.message.reply_text("اسم نامعتبره.", reply_markup=main_menu(user_id))
        return

    info = BUILDINGS[btype]
    if count_buildings(user_id, btype) >= info["cap"]:
        await update.message.reply_text(f"سقف ساخت {info['name']} پره ({info['cap']} تا).", reply_markup=main_menu(user_id))
        return

    p = get_player(user_id)
    for res, amount in info["cost"].items():
        if p[res] < amount:
            await update.message.reply_text(
                f"منابع کافی نیست. برای ساخت {info['name']} به {fmt(amount)} {RESOURCE_NAMES[res]} نیاز داری.",
                reply_markup=main_menu(user_id),
            )
            return

    conn = db()
    set_clause = ", ".join(f"{k}={k}-?" for k in info["cost"])
    conn.execute(f"UPDATE players SET {set_clause} WHERE user_id=?", (*info["cost"].values(), user_id))
    conn.execute(
        "INSERT INTO player_buildings (user_id, btype, name, created_at) VALUES (?,?,?,?)",
        (user_id, btype, name, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ {info['emoji']} {info['name']} «{name}» ساخته شد.", reply_markup=main_menu(user_id))


# ============================================================
#                            حمله
# ============================================================
async def do_attack(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    clear_pending(context)
    try:
        target_id = int(text.strip())
    except ValueError:
        await update.message.reply_text("آیدی نامعتبره.", reply_markup=main_menu(user_id))
        return
    if target_id == user_id:
        await update.message.reply_text("نمی‌تونی به خودت حمله کنی!", reply_markup=main_menu(user_id))
        return

    attacker = get_player(user_id)
    defender = get_player(target_id)
    if not defender or not defender["alive"]:
        await update.message.reply_text("این بازیکن وجود نداره یا از قبل نابود شده.", reply_markup=main_menu(user_id))
        return

    atk_units = get_units(user_id)
    atk_power = sum(qty * FLAT_UNITS[k]["attack"] for k, qty in atk_units.items())
    if atk_power == 0:
        await update.message.reply_text("هیچ نیروی نظامی نداری! اول تجهیزات بساز.", reply_markup=main_menu(user_id))
        return

    def_units = get_units(target_id)
    def_power = sum(qty * FLAT_UNITS[k]["defense"] for k, qty in def_units.items())

    net_power = max(0, atk_power - def_power * 0.5)
    population_loss = min(int(net_power * 2000), defender["population"])
    resource_loss_ratio = 0.15 if net_power > 0 else 0.0

    conn = db()
    # مصرف کل تجهیزات مهاجم (حمله‌ی همه‌جانبه)
    conn.execute("DELETE FROM player_units WHERE user_id=?", (user_id,))
    # نصف تجهیزات مدافع از بین می‌ره
    conn.execute("UPDATE player_units SET quantity=quantity/2 WHERE user_id=?", (target_id,))
    conn.execute("DELETE FROM player_units WHERE user_id=? AND quantity<=0", (target_id,))
    conn.execute(
        """UPDATE players SET
            population=population-?,
            money=CAST(money*(1-?) AS INTEGER),
            oil=CAST(oil*(1-?) AS INTEGER),
            iron=CAST(iron*(1-?) AS INTEGER),
            gold=CAST(gold*(1-?) AS INTEGER)
        WHERE user_id=?""",
        (population_loss, resource_loss_ratio, resource_loss_ratio, resource_loss_ratio, resource_loss_ratio, target_id),
    )
    conn.commit()

    new_defender = get_player(target_id)
    destroyed = new_defender["population"] <= 0
    if destroyed:
        conn.execute("UPDATE players SET alive=0, population=0 WHERE user_id=?", (target_id,))
        conn.commit()
    conn.close()

    result = (
        f"⚔️ حمله‌ی {attacker['country']} به {defender['country']}!\n"
        f"قدرت حمله: {int(atk_power)} | قدرت دفاع: {int(def_power)}\n"
        f"تلفات جمعیت دشمن: {fmt(population_loss)} نفر\n"
    )
    if destroyed:
        result += f"\n💀 کشور {defender['country']} کاملاً نابود شد!"
    await update.message.reply_text(result, reply_markup=main_menu(user_id))

    try:
        note = f"🚨 کشورت مورد حمله‌ی {attacker['country']} قرار گرفت!\nتلفات جمعیت: {fmt(population_loss)} نفر"
        if destroyed:
            note += "\n💀 متاسفانه کشورت نابود شد."
        await context.bot.send_message(chat_id=target_id, text=note)
    except Exception:
        pass


# ============================================================
#                    هندلر دکمه‌های شیشه‌ای (Inline)
# ============================================================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    # ---------- انتخاب دسته‌ی تجهیزات ----------
    if data.startswith("cat:"):
        category = data.split(":", 1)[1]
        await query.edit_message_text(
            f"{CATEGORY_NAMES[category]} — یکی رو انتخاب کن:", reply_markup=units_list_kb(category)
        )
        return

    if data == "cat_back":
        await query.edit_message_text("کدوم دسته از تجهیزات رو می‌خوای بسازی؟", reply_markup=units_category_kb())
        return

    if data.startswith("unit:"):
        unit_key = data.split(":", 1)[1]
        info = FLAT_UNITS[unit_key]
        set_pending(context, "await_build_qty", unit_key=unit_key)
        await query.message.reply_text(
            f"چند تا {info['emoji']} {info['name']} می‌خوای بسازی؟ (فقط عدد بفرست)",
            reply_markup=cancel_menu(),
        )
        return

    # ---------- ساخت شهر/معدن ----------
    if data.startswith("build:"):
        btype = data.split(":", 1)[1]
        info = BUILDINGS[btype]
        if count_buildings(user_id, btype) >= info["cap"]:
            await query.message.reply_text(f"سقف ساخت {info['name']} پره ({info['cap']} تا).")
            return
        set_pending(context, "await_building_name", btype=btype)
        await query.message.reply_text(f"اسم دلخواه برای این {info['name']} رو بفرست:", reply_markup=cancel_menu())
        return

    # ---------- تایید/رد درخواست کشور توسط ادمین ----------
    if data.startswith("approve:") or data.startswith("reject:"):
        if not is_admin(user_id):
            return
        action, target_id_str = data.split(":", 1)
        target_id = int(target_id_str)
        pending_requests = context.bot_data.get("pending_requests", {})
        req = pending_requests.get(target_id)
        if not req:
            await query.edit_message_text("این درخواست دیگه معتبر نیست (شاید قبلاً پردازش شده).")
            return

        if action == "reject":
            pending_requests.pop(target_id, None)
            await query.edit_message_text(f"❌ درخواست کشور «{req['country_name']}» رد شد.")
            try:
                await context.bot.send_message(chat_id=target_id, text="متاسفانه درخواست کشورت رد شد.")
            except Exception:
                pass
            return

        # approve -> از ادمین جمعیت رو می‌پرسیم
        set_pending(context, "await_admin_population", target_user_id=target_id, country_name=req["country_name"])
        await query.edit_message_text(
            f"✅ در حال تایید «{req['country_name']}» برای آیدی {target_id}.\n"
            "جمعیت این کشور رو به عدد بفرست (مثلاً 5000000):"
        )
        return

    # ---------- پنل مدیریت ----------
    if data.startswith("admin:"):
        if not is_admin(user_id):
            return
        sub = data.split(":", 1)[1]

        if sub == "pending":
            pending_requests = context.bot_data.get("pending_requests", {})
            if not pending_requests:
                await query.message.reply_text("هیچ درخواست در انتظاری نیست.")
                return
            for uid, req in pending_requests.items():
                kb = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("✅ تایید", callback_data=f"approve:{uid}"), InlineKeyboardButton("❌ رد", callback_data=f"reject:{uid}")]]
                )
                await query.message.reply_text(
                    f"بازیکن: @{req['username']} (`{uid}`)\nنام کشور پیشنهادی: {req['country_name']}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=kb,
                )
            return

        if sub == "profit":
            summary = apply_daily_profit()
            await query.message.reply_text(f"💰 سود روزانه اعمال شد.\n{summary}")
            return

        if sub == "give":
            set_pending(context, "await_admin_give_userid")
            await query.message.reply_text("آیدی عددی بازیکن رو بفرست:", reply_markup=cancel_menu())
            return

        if sub == "list":
            conn = db()
            rows = conn.execute("SELECT * FROM players ORDER BY created_at").fetchall()
            conn.close()
            if not rows:
                await query.message.reply_text("هیچ بازیکنی ثبت نشده.")
                return
            text = "👑 *همه بازیکنان:*\n"
            for r in rows:
                icon = "✅" if r["alive"] else "💀"
                text += f"{icon} `{r['user_id']}` — {r['country']} ({fmt(r['population'])} نفر)\n"
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return

        if sub == "remove":
            set_pending(context, "await_admin_remove_userid")
            await query.message.reply_text("آیدی عددی بازیکنی که می‌خوای حذف بشه رو بفرست:", reply_markup=cancel_menu())
            return

    # ---------- انتخاب نوع منبع برای افزودن (ادمین) ----------
    if data.startswith("giveres:"):
        if not is_admin(user_id):
            return
        resource = data.split(":", 1)[1]
        pending = get_pending(context) or {}
        target_id = pending.get("target_user_id")
        if not target_id:
            await query.message.reply_text("خطا: ابتدا آیدی بازیکن رو بفرست.")
            return
        set_pending(context, "await_admin_give_amount", target_user_id=target_id, resource=resource)
        await query.message.reply_text(f"مقدار {RESOURCE_NAMES.get(resource,'جمعیت')} که می‌خوای اضافه کنی رو بفرست:", reply_markup=cancel_menu())
        return


# ============================================================
#                  ادامه‌ی فلوهای ادمین (بعد از دریافت متن)
# ============================================================
async def do_approve_with_population(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, target_user_id: int, country_name: str):
    clear_pending(context)
    try:
        population = int(text.strip())
        if population <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("عدد جمعیت نامعتبره. دوباره تلاش کن.")
        return

    if get_player(target_user_id):
        await update.message.reply_text("این بازیکن از قبل کشور داره.")
        return

    conn = db()
    conn.execute(
        """INSERT INTO players (user_id, country, population, money, oil, iron, gold, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            target_user_id,
            country_name,
            population,
            DEFAULT_START["money"],
            DEFAULT_START["oil"],
            DEFAULT_START["iron"],
            DEFAULT_START["gold"],
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    pending_requests = context.bot_data.get("pending_requests", {})
    pending_requests.pop(target_user_id, None)

    await update.message.reply_text(f"✅ کشور «{country_name}» با جمعیت {fmt(population)} ساخته شد.")
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎉 تبریک! کشور «{country_name}» تاییدشد. از دکمه‌ی «{BTN_STATUS}» وضعیتت رو ببین.",
            reply_markup=main_menu(target_user_id),
        )
    except Exception:
        pass


async def ask_give_resource_type(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        target_id = int(text.strip())
    except ValueError:
        await update.message.reply_text("آیدی نامعتبره.")
        return
    if not get_player(target_id):
        await update.message.reply_text("این بازیکن کشوری نداره.")
        clear_pending(context)
        return
    set_pending(context, "await_admin_give_userid", target_user_id=target_id)
    await update.message.reply_text("کدوم منبع رو می‌خوای اضافه کنی؟", reply_markup=resource_choice_kb("giveres"))


async def do_give_resource(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, target_user_id: int, resource: str):
    clear_pending(context)
    try:
        amount = int(text.strip())
    except ValueError:
        await update.message.reply_text("مقدار نامعتبره.")
        return
    conn = db()
    conn.execute(f"UPDATE players SET {resource}={resource}+? WHERE user_id=?", (amount, target_user_id))
    conn.commit()
    conn.close()
    res_label = RESOURCE_NAMES.get(resource, "جمعیت")
    await update.message.reply_text(f"✅ {fmt(amount)} {res_label} به بازیکن {target_user_id} اضافه شد.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"🎁 ادمین {fmt(amount)} {res_label} به کشورت اضافه کرد.")
    except Exception:
        pass


async def do_remove_player(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    clear_pending(context)
    try:
        target_id = int(text.strip())
    except ValueError:
        await update.message.reply_text("آیدی نامعتبره.")
        return
    conn = db()
    conn.execute("DELETE FROM players WHERE user_id=?", (target_id,))
    conn.execute("DELETE FROM player_units WHERE user_id=?", (target_id,))
    conn.execute("DELETE FROM player_buildings WHERE user_id=?", (target_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"بازیکن {target_id} حذف شد.")


# ============================================================
#                        سود روزانه
# ============================================================
def apply_daily_profit() -> str:
    conn = db()
    players = conn.execute("SELECT user_id, country FROM players WHERE alive=1").fetchall()
    affected = 0
    for p in players:
        buildings = conn.execute(
            "SELECT btype FROM player_buildings WHERE user_id=?", (p["user_id"],)
        ).fetchall()
        if not buildings:
            continue
        totals = {"money": 0, "oil": 0, "iron": 0, "gold": 0}
        for b in buildings:
            profit = BUILDINGS[b["btype"]]["profit"]
            for res, amount in profit.items():
                totals[res] += amount
        keys_with_values = [k for k in totals if totals[k]]
        if keys_with_values:
            set_clause = ", ".join(f"{k}={k}+?" for k in keys_with_values)
            conn.execute(
                f"UPDATE players SET {set_clause} WHERE user_id=?",
                (*[totals[k] for k in keys_with_values], p["user_id"]),
            )
            affected += 1
    conn.commit()
    conn.close()
    return f"سود به {affected} بازیکن (دارای شهر/معدن) داده شد."


# ============================================================
#                            main
# ============================================================
def main():
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("⚠️  لطفاً BOT_TOKEN را در متغیر محیطی تنظیم کنید.")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    logger.info("بات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
