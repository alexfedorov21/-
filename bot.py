import os
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from flask import Flask
from threading import Thread

# --- ТОКЕН ---
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    # Для локального запуска замени на свой токен:
    TOKEN = "8633693344:AAEoYCYB0s4z89ujmGRC7oarE1aNT5t6ziI"
# ------------

# --- СПИСОК СОТРУДНИКОВ ---
WORKERS = ["Сергей", "Денис", "Иван", "Александр"]

# --- База данных ---
def init_db():
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS checkins (
            user_id INTEGER,
            telegram_username TEXT,
            worker_name TEXT,
            date TEXT,
            hours TEXT,
            PRIMARY KEY (user_id, date)
        )
    """)
    conn.commit()
    conn.close()

def add_checkin(user_id, telegram_username, worker_name, hours):
    """Добавляет или обновляет отметку"""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO checkins VALUES (?, ?, ?, ?, ?)",
              (user_id, telegram_username, worker_name, today, hours))
    conn.commit()
    conn.close()

def delete_checkin(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("DELETE FROM checkins WHERE user_id = ? AND date = ?", (user_id, today))
    conn.commit()
    conn.close()

def get_today_list():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("SELECT worker_name, hours FROM checkins WHERE date = ?", (today,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_user_checkin(user_id):
    """Проверяет, отметился ли уже этот Telegram-пользователь сегодня"""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("SELECT worker_name, hours FROM checkins WHERE user_id = ? AND date = ?", (user_id, today))
    row = c.fetchone()
    conn.close()
    return row

# --- НОВОЕ: Запросы для статистики ---

def get_stats_by_period(start_date, end_date):
    """
    Возвращает статистику за период.
    Результат: список (worker_name, total_hours, days_count)
    """
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("""
        SELECT worker_name, SUM(CAST(hours AS REAL)), COUNT(DISTINCT date)
        FROM checkins
        WHERE date BETWEEN ? AND ?
        GROUP BY worker_name
        ORDER BY worker_name
    """, (start_date, end_date))
    rows = c.fetchall()
    conn.close()
    return rows

def get_daily_report(start_date, end_date):
    """
    Возвращает отчёт по дням.
    Результат: список (date, worker_name, hours)
    """
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("""
        SELECT date, worker_name, hours
        FROM checkins
        WHERE date BETWEEN ? AND ?
        ORDER BY date, worker_name
    """, (start_date, end_date))
    rows = c.fetchall()
    conn.close()
    return rows

def get_worker_monthly(worker_name, year, month):
    """
    Статистика сотрудника за конкретный месяц.
    """
    start = f"{year}-{month:02d}-01"
    # Последний день месяца
    if month == 12:
        end = f"{year}-12-31"
    else:
        end = f"{year}-{month+1:02d}-01"
    
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("""
        SELECT date, hours
        FROM checkins
        WHERE worker_name = ? AND date BETWEEN ? AND ?
        ORDER BY date
    """, (worker_name, start, end))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_workers_stats(month=None, year=None):
    """
    Статистика по всем сотрудникам за месяц.
    Если месяц не указан — текущий.
    """
    if month is None:
        month = datetime.now().month
    if year is None:
        year = datetime.now().year
    
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year}-12-31"
    else:
        end = f"{year}-{month+1:02d}-01"
    
    conn = sqlite3.connect("checkins.db")
    c = conn.cursor()
    c.execute("""
        SELECT worker_name, SUM(CAST(hours AS REAL)), COUNT(DISTINCT date)
        FROM checkins
        WHERE date BETWEEN ? AND ?
        GROUP BY worker_name
        ORDER BY worker_name
    """, (start, end))
    rows = c.fetchall()
    conn.close()
    return rows

# --- Клавиатуры ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("✅ Отметиться на смене", callback_data="checkin")],
        [InlineKeyboardButton("❌ Отменить мою отметку", callback_data="uncheckin")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_workers_keyboard():
    keyboard = []
    for worker in WORKERS:
        keyboard.append([InlineKeyboardButton(worker, callback_data=f"worker_{worker}")])
    return InlineKeyboardMarkup(keyboard)

def get_hours_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("4 ч", callback_data="hours_4"),
            InlineKeyboardButton("6 ч", callback_data="hours_6"),
            InlineKeyboardButton("8 ч", callback_data="hours_8"),
        ],
        [
            InlineKeyboardButton("10 ч", callback_data="hours_10"),
            InlineKeyboardButton("12 ч", callback_data="hours_12"),
            InlineKeyboardButton("✏️ Своё", callback_data="hours_other"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Формирование текста ---
def build_today_text():
    today = datetime.now().strftime("%Y-%m-%d")
    checkins = get_today_list()

    if checkins:
        total_hours = 0
        names = []
        for worker_name, hours in checkins:
            h = float(hours) if '.' in hours else int(hours)
            total_hours += h
            names.append(f"• {worker_name} — {h} ч")
        text = f"📅 *{today}*\n👥 На смене ({len(checkins)} чел, {total_hours} ч):\n" + "\n".join(names)
    else:
        text = f"📅 *{today}*\nПока никто не отметился."
    return text

# --- Команды ---
async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = build_today_text()
    await update.message.reply_text(
        text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = build_today_text()
    await update.message.reply_text(text, parse_mode="Markdown")

# --- НОВЫЕ КОМАНДЫ СТАТИСТИКИ ---

async def month_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /month — статистика за текущий месяц
    /month 7 — за июль
    /month 7 2026 — за июль 2026 года
    """
    args = context.args
    now = datetime.now()
    month = now.month
    year = now.year

    if len(args) >= 1:
        try:
            month = int(args[0])
            if month < 1 or month > 12:
                raise ValueError
        except:
            await update.message.reply_text("❌ Месяц должен быть числом от 1 до 12. Пример: `/month 7`", parse_mode="Markdown")
            return
    
    if len(args) >= 2:
        try:
            year = int(args[1])
        except:
            await update.message.reply_text("❌ Год должен быть числом. Пример: `/month 7 2026`", parse_mode="Markdown")
            return

    stats = get_all_workers_stats(month, year)
    
    # Названия месяцев
    month_names = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    
    if stats:
        total_hours = 0
        total_days = 0
        lines = []
        for worker_name, hours, days in stats:
            total_hours += hours
            total_days += days
            lines.append(f"• {worker_name}: {hours} ч ({days} смен)")
        text = f"📊 *{month_names[month]} {year}*\n\n" + "\n".join(lines)
        text += f"\n\n👥 Всего: {total_hours} ч, {total_days} смен"
    else:
        text = f"📊 *{month_names[month]} {year}*\n\nНет данных за этот месяц."

    await update.message.reply_text(text, parse_mode="Markdown")

async def worker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /worker Иван — статистика сотрудника за текущий месяц
    /worker Иван 7 — за июль
    /worker Иван 7 2026 — за июль 2026 года
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Укажи имя сотрудника. Пример: `/worker Иван`\n"
            "Доступные имена: " + ", ".join(WORKERS),
            parse_mode="Markdown"
        )
        return

    worker_name = args[0]
    if worker_name not in WORKERS:
        await update.message.reply_text(
            f"❌ Сотрудник не найден. Доступные: {', '.join(WORKERS)}",
            parse_mode="Markdown"
        )
        return

    now = datetime.now()
    month = now.month
    year = now.year

    if len(args) >= 2:
        try:
            month = int(args[1])
            if month < 1 or month > 12:
                raise ValueError
        except:
            await update.message.reply_text("❌ Месяц должен быть числом от 1 до 12.")
            return
    
    if len(args) >= 3:
        try:
            year = int(args[2])
        except:
            await update.message.reply_text("❌ Год должен быть числом.")
            return

    records = get_worker_monthly(worker_name, year, month)
    
    month_names = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

    if records:
        total_hours = 0
        lines = []
        for date, hours in records:
            h = float(hours) if '.' in hours else int(hours)
            total_hours += h
            # Форматируем дату красиво
            d = datetime.strptime(date, "%Y-%m-%d")
            date_str = d.strftime("%d.%m")
            lines.append(f"• {date_str}: {h} ч")
        
        text = f"👤 *{worker_name}*\n📅 {month_names[month]} {year}\n\n"
        text += "\n".join(lines)
        text += f"\n\n✅ Всего: {total_hours} ч ({len(records)} смен)"
    else:
        text = f"👤 *{worker_name}*\n📅 {month_names[month]} {year}\n\nНет данных."

    await update.message.reply_text(text, parse_mode="Markdown")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /report — отчёт за последние 7 дней
    /report 01.07 08.07 — отчёт за период
    /report 01.07 — отчёт с указанной даты по сегодня
    """
    args = context.args
    today = datetime.now()
    
    if len(args) == 0:
        # По умолчанию: последние 7 дней
        end_date = today.strftime("%Y-%m-%d")
        start_date = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    elif len(args) == 1:
        # Одна дата: с неё по сегодня
        try:
            start = datetime.strptime(args[0], "%d.%m")
            start = start.replace(year=today.year)
            start_date = start.strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        except:
            await update.message.reply_text("❌ Неверный формат даты. Используй ДД.ММ (например, 01.07)")
            return
    elif len(args) == 2:
        # Две даты: период
        try:
            start = datetime.strptime(args[0], "%d.%m").replace(year=today.year)
            end = datetime.strptime(args[1], "%d.%m").replace(year=today.year)
            start_date = start.strftime("%Y-%m-%d")
            end_date = end.strftime("%Y-%m-%d")
        except:
            await update.message.reply_text("❌ Неверный формат даты. Используй ДД.ММ ДД.ММ (например, 01.07 08.07)")
            return
    else:
        await update.message.reply_text("❌ Слишком много аргументов. Пример: `/report 01.07 08.07`", parse_mode="Markdown")
        return

    stats = get_stats_by_period(start_date, end_date)
    daily = get_daily_report(start_date, end_date)

    # Форматируем даты для заголовка
    s = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d.%m")
    e = datetime.strptime(end_date, "%Y-%m-%d").strftime("%d.%m")

    if not stats:
        await update.message.reply_text(f"📊 *Отчёт {s}–{e}*\n\nНет данных за этот период.", parse_mode="Markdown")
        return

    # Суммарная статистика
    total_hours = 0
    worker_lines = []
    for worker_name, hours, days in stats:
        total_hours += hours
        worker_lines.append(f"• {worker_name}: {hours} ч ({days} смен)")

    text = f"📊 *Отчёт {s}–{e}*\n\n"
    text += "*По сотрудникам:*\n"
    text += "\n".join(worker_lines)
    text += f"\n\n👥 *Всего: {total_hours} ч*"

    # Детализация по дням (компактно)
    if len(daily) <= 30:  # Показываем, если не слишком много записей
        text += "\n\n*По дням:*"
        # Группируем по датам
        days_dict = {}
        for date, worker_name, hours in daily:
            if date not in days_dict:
                days_dict[date] = []
            h = float(hours) if '.' in hours else int(hours)
            days_dict[date].append(f"{worker_name}: {h} ч")
        
        for date in sorted(days_dict.keys()):
            d = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m")
            text += f"\n📅 *{d}*: " + ", ".join(days_dict[date])

    await update.message.reply_text(text, parse_mode="Markdown")

# --- Обработка кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "checkin":
        existing = get_user_checkin(user.id)
        if existing:
            await query.message.reply_text(
                f"⚠️ Ты уже отметился как *{existing[0]}* ({existing[1]} ч).\n"
                f"Хочешь изменить? Выбери себя из списка:",
                reply_markup=get_workers_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text(
                "👤 Кто ты?",
                reply_markup=get_workers_keyboard()
            )

    elif query.data == "uncheckin":
        existing = get_user_checkin(user.id)
        if existing:
            delete_checkin(user.id)
            await query.answer(f"❌ Отметка {existing[0]} удалена.")
        else:
            await query.answer("⚠️ Ты ещё не отмечался сегодня.")
        await update_main_message(query)

    elif query.data.startswith("worker_"):
        worker_name = query.data.split("_", 1)[1]
        context.user_data["selected_worker"] = worker_name
        await query.message.edit_text(
            f"👤 *{worker_name}*\nВыбери количество часов:",
            reply_markup=get_hours_keyboard(),
            parse_mode="Markdown"
        )

    elif query.data.startswith("hours_"):
        hours = query.data.split("_", 1)[1]
        worker_name = context.user_data.get("selected_worker")

        if not worker_name:
            await query.answer("⚠️ Сначала выбери сотрудника.")
            return

        if hours == "other":
            context.user_data["awaiting_hours"] = True
            await query.message.edit_text(
                f"👤 *{worker_name}*\n✏️ Напиши количество часов числом (например, 5 или 7.5):",
                parse_mode="Markdown"
            )
            return
        else:
            add_checkin(user.id, user.username or "", worker_name, hours)
            h = int(hours)
            await query.answer(f"✅ {worker_name}: {h} ч")
            await query.message.delete()
            await update_main_message(query)
            context.user_data.pop("selected_worker", None)

# --- Обработка текста (своё количество часов) ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_hours"):
        return

    user = update.effective_user
    worker_name = context.user_data.get("selected_worker")
    text = update.message.text.strip().replace(",", ".")

    if not worker_name:
        await update.message.reply_text("⚠️ Сначала выбери сотрудника через кнопки.")
        context.user_data["awaiting_hours"] = False
        return

    try:
        hours = float(text)
        if hours <= 0 or hours > 24:
            raise ValueError
        hours_str = str(int(hours)) if hours == int(hours) else str(hours)
    except:
        await update.message.reply_text("❌ Введи число от 0 до 24 (например, 5 или 7.5):")
        return

    add_checkin(user.id, user.username or "", worker_name, hours_str)
    context.user_data["awaiting_hours"] = False
    context.user_data.pop("selected_worker", None)
    await update.message.reply_text(f"✅ {worker_name}: {hours_str} ч")

async def update_main_message(query):
    text = build_today_text()
    try:
        await query.edit_message_text(
            text,
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    except:
        pass

# --- Запуск ---
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("checkin", checkin_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("month", month_command))
    app.add_handler(CommandHandler("worker", worker_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Заглушка для Render
    web_app = Flask(__name__)

    @web_app.route('/')
    def home():
        return "Бот работает"

    def run_web():
        web_app.run(host='0.0.0.0', port=10000)

    Thread(target=run_web).start()

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()