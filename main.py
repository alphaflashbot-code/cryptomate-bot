import os
import asyncio
import logging
import sys
from aiohttp import web # Добавили библиотеку для "сайта"

# Библиотеки бота
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import google.generativeai as genai

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- ИНИЦИАЛИЗАЦИЯ ---
dp = Dispatcher()

if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
else:
    bot = None

# --- ГЕМИНИ ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
except:
    pass

# --- МЕНЮ ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💱 Обменник"), KeyboardButton(text="🏆 Топ бирж")],
        [KeyboardButton(text="🧠 Крипто-ИИ")]
    ],
    resize_keyboard=True
)

# --- ЛОГИКА БОТА ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"Привет, {message.from_user.first_name}! Я CryptoMate 🤖", reply_markup=main_keyboard)

@dp.message(F.text == "💱 Обменник")
async def exchange(message: types.Message):
    await message.answer("🛠 Раздел Обменник в разработке.")

@dp.message(F.text == "🏆 Топ бирж")
async def top_exchanges(message: types.Message):
    await message.answer("🔥 Топ бирж:\n1. Bybit\n2. BingX\n3. OKX")

@dp.message()
async def ai_chat(message: types.Message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = model.generate_content(message.text)
        await message.answer(response.text)
    except Exception as e:
        await message.answer("Ошибка ИИ или сети.")

# --- ФУНКЦИЯ-ОБМАНКА ДЛЯ RENDER (Keep-Alive) ---
async def health_check(request):
    return web.Response(text="Бот работает нормально!")

async def start_web_server():
    # Создаем маленький веб-сервер
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render сам скажет, какой порт использовать (обычно 10000)
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Веб-сервер запущен на порту {port} (Render доволен)")

# --- ГЛАВНЫЙ ЗАПУСК ---
async def main():
    if not BOT_TOKEN:
        print("❌ Нет токена!")
        return

    # 1. Запускаем обманку
    await start_web_server()
    
    # 2. Запускаем бота
    print("✅ Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
