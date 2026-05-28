// ═══════════════════════════════════════════════════════════════
// Вставь этот код в Google Apps Script твоей таблицы:
// Расширения → Apps Script → вставь → Сохрани → Развернуть
// ═══════════════════════════════════════════════════════════════

const SPREADSHEET_ID = "1-Xj_JrWZpQuZRs57b2uSbqPUD_17xHTRgHvgJhTWxnc";

const MONTH_SHEETS = {
  1: "Янв26",  2: "Февр26", 3: "Март26",  4: "Апр26",
  5: "Май26",  6: "Июнь26", 7: "Июль26",  8: "Авг26",
  9: "Сент26", 10: "Окт26", 11: "Нояб26", 12: "Дек26"
};

const DATA_START_ROW = 6;  // строка с первой транзакцией
// Столбцы: H=8(дата), I=9(сумма), J=10(тип), K=11(комментарий), L=12(категория)

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    switch (body.action) {
      case "add":     return respond(addTransaction(body));
      case "report":  return respond(getReport(body));
      case "balance": return respond(getBalance());
      default:        return respond({status: "error", message: "unknown action"});
    }
  } catch (err) {
    return respond({status: "error", message: err.toString()});
  }
}

// ─── Получить текущий лист (по месяцу) ───────────────────────
function getCurrentSheet() {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const month = new Date().getMonth() + 1;
  const name = MONTH_SHEETS[month];
  const sheet = ss.getSheetByName(name);
  if (!sheet) throw new Error("Лист не найден: " + name);
  return sheet;
}

// ─── Добавить транзакцию ──────────────────────────────────────
function addTransaction(data) {
  const sheet = getCurrentSheet();

  // Найти первую пустую строку в колонке H начиная с DATA_START_ROW
  const colH = sheet.getRange(1, 8, sheet.getLastRow() + 1, 1).getValues();
  let nextRow = DATA_START_ROW;
  for (let i = DATA_START_ROW - 1; i < colH.length; i++) {
    if (!colH[i][0]) { nextRow = i + 1; break; }
    nextRow = i + 2;
  }

  sheet.getRange(nextRow, 8, 1, 5).setValues([
    [data.date, data.amount, data.op_type, data.comment || "", data.category]
  ]);

  return {status: "ok", row: nextRow};
}

// ─── Отчёт за период ─────────────────────────────────────────
function getReport(data) {
  const sheet = getCurrentSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) return {status: "ok", data: []};

  const rows = sheet.getRange(DATA_START_ROW, 8, lastRow - DATA_START_ROW + 1, 5).getValues();

  const from = parseDate(data.date_from);
  const to   = parseDate(data.date_to);
  to.setHours(23, 59, 59);

  const result = [];
  for (const r of rows) {
    if (!r[0]) continue;
    const d = r[0] instanceof Date ? r[0] : parseDate(r[0].toString());
    if (!d || d < from || d > to) continue;
    result.push({
      date:     r[0] instanceof Date ? formatDate(r[0]) : r[0],
      amount:   r[1],
      op_type:  r[2],
      comment:  r[3],
      category: r[4]
    });
  }
  return {status: "ok", data: result};
}

// ─── Баланс за текущий месяц ──────────────────────────────────
function getBalance() {
  const sheet = getCurrentSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) return {status: "ok", income: 0, expenses: 0, balance: 0};

  const rows = sheet.getRange(DATA_START_ROW, 8, lastRow - DATA_START_ROW + 1, 5).getValues();
  let income = 0, expenses = 0;
  for (const r of rows) {
    if (!r[0] || !r[1]) continue;
    const amt = parseFloat(r[1]) || 0;
    if (r[2] === "Доход")   income   += amt;
    if (r[2] === "Расход")  expenses += amt;
  }
  return {status: "ok", income, expenses, balance: income - expenses};
}

// ─── Вспомогательные ─────────────────────────────────────────
function parseDate(str) {
  if (!str) return null;
  const p = str.toString().split(".");
  if (p.length !== 3) return null;
  return new Date(p[2] + "-" + p[1] + "-" + p[0]);
}

function formatDate(d) {
  return Utilities.formatDate(d, "GMT+3", "dd.MM.yyyy");
}

function respond(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
