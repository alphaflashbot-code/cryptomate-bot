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

# --- НАСТРОЙКИ ---
APP_URL = "https://cryptomate-bot-59m4.onrender.com"
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

dp = Dispatcher()
bot = None
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))

try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
except:
    pass

class BotStates(StatesGroup):
    exchange_pair = State()
    exchange_city = State()
    crypto_price_wait = State()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💱 Обменник"), KeyboardButton(text="🏆 Топ бирж")],
        [KeyboardButton(text="💵 Курс валют"), KeyboardButton(text="🪙 Курс криптовалют")],
        [KeyboardButton(text="📈 Рынок Live"), KeyboardButton(text="🧠 Крипто-ИИ")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

# --- BINANCE PRICE ---
async def get_binance_price(coin):
    symbol = coin.upper().replace(" ", "")
    if not symbol.endswith("USDT"): symbol += "USDT"
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data['price'])
                return None
    except: return None

# =================================================
# ЛОГИКА ОБМЕННИКА (УМНАЯ)
# =================================================

@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer("🔄 **Что меняем?**\n(Например: `USDT на Наличные USD` или `RUB на BTC`)", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.exchange_pair)

@dp.message(BotStates.exchange_pair)
async def exchange_get_pair(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    
    await state.update_data(pair=message.text)
    await message.answer("🏙 **Где нужен обмен?**\n\nНапиши **Название города** (для наличных)\nИли напиши **Онлайн** (для карт/банков).", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.exchange_city)

@dp.message(BotStates.exchange_city)
async def exchange_finish(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return

    data = await state.get_data()
    pair = data['pair']
    city_raw = message.text.strip()
    
    # Проверяем, хочет ли человек наличные или онлайн
    is_online = city_raw.lower() in ['онлайн', 'online', 'интернет', 'internet', 'сбер', 'тинькофф', 'карта']
    
    # Формируем клавиатуру (кнопки)
    rows = []
    
    if is_online:
        # Если Онлайн -> Даем P2P и агрегаторы
        text_result = f"💻 **Подборка для онлайн обмена:**\nПара: `{pair}`"
        rows.append([InlineKeyboardButton(text="🟢 BestChange (Все обменники)", url="https://www.bestchange.ru/")])
        rows.append([InlineKeyboardButton(text="🟡 Bybit P2P (Без комиссий)", url="https://www.bybit.com/fiat/trade/otc")])
        rows.append([InlineKeyboardButton(text="🔵 Telegram Wallet", url="https://t.me/wallet")])
    else:
        # Если Город -> Генерируем ссылку на Карту этого города!
        text_result = f"🏙 **Обмен наличных в г. {city_raw}**\nПара: `{pair}`"
        
        # Ссылка на Google Maps с поиском "Криптообменник + Город"
        maps_url = f"https://www.google.com/maps/search/crypto+exchange+{city_raw}"
        
        rows.append([InlineKeyboardButton(text=f"📍 Открыть карту обменников ({city_raw})", url=maps_url)])
        rows.append([InlineKeyboardButton(text="🟢 Найти курс на BestChange", url="https://www.bestchange.ru/")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    await message.answer(text_result, reply_markup=keyboard)
    await message.answer("Если нужно что-то еще — выбери в меню 👇", reply_markup=main_keyboard)
    await state.clear()

# =================================================
# ОСТАЛЬНОЕ (БЕЗ ИЗМЕНЕНИЙ)
# =================================================

@dp.message(F.text == "🪙 Курс криптовалют")
async def crypto_rates_start(message: types.Message, state: FSMContext):
    await message.answer("🪙 Введи тикер монеты (BTC, ETH, SOL):", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.crypto_price_wait)

@dp.message(BotStates.crypto_price_wait)
async def crypto_rates_result(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    coin = message.text.upper()
    price = await get_binance_price(coin)
    if price:
        await message.answer(f"📊 **{coin}/USDT:** `{price:,.2f} $`", reply_markup=main_keyboard)
    else:
        await message.answer("⚠️ Не нашел такую монету.", reply_markup=main_keyboard)
    await state.clear()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"Привет! Я CryptoMate 🤖.", reply_markup=main_keyboard)

@dp.message(F.text == "🏆 Топ бирж")
async def top_exchanges(message: types.Message):
    await message.answer("🔥 Bybit, BingX, OKX (твои ссылки)")

@dp.message()
async def ai_chat(message: types.Message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = model.generate_content(message.text)
        await message.answer(response.text)
    except: pass

async def health_check(request): return web.Response(text="OK")
async def start_web_server():
    app = web.Application(); app.router.add_get('/', health_check)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port); await site.start()

async def keep_alive():
    while True:
        await asyncio.sleep(600)
        try:
            async with ClientSession() as session:
                async with session.get(APP_URL) as response: pass
        except: pass

async def main():
    if not BOT_TOKEN: return
    await start_web_server()
    asyncio.create_task(keep_alive())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
