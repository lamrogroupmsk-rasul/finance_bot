import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import sheets
from config import (
    ALLOWED_USER_IDS,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    MONTH_SHEETS,
    REPORT_DAY_OF_WEEK,
    REPORT_HOUR,
    REPORT_MINUTE,
    TELEGRAM_BOT_TOKEN,
    TIMEZONE,
)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

CHAT_IDS_FILE = Path("data/chat_ids.json")
CHAT_IDS_FILE.parent.mkdir(exist_ok=True)


# ─── Chat ID storage ──────────────────────────────────────────────────────────

def load_chat_ids():
    if CHAT_IDS_FILE.exists():
        return set(json.loads(CHAT_IDS_FILE.read_text()))
    return set()


def save_chat_id(chat_id: int):
    ids = load_chat_ids()
    ids.add(chat_id)
    CHAT_IDS_FILE.write_text(json.dumps(list(ids)))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def fmt(amount: float) -> str:
    return f"{amount:,.0f}₽".replace(",", " ")


def is_allowed(user_id: int) -> bool:
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


# ─── Message parser ───────────────────────────────────────────────────────────

INCOME_TRIGGERS = r"^(приход|доход|получил[а]?|п)\s+"

ALL_CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES

# Number pattern: handles 1500, 1 500, 50 000, 1500.50
_NUM_RE = re.compile(r"(\d{1,3}(?:\s\d{3})+|\d+)(?:[.,](\d+))?")


def _parse_amount(s: str):
    """Extract first number from string, return (amount, match) or (None, None)."""
    m = _NUM_RE.search(s)
    if not m:
        return None, None
    integer_part = m.group(1).replace(" ", "")
    decimal_part = m.group(2) or "0"
    try:
        return float(f"{integer_part}.{decimal_part}"), m
    except ValueError:
        return None, None


def _match_category(text: str, candidates: list):
    """Find first category that appears in text (longest match wins)."""
    for cat in sorted(candidates, key=len, reverse=True):
        if cat.lower() in text.lower():
            return cat
    return None


_DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")


def parse_transaction(text: str):
    """
    Formats accepted:
      Магазин 2100                          → сегодня, Расход
      26.05.2026 Кафе 1500 обед             → указанная дата, Расход
      доход СК Небо 50000                   → сегодня, Доход
      26.05.2026 доход Исаев Групп 125000   → указанная дата, Доход
    Returns None if no amount found.
    """
    text = text.strip()

    # Extract date if present (DD.MM.YYYY)
    date_m = _DATE_RE.search(text)
    if date_m:
        date_str = date_m.group(1)
        text = (text[:date_m.start()] + text[date_m.end():]).strip()
    else:
        date_str = datetime.now().strftime("%d.%m.%Y")

    # Detect income explicitly; everything else is expense
    income_m = re.match(INCOME_TRIGGERS, text, re.IGNORECASE)
    if income_m:
        op_type = "Доход"
        rest = text[income_m.end():].strip()
        candidates = INCOME_CATEGORIES
    else:
        op_type = "Расход"
        rest = text
        candidates = EXPENSE_CATEGORIES

    amount, num_m = _parse_amount(rest)
    if amount is None:
        return None

    before = rest[:num_m.start()].strip()
    after  = rest[num_m.end():].strip()

    # Find category in before, then after
    category = _match_category(before, candidates) or _match_category(after, candidates)

    # Build comment from whatever is left after removing category
    leftovers = (before + " " + after).strip()
    if category:
        comment = re.sub(re.escape(category), "", leftovers, flags=re.IGNORECASE).strip()
    else:
        comment = leftovers

    return {"op_type": op_type, "amount": amount, "category": category, "comment": comment, "date": date_str}


# ─── Keyboards ────────────────────────────────────────────────────────────────

def category_keyboard(op_type: str) -> InlineKeyboardMarkup:
    cats = EXPENSE_CATEGORIES if op_type == "Расход" else INCOME_CATEGORIES
    buttons = []
    row: list = []
    for i, cat in enumerate(cats):
        row.append(InlineKeyboardButton(cat, callback_data=f"cat|{i}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    save_chat_id(update.effective_chat.id)
    await update.message.reply_text(
        "👋 *Бот учёта финансов*\n\n"
        "Пиши операции в свободном виде:\n"
        "`расход 1500 кафе обед` — расход\n"
        "`р 500 кофе` — сокращённо\n"
        "`приход 50000 СК Небо зарплата` — доход\n"
        "`п 10000 Исаев Групп` — сокращённо\n\n"
        "Команды:\n"
        "/report — отчёт за неделю\n"
        "/balance — баланс за месяц\n"
        "/help — категории и помощь",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "📖 *Справка*\n\n"
        "*Расходы:* `расход / р / трата / потратил`\n"
        "*Доходы:* `приход / п / доход / получил`\n\n"
        "*Категории расходов:*\n" + " · ".join(EXPENSE_CATEGORIES) + "\n\n"
        "*Категории доходов:*\n" + " · ".join(INCOME_CATEGORIES) + "\n\n"
        "Если категория не указана — бот предложит выбрать.\n"
        "Комментарий пиши после категории: `р 1500 кафе обед с другом`",
        parse_mode="Markdown",
    )


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    msg = await update.message.reply_text("⏳ Формирую отчёт…")
    await _send_weekly_report(ctx, update.effective_chat.id, msg)


async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    msg = await update.message.reply_text("⏳ Загружаю…")
    try:
        data = sheets.monthly_summary()
        month_name = MONTH_SHEETS.get(datetime.now().month, "?")
        sign = "✅" if data["balance"] >= 0 else "❌"
        text = (
            f"💰 *Баланс за {month_name}*\n\n"
            f"📥 Доходы: *{fmt(data['income'])}*\n"
            f"📤 Расходы: *{fmt(data['expenses'])}*\n"
            f"{sign} Остаток: *{fmt(data['balance'])}*"
        )
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        log.exception("balance error")
        await msg.edit_text(f"❌ Ошибка: {e}")


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return

    text = update.message.text or ""
    parsed = parse_transaction(text)

    if parsed is None:
        await update.message.reply_text(
            "Не понял 🤔\nПример: `расход 1500 кафе` или `приход 50000 СК Небо`",
            parse_mode="Markdown",
        )
        return

    if parsed["category"] is None:
        # Ask user to pick category
        ctx.user_data["pending"] = parsed
        emoji = "📤" if parsed["op_type"] == "Расход" else "📥"
        await update.message.reply_text(
            f"{emoji} *{parsed['op_type']}* {fmt(parsed['amount'])}\n\nВыбери категорию:",
            parse_mode="Markdown",
            reply_markup=category_keyboard(parsed["op_type"]),
        )
    else:
        await _record(update.message.reply_text, ctx, parsed)


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        ctx.user_data.pop("pending", None)
        await query.edit_message_text("❌ Отменено")
        return

    if query.data.startswith("cat|"):
        pending = ctx.user_data.get("pending")
        if not pending:
            await query.edit_message_text("❌ Сессия истекла, попробуй снова")
            return

        idx = int(query.data.split("|")[1])
        cats = EXPENSE_CATEGORIES if pending["op_type"] == "Расход" else INCOME_CATEGORIES
        if idx >= len(cats):
            await query.edit_message_text("❌ Ошибка")
            return

        pending["category"] = cats[idx]
        ctx.user_data.pop("pending", None)
        await query.edit_message_text("⏳ Записываю…")
        await _record(query.edit_message_text, ctx, pending)


async def _record(reply_fn, ctx, parsed: dict):
    """Write transaction to sheet and send confirmation."""
    try:
        date = parsed.get("date") or datetime.now().strftime("%d.%m.%Y")
        row = sheets.add_transaction(
            amount=parsed["amount"],
            op_type=parsed["op_type"],
            category=parsed["category"],
            comment=parsed["comment"],
            date=date,
        )
        emoji = "📤" if parsed["op_type"] == "Расход" else "📥"
        text = (
            f"✅ *Записано!*\n\n"
            f"{emoji} {parsed['op_type']} · *{fmt(parsed['amount'])}*\n"
            f"📁 {parsed['category']}\n"
        )
        if parsed["comment"]:
            text += f"💬 {parsed['comment']}\n"
        text += f"📅 {date}"
        await reply_fn(text, parse_mode="Markdown")
    except Exception as e:
        log.exception("add_transaction error")
        await reply_fn(f"❌ Ошибка при записи: {e}")


# ─── Weekly report sender ─────────────────────────────────────────────────────

async def _send_weekly_report(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, msg=None):
    try:
        data = sheets.weekly_report()
        ws = data["week_start"].strftime("%d.%m")
        we = data["today"].strftime("%d.%m.%Y")
        text = f"📊 *Недельный отчёт* {ws} — {we}\n\n"

        if data["expenses"]:
            text += "📤 *Расходы по категориям:*\n"
            for cat, amt in sorted(data["expenses"].items(), key=lambda x: -x[1]):
                text += f"  • {cat}: {fmt(amt)}\n"
            text += f"\n*Итого расходов: {fmt(data['total_expenses'])}*\n"
        else:
            text += "📤 Расходов за неделю нет\n"

        if data["incomes"]:
            text += "\n📥 *Доходы:*\n"
            for cat, amt in data["incomes"].items():
                text += f"  • {cat}: {fmt(amt)}\n"
            text += f"\n*Итого доходов: {fmt(data['total_incomes'])}*"

        balance = data["total_incomes"] - data["total_expenses"]
        sign = "✅" if balance >= 0 else "❌"
        text += f"\n\n{sign} *Баланс за неделю: {fmt(balance)}*"

        if msg:
            await msg.edit_text(text, parse_mode="Markdown")
        else:
            await ctx.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except Exception as e:
        log.exception("weekly report error")
        err = f"❌ Ошибка отчёта: {e}"
        if msg:
            await msg.edit_text(err)
        else:
            await ctx.bot.send_message(chat_id=chat_id, text=err)


async def scheduled_weekly_report(app: Application):
    """Called by APScheduler — sends report to all known chats."""
    chat_ids = load_chat_ids()
    log.info(f"Sending weekly report to {len(chat_ids)} chats")
    for cid in chat_ids:
        await _send_weekly_report(app, cid)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    tz = pytz.timezone(TIMEZONE)
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(
        lambda: app.create_task(scheduled_weekly_report(app)),
        CronTrigger(day_of_week=REPORT_DAY_OF_WEEK, hour=REPORT_HOUR, minute=REPORT_MINUTE, timezone=tz),
    )
    scheduler.start()

    log.info("Бот запущен ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
