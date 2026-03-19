import telebot
import requests
import os
from telebot import types
from datetime import datetime, timedelta
import json
from supabase import create_client, Client

# ========== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (GitHub не орёт) ==========
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
BRAWL_API_KEY = os.environ.get('BRAWL_API_KEY')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if not all([TELEGRAM_TOKEN, BRAWL_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("❌ Не все переменные окружения заданы!")

# ========== ПОДКЛЮЧЕНИЕ К SUPABASE ==========
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Создаём таблицы, если их нет
try:
    supabase.table('accounts').select('*').limit(1).execute()
except:
    supabase.table('accounts').insert({
        'id': 0,
        'user_id': 0,
        'player_tag': '',
        'player_name': '',
        'goal': 1000,
        'total_goal': 0
    }).execute()

try:
    supabase.table('history').select('*').limit(1).execute()
except:
    supabase.table('history').insert({
        'id': 0,
        'user_id': 0,
        'player_tag': '',
        'date': '',
        'trophies': 0
    }).execute()

# ========== БОТ ==========
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Кэш для страниц гринд
grind_cache = {}

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С SUPABASE ==========
def get_accounts(user_id):
    response = supabase.table('accounts').select('*').eq('user_id', user_id).execute()
    return response.data if response.data else []

def add_account_to_db(user_id, tag, name):
    supabase.table('accounts').insert({
        'user_id': user_id,
        'player_tag': tag,
        'player_name': name,
        'goal': 1000,
        'total_goal': 0
    }).execute()

def delete_account_from_db(user_id, tag):
    supabase.table('accounts').delete().eq('user_id', user_id).eq('player_tag', tag).execute()
    supabase.table('history').delete().eq('user_id', user_id).eq('player_tag', tag).execute()

def save_trophies_history(user_id, player_tag, trophies):
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        supabase.table('history').upsert({
            'user_id': user_id,
            'player_tag': player_tag,
            'date': today,
            'trophies': trophies
        }, on_conflict=['user_id', 'player_tag', 'date']).execute()
    except:
        pass

def get_trophies_history(user_id, player_tag, days):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    response = supabase.table('history')\
        .select('date, trophies')\
        .eq('user_id', user_id)\
        .eq('player_tag', player_tag)\
        .gte('date', start_date.strftime("%Y-%m-%d"))\
        .order('date', desc=False)\
        .execute()
    return [(row['date'], row['trophies']) for row in response.data]

# ========== ФУНКЦИИ ДЛЯ ГРАФИКА ==========
def generate_chart_url(dates, trophies, player_name):
    chart_data = {
        "type": "line",
        "data": {
            "labels": dates,
            "datasets": [{
                "label": f"Кубки - {player_name}",
                "data": trophies,
                "borderColor": "rgb(75, 192, 192)",
                "backgroundColor": "rgba(75, 192, 192, 0.2)",
                "fill": True,
                "tension": 0.1
            }]
        },
        "options": {
            "title": {
                "display": True,
                "text": f"Динамика кубков - {player_name}"
            },
            "scales": {
                "yAxes": [{
                    "ticks": {
                        "beginAtZero": False
                    }
                }]
            }
        }
    }
    chart_json = json.dumps(chart_data)
    return f"https://quickchart.io/chart?c={chart_json}&width=600&height=400"

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
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📊 Прогресс", "🔥 Гринд", "📋 Мои аккаунты", "⚙️ Цели")
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
        show_progress_menu(message)
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

def show_progress_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📈 График трофеев", callback_data="progress_graph_menu"),
        types.InlineKeyboardButton("📊 Общий прогресс", callback_data="progress_stats")
    )
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
    bot.send_message(message.chat.id, "📊 **Прогресс**\n\nВыбери действие:", 
                    parse_mode='Markdown', reply_markup=markup)

def show_graph_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=4)
    markup.add(
        types.InlineKeyboardButton("3 дня", callback_data="graph_period_3"),
        types.InlineKeyboardButton("7 дней", callback_data="graph_period_7"),
        types.InlineKeyboardButton("14 дней", callback_data="graph_period_14"),
        types.InlineKeyboardButton("30 дней", callback_data="graph_period_30")
    )
    markup.add(types.InlineKeyboardButton("❓ Почему не работает график?", callback_data="graph_help"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_progress_menu"))
    bot.send_message(message.chat.id, "📈 **График трофеев**\n\nВыбери период:", 
                    parse_mode='Markdown', reply_markup=markup)

def show_graph_help(message):
    help_text = """
📈 **График трофеев — как это работает**

🔹 **История собирается автоматически**
   Каждый раз при просмотре прогресса бот сохраняет текущие кубки.
   Со временем накапливаются данные — и график становится полезнее.

🔹 **Почему график может быть пустым?**
   Если ты только начал пользоваться ботом — истории ещё нет.
   Нажми сначала «📊 Общий прогресс» 2–3 дня подряд,
   чтобы появились точки для графика.

🔹 **Что влияет на график**
   • Кубки сохраняются раз в день (при первом просмотре прогресса)
   • Если не смотреть прогресс — данные не обновляются
   • График строится только за выбранный период (3, 7, 14, 30 дней)

🔹 **Совет**
   Заглядывай в прогресс почаще — и через неделю
   увидишь красивую динамику своего роста 📊🚀

🔹 **Если график не появляется**
   • Проверь, есть ли аккаунты в списке
   • Убедись, что ты нажимал «Общий прогресс» хотя бы 2 раза
   • Попробуй выбрать другой период
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_graph_menu"))
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown', reply_markup=markup)

def show_accounts(message):
    user_id = message.from_user.id
    accs = get_accounts(user_id)
    
    count = len(accs)
    text = "👤 **Мои Профили**\n\n"
    text += f"Профилей сохранено: {count}/5\n\n"
    
    if accs:
        for i, acc in enumerate(accs, 1):
            text += f"{i}. {acc['player_name']}.[{acc['player_tag']}]\n"
    else:
        text += "У вас пока нет сохраненных профилей.\n\n"
    
    text += "\nНажмите на кнопку '➕ Добавить', чтобы добавить профиль в свой список сохраненных"
    text += "\nНажмите на кнопку '✏️ Изменить', чтобы заменить один сохраненный профиль на другой"
    text += "\nНажмите на кнопку '🗑️ Удалить', чтобы удалить профиль из списка сохраненных"
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить", callback_data="add_account"),
        types.InlineKeyboardButton("✏️ Изменить", callback_data="edit_account"),
        types.InlineKeyboardButton("🗑️ Удалить", callback_data="delete_account")
    )
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

def show_progress(message):
    user_id = message.from_user.id
    accs = get_accounts(user_id)
    
    if not accs:
        bot.send_message(message.chat.id, "📭 Сначала добавь аккаунты", reply_markup=main_keyboard())
        return

    bot.send_message(message.chat.id, "🔍 Считаю прогресс...")
    
    for acc in accs:
        tag = acc['player_tag']
        name = acc['player_name']
        goal = acc['goal']
        total_goal = acc['total_goal']
        
        data = get_brawl_data(tag)
        if not data:
            bot.send_message(message.chat.id, f"❌ Ошибка загрузки {name}")
            continue

        brawlers = data.get('brawlers', [])
        total_brawlers = len(brawlers)
        current_trophies = sum(b['trophies'] for b in brawlers)
        
        save_trophies_history(user_id, tag, current_trophies)
        
        if total_goal and total_goal > 0:
            goal_total = total_goal
        else:
            goal_total = total_brawlers * goal
        
        remaining = max(0, goal_total - current_trophies)
        percent = (current_trophies / goal_total * 100) if goal_total > 0 else 0
        at_goal = sum(1 for b in brawlers if b['trophies'] >= goal)

        bar_length = 20
        filled = int((current_trophies / goal_total) * bar_length) if goal_total > 0 else 0
        filled = min(filled, bar_length)
        bar = "█" * filled + "─" * (bar_length - filled)

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
    user_id = message.from_user.id
    accs = get_accounts(user_id)
    
    if not accs:
        bot.send_message(message.chat.id, "📭 Сначала добавь аккаунты", reply_markup=main_keyboard())
        return

    if message.chat.id in grind_cache:
        del grind_cache[message.chat.id]

    bot.send_message(message.chat.id, "🔍 Считаю гринд...")
    
    for acc in accs:
        tag = acc['player_tag']
        name = acc['player_name']
        goal = acc['goal']
        
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
    
    total_current = sum(t for _, t in brawlers)
    total_goal = total * goal
    remaining = total_goal - total_current
    percent = (total_current / total_goal * 100) if total_goal > 0 else 0
    
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
    user_id = message.from_user.id
    accs = get_accounts(user_id)
    
    if not accs:
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
    user_id = call.from_user.id

    if call.data == "add_account":
        bot.send_message(call.message.chat.id, "Отправь тег аккаунта (например #8VYOJJ0GG)")
        bot.register_next_step_handler(call.message, add_account)
    
    elif call.data == "edit_account":
        bot.answer_callback_query(call.id, "Функция изменения будет позже")
    
    elif call.data == "delete_account":
        accs = get_accounts(user_id)
        if not accs:
            bot.answer_callback_query(call.id, "Нет аккаунтов для удаления")
            return
        
        markup = types.InlineKeyboardMarkup()
        for acc in accs:
            markup.add(types.InlineKeyboardButton(f"🗑️ {acc['player_name']}", callback_data=f"remove_{acc['player_tag']}"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
        
        bot.edit_message_text("Выбери аккаунт для удаления:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == "main_menu":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=main_keyboard())
    
    elif call.data.startswith("remove_"):
        tag = call.data.replace("remove_", "")
        delete_account_from_db(user_id, tag)
        bot.answer_callback_query(call.id, "✅ Аккаунт удалён")
        show_accounts(call.message)
    
    elif call.data == "set_goal_brawler":
        accs = get_accounts(user_id)
        if not accs:
            bot.answer_callback_query(call.id, "Нет аккаунтов")
            return
        
        markup = types.InlineKeyboardMarkup()
        for acc in accs:
            markup.add(types.InlineKeyboardButton(f"🛡️ {acc['player_name']} ({acc['goal']})", callback_data=f"edit_goal_{acc['player_tag']}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить аккаунт", callback_data="add_account"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
        
        bot.edit_message_text("Выбери аккаунт для изменения прогресса бойцов:", 
                             call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == "set_total_goal":
        accs = get_accounts(user_id)
        if not accs:
            bot.answer_callback_query(call.id, "Нет аккаунтов")
            return
        
        markup = types.InlineKeyboardMarkup()
        for acc in accs:
            display_goal = acc['total_goal'] if acc['total_goal'] and acc['total_goal'] > 0 else "не задана"
            markup.add(types.InlineKeyboardButton(f"💎 {acc['player_name']} ({display_goal})", callback_data=f"edit_total_{acc['player_tag']}"))
        markup.add(types.InlineKeyboardButton("➕ Добавить аккаунт", callback_data="add_account"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu"))
        
        bot.edit_message_text("Выбери аккаунт для изменения общего прогресса:", 
                             call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data.startswith("edit_goal_"):
        tag = call.data.replace("edit_goal_", "")
        bot.send_message(call.message.chat.id, "Отправь новую цель для прогресса бойцов (например 1000)")
        bot.register_next_step_handler(call.message, set_brawler_goal, tag)
    
    elif call.data.startswith("edit_total_"):
        tag = call.data.replace("edit_total_", "")
        bot.send_message(call.message.chat.id, "Отправь новую общую цель для этого аккаунта (например 150000)")
        bot.register_next_step_handler(call.message, set_total_goal_for_account, tag)
    
    # ========== ГРАФИК ==========
    elif call.data == "progress_graph_menu":
        show_graph_menu(call.message)
    
    elif call.data == "progress_stats":
        show_progress(call.message)
    
    elif call.data == "back_to_progress_menu":
        show_progress_menu(call.message)
    
    elif call.data == "back_to_graph_menu":
        show_graph_menu(call.message)
    
    elif call.data == "graph_help":
        show_graph_help(call.message)
    
    elif call.data.startswith("graph_period_"):
        days = int(call.data.replace("graph_period_", ""))
        accs = get_accounts(user_id)
        
        if not accs:
            bot.answer_callback_query(call.id, "Нет аккаунтов")
            return
        
        bot.send_message(call.message.chat.id, f"🔍 Генерирую графики за {days} дней...")
        
        for acc in accs:
            tag = acc['player_tag']
            name = acc['player_name']
            history = get_trophies_history(user_id, tag, days)
            if len(history) < 2:
                bot.send_message(call.message.chat.id, f"📉 {name}: недостаточно данных за {days} дней")
                continue
            
            dates = [h[0] for h in history]
            trophies = [h[1] for h in history]
            chart_url = generate_chart_url(dates, trophies, name)
            
            try:
                response = requests.get(chart_url, timeout=15)
                if response.status_code == 200:
                    bot.send_photo(call.message.chat.id, response.content, 
                                  caption=f"📈 {name} - график за {days} дней")
                else:
                    bot.send_message(call.message.chat.id, f"❌ Ошибка генерации графика для {name}")
            except:
                bot.send_message(call.message.chat.id, f"❌ Ошибка загрузки графика для {name}")

def set_brawler_goal(message, tag):
    user_id = message.from_user.id
    try:
        new_goal = int(message.text.strip())
        if new_goal < 100:
            bot.send_message(message.chat.id, "❌ Цель должна быть не меньше 100", reply_markup=main_keyboard())
            return
        supabase.table('accounts').update({'goal': new_goal}).eq('user_id', user_id).eq('player_tag', tag).execute()
        bot.send_message(message.chat.id, f"✅ Прогресс бойцов изменён на {new_goal}", reply_markup=main_keyboard())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введи число", reply_markup=main_keyboard())

def set_total_goal_for_account(message, tag):
    user_id = message.from_user.id
    try:
        new_goal = int(message.text.strip())
        if new_goal < 0:
            bot.send_message(message.chat.id, "❌ Цель не может быть отрицательной", reply_markup=main_keyboard())
            return
        supabase.table('accounts').update({'total_goal': new_goal}).eq('user_id', user_id).eq('player_tag', tag).execute()
        bot.send_message(message.chat.id, f"✅ Общий прогресс для аккаунта установлен: {new_goal}", reply_markup=main_keyboard())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введи число", reply_markup=main_keyboard())

def add_account(message):
    user_id = message.from_user.id
    tag = message.text.strip().upper()
    if not tag.startswith('#'):
        tag = '#' + tag
    
    accs = get_accounts(user_id)
    if len(accs) >= 5:
        bot.send_message(message.chat.id, "❌ Нельзя добавить больше 5 аккаунтов", reply_markup=main_keyboard())
        return
    
    data = get_brawl_data(tag)
    if not data:
        bot.send_message(message.chat.id, "❌ Аккаунт не найден", reply_markup=main_keyboard())
        return
    
    name = data.get('name', 'Без имени')
    try:
        add_account_to_db(user_id, tag, name)
        bot.send_message(message.chat.id, f"✅ {name} добавлен", reply_markup=main_keyboard())
    except:
        bot.send_message(message.chat.id, "❌ Этот аккаунт уже есть", reply_markup=main_keyboard())

print("✅ Финальная версия с Supabase и графиком запущена!")
bot.infinity_polling()