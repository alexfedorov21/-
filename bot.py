import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from flask import Flask
from threading import Thread

TOKEN = "8929241175:AAHX53utdWnRLhRJl5VtKBaZ5n5Taab2CGU"
WORKERS = ["Сергей", "Денис", "Иван", "Александр"]

# --- База данных ---
def init_db():
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS checkins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, telegram_username TEXT,
        worker_name TEXT, date TEXT, hours TEXT,
        UNIQUE(worker_name, date))""")
    conn.commit()
    conn.close()

def add_checkin(user_id, telegram_username, worker_name, hours):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO checkins VALUES (?, ?, ?, ?, ?)",
              (user_id, telegram_username, worker_name, today, hours))
    conn.commit()
    conn.close()

def delete_worker_checkin(worker_name):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("DELETE FROM checkins WHERE worker_name = ? AND date = ?", (worker_name, today))
    conn.commit()
    conn.close()

def get_today_list():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("SELECT worker_name, hours FROM checkins WHERE date = ? ORDER BY worker_name", (today,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_worker_today(worker_name):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("SELECT hours FROM checkins WHERE worker_name = ? AND date = ?", (worker_name, today))
    row = c.fetchone()
    conn.close()
    return row

# --- Клавиатуры ---
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отметить сотрудника", callback_data="checkin")],
        [InlineKeyboardButton("❌ Удалить отметку", callback_data="uncheckin")]
    ])

def get_workers_keyboard(action="add"):
    keyboard = []
    for worker in WORKERS:
        existing = get_worker_today(worker)
        if existing and action == "add":
            keyboard.append([InlineKeyboardButton(f"✏️ {worker} ({existing[0]} ч)", callback_data=f"worker_{worker}")])
        elif existing and action == "remove":
            keyboard.append([InlineKeyboardButton(f"❌ {worker}", callback_data=f"remove_{worker}")])
        elif not existing and action == "add":
            keyboard.append([InlineKeyboardButton(f"➕ {worker}", callback_data=f"worker_{worker}")])
    if action == "remove" and not any(get_worker_today(w) for w in WORKERS):
        return None
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)

def get_hours_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("4 ч", callback_data="hours_4"), InlineKeyboardButton("6 ч", callback_data="hours_6"), InlineKeyboardButton("8 ч", callback_data="hours_8")],
        [InlineKeyboardButton("10 ч", callback_data="hours_10"), InlineKeyboardButton("12 ч", callback_data="hours_12"), InlineKeyboardButton("✏️ Своё", callback_data="hours_other")],
    ])

def build_today_text():
    today = datetime.now().strftime("%Y-%m-%d")
    checkins = get_today_list()
    if checkins:
        names = [f"• {n} — {h} ч" for n, h in checkins]
        total = sum(float(h) for _, h in checkins)
        return f"📅 *{today}*\n👥 На смене ({len(checkins)} чел, {total} ч):\n" + "\n".join(names)
    return f"📅 *{today}*\nПока никто не отметился."

# --- Команды ---
async def checkin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_today_text(), reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_today_text(), parse_mode="Markdown")

async def month_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    now = datetime.now()
    month, year = now.month, now.year
    if args:
        try:
            month = int(args[0])
            if len(args) > 1:
                year = int(args[1])
        except:
            pass
    month_names = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year+1}-01-01"
    else:
        end = f"{year}-{month+1:02d}-01"
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("SELECT worker_name, date, hours FROM checkins WHERE date >= ? AND date < ? ORDER BY worker_name, date", (start, end))
    rows = c.fetchall()
    conn.close()
    if rows:
        workers = {}
        for w, d, h in rows:
            if w not in workers:
                workers[w] = {"total": 0, "days": []}
            workers[w]["total"] += float(h)
            workers[w]["days"].append(f"{datetime.strptime(d, '%Y-%m-%d').strftime('%d.%m')}: {h} ч")
        text = f"📊 *{month_names[month]} {year}*\n\n"
        for w, data in workers.items():
            text += f"• *{w}*: {data['total']} ч\n   {', '.join(data['days'])}\n\n"
    else:
        text = f"📊 *{month_names[month]} {year}*\n\nНет данных."
    await update.message.reply_text(text, parse_mode="Markdown")

# --- Кнопки ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "checkin":
        await query.message.edit_text("👤 Выбери сотрудника:", reply_markup=get_workers_keyboard("add"))
    elif query.data == "uncheckin":
        kb = get_workers_keyboard("remove")
        if kb is None:
            await query.answer("Нечего удалять.")
            return
        await query.message.edit_text("Выбери для удаления:", reply_markup=kb)
    elif query.data.startswith("remove_"):
        worker_name = query.data.split("_", 1)[1]
        delete_worker_checkin(worker_name)
        await query.answer(f"❌ {worker_name} удалён.")
        await query.message.edit_text(build_today_text(), reply_markup=get_main_keyboard(), parse_mode="Markdown")
    elif query.data.startswith("worker_"):
        worker_name = query.data.split("_", 1)[1]
        context.user_data["selected_worker"] = worker_name
        await query.message.edit_text(f"👤 {worker_name}\nВыбери часы:", reply_markup=get_hours_keyboard())
    elif query.data.startswith("hours_"):
        hours = query.data.split("_", 1)[1]
        worker_name = context.user_data.get("selected_worker")
        if not worker_name: return
        if hours == "other":
            context.user_data["awaiting_hours"] = True
            await query.message.edit_text(f"👤 {worker_name}\n✏️ Напиши количество часов:")
            return
        add_checkin(user.id, user.username or "", worker_name, hours)
        await query.answer(f"✅ {worker_name}: {hours} ч")
        await query.message.edit_text(build_today_text(), reply_markup=get_main_keyboard(), parse_mode="Markdown")
        context.user_data.pop("selected_worker", None)
    elif query.data == "back_main":
        await query.message.edit_text(build_today_text(), reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_hours"): return
    text = update.message.text.strip().replace(",", ".")
    worker_name = context.user_data.get("selected_worker")
    try:
        hours = float(text)
        hours_str = str(int(hours)) if hours == int(hours) else str(hours)
    except:
        await update.message.reply_text("❌ Введи число.")
        return
    add_checkin(update.effective_user.id, update.effective_user.username or "", worker_name, hours_str)
    context.user_data["awaiting_hours"] = False
    await update.message.reply_text(f"✅ {worker_name}: {hours_str} ч")

# --- Запуск ---
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("checkin", checkin_cmd))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("month", month_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Flask-заглушка для Render
    web = Flask(__name__)
    @web.route('/')
    def home():
        return "OK"
       Thread(target=lambda: web.run(host='0.0.0.0', port=10000)).start()

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
