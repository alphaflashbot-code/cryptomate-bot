import telebot
from PIL import Image
import os
from flask import Flask
from threading import Thread
import time

# --- ЧАСТЬ 1: НАСТРОЙКИ БОТА ---
# Лучше брать токен из переменных окружения (безопасность), 
# но для начала можно оставить и так, или настроить Environment Variables в Render.
TOKEN = 'ВАШ_ТОКЕН_ЗДЕСЬ' 
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я работаю на сервере Render! 🚀\nПришли фото для конвертации.")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        chat_id = message.chat.id
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        src_filename = f"photo_{chat_id}.jpg"
        pdf_filename = f"document_{chat_id}.pdf"

        with open(src_filename, 'wb') as new_file:
            new_file.write(downloaded_file)

        bot.send_message(chat_id, "⚙️ Конвертирую...")

        image = Image.open(src_filename)
        rgb_image = image.convert('RGB')
        rgb_image.save(pdf_filename)

        with open(pdf_filename, 'rb') as doc:
            bot.send_document(chat_id, doc, caption="Готово! ✅")

        os.remove(src_filename)
        os.remove(pdf_filename)

    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

# --- ЧАСТЬ 2: ФЕЙКОВЫЙ ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive"

def run():
    # Render ожидает, что мы будем слушать порт 0.0.0.0
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- ЗАПУСК ---
if __name__ == "__main__":
    keep_alive() # Запускаем веб-сервер в отдельном потоке
    bot.infinity_polling() # Запускаем бота
