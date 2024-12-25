import telebot
from telebot import types
import time
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import sqlite3
import threading
import json
import os

# Токен бота
bot_token = os.environ.get("BOT_TOKEN")
if bot_token is None:
    #raise ValueError("BOT_TOKEN environment variable not set")
    bot_token = "7830801217:AAEr_hdveblXJUZlnZ1IMjGvtLIK2-9eMz4"

bot = telebot.TeleBot(bot_token)

# Создание базы данных
conn = sqlite3.connect('giveaways.db', check_same_thread=False) # Отключить проверку потоков
cursor = conn.cursor()

# Создание таблицы для пользователей
cursor.execute('''
  CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    last_steam_update DATETIME,
    last_epic_update DATETIME,
    last_gog_update DATETIME,
    subscribed BOOLEAN DEFAULT FALSE,
    preferences TEXT DEFAULT '{}'
  )
''')

# Создание таблицы для раздач
cursor.execute('''
  CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT,
    title TEXT,
    link TEXT,
    date_added DATETIME
  )
''')

conn.commit()

# --- Обработчики команд и кнопок ---

# Команда старт
@bot.message_handler(commands=['start'])
def welcome(message):
 chat_id = message.chat.id
 # Проверяем, есть ли пользователь в базе данных
 cursor.execute("SELECT 1 FROM users WHERE chat_id = ?", (chat_id,))
 user_exists = cursor.fetchone()
 if not user_exists:
  # Добавляем нового пользователя в базу данных
  cursor.execute("INSERT INTO users (chat_id) VALUES (?)", (chat_id,))
  conn.commit()

 bot.reply_to(message, "Привет! Я бот, который оповещает о раздачах игр. Выберите команду в меню.")
 show_menu(message)

# Функция для показа меню
def show_menu(message):
 markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
 item1 = types.KeyboardButton("Проверить раздачи в Steam")
 item2 = types.KeyboardButton("Проверить раздачи в Epic")
 item3 = types.KeyboardButton("Проверить раздачи в GOG")
 item4 = types.KeyboardButton("Проверить все раздачи")
 item5 = types.KeyboardButton("Подобрать игру по вкусу")
 item6 = types.KeyboardButton("Рекомендация от бота")
 item7 = types.KeyboardButton("Подписаться")
 item8 = types.KeyboardButton("Отписаться")
 item9 = types.KeyboardButton("Помощь")
 markup.add(item1, item2, item3, item4, item5, item6, item7, item8, item9)
 bot.send_message(message.chat.id, "Выберите команду", reply_markup=markup)

# Обработка кнопок и текстовых команд
@bot.message_handler(content_types=['text'])
def func(message):
 chat_id = message.chat.id
 if message.text == "Проверить раздачи в Steam":
  check_steam_giveaways(chat_id)
 elif message.text == "Проверить раздачи в Epic":
  check_epic_giveaways(chat_id)
 elif message.text == "Проверить раздачи в GOG":
  check_gog_giveaways(chat_id)
 elif message.text == "Проверить все раздачи":
  check_all_giveaways(chat_id)
 elif message.text == "Подобрать игру по вкусу":
  choose_a_game_to_your_taste(chat_id)
 elif message.text == "Рекомендация от бота":
  recommend_command(message)
 elif message.text == "Подписаться":
  subscribe(chat_id)
 elif message.text == "Отписаться":
  unsubscribe(chat_id)
 elif message.text == "Помощь":
  help_command(message)
 elif message.text == "/start":
  welcome(message)
 elif message.text == "/subscribe":
  subscribe(chat_id)
 elif message.text == "/unsubscribe":
  unsubscribe(chat_id)
 elif message.text == "/check":
  check_giveaways(message)
 elif message.text == "/help":
  help_command(message)
 else:
  bot.send_message(chat_id, "Я не понял вашу команду. Пожалуйста, выберите команду в меню.")

# Команда '/subscribe' для подписки на уведомления
@bot.message_handler(commands=['subscribe'])
def subscribe(chat_id):
  cursor.execute("UPDATE users SET subscribed = TRUE WHERE chat_id = ?", (chat_id,))
  conn.commit()
  bot.send_message(chat_id, "Вы подписались на уведомления!")

# Команда '/unsubscribe' для отписки от уведомлений
@bot.message_handler(commands=['unsubscribe'])
def unsubscribe(chat_id):
  cursor.execute("UPDATE users SET subscribed = FALSE WHERE chat_id = ?", (chat_id,))
  conn.commit()
  bot.send_message(chat_id, "Вы отписались от уведомлений!")

#  '/check' для ручного запуска проверки раздач
@bot.message_handler(commands=['check'])
def check_giveaways(message):
  check_all_giveaways(message.chat.id)

# Команда '/help' для вывода списка доступных команд
@bot.message_handler(commands=['help'])
def help_command(message):
  bot.reply_to(message, "Мои команды:\n/start - начать\n/subscribe - подписаться на уведомления\n/unsubscribe - отписаться от уведомлений\n/check - проверить раздачи\n/help - вывести список команд")

@bot.message_handler(commands=['recommend'])
def recommend_command(message):
    recommend_games(message.chat.id)

# --- Функции для проверки раздач ---

# Инициализация словарей для хранения последних раздач ЭТО ФИКС ДЛЯ ТЕСТА
last_steam_giveaways = {}
last_epic_giveaways = {}
last_gog_giveaways = {}

# Функция для проверки раздач на Steam

def check_steam_giveaways(chat_id):
  url = 'https://store.steampowered.com/search/?specials=1'
  response = requests.get(url)
  soup = BeautifulSoup(response.content, 'html.parser')

  giveaways = []
  for item in soup.find_all('a', class_='search_result_row'):
    title = item.find('span', class_='title').text.strip()
    link = item.get('href')
    giveaways.append({'title': title, 'link': link})

  new_giveaways = []
  for giveaway in giveaways:
    if giveaway['title'] not in last_steam_giveaways:
      new_giveaways.append(giveaway)

  send_giveaway_notifications(new_giveaways, "Steam", chat_id)

  # Обновляем словарь последних раздач
  last_steam_giveaways.clear()
  for giveaway in giveaways:
    last_steam_giveaways[giveaway['title']] = giveaway['link']

  # Обновляем время последнего обновления для Steam в базе данных
  cursor.execute("UPDATE users SET last_steam_update = ? WHERE chat_id = ?", (datetime.now(), chat_id))
  conn.commit()

# Функция для проверки раздач на Epic Games Store
def check_epic_giveaways(chat_id):
  url = 'https://store.epicgames.com/en-US/free-games'
  response = requests.get(url)
  soup = BeautifulSoup(response.content, 'html.parser')

  giveaways = []
  for item in soup.find_all('div', class_='css-1w6h27r'):
    title = item.find('span', class_='css-1n2d964').text.strip()
    link = item.find('a', class_='css-1w6h27r')['href']
    giveaways.append({'title': title, 'link': link})

  new_giveaways = []
  for giveaway in giveaways:
    if giveaway['title'] not in last_epic_giveaways:
      new_giveaways.append(giveaway)

  send_giveaway_notifications(new_giveaways, "Epic Games Store", chat_id)

  # Обновляем словарь последних раздач
  last_epic_giveaways.clear()
  for giveaway in giveaways:
    last_epic_giveaways[giveaway['title']] = giveaway['link']

  # Обновляем время последнего обновления для Epic в базе данных
  cursor.execute("UPDATE users SET last_epic_update = ? WHERE chat_id = ?", (datetime.now(), chat_id))
  conn.commit()

# Функция для проверки раздач на GOG
def check_gog_giveaways(chat_id):
  url = 'https://www.gog.com/giveaways'
  response = requests.get(url)
  soup = BeautifulSoup(response.content, 'html.parser')

  giveaways = []
  for item in soup.find_all('div', class_='giveaway__details'):
    title = item.find('h2', class_='giveaway__title').text.strip()
    link = item.find('a', class_='giveaway__link')['href']
    giveaways.append({'title': title, 'link': link})

  new_giveaways = []
  for giveaway in giveaways:
    if giveaway['title'] not in last_gog_giveaways:
      new_giveaways.append(giveaway)

  send_giveaway_notifications(new_giveaways, "GOG", chat_id)

  # Обновляем словарь последних раздач
  last_gog_giveaways.clear()
  for giveaway in giveaways:
    last_gog_giveaways[giveaway['title']] = giveaway['link']

  # Обновляем время последнего обновления для GOG в базе данных
  cursor.execute("UPDATE users SET last_gog_update = ? WHERE chat_id = ?", (datetime.now(), chat_id))
  conn.commit()

# --- Функции для подбора игры по вкусу ---

def choose_a_game_to_your_taste(chat_id):
    bot.send_message(chat_id, "Пожалуйста, введите жанр (например, RPG, Horror, Stealth):")
    bot.register_next_step_handler_by_chat_id(chat_id, lambda message: fetch_top_games(message, chat_id))

def fetch_top_games(message, chat_id):
    genre = message.text.strip()
    update_user_preferences(chat_id, genre)  # Обновляем предпочтения
    url = f'https://opencritic.com/browse/pc/all-time/score/{genre}'

    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    games = []
    for item in soup.find_all('div', class_='game-name col ml-2'):
        title = item.find('a').text.strip()
        link = "https://opencritic.com" + item.find('a')['href']
        games.append({'title': title, 'link': link})

    if games:
        top_games = games[:3]
        for game in top_games:
            bot.send_message(message.chat.id, "{} - {}".format(game['title'], game['link']))
    else:
        bot.send_message(message.chat.id, "Извините, игры в этом жанре не найдены.")

def update_user_preferences(chat_id, genre):
    cursor.execute("SELECT preferences FROM users WHERE chat_id = ?", (chat_id,))
    preferences = cursor.fetchone()

    if preferences:
        preferences = json.loads(preferences[0])
        if genre in preferences:
            preferences[genre] += 1
        else:
            preferences[genre] = 1
    else:
        preferences = {genre: 1}

    cursor.execute("UPDATE users SET preferences = ? WHERE chat_id = ?", (json.dumps(preferences), chat_id))
    conn.commit()

#Рекомендации от бота

def recommend_games(chat_id):
    cursor.execute("SELECT preferences FROM users WHERE chat_id = ?", (chat_id,))
    preferences = cursor.fetchone()

    if preferences:
        preferences = json.loads(preferences[0])
        top_genre = max(preferences, key=preferences.get)  # Получаем наиболее предпочтительный жанр
        return fetch_top_games_by_genre(top_genre, chat_id)
    else:
        bot.send_message(chat_id, "Нет предпочтений для рекомендаций.")

def fetch_top_games_by_genre(genre, chat_id):
    url = f'https://opencritic.com/browse/pc/all-time/score/{genre}'
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    games = []
    for item in soup.find_all('div', class_='game-name col ml-2'):
        title = item.find('a').text.strip()
        link = "https://opencritic.com" + item.find('a')['href']
        games.append({'title': title, 'link': link})

    if games:
        top_games = games[:3]
        for game in top_games:
            bot.send_message(chat_id, "{} - {}".format(game['title'], game['link']))
    else:
        bot.send_message(chat_id, "Извините, игры в этом жанре не найдены.")

# --- Функции для отправки уведомлений ---

# Функция для отправки уведомлений о новых раздачах всем пользователям
def send_giveaway_notifications(giveaways, platform, chat_id):
  if giveaways:
    for giveaway in giveaways:
      bot.send_message(chat_id, f"Новая бесплатная игра на {platform}: \n{giveaway['title']} - {giveaway['link']}")
  else:
    bot.send_message(chat_id, f"Новых раздач в {platform} нет!")

# Функция для проверки всех раздач
def check_all_giveaways(chat_id):
  check_steam_giveaways(chat_id)
  check_epic_giveaways(chat_id)
  check_gog_giveaways(chat_id)
  bot.send_message(chat_id, "Проверка всех раздач завершена!")

# --- Функция для повторения информации о последних раздачах ---
def repeat_giveaways(message, platform):
  chat_id = message.chat.id
  cursor.execute("SELECT last_steam_update, last_epic_update, last_gog_update FROM users WHERE chat_id = ?", (chat_id,))
  last_updates = cursor.fetchone()

  if platform == "Steam" and last_updates[0] is not None:
    check_steam_giveaways(chat_id)
  elif platform == "Epic Games Store" and last_updates[1] is not None:
    check_epic_giveaways(chat_id)
  elif platform == "GOG" and last_updates[2] is not None:
    check_gog_giveaways(chat_id)
  else:
    bot.send_message(chat_id, f"Информация о раздачах в {platform} отсутствует.")

# --- Автоматическая проверка раздач ---
def auto_check_giveaways():
  while True:
    cursor.execute("SELECT chat_id FROM users WHERE subscribed = TRUE")
    users = cursor.fetchall()
    for user in users:
      check_all_giveaways(user[0])
    time.sleep(43200) # 12 часов в секундах

# --- Запуск бота ---
# Запускаем автоматическую проверку раздач в отдельном потоке
thread = threading.Thread(target=auto_check_giveaways)
thread.start()

bot.polling(none_stop=True)