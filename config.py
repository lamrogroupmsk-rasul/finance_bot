import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SPREADSHEET_ID = "1-Xj_JrWZpQuZRs57b2uSbqPUD_17xHTRgHvgJhTWxnc"

# Your Telegram user ID (leave empty to allow anyone)
ALLOWED_USER_IDS = [int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]

EXPENSE_CATEGORIES = [
    "Кафе", "Кофе", "Магазин", "Медицина", "Бензин",
    "Продукты", "Работа", "Прочие", "Домашние платежи",
    "Вика", "Расул", "Кредит", "Развлечения",
]

INCOME_CATEGORIES = ["СК Небо", "Исаев Групп", "Скрапмет"]

# Sheet tab names by month number
MONTH_SHEETS = {
    1: "Янв26",
    2: "Февр26",
    3: "Март26",
    4: "Апр26",
    5: "Май26",
    6: "Июнь26",
    7: "Июль26",
    8: "Авг26",
    9: "Сент26",
    10: "Окт26",
    11: "Нояб26",
    12: "Дек26",
}

# Operations table layout (1-indexed columns)
COL_DATE = 8       # H
COL_AMOUNT = 9     # I
COL_TYPE = 10      # J — "Доход" or "Расход"
COL_COMMENT = 11   # K
COL_CATEGORY = 12  # L

DATA_START_ROW = 6  # First transaction row

# Weekly report schedule (Moscow time)
TIMEZONE = "Europe/Moscow"
REPORT_DAY_OF_WEEK = "mon"   # mon, tue, wed, thu, fri, sat, sun
REPORT_HOUR = 9
REPORT_MINUTE = 0
