import os
import asyncio
import logging
import sys

# Библиотеки
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import google.generativeai as genai

# --- ПОЛУЧАЕМ КЛЮЧИ ИЗ НАСТРОЕК СЕРВЕРА (RENDER) ---
# Бот сам заберет их из безопасного хранилища Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Проверка, что ключи загрузились
if not BOT_TOKEN or not GEMINI_API_KEY:
    print("❌ ОШИБКА: Ключи не найдены! Проверь Environment Variables на Render.")
    # Не выходим, чтобы бот не падал в цикле перезагрузки, но пишем ошибку
    
# --- НАСТРОЙКА GEMINI ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Ошибка настройки Gemini: {e}")

# --- НАСТРОЙКА БОТА ---
dp = Dispatcher()
# Если токена нет, бот не запустится, но код не упадет сразу
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
else:
    print("⚠️ Бот не инициализирован (нет токена)")

# --- МЕНЮ ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💱 Обменник"), KeyboardButton(text="🏆 Топ бирж")],
        [KeyboardButton(text="🧠 Крипто-ИИ")]
    ],
    resize_keyboard=True
)

# --- ЛОГИКА ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}! Я CryptoMate 🤖\nЯ работаю в облаке 24/7!", 
        reply_markup=main_keyboard
    )

@dp.message(F.text == "💱 Обменник")
async def exchange(message: types.Message):
    await message.answer("🛠 Раздел Обменник в разработке.")

@dp.message(F.text == "🏆 Топ бирж")
async def top_exchanges(message: types.Message):
    await message.answer("🔥 Топ бирж:\n1. Bybit\n2. BingX\n3. OKX")

@dp.message()
async def ai_chat(message: types.Message):
    if not GEMINI_API_KEY:
        await message.answer("⚠️ ИИ пока не настроен.")
        return
        
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = model.generate_content(message.text)
        await message.answer(response.text)
    except Exception as e:
        await message.answer(f"Ошибка ИИ: {e}")

# --- ЗАПУСК ---
async def main():
    if not BOT_TOKEN:
        print("⛔️ Стоп: Нет токена бота.")
        return
        
    print("✅ Бот запущен на сервере Render!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
