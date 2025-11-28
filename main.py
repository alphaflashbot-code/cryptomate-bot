import os
import asyncio
import logging
import sys
from aiohttp import web, ClientSession

# Библиотеки бота
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import google.generativeai as genai

# --- URL ДЛЯ БУДИЛЬНИКА ---
APP_URL = "https://cryptomate-bot-59m4.onrender.com"

# --- НАСТРОЙКИ ---
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

# --- СОСТОЯНИЯ ---
class ExchangeSteps(StatesGroup):
    waiting_for_pair = State()
    waiting_for_city = State()

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

# --- ФУНКЦИЯ: ПОЛУЧЕНИЕ ЦЕНЫ С BINANCE ---
async def get_crypto_price(pair_text):
    # Пытаемся привести текст к формату биржи (например "BTC USDT" -> "BTCUSDT")
    symbol = pair_text.upper().replace(" ", "").replace("/", "")
    
    # Binance API (бесплатный, ключи не нужны)
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    
    try:
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data['price'])
                    # Красиво форматируем цену
                    return f"{price:,.2f}" 
                else:
                    return None # Не нашли такую пару
    except:
        return None

# --- ЛОГИКА БОТА ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"Привет! Я CryptoMate 🤖. Работаю на реальных данных!", reply_markup=main_keyboard)

# 1. СТАРТ ОБМЕНА
@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer(
        "🔄 **Поиск выгодного курса**\n\n"
        "Напиши пару тикеров через пробел.\n"
        "Примеры: `BTC USDT`, `ETH BTC`, `TON USDT`",
        reply_markup=cancel_keyboard
    )
    await state.set_state(ExchangeSteps.waiting_for_pair)

# 2. ПОЛУЧАЕМ ПАРУ
@dp.message(ExchangeSteps.waiting_for_pair)
async def exchange_get_pair(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_keyboard)
        return

    # Запоминаем пару
    await state.update_data(pair=message.text)
    
    await message.answer(
        "🏙 Введи **Город** (или напиши 'Карта', 'Сбер', 'Тинькофф' для онлайна):",
        reply_markup=cancel_keyboard
    )
    await state.set_state(ExchangeSteps.waiting_for_city)

# 3. ФИНАЛ: ВЫДАЕМ РЕЗУЛЬТАТ
@dp.message(ExchangeSteps.waiting_for_city)
async def exchange_finish(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_keyboard)
        return

    user_data = await state.get_data()
    pair_raw = user_data['pair']
    city = message.text

    await message.answer(f"🔎 Сканирую рынок для **{pair_raw}** ({city})...")

    # 1. Пытаемся узнать реальную биржевую цену
    real_price = await get_crypto_price(pair_raw)

    if real_price:
        price_text = f"📈 **Биржевой курс:** `{real_price}`"
        note = "ℹ️ _В обменниках курс обычно отличается на 1-3%_"
    else:
        price_text = "⚠️ Биржевой курс не найден (возможно, редкая пара)."
        note = ""

    # 2. Формируем "Умную ссылку" на BestChange (поиск)
    # Мы не можем парсить BestChange напрямую (защита), но можем отправить человека туда
    search_link = "https://www.bestchange.ru/" 

    # Кнопка ссылки
    keyboard_inline = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Найти на BestChange", url=search_link)]
    ])

    result_text = (
        f"✅ **Результат для {pair_raw}**\n\n"
        f"{price_text}\n"
        f"{note}\n\n"
        f"📍 Локация: {city}\n"
        f"👇 Жми кнопку ниже, чтобы увидеть список продавцов:"
    )
    
    await message.answer(result_text, reply_markup=keyboard_inline)
    await message.answer("Готово! Что делаем дальше?", reply_markup=main_keyboard) # Возвращаем главное меню
    
    await state.clear()

# --- ОСТАЛЬНЫЕ КНОПКИ ---
@dp.message(F.text == "🏆 Топ бирж")
async def top_exchanges(message: types.Message):
    # Сюда вставь СВОИ реферальные ссылки
    text = (
        "🔥 **ТОП БИРЖ (Проверено)**\n\n"
        "1. 🟡 **Bybit** — [Бонусы до $30,000](https://www.bybit.com)\n"
        "2. 🔵 **BingX** — [Без KYC](https://bingx.com)\n"
        "3. ⚫️ **OKX** — [Надежность](https://okx.com)\n"
    )
    await message.answer(text, disable_web_page_preview=True)

@dp.message()
async def ai_chat(message: types.Message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = model.generate_content(message.text)
        await message.answer(response.text)
    except:
        pass

# --- СЕРВЕР И PING ---
async def health_check(request):
    return web.Response(text="OK")

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

async def main():
    if not BOT_TOKEN: return
    await start_web_server()
    asyncio.create_task(keep_alive())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
