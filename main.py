import telebot
from PIL import Image
import os
import sys

# ПОЛУЧАЕМ ТОКЕН ИЗ ОКРУЖЕНИЯ (Безопасно)
# Если переменной нет (например, при локальном запуске), программа выдаст ошибку
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("Ошибка: Токен не найден! Установите переменную окружения BOT_TOKEN.")
    sys.exit()

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Пришли мне фото, я сделаю из него PDF.")

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
            bot.send_document(chat_id, doc, caption="Ваш PDF готов! 📄")

        os.remove(src_filename)
        os.remove(pdf_filename)

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

# Запуск
print("Бот запущен...")
bot.infinity_polling()
