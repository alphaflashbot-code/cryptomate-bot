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
APP_URL = "https://cryptomate-bot-59m4.onrender.com" # Твоя ссылка
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

# --- МАШИНА СОСТОЯНИЙ ---
class BotStates(StatesGroup):
    # Для обменника
    exchange_pair = State()
    exchange_city = State()
    # Для курса крипты
    crypto_price_wait = State()

# --- КЛАВИАТУРЫ ---
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

# --- ФУНКЦИЯ: ЦЕНА С BINANCE (Только для Крипты) ---
async def get_binance_price(coin):
    # Добавляем USDT к названию, если пользователь не написал
    symbol = coin.upper().replace(" ", "")
    if not symbol.endswith("USDT"):
        symbol += "USDT"
    
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data['price'])
                return None
    except:
        return None

# =================================================
# ЛОГИКА 1: ОБМЕННИК (Любая пара + Город)
# =================================================

@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer(
        "🔄 **Подбор обменника**\n\n"
        "Напиши, что на что меняем.\n"
        "Пример: `Сбербанк RUB на BTC` или `Наличные USD на USDT`",
        reply_markup=cancel_keyboard
    )
    await state.set_state(BotStates.exchange_pair)

@dp.message(BotStates.exchange_pair)
async def exchange_get_pair(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_keyboard)
        return

    await state.update_data(pair=message.text)
    await message.answer("🏙 В каком городе (или напиши 'Онлайн')?", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.exchange_city)

@dp.message(BotStates.exchange_city)
async def exchange_finish(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_keyboard)
        return

    data = await state.get_data()
    pair = data['pair']
    city = message.text

    # Тут мы даем ссылки на агрегаторы, так как они работают с ЛЮБЫМИ парами
    text = (
        f"🔎 **Заявка принята!**\n"
        f"Обмен: `{pair}`\n"
        f"Место: `{city}`\n\n"
        f"✅ **Где можно совершить этот обмен прямо сейчас:**\n\n"
        f"1. **BestChange** (Агрегатор №1) — [Найти предложения](https://www.bestchange.ru/)\n"
        f"2. **Bybit P2P** (Гарантия биржи) — [Перейти](https://www.bybit.com/fiat/trade/otc)\n"
        f"3. **Telegram Wallet** (Быстро) — @wallet\n\n"
        f"⚠️ _Всегда проверяйте отзывы перед отправкой средств!_"
    )
    
    await message.answer(text, reply_markup=main_keyboard, disable_web_page_preview=True)
    await state.clear()

# =================================================
# ЛОГИКА 2: КУРС КРИПТОВАЛЮТ (Через Binance)
# =================================================

@dp.message(F.text == "🪙 Курс криптовалют")
async def crypto_rates_start(message: types.Message, state: FSMContext):
    await message.answer(
        "🪙 **Проверка стоимости**\n\n"
        "Напиши название монеты (тикер).\n"
        "Пример: `BTC`, `ETH`, `NOT`, `TON`",
        reply_markup=cancel_keyboard
    )
    await state.set_state(BotStates.crypto_price_wait)

@dp.message(BotStates.crypto_price_wait)
async def crypto_rates_result(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_keyboard)
        return

    coin = message.text.upper()
    await message.answer(f"🔎 Узнаю курс для **{coin}**...")

    price = await get_binance_price(coin)

    if price:
        # Красивое форматирование цены
        if price < 1:
            price_str = f"{price:.6f}" # Для дешевых монет типа PEPE
        else:
            price_str = f"{price:,.2f}" # Для дорогих типа BTC

        await message.answer(
            f"📊 **Курс {coin}/USDT:**\n"
            f"💰 `{price_str} $`",
            reply_markup=main_keyboard
        )
    else:
        await message.answer(
            f"⚠️ Не нашел монету **{coin}** на бирже.\n"
            f"Попробуй написать тикер точнее (например BTC).",
            reply_markup=main_keyboard
        )
    
    await state.clear()

# =================================================
# ОСТАЛЬНОЕ
# =================================================

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"Привет! Я CryptoMate 🤖.", reply_markup=main_keyboard)

@dp.message(F.text == "🏆 Топ бирж")
async def top_exchanges(message: types.Message):
    await message.answer(
        "🔥 **ТОП БИРЖ:**\n\n"
        "1. 🟡 **Bybit** — [Регистрация](https://www.bybit.com)\n"
        "2. 🔵 **BingX** — [Регистрация](https://bingx.com)\n"
        "3. ⚫️ **OKX** — [Регистрация](https://okx.com)",
        disable_web_page_preview=True
    )

# Заглушки для кнопок, которые еще не сделали
@dp.message(F.text.in_({"💵 Курс валют", "📈 Рынок Live"}))
async def development(message: types.Message):
    await message.answer("🛠 Этот раздел скоро появится!")

@dp.message()
async def ai_chat(message: types.Message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        response = model.generate_content(message.text)
        await message.answer(response.text)
    except:
        pass

# --- СЕРВЕР И PING (ЧТОБЫ РАБОТАЛ НА RENDER) ---
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
