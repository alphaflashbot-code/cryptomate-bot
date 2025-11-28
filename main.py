import os
import asyncio
import logging
import sys
from aiohttp import web, ClientSession

# Библиотеки бота
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup # Для диалогов

import google.generativeai as genai

# --- ВАЖНО: АДРЕС ТВОЕГО БОТА ---
# (Оставляем как есть, чтобы не уснул)
APP_URL = "https://cryptomate-bot-59m4.onrender.com"
# --------------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

dp = Dispatcher()
bot = None
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))

# --- НАСТРОЙКА GEMINI ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
except:
    pass

# --- МАШИНА СОСТОЯНИЙ (ЭТАПЫ ОПРОСА) ---
class ExchangeSteps(StatesGroup):
    waiting_for_pair = State() # Ждем пару
    waiting_for_city = State() # Ждем город

# --- КЛАВИАТУРЫ ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💱 Обменник"), KeyboardButton(text="🏆 Топ бирж")],
        [KeyboardButton(text="🧠 Крипто-ИИ")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

# --- ЛОГИКА БОТА ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"Привет! Я CryptoMate 🤖. Выбери действие:", reply_markup=main_keyboard)

# 1. ЧЕЛОВЕК НАЖАЛ "ОБМЕННИК"
@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer(
        "🔄 **Начинаем поиск обмена!**\n\n"
        "Напиши валютную пару (например: `BTC RUB` или `USDT USD`).",
        reply_markup=cancel_keyboard
    )
    # Включаем режим ожидания пары
    await state.set_state(ExchangeSteps.waiting_for_pair)

# 2. ЧЕЛОВЕК НАПИСАЛ ПАРУ (Ловим ответ)
@dp.message(ExchangeSteps.waiting_for_pair)
async def exchange_get_pair(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Поиск отменен.", reply_markup=main_keyboard)
        return

    # Запоминаем пару в память
    await state.update_data(pair=message.text)
    
    await message.answer(
        "Хорошо. Теперь напиши **Город**, где хочешь получить деньги.\n(Например: `Москва` или `Онлайн`)",
        reply_markup=cancel_keyboard
    )
    # Переключаем состояние на ожидание города
    await state.set_state(ExchangeSteps.waiting_for_city)

# 3. ЧЕЛОВЕК НАПИСАЛ ГОРОД (Финал)
@dp.message(ExchangeSteps.waiting_for_city)
async def exchange_finish(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Поиск отменен.", reply_markup=main_keyboard)
        return

    # Достаем запомненные данные
    user_data = await state.get_data()
    pair = user_data['pair']
    city = message.text

    await message.answer(f"🔎 Ищу лучшие курсы для: **{pair}** в городе **{city}**...")
    
    # --- ТУТ БУДЕТ РЕАЛЬНЫЙ ПОИСК (В СЛЕДУЮЩЕМ УРОКЕ) ---
    await asyncio.sleep(1) # Имитация работы
    
    fake_result = (
        f"📊 **Лучшие предложения ({pair} -> {city}):**\n\n"
        "1. **CryptoFast** — Курс: 98.5 — [Перейти](https://google.com)\n"
        "2. **BestChange** — Курс: 98.2 — [Перейти](https://google.com)\n"
        "3. **MoneySwap** — Курс: 97.9 — [Перейти](https://google.com)\n\n"
        "⚠️ _Это тестовые данные. Реальный поиск подключим следующим шагом._"
    )
    # ----------------------------------------------------
    
    await message.answer(fake_result, reply_markup=main_keyboard, disable_web_page_preview=True)
    # Очищаем память
    await state.clear()

# ОБРАБОТКА ИИ (Только если не идет поиск обмена)
@dp.message()
async def ai_chat(message: types.Message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = model.generate_content(message.text)
        await message.answer(response.text)
    except:
        await message.answer("Я слушаю...")

# --- ВЕБ-СЕРВЕР И БУДИЛЬНИК (ЧТОБЫ НЕ СПАЛ) ---
async def health_check(request):
    return web.Response(text="Бот работает!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def keep_alive():
    while True:
        await asyncio.sleep(600)
        try:
            async with ClientSession() as session:
                async with session.get(APP_URL) as response:
                    pass
        except:
            pass

# --- ЗАПУСК ---
async def main():
    if not BOT_TOKEN:
        print("❌ Нет токена!")
        return
    await start_web_server()
    asyncio.create_task(keep_alive())
    print("✅ Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
