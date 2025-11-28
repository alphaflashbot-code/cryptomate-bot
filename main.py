import os
import asyncio
import logging
import sys
from aiohttp import web, ClientSession # Добавили ClientSession для пинга

# Библиотеки бота
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import google.generativeai as genai

# --- ВАЖНО: АДРЕС ТВОЕГО БОТА (из логов Render) ---
APP_URL = "https://cryptomate-bot-59m4.onrender.com"
# --------------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

dp = Dispatcher()
bot = None
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))

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

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"Привет! Я CryptoMate 🤖. Я не сплю!", reply_markup=main_keyboard)

@dp.message(F.text == "💱 Обменник")
async def exchange(message: types.Message):
    await message.answer("🛠 Скоро будет.")

@dp.message(F.text == "🏆 Топ бирж")
async def top_exchanges(message: types.Message):
    await message.answer("🔥 Bybit, BingX, OKX")

@dp.message()
async def ai_chat(message: types.Message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = model.generate_content(message.text)
        await message.answer(response.text)
    except:
        await message.answer("Ошибка ИИ.")

# --- ВЕБ-СЕРВЕР ---
async def health_check(request):
    return web.Response(text="Бот работает и не спит!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"✅ Веб-сервер запущен на порту {port}")

# --- БУДИЛЬНИК (PING) ---
async def keep_alive():
    while True:
        await asyncio.sleep(600) # Ждем 10 минут
        try:
            async with ClientSession() as session:
                async with session.get(APP_URL) as response:
                    print(f"⏰ ПИНГ САМОГО СЕБЯ: Статус {response.status}")
        except Exception as e:
            print(f"⚠️ Ошибка пинга: {e}")

# --- ЗАПУСК ---
async def main():
    if not BOT_TOKEN:
        print("❌ Нет токена!")
        return

    # 1. Запускаем сервер
    await start_web_server()
    
    # 2. Запускаем "Будильник" в фоне
    asyncio.create_task(keep_alive())
    
    # 3. Запускаем бота
    print("✅ Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
