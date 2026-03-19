import telebot
import requests
import sqlite3
from telebot import types

# ⚠️ ТВОИ ДАННЫЕ
TELEGRAM_TOKEN = "8598712762:AAGllJbSAwvyY8jPTaQY-f7KxeYn4Ic-TXY"
BRAWL_API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6IjlmNDAyNTY5LTdjNDctNGQ0YS1hNzQyLWY3NzQwZDFkNDMxNyIsImlhdCI6MTc3MzgwNjQyNywic3ViIjoiZGV2ZWxvcGVyL2Q5ODJjNjFmLWQ2MzItN2M1Zi1iY2FhLThmNmE2YTQwZTc3ZCIsInNjb3BlcyI6WyJicmF3bHN0YXJzIl0sImxpbWl0cyI6W3sidGllciI6ImRldmVsb3Blci9zaWx2ZXIiLCJ0eXBlIjoidGhyb3R0bGluZyJ9LHsiY2lkcnMiOlsiNzcuODIuMTczLjU3Il0sInR5cGUiOiJjbGllbnQifV19.N3w5KVWQia3bHqTAfO36ULB72AhaUhDTGaC8rImhAOJ2eWnA1JPsWY1xE_rnZZcLNduFOxvODBq6jvbOvPNZ9w"
# ⚠️ КОНЕЦ

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect('brawl_accounts.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        player_tag TEXT UNIQUE,
        player_name TEXT,
        goal INTEGER DEFAULT 1000,
        total_goal INTEGER DEFAULT 0
    )
''')

# Проверяем и добавляем колонки, если их нет
cursor.execute("PRAGMA table_info(accounts)")
columns = [col[1] for col in cursor.fetchall()]
if 'goal' not in columns:
    cursor.execute("ALTER TABLE accounts ADD COLUMN goal INTEGER DEFAULT 1000")
if 'total_goal' not in columns:
    cursor.execute("ALTER TABLE accounts ADD COLUMN total_goal INTEGER DEFAULT 0")

conn.commit()
# =================================

# Кэш для страниц гринд
grind_cache = {}

def get_brawl_data(player_tag):
    url = f"https://api.brawlstars.com/v1/players/%23{player_tag.strip('#')}"
    headers = {"Authorization": f"Bearer {BRAWL_API_KEY}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def main_keyboard():
    """Главное меню (reply-кнопки)"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        "📊 Прогресс",
        "🔥 Гринд",
        "📋 Мои аккаунты",
        "⚙️ Цели"
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я бот для отслеживания статистики.\nразработано - @neweraxd",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    text = message.text

    if text == "📋 Мои аккаунты":
        show_accounts(message)

    elif text == "📊 Прогресс":
        show_progress(message)

    elif text == "🔥 Гринд":
        show_grind(message)

    elif text == "⚙️ Цели":
        show_goals_menu(message)

    elif text in ["⬅️ Назад", "➡️ Вперёд"]:
        if message.chat.id in grind_cache:
            for tag, data in grind_cache[message.chat.id].items():
                if text == "➡️ Вперёд":
                    data['page'] += 1
                elif text == "⬅️ Назад" and data['page'] > 0:
                    data['page'] -= 1
                send_grind_page(message.chat.id, tag)
                return
    else:
        bot.send_message(message.chat.id, "Используй кнопки", reply_markup=main_keyboard())

def show_accounts(message):
    """Показывает список аккаунтов в стиле фото"""
    user_id = message.from_user.id
    cursor.execute("SELECT player_tag, player_name, goal FROM accounts WHERE user_id = ?", (user_id,))
    accs = cursor.fetchall()
    
    count = len(accs)
    text = "👤 **Мои Профили**\n\n"
    text += f"Профилей сохранено: {count}/5\n\n"
    
    if accs:
        for i, (tag, name, goal) in enumerate(accs, 1):
            text += f"{i}. {name}.[{tag}]\n"
    else:
        text += "У вас пока нет сохраненных профилей.\n\n"
    
    text += "\nНажмите на кнопку '➕ Добавить', чтобы добавить профиль в свой список сохраненных"
    text += "\nНажмите на кнопку '✏️ Изменить', чтобы заменить один сохраненный профиль на другой"
    text += "\nНажмите на кнопку '🗑️ Удалить', чтобы удалить профиль из списка сохраненных"
    
    # Инлайн-кнопки
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить", callback_data="add_account"),
        types.InlineKeyboardButton("✏️ Изменить", callback_data="edit_account"),
        types.InlineKeyboardButton("🗑️ Удалить", callback_data="delete_account")
    )
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

def show_progress(message):
    """Показывает прогресс по аккаунтам"""
    user_id = message.from_user.id
    cursor.execute("SELECT player_tag, player_name, goal, total_goal FROM accounts WHERE user_id = ?", (user_id,))
    accs = cursor.fetchall()
    
    if not accs:
        bot.send_message(message.chat.id, "📭 Сначала добавь аккаунты", reply_markup=main_keyboard())
        return

    bot.send_message(message.chat.id, "🔍 Считаю прогресс...")
    
    for tag, name, goal, total_goal in accs:
        data = get_brawl_data(tag)
        if not data:
            bot.send_message(message.chat.id, f"❌ Ошибка загрузки {name}")
            continue

        brawlers = data.get('brawlers', [])
        total_brawlers = len(brawlers)
        current_trophies = sum(b['trophies'] for b in brawlers)
        
        # Если задана общая цель, используем её, иначе считаем от бойцов
        if total_goal and total_goal > 0:
            goal_total = total_goal
        else:
            goal_total = total_brawlers * goal
        
        remaining = max(0, goal_total - current_trophies)
        percent = (current_trophies / goal_total * 100) if goal_total > 0 else 0
        at_goal = sum(1 for b in brawlers if b['trophies'] >= goal)

        # Шкала прогресса
        bar_length = 20
        filled = int((current_trophies / goal_total) * bar_length) if goal_total > 0 else 0
        filled = min(filled, bar_length)
        bar = "█" * filled + "─" * (bar_length - filled)

        # Ближайшие к цели
        close = sorted(
            [(b['name'], b['trophies']) for b in brawlers if b['trophies'] < goal],
            key=lambda x: goal - x[1]
        )[:5]

        text = f"📊 **{name}**\n\n"
        text += f"🛡️ **Прогресс бойцов:** {goal}\n"
        if total_goal and total_goal > 0:
            text += f"💎 **Общий прогресс:** {total_goal:,}\n".replace(',', ' ')
        text += f"👥 **Всего бойцов:** {total_brawlers}\n"
        text += f"💰 **Текущие кубки:** {current_trophies:,}\n".replace(',', ' ')
        text += f"📊 **Цель:** {goal_total:,}\n".replace(',', ' ')
        text += f"⏳ **Осталось:** {remaining:,}\n".replace(',', ' ')
        text += f"📈 **Прогресс:** {percent:.1f}%\n"
        text += f"✅ **На {goal}:** {at_goal}\n\n"
        
        text += f"```\n0 {bar} {goal_total:,}\n".replace(',', ' ')
        text += f"{current_trophies:,} / {goal_total:,} ({percent:.1f}%) осталось {remaining:,}\n```\n\n".replace(',', ' ')
        
        if close:
            text += "🔥 **Ближайшие к цели:**\n"
            for b, t in close:
                text += f"• {b}: {t} (осталось {goal - t})\n"

        bot.send_message(message.chat.id, text, parse_mode='Markdown')

def show_grind(message):
    """Показывает гринд по аккаунтам"""
    user_id = message.from_user.id
    cursor.execute("SELECT player_tag, player_name, goal FROM accounts WHERE user_id = ?", (user_id,))
    accs = cursor.fetchall()
    
    if not accs:
        bot.send_message(message.chat.id, "📭 Сначала добавь аккаунты", reply_markup=main_keyboard())
        return

    if message.chat.id in grind_cache:
        del grind_cache[message.chat.id]

    bot.send_message(message.chat.id, "🔍 Считаю гринд...")
    
    for tag, name, goal in accs:
        data = get_brawl_data(tag)
        if not data:
            continue

        brawlers = [(b['name'], b['trophies']) for b in data.get('brawlers', []) if b['trophies'] < goal]
        if not brawlers:
            bot.send_message(message.chat.id, f"✅ **{name}** — все на {goal}!", parse_mode='Markdown')
            continue

        brawlers.sort(key=lambda x: goal - x[1])
        
        if message.chat.id not in grind_cache:
            grind_cache[message.chat.id] = {}
        grind_cache[message.chat.id][tag] = {
            'name': name,
            'goal': goal,
            'brawlers': brawlers,
            'page': 0
        }

        send_grind_page(message.chat.id, tag)

def send_grind_page(chat_id, tag):
    if chat_id not in grind_cache or tag not in grind_cache[chat_id]:
        return
    
    data = grind_cache[chat_id][tag]
    name = data['name']
    goal = data['goal']
    brawlers = data['brawlers']
    page = data['page']
    
    total = len(brawlers)
    per_page = 10
    pages = (total + per_page - 1) // per_page
    start = page * per_page
    end = min(start + per_page, total)
    
    # Считаем общий прогресс
    total_current = sum(t for _, t in brawlers)
    total_goal = total * goal
    remaining = total_goal - total_current
    percent = (total_current / total_goal * 100) if total_goal > 0 else 0
    
    # Шкала прогресса
    bar_length = 20
    filled = int((total_current / total_goal) * bar_length) if total_goal > 0 else 0
    filled = min(filled, bar_length)
    bar = "█" * filled + "─" * (bar_length - filled)
    
    text = f"🔥 **{name}** (цель {goal}) — осталось бойцов: {total}\n\n"
    text += f"```\n0 {bar} {total_goal}\n"
    text += f"{total_current} / {total_goal} ({percent:.1f}%) осталось {remaining}\n```\n\n"
    text += f"Страница {page + 1} из {pages}\n\n"
    
    for i in range(start, end):
        b, t = brawlers[i]
        text += f"🏆 {b}: {t} (осталось {goal - t})\n"
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    nav_buttons = []
    if page > 0:
        nav_buttons.append("⬅️ Назад")
    if page < pages - 1:
        nav_buttons.append("➡️ Вперёд")
    if nav_buttons:
        markup.add(*nav_buttons)
    markup.add("🏠 Главное меню")
    
    bot.send_message(chat_id, text, parse_mode='Markdown', reply_markup=markup)

def show_goals_menu(message):
    """Меню выбора типа цели"""
    # Проверяем, есть ли аккаунты
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE user_id = ?", (message.from_user.id,))
    count = cursor.fetchone()[0]
    
    if count == 0:
        bot.send_message(message.chat.id, "📭 Сначала добавь аккаунты", reply_markup=main_keyboard())
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛡️ Прогресс бойцов", callback_data="set_goal_brawler"),
        types.InlineKeyboardButton("💎 Общий прогресс", callback_data="set_total_goal")
    )
    markup.add(types.InlineKeyboardButton("➕ Добавить аккаунт", callback_data="add_account"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
    
    bot.send_message(message.chat.id, "Выбери тип цели:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "add_account":
        bot.send_message(call.message.chat.id, "Отправь тег аккаунта (например #8VYOJJ0GG)")
        bot.register_next_step_handler(call.message, add_account)
    
    elif call.data == "edit_account":
        bot.answer_callback_query(call.id, "Функция изменения будет позже")
    
    elif call.data == "delete_account":
        user_id = call.from_user.id
        cursor.execute("SELECT player_tag, player_name FROM accounts WHERE user_id = ?", (user_id,))
        accs = cursor.fetchall()
        
        if not accs:
            bot.answer_callback_query(call.id, "Нет аккаунтов для удаления")
            return
        
        markup = types.InlineKeyboardMarkup()
        for tag, name in accs:
            markup.add(types.InlineKeyboardButton(f"🗑️ {name}", callback_data=f"remove_{tag}"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
        
        bot.edit_message_text("Выбери аккаунт для удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == "main_menu":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=main_keyboard())
    
    elif call.data.startswith("remove_"):
        tag = call.data.replace("remove_", "")
        cursor.execute("DELETE FROM accounts WHERE user_id = ? AND player_tag = ?",
                       (call.from_user.id, tag))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ Аккаунт удалён")
        show_accounts(call.message)
    
    elif call.data == "set_goal_brawler":
        # Показываем список аккаунтов для выбора цели бойцов
        user_id = call.from_user.id
        cursor.execute("SELECT player_tag, player_name, goal FROM accounts WHERE user_id = ?", (user_id,))
        accs = cursor.fetchall()
        
        if not accs:
            bot.answer_callback_query(call.id, "Нет аккаунтов")
            return
        
        markup = types.InlineKeyboardMarkup()
        for tag, name, goal in accs:
            markup.add(types.InlineKeyboardButton(f"🛡️ {name} ({goal})", callback_data=f"edit_goal_{tag}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить аккаунт", callback_data="add_account"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
        
        bot.edit_message_text("Выбери аккаунт для изменения прогресса бойцов:", 
                             call.message.chat.id, 
                             call.message.message_id, 
                             reply_markup=markup)
    
    elif call.data == "set_total_goal":
        # Показываем список аккаунтов для выбора общей цели
        user_id = call.from_user.id
        cursor.execute("SELECT player_tag, player_name, total_goal FROM accounts WHERE user_id = ?", (user_id,))
        accs = cursor.fetchall()
        
        if not accs:
            bot.answer_callback_query(call.id, "Нет аккаунтов")
            return
        
        markup = types.InlineKeyboardMarkup()
        for tag, name, total_goal in accs:
            display_goal = total_goal if total_goal and total_goal > 0 else "не задана"
            markup.add(types.InlineKeyboardButton(f"💎 {name} ({display_goal})", callback_data=f"edit_total_{tag}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить аккаунт", callback_data="add_account"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
        
        bot.edit_message_text("Выбери аккаунт для изменения общего прогресса:", 
                             call.message.chat.id, 
                             call.message.message_id, 
                             reply_markup=markup)
    
    elif call.data.startswith("edit_goal_"):
        tag = call.data.replace("edit_goal_", "")
        bot.send_message(call.message.chat.id, f"Отправь новую цель для прогресса бойцов (например 1000)")
        bot.register_next_step_handler(call.message, set_brawler_goal, tag)
    
    elif call.data.startswith("edit_total_"):
        tag = call.data.replace("edit_total_", "")
        bot.send_message(call.message.chat.id, f"Отправь новую общую цель для этого аккаунта (например 150000)")
        bot.register_next_step_handler(call.message, set_total_goal_for_account, tag)

def set_brawler_goal(message, tag):
    try:
        new_goal = int(message.text.strip())
        if new_goal < 100:
            bot.send_message(message.chat.id, "❌ Цель должна быть не меньше 100", reply_markup=main_keyboard())
            return
        cursor.execute("UPDATE accounts SET goal = ? WHERE user_id = ? AND player_tag = ?",
                       (new_goal, message.from_user.id, tag))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Прогресс бойцов изменён на {new_goal}", reply_markup=main_keyboard())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введи число", reply_markup=main_keyboard())

def set_total_goal_for_account(message, tag):
    try:
        new_goal = int(message.text.strip())
        if new_goal < 0:
            bot.send_message(message.chat.id, "❌ Цель не может быть отрицательной", reply_markup=main_keyboard())
            return
        
        cursor.execute("UPDATE accounts SET total_goal = ? WHERE user_id = ? AND player_tag = ?",
                       (new_goal, message.from_user.id, tag))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Общий прогресс для аккаунта установлен: {new_goal}", reply_markup=main_keyboard())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введи число", reply_markup=main_keyboard())

def add_account(message):
    tag = message.text.strip().upper()
    if not tag.startswith('#'):
        tag = '#' + tag
    
    # Проверяем лимит в 5 аккаунтов
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE user_id = ?", (message.from_user.id,))
    count = cursor.fetchone()[0]
    if count >= 5:
        bot.send_message(message.chat.id, "❌ Нельзя добавить больше 5 аккаунтов", reply_markup=main_keyboard())
        return
    
    data = get_brawl_data(tag)
    if not data:
        bot.send_message(message.chat.id, "❌ Аккаунт не найден", reply_markup=main_keyboard())
        return
    
    name = data.get('name', 'Без имени')
    try:
        cursor.execute("INSERT INTO accounts (user_id, player_tag, player_name) VALUES (?, ?, ?)",
                       (message.from_user.id, tag, name))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ {name} добавлен", reply_markup=main_keyboard())
    except sqlite3.IntegrityError:
        bot.send_message(message.chat.id, "❌ Этот аккаунт уже есть", reply_markup=main_keyboard())

print("✅ Финальная версия бота с новыми названиями запущена!")
bot.infinity_polling()