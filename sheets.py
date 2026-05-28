import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "")


def _post(data: dict) -> dict:
    if not APPS_SCRIPT_URL:
        raise RuntimeError("APPS_SCRIPT_URL не задан в .env")
    resp = requests.post(APPS_SCRIPT_URL, json=data, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if result.get("status") != "ok":
        raise RuntimeError(result.get("message", "Ошибка Apps Script"))
    return result


def add_transaction(amount: float, op_type: str, category: str, comment: str = "", date: str = "") -> int:
    if not date:
        date = datetime.now().strftime("%d.%m.%Y")
    result = _post({
        "action": "add",
        "date": date,
        "amount": amount,
        "op_type": op_type,
        "comment": comment,
        "category": category,
    })
    return result.get("row", 0)


def weekly_report() -> dict:
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())

    result = _post({
        "action": "report",
        "date_from": week_start.strftime("%d.%m.%Y"),
        "date_to": today.strftime("%d.%m.%Y"),
    })

    expenses = {}
    incomes = {}

    for op in result.get("data", []):
        cat = op.get("category") or "Прочие"
        amt = float(op.get("amount", 0))
        if op.get("op_type") == "Расход":
            expenses[cat] = expenses.get(cat, 0) + amt
        elif op.get("op_type") == "Доход":
            incomes[cat] = incomes.get(cat, 0) + amt

    return {
        "week_start": week_start,
        "today": today,
        "expenses": expenses,
        "incomes": incomes,
        "total_expenses": sum(expenses.values()),
        "total_incomes": sum(incomes.values()),
    }


def monthly_summary() -> dict:
    result = _post({"action": "balance"})
    return {
        "income": float(result.get("income", 0)),
        "expenses": float(result.get("expenses", 0)),
        "balance": float(result.get("balance", 0)),
    }
