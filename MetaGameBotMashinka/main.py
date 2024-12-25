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
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

user_states = {}
games_data = None
tfidf_matrix = None
tfidf = None
# Токен бота
bot_token = "7799776104:AAGLrlCXCFDjzjFAmt77qptkTAVhui6XIPM"
if bot_token is None:
    raise ValueError("BOT_TOKEN environment variable not set")

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
    subscribed BOOLEAN DEFAULT FALSE
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

    # Database interaction (remains the same)
    cursor.execute("SELECT 1 FROM users WHERE chat_id = ?", (chat_id,))
    user_exists = cursor.fetchone()
    if not user_exists:
        cursor.execute("INSERT INTO users (chat_id) VALUES (?)", (chat_id,))
        conn.commit()

    text = "Привет! Я бот, с которым тебе будет проще подбирать классные игры на вечер! ✨\n ——— Что я умею 👇 ——— \n Оповещать о раздачах бесплатных игр и клевых скидках в Steam 🎮💨\n Оповещать о раздачах бесплатных игр и клевых скидках в Epic Store 🎮🪄\n Оповещать о раздачах бесплатных игр и клевых скидках в Gog Store🎮🎉\n Подберу тебе персонально замечательную игру исходя из твоих предпочтений!⚡️🎯\n\n ——— 🤖 Почему меня стоит использовать? 📍 ———\n 1) Твой персональный подбор игр прямо в Telegram! Вечер явно будет интереснее! 🎮🤖\n 2) Оповещение о раздачах сразу из трёх магазинов! Больше не нужно заходить на остальные сайты, достаточно подождать моего оповещения!💎🎁\n 3) Оповещу о новых раздачах быстрее чем остальные ресурсы! Мои процессы оптимизированы, раздачи и скидки присылаю по мере их появления! 🚀\n ——————\n Для начала работы со мной, выбери один из пунктов в меню! Также пожалуйста подпишись, чтобы не пропустить свежие раздачи! 💫"

    image_path = os.path.join('image', 'Hello.png')

    try:
        with open(image_path, 'rb') as photo_file: # Open file in a with statement, still
            photo = photo_file.read() # Read the file content into a variable
            bot.send_photo(chat_id, photo, caption=text)
    except FileNotFoundError:
        bot.reply_to(message, f"Ошибка: изображение {image_path} не найдено.")
        print(f"Ошибка: изображение {image_path} не найдено.")
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {e}")
        print(f"Произошла ошибка: {e}")
    else:
        show_menu(message)


# Функция для показа меню
def show_menu(message):
 markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
 item1 = types.KeyboardButton("Раздачи в Steam")
 item2 = types.KeyboardButton("Раздачи в Epic")
 item3 = types.KeyboardButton("Раздачи в GOG")
 item4 = types.KeyboardButton("Все раздачи")
 item5 = types.KeyboardButton("Подписаться")
 item6 = types.KeyboardButton("Отписаться")
 item7 = types.KeyboardButton("Помощь")
 item8 = types.KeyboardButton("Рекомендовать игру")
 markup.add(item1, item2, item3, item4, item5, item6, item7, item8)
 bot.send_message(message.chat.id, "Выберите команду", reply_markup=markup)

# Обработка кнопок и текстовых команд
@bot.message_handler(content_types=['text'])
def func(message):
 chat_id = message.chat.id
 if message.text == "Раздачи в Steam":
  check_steam_giveaways(chat_id)
 elif message.text == "Раздачи в Epic":
  check_epic_giveaways(chat_id)
 elif message.text == "Раздачи в GOG":
  check_gog_giveaways(chat_id)
 elif message.text == "Все раздачи":
  check_all_giveaways(chat_id)
 elif message.text == "Подписаться":
  subscribe(chat_id)
 elif message.text == "Рекомендовать игру":
  start_recommendation(message)
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

# ---- рекомендательная система ----
def init_recommendations():
    global games_data, tfidf_matrix, tfidf
    try:
        games_data = pd.read_csv("games.csv")
        #  Добавляем проверку на наличие необходимых столбцов
        required_columns = ['Name', 'Genre', 'Publisher', 'Rating', 'Platform']
        if not all(col in games_data.columns for col in required_columns):
            raise ValueError(f"games.csv must contain columns: {required_columns}")

        # Создаем TF-IDF векторизатор для каждого критерия
        tfidf = TfidfVectorizer(stop_words='english')
        tfidf_matrix = tfidf.fit_transform(games_data['Genre'] + ' ' + games_data['Publisher'] + ' ' + games_data['Platform'] + ' ' + games_data['Rating'].astype(str))

    except FileNotFoundError:
        print("Файл games.csv не найден.")
    except Exception as e:
        print(f"Ошибка при инициализации рекомендательной системы: {e}")

init_recommendations()

# рекомендации
def get_recommendations(genre=None, publisher=None, platform=None, rating=None):
    if games_data is None or tfidf_matrix is None:
        return pd.DataFrame(columns=['Name', 'Genre', 'Publisher', 'Rating', 'Platform'])

    query = ""
    if genre:
        query += genre + " "
    if rating:
        query += rating + " "

    if not query.strip(): #Если ни одного критерия не указано
      return pd.DataFrame(columns=['Name', 'Genre', 'Publisher', 'Rating', 'Platform'])

    query_vector = tfidf.transform([query])
    similarities = cosine_similarity(query_vector, tfidf_matrix).flatten()
    related_docs_indices = np.argsort(similarities)[::-1]
    recommendations = games_data.iloc[related_docs_indices[1:6]]
    return recommendations


@bot.message_handler(func=lambda message: message.text.lower() == "рекомендовать игру")
def start_recommendation(message):
    chat_id = message.chat.id
    user_states[chat_id] = {"stage": "genre"}
    msg = bot.reply_to(message, "Введите жанр игры (например, RPG, Action, Adventure, Strategy, Simulation, Puzzle, Racing):")
    bot.register_next_step_handler(msg, handle_genre_selection)

#жанровое
def show_genre_selection(message):
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    genres = ['RPG', 'Action', 'Adventure', 'Strategy', 'Simulation', 'Puzzle', 'Racing']
    markup.add(*genres)
    bot.send_message(chat_id, "Выберите жанр:", reply_markup=markup)

#@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("stage") == "genre")
def handle_genre_selection(message):
  chat_id = message.chat.id
  genre = message.text.strip().title()
  valid_genres = ['RPG', 'Action', 'Adventure', 'Strategy', 'Simulation', 'Puzzle', 'Racing']
  if genre in valid_genres:
      user_states[chat_id]["genre"] = genre
      user_states[chat_id]["stage"] = "rating"
      msg = bot.reply_to(message, "Введите минимальную оценку (7, 8, или 9):")
      bot.register_next_step_handler(msg, handle_rating_selection)
  else:
      msg = bot.reply_to(message, f"Неверный жанр. Пожалуйста, выберите из списка: {', '.join(valid_genres)}")
      bot.register_next_step_handler(msg, handle_genre_selection) #Loop back if invalid


#оценковое

def handle_rating_selection(message):
    chat_id = message.chat.id
    rating_str = message.text.strip()

    # Проверка на наличие только цифр
    if not rating_str.isdigit():
        msg = bot.reply_to(message, "Неверный формат оценки. Пожалуйста, введите число (7, 8 или 9):")
        bot.register_next_step_handler(msg, handle_rating_selection)
        return

    try:
        rating = int(rating_str)
        if rating in [7, 8, 9]:
            user_states[chat_id]["rating"] = str(rating) + "+"
            recommendations = get_recommendations(genre=user_states[chat_id].get("genre"), rating=user_states[chat_id]["rating"])
            send_recommendations(recommendations, chat_id)  # Изменено на send_recommendations
            del user_states[chat_id]  # Удаляем состояние пользователя
        else:
            msg = bot.reply_to(message, "Неверная оценка. Пожалуйста, введите 7, 8 или 9:")
            bot.register_next_step_handler(msg, handle_rating_selection)
    except Exception as e:
        msg = bot.reply_to(message, f"Произошла ошибка: {str(e)}. Попробуйте еще раз.")
        bot.register_next_step_handler(msg, handle_rating_selection)


@bot.message_handler(func=lambda message: True)
def handle_default_message(message):
    chat_id = message.chat.id
    if chat_id in user_states:
        current_stage = user_states[chat_id]["stage"]
        if current_stage == "genre":
            bot.send_message(chat_id, "Выберите жанр из предложенных вариантов.")
        elif current_stage == "rating":
            bot.send_message(chat_id, "Выберите минимальную оценку из предложенных вариантов.")
    else:
        bot.send_message(chat_id, "Чтобы получить рекомендации, напишите 'Рекомендовать игру'.")


def send_recommendations(recommendations, chat_id):
    if not recommendations.empty:
        for index, row in recommendations.iterrows():
            game_name = row['Name']
            image_url, description = get_steam_game_info(chat_id, game_name) # chat_id передается сюда

            if image_url:
                try:
                    bot.send_photo(chat_id, image_url)
                except Exception as e:
                    bot.send_message(chat_id, f"Ошибка при отправке изображения {game_name}: {e}")
            else:
                bot.send_message(chat_id, f"Изображение для {game_name} не найдено.")

            if description:
                bot.send_message(chat_id, f"Название: {game_name}\nОписание: {description}")
            else:
                bot.send_message(chat_id, f"Описание для {game_name} не найдено.")
    else:
        bot.send_message(chat_id, "К сожалению, ничего не найдено.")


def get_steam_game_info(chat_id, game_name):
    try:
        # Формируем URL для поиска игры на Steam (более точный поиск невозможен без API)
        url = f"https://store.steampowered.com/search/?term={game_name}"
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Попытка найти более надежные селекторы (но все равно не идеально без API)
        image_element = soup.select_one('.col-search-result__image img') # попробуем другой селектор
        if image_element:
            image_url = image_element['src']
        else:
            image_url = None

        description_element = soup.select_one('.search_result_desc')
        description = description_element.text.strip() if description_element else "Описание не найдено."


        return image_url, description

    except requests.exceptions.RequestException as e:
        bot.send_message(chat_id, f"Ошибка при подключении к Steam: {e}")
        return None, None
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка: {e}")
        return None, None


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

@bot.message_handler(commands=['help'])
def help_command(message):
    chat_id = message.chat.id
    text = "Мои команды:\n/start - начать\n/subscribe - подписаться на уведомления\n/unsubscribe - отписаться от уведомлений\n/check - проверить раздачи\n/help - вывести список команд"
    image_path = os.path.join('image', 'Help.png')

    try:
        with open(image_path, 'rb') as photo_file:
            photo = photo_file.read()
            bot.send_photo(chat_id, photo, caption=text)
    except FileNotFoundError:
        bot.reply_to(message, f"Ошибка: изображение {image_path} не найдено. Текст справки:\n{text}")
        print(f"Ошибка: изображение {image_path} не найдено.")
    except Exception as e:
        bot.reply_to(message, f"Произошла ошибка: {e}. Текст справки:\n{text}")
        print(f"Произошла ошибка: {e}")
# --- Функции для проверки раздач ---

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

  #new_giveaways = []
  #for giveaway in giveaways:
   # if giveaway['title'] not in last_steam_giveaways:
    #  new_giveaways.append(giveaway)

  send_giveaway_notifications(giveaways, "Steam", chat_id)

  # Обновляем словарь последних раздач
  #last_steam_giveaways.clear()
  #for giveaway in giveaways:
  #  last_steam_giveaways[giveaway['title']] = giveaway['link']

  # Обновляем время последнего обновления для Steam в базе данных
  #cursor.execute("UPDATE users SET last_steam_update = ? WHERE chat_id = ?", (datetime.now(), chat_id))
  #conn.commit()

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

 # new_giveaways = []
  #for giveaway in giveaways:
   # if giveaway['title'] not in last_epic_giveaways:
   #   new_giveaways.append(giveaway)

  #send_giveaway_notifications(new_giveaways, "Epic Games Store", chat_id)

  # Обновляем словарь последних раздач
  #last_epic_giveaways.clear()
  #for giveaway in giveaways:
  #  last_epic_giveaways[giveaway['title']] = giveaway['link']

  # Обновляем время последнего обновления для Epic в базе данных
  #cursor.execute("UPDATE users SET last_epic_update = ? WHERE chat_id = ?", (datetime.now(), chat_id))
  #conn.commit()

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

 # new_giveaways = []
  #for giveaway in giveaways:
  #  if giveaway['title'] not in last_gog_giveaways:
   #   new_giveaways.append(giveaway)

 # send_giveaway_notifications(new_giveaways, "GOG", chat_id)

  # Обновляем словарь последних раздач
  #last_gog_giveaways.clear()
  #for giveaway in giveaways:
  #  last_gog_giveaways[giveaway['title']] = giveaway['link']

  # Обновляем время последнего обновления для GOG в базе данных
  #cursor.execute("UPDATE users SET last_gog_update = ? WHERE chat_id = ?", (datetime.now(), chat_id))
  #conn.commit()

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
#def repeat_giveaways(message, platform):
  #chat_id = message.chat.id
 # cursor.execute("SELECT last_steam_update, last_epic_update, last_gog_update FROM users WHERE chat_id = ?", (chat_id,))
 # last_updates = cursor.fetchone()

  #if platform == "Steam" and last_updates[0] is not None:
   # check_steam_giveaways(chat_id)
 # elif platform == "Epic Games Store" and last_updates[1] is not None:
 #   check_epic_giveaways(chat_id)
 # elif platform == "GOG" and last_updates[2] is not None:
 #   check_gog_giveaways(chat_id)
 # else:
 #   bot.send_message(chat_id, f"Информация о раздачах в {platform} отсутствует.")

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

bot.polling(none_stop=True)