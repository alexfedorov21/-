import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from flask import Flask
from threading import Thread

TOKEN = "8929241175:AAGhMNIdaGVj5dPWETPaPL5UEfRauU8InRI"
WORKERS = ["Сергей", "Денис", "Иван", "Александр"]

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
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)

def get_hours_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("4 ч", callback_data="hours_4"),
         InlineKeyboardButton("6 ч", callback_data="hours_6"),
         InlineKeyboardButton("8 ч", callback_data="hours_8")],
        [InlineKeyboardButton("10 ч", callback_data="hours_10"),
         InlineKeyboardButton("12 ч", callback_data="hours_12"),
         InlineKeyboardButton("✏️ Своё", callback_data="hours_other")],
    ])

def build_today_text():
    today = datetime.now().strftime("%Y-%m-%d")
    checkins = get_today_list()
    if checkins:
        names = [f"• {n} — {h} ч" for n, h in checkins]
        total = sum(float(h) for _, h in checkins)
        return f"📅 *{today}*\n👥 ({len(checkins)} чел, {total} ч):\n" + "\n".join(names)
    return f"📅 *{today}*\nНикого."

async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_today_text(), reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_today_text(), parse_mode="Markdown")

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    u = q.from_user
    d = q.data

    if d == "checkin":
        await q.message.edit_text("👤 Выбери сотрудника:", reply_markup=get_workers_keyboard("add"))
    elif d == "uncheckin":
        kb = get_workers_keyboard("remove")
        if kb is None:
            await q.answer("Нечего удалять.")
            return
        await q.message.edit_text("🗑 Выбери для удаления:", reply_markup=kb)
    elif d.startswith("remove_"):
        w = d.split("_", 1)[1]
        delete_worker_checkin(w)
        await q.answer(f"❌ {w} удалён")
        await q.message.edit_text(build_today_text(), reply_markup=get_main_keyboard(), parse_mode="Markdown")
    elif d.startswith("worker_"):
        w = d.split("_", 1)[1]
        context.user_data["selected_worker"] = w
        existing = get_worker_today(w)
        txt = f"👤 {w}\nСейчас: {existing[0]} ч\nНовые часы:" if existing else f"👤 {w}\nВыбери часы:"
        await q.message.edit_text(txt, reply_markup=get_hours_keyboard())
    elif d.startswith("hours_"):
        h = d.split("_", 1)[1]
        w = context.user_data.get("selected_worker")
        if not w:
            return
        if h == "other":
            context.user_data["awaiting_hours"] = True
            context.user_data["selected_worker"] = w
            await q.message.edit_text(f"👤 {w}\n✏️ Напиши свои часы числом (например, 5.5):")
            return
        add_checkin(u.id, u.username or "", w, h)
        await q.answer(f"✅ {w}: {h} ч")
        await q.message.edit_text(build_today_text(), reply_markup=get_main_keyboard(), parse_mode="Markdown")
        context.user_data.pop("selected_worker", None)
    elif d == "back_main":
        await q.message.edit_text(build_today_text(), reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_hours"):
        return
    t = update.message.text.strip().replace(",", ".")
    w = context.user_data.get("selected_worker")
    if not w:
        return
    try:
        hours = float(t)
        if hours <= 0 or hours > 24:
            raise ValueError
        hs = str(int(hours)) if hours == int(hours) else str(hours)
    except:
        await update.message.reply_text("❌ Введи число от 0.5 до 24.")
        return
    add_checkin(update.effective_user.id, update.effective_user.username or "", w, hs)
    context.user_data["awaiting_hours"] = False
    context.user_data.pop("selected_worker", None)
    await update.message.reply_text(f"✅ {w}: {hs} ч")
    await update.message.reply_text(build_today_text(), parse_mode="Markdown")

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    web = Flask(__name__)
    @web.route('/')
    def home():
        return "OK"
    Thread(target=lambda: web.run(host='0.0.0.0', port=10000)).start()

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
