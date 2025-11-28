import os
import asyncio
import logging
import sys
import re
from aiohttp import web, ClientSession

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

# --- СЛОВАРЬ ВАЛЮТ ---
CURRENCY_MAP = {
    'RUB': 'rub', 'РУБ': 'rub', 'РУБЛЬ': 'rub', 'RUR': 'rub', 'СБЕР': 'rub', 'ТИНЬКОФФ': 'rub',
    'UAH': 'uah', 'ГРН': 'uah', 'ГРИВНА': 'uah', 'МОНО': 'uah', 'ПРИВАТ': 'uah',
    'USD': 'usd', 'ДОЛЛАР': 'usd', 'БАКИ': 'usd',
    'EUR': 'eur', 'ЕВРО': 'eur',
    'KZT': 'kzt', 'ТЕНГЕ': 'kzt', 'КАСПИ': 'kzt',
    'USDT': 'tether-trc20', 'TRC20': 'tether-trc20', 'ТЕЗЕР': 'tether-trc20',
    'BTC': 'bitcoin', 'БИТОК': 'bitcoin',
    'ETH': 'ethereum', 'TON': 'toncoin', 'LTC': 'litecoin'
}

# --- СОСТОЯНИЯ ---
class BotStates(StatesGroup):
    exchange_pair = State()
    exchange_method_give = State()
    exchange_method_get = State()
    exchange_city = State()
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

def get_method_keyboard(prefix):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта / Банк / Онлайн", callback_data=f"{prefix}_card")],
        [InlineKeyboardButton(text="💵 Наличные (Cash)", callback_data=f"{prefix}_cash")],
        [InlineKeyboardButton(text="🪙 Криптовалюта", callback_data=f"{prefix}_crypto")]
    ])

# --- ЛОГИКА КОДОВ ---
def resolve_code(currency_raw, method):
    cur = currency_raw.upper()
    code_base = CURRENCY_MAP.get(cur, cur.lower()) 
    
    if '-' in code_base or code_base in ['bitcoin', 'ethereum', 'toncoin', 'litecoin', 'monero', 'tether-trc20']:
        return code_base

    if method == 'cash':
        return f"cash-{code_base}"
    
    elif method == 'card':
        if code_base == 'rub': return 'sberbank'
        if code_base == 'uah': return 'visa-mastercard-uah'
        if code_base == 'kzt': return 'visa-mastercard-kzt'
        if code_base == 'usd': return 'visa-mastercard-usd'
        return code_base
        
    return code_base

# --- ФУНКЦИЯ ПОКАЗА РЕЗУЛЬТАТА (ЧТОБЫ НЕ ДУБЛИРОВАТЬ КОД) ---
async def show_result(message, give_raw, get_raw, m_give, m_get, city):
    # Генерируем коды
    code_give = resolve_code(give_raw, m_give)
    code_get = resolve_code(get_raw, m_get)

    # Ссылка
    if code_give == code_get:
        final_link = "https://www.bestchange.ru/"
    else:
        final_link = f"https://www.bestchange.ru/{code_give}-to-{code_get}.html"
        
    rows = []
    rows.append([InlineKeyboardButton(text="🟢 Открыть BestChange", url=final_link)])
    
    # Если это онлайн - даем P2P, если город - карту
    is_online = city.lower() in ['онлайн', 'online', 'интернет']
    if is_online:
        rows.append([InlineKeyboardButton(text="🟡 Bybit P2P", url="https://www.bybit.com/fiat/trade/otc")])
    else:
        maps_url = f"https://www.google.com/maps/search/crypto+exchange+{city}"
        rows.append([InlineKeyboardButton(text=f"📍 Карта обменников ({city})", url=maps_url)])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    # Красивое описание
    dict_names = {'cash': 'Нал', 'card': 'Карта', 'crypto': 'Крипта'}
    
    await message.answer(
        f"🔎 **Заявка:** `{give_raw.upper()}` ({dict_names.get(m_give)}) -> `{get_raw.upper()}` ({dict_names.get(m_get)})\n"
        f"📍 **Локация:** `{city}`\n\n"
        "👇 Результат поиска:", 
        reply_markup=keyboard
    )

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
# ЛОГИКА ОБМЕННИКА (ШАГИ)
# =================================================

@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer("🔄 **Новая заявка**\n\nНапиши пару (например: `UAH USDT`).", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.exchange_pair)

@dp.message(BotStates.exchange_pair)
async def exchange_get_pair(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    
    words = re.findall(r'\w+', message.text)
    if len(words) < 2:
        await message.answer("⚠️ Напиши две валюты через пробел.")
        return

    await state.update_data(give_raw=words[0], get_raw=words[1])
    await message.answer(f"➡️ Как отдаете **{words[0].upper()}**?", reply_markup=get_method_keyboard("give"))
    await state.set_state(BotStates.exchange_method_give)

@dp.callback_query(F.data.startswith("give_"), BotStates.exchange_method_give)
async def exchange_save_give(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1]
    await state.update_data(method_give=method)
    data = await state.get_data()
    await callback.message.answer(f"⬅️ Куда принимаете **{data['get_raw'].upper()}**?", reply_markup=get_method_keyboard("get"))
    await state.set_state(BotStates.exchange_method_get)
    await callback.answer()

# === ЗДЕСЬ ИЗМЕНЕНИЯ (УМНЫЙ ПРОПУСК ГОРОДА) ===
@dp.callback_query(F.data.startswith("get_"), BotStates.exchange_method_get)
async def exchange_save_get(callback: types.CallbackQuery, state: FSMContext):
    method_get = callback.data.split("_")[1]
    await state.update_data(method_get=method_get)
    
    # Получаем то, что выбрали на прошлом шаге
    data = await state.get_data()
    method_give = data['method_give']
    
    # ЛОГИКА: Если нигде нет "cash" (нала) - значит это Онлайн!
    if method_give != 'cash' and method_get != 'cash':
        # Сразу показываем результат, город "Онлайн"
        await show_result(callback.message, data['give_raw'], data['get_raw'], method_give, method_get, "Онлайн")
        await callback.message.answer("Главное меню:", reply_markup=main_keyboard)
        await state.clear()
    else:
        # Если есть Нал - спрашиваем город
        await callback.message.answer("🏙 **В каком городе вы находитесь?**\n(Например: `Москва`)", reply_markup=cancel_keyboard)
        await state.set_state(BotStates.exchange_city)
    
    await callback.answer()

@dp.message(BotStates.exchange_city)
async def exchange_finish_city(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return

    data = await state.get_data()
    await show_result(message, data['give_raw'], data['get_raw'], data['method_give'], data['method_get'], message.text.strip())
    await message.answer("Главное меню:", reply_markup=main_keyboard)
    await state.clear()

# =================================================
# ОСТАЛЬНОЕ
# =================================================

@dp.message(F.text == "🪙 Курс криптовалют")
async def crypto_rates_start(message: types.Message, state: FSMContext):
    await message.answer("🪙 Введи тикер (BTC, ETH, TON):", reply_markup=cancel_keyboard)
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
        await message.answer("⚠️ Не нашел.", reply_markup=main_keyboard)
    await state.clear()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"Привет! Я CryptoMate 🤖.", reply_markup=main_keyboard)

@dp.message(F.text == "🏆 Топ бирж")
async def top_exchanges(message: types.Message):
    await message.answer("🔥 Bybit, BingX, OKX")

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
