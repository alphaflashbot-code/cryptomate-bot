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

# --- РЕФЕРАЛКИ ---
REF_BESTCHANGE = "?p=1337426"
REF_BYBIT = "https://www.bybit.com/invite?ref=KAB7WYP"
REF_BINGX = "https://bingx.com/invite/DZ92UK/"
REF_OKX = "https://okx.com"

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

# --- СЛОВАРЬ (ДЛЯ ОБМЕННИКА) ---
CURRENCY_MAP = {
    'USDT': 'tether-trc20', 'TRC20': 'tether-trc20', 'ТЕЗЕР': 'tether-trc20',
    'ERC20': 'tether-erc20',
    'BTC': 'bitcoin', 'BITCOIN': 'bitcoin', 'БИТОК': 'bitcoin',
    'ETH': 'ethereum', 'ЭФИР': 'ethereum',
    'LTC': 'litecoin', 'TON': 'toncoin', 'XMR': 'monero',
    'DOGE': 'dogecoin', 'SOL': 'solana', 'TRX': 'tron',
    'USD': 'GENERIC_USD', 'ДОЛЛАР': 'GENERIC_USD', 'DOL': 'GENERIC_USD',
    'EUR': 'GENERIC_EUR', 'ЕВРО': 'GENERIC_EUR',
    'RUB': 'GENERIC_RUB', 'РУБ': 'GENERIC_RUB', 'РУБЛЬ': 'GENERIC_RUB',
    'UAH': 'GENERIC_UAH', 'ГРН': 'GENERIC_UAH', 'ГРИВНА': 'GENERIC_UAH',
    'KZT': 'GENERIC_KZT', 'ТЕНГЕ': 'GENERIC_KZT',
    'AED': 'GENERIC_AED', 'ДИРХАМ': 'GENERIC_AED',
    'TRY': 'GENERIC_TRY', 'LIRA': 'GENERIC_TRY', 'ЛИРА': 'GENERIC_TRY',
    'PLN': 'GENERIC_PLN', 'ZLOTY': 'GENERIC_PLN',
    'GBP': 'GENERIC_GBP', 'POUND': 'GENERIC_GBP',
    'GEL': 'GENERIC_GEL', 'ЛАРИ': 'GENERIC_GEL',
    'CNY': 'GENERIC_CNY', 'YUAN': 'GENERIC_CNY',
    'SBER': 'sberbank', 'СБЕР': 'sberbank',
    'TINKOFF': 'tinkoff', 'ТИНЬКОФФ': 'tinkoff',
    'MONO': 'monobank', 'МОНО': 'monobank',
    'PRIVAT': 'privat24-uah', 'ПРИВАТ': 'privat24-uah',
    'KASPI': 'kaspi-bank', 'КАСПИ': 'kaspi-bank',
}

# --- СЛОВАРЬ ТИКЕРОВ (ДЛЯ КУРСА КРИПТЫ) ---
# Помогает боту понять кириллицу перед поиском
CRYPTO_ALIASES = {
    'БИТОК': 'BTC', 'БИТКОИН': 'BTC', 'BITCOIN': 'BTC',
    'ЭФИР': 'ETH', 'ETHER': 'ETH', 'ETHEREUM': 'ETH',
    'ТОН': 'TON', 'TONCOIN': 'TON',
    'СОЛ': 'SOL', 'СОЛАНА': 'SOL',
    'ДОГИ': 'DOGE', 'DOGECOIN': 'DOGE',
    'РИПЛ': 'XRP', 'RIPPLE': 'XRP',
    'НОТ': 'NOT', 'NOTCOIN': 'NOT',
    'ПЕПЕ': 'PEPE',
    'ТЕЗЕР': 'USDT'
}

class BotStates(StatesGroup):
    exchange_pair = State()
    exchange_method_give = State()
    exchange_method_get = State()
    exchange_city = State()
    crypto_price_wait = State()
    fiat_price_wait = State()

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

def resolve_bestchange_code(user_word, method):
    word = user_word.upper()
    code = CURRENCY_MAP.get(word)
    if not code:
        if word in ['USDC']: return 'usd-coin'
        return None
    if not code.startswith('GENERIC_'): return code

    if method == 'cash':
        if code == 'GENERIC_USD': return 'dollar-cash'
        if code == 'GENERIC_EUR': return 'euro-cash'
        if code == 'GENERIC_RUB': return 'ruble-cash'
        if code == 'GENERIC_UAH': return 'hryvna-cash'
        if code == 'GENERIC_AED': return 'dirham'
        if code == 'GENERIC_TRY': return 'lira'
        if code == 'GENERIC_PLN': return 'zloty'
        if code == 'GENERIC_GBP': return 'pound'
        if code == 'GENERIC_KZT': return 'tenge-cash'
        if code == 'GENERIC_GEL': return 'gel'
        if code == 'GENERIC_CNY': return 'yuan'
        return 'dollar-cash'

    if method == 'card':
        if code == 'GENERIC_USD': return 'visa-mastercard-usd'
        if code == 'GENERIC_EUR': return 'visa-mastercard-eur'
        if code == 'GENERIC_RUB': return 'sberbank'
        if code == 'GENERIC_UAH': return 'visa-mastercard-uah'
        if code == 'GENERIC_KZT': return 'visa-mastercard-kzt'
        if code == 'GENERIC_TRY': return 'visa-mastercard-try'
        if code == 'GENERIC_AED': return 'visa-mastercard-aed'
        return 'visa-mastercard-usd'
    return 'tether-trc20'

# --- 1. BINANCE API (БЫСТРО) ---
async def get_binance_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data['price'])
    except: return None

# --- 2. COINGECKO API (РЕЗЕРВ ДЛЯ ЛЮБОЙ КРИПТЫ) ---
async def get_coingecko_price(query):
    try:
        async with ClientSession() as session:
            # Сначала ищем ID монеты
            search_url = f"https://api.coingecko.com/api/v3/search?query={query}"
            async with session.get(search_url) as resp:
                if resp.status != 200: return None, None
                data = await resp.json()
                if not data.get('coins'): return None, None
                
                # Берем первый результат (самый релевантный)
                best_match = data['coins'][0]
                coin_id = best_match['id']
                coin_symbol = best_match['symbol'].upper()
                
                # Теперь узнаем цену
                price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
                async with session.get(price_url) as price_resp:
                    price_data = await price_resp.json()
                    if coin_id in price_data:
                        return price_data[coin_id]['usd'], coin_symbol
    except: return None, None
    return None, None

# --- 3. FOREX API (ФИАТ) ---
async def get_forex_rate(base, quote):
    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    rates = data.get('rates', {})
                    if quote in rates: return float(rates[quote])
    except: return None

# =================================================
# ЛОГИКА
# =================================================

@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer("🔄 **Новая заявка**\n\nНапиши пару (например: `AED USD`).", reply_markup=cancel_keyboard)
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

@dp.callback_query(F.data.startswith("get_"), BotStates.exchange_method_get)
async def exchange_save_get(callback: types.CallbackQuery, state: FSMContext):
    method_get = callback.data.split("_")[1]
    await state.update_data(method_get=method_get)
    data = await state.get_data()
    m_give = data['method_give']
    if m_give != 'cash' and method_get != 'cash':
        await show_final_result(callback.message, data, "Онлайн")
        await state.clear()
    else:
        await callback.message.answer("🏙 **Город?**\n(Например: `Дубай`, `Москва`)", reply_markup=cancel_keyboard)
        await state.set_state(BotStates.exchange_city)
    await callback.answer()

@dp.message(BotStates.exchange_city)
async def exchange_finish_city(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    data = await state.get_data()
    await show_final_result(message, data, message.text.strip())
    await state.clear()

async def show_final_result(message, data, city):
    give_raw = data['give_raw']
    get_raw = data['get_raw']
    m_give = data['method_give']
    m_get = data['method_get']
    
    code_give = resolve_bestchange_code(give_raw, m_give)
    code_get = resolve_bestchange_code(get_raw, m_get)
    
    if not code_give or not code_get:
        await message.answer(f"⚠️ Ошибка: Я не понял валюту.", reply_markup=main_keyboard)
        return

    if code_give == code_get:
        link = f"https://www.bestchange.ru/{REF_BESTCHANGE}"
    else:
        link = f"https://www.bestchange.ru/{code_give}-to-{code_get}.html{REF_BESTCHANGE}"
        
    rows = []
    rows.append([InlineKeyboardButton(text="🟢 Открыть BestChange", url=link)])
    rows.append([InlineKeyboardButton(text="📋 Список вручную", url=f"https://www.bestchange.ru/list.html{REF_BESTCHANGE}")])
    
    if city.lower() in ['онлайн', 'online', 'интернет']:
        rows.append([InlineKeyboardButton(text="🟡 Bybit P2P", url="https://www.bybit.com/fiat/trade/otc")])
    else:
        maps_url = f"https://www.google.com/maps/search/crypto+exchange+{city}"
        rows.append([InlineKeyboardButton(text=f"📍 Карта обменников ({city})", url=maps_url)])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    await message.answer(
        f"🔎 **Пара:** `{give_raw.upper()}` -> `{get_raw.upper()}`\n"
        f"📍 **Локация:** `{city}`\n\n"
        "👇 Результат поиска:", 
        reply_markup=keyboard
    )
    await message.answer("Меню:", reply_markup=main_keyboard)

# =================================================
# ЛОГИКА 2: КУРС КРИПТОВАЛЮТ (УМНЫЙ)
# =================================================

@dp.message(F.text == "🪙 Курс криптовалют")
async def crypto_rates_start(message: types.Message, state: FSMContext):
    await message.answer("🪙 Введи название (любое).\nПример: `TON`, `Notcoin`, `Pepe`, `Биткоин`", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.crypto_price_wait)

@dp.message(BotStates.crypto_price_wait)
async def crypto_rates_result(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    
    user_input = message.text.upper()
    await message.answer(f"🔎 Ищу цену для **{user_input}**...")

    # 1. Сначала проверяем наш словарь синонимов (ТОН -> TON)
    ticker = CRYPTO_ALIASES.get(user_input, user_input)

    # 2. Пробуем Binance (быстро и точно для популярных)
    # Пытаемся сформировать пару (например TONUSDT)
    binance_pair = ticker + "USDT"
    price_binance = await get_binance_price(binance_pair)

    if price_binance:
        # Успех на Binance
        await message.answer(f"📊 **{ticker}/USDT** (Binance):\n💰 `{price_binance:,.4f} $`", reply_markup=main_keyboard)
    
    else:
        # 3. Если Binance не нашел - ищем ВЕЗДЕ через CoinGecko
        price_cg, symbol_cg = await get_coingecko_price(user_input)
        
        if price_cg:
            await message.answer(
                f"🦎 **{symbol_cg}/USD** (CoinGecko):\n"
                f"💰 `{price_cg:,.6f} $`\n"
                f"_(Найден по запросу: {user_input})_", 
                reply_markup=main_keyboard
            )
        else:
            await message.answer("⚠️ Не нашел такую крипту ни на биржах, ни в агрегаторах.", reply_markup=main_keyboard)
            
    await state.clear()

# =================================================
# ЛОГИКА 3: КУРС ФИАТА
# =================================================

@dp.message(F.text == "💵 Курс валют")
async def fiat_rates_start(message: types.Message, state: FSMContext):
    await message.answer("💵 Введи пару (например `EUR USD`):", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.fiat_price_wait)

@dp.message(BotStates.fiat_price_wait)
async def fiat_rates_result(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    words = re.findall(r'\w+', message.text.upper())
    if len(words) < 2:
        await message.answer("⚠️ Нужно две валюты.", reply_markup=main_keyboard); return

    base_raw = words[0]; quote_raw = words[1]
    base = CURRENCY_MAP.get(base_raw, base_raw) # Попытка нормализации
    quote = CURRENCY_MAP.get(quote_raw, quote_raw)
    
    # Очистка от GENERIC_ префиксов для Forex API
    base = base.replace("GENERIC_", "")
    quote = quote.replace("GENERIC_", "")

    rate = await get_forex_rate(base, quote)
    
    if rate:
        await message.answer(f"💱 **Курс ЦБ / Forex:**\n1 {base} = **{rate:,.2f}** {quote}", reply_markup=main_keyboard)
    else:
        await message.answer(f"⚠️ Не нашел курс `{base}` -> `{quote}`.", reply_markup=main_keyboard)
    await state.clear()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(f"Привет! Я CryptoMate 🤖.", reply_markup=main_keyboard)

@dp.message(F.text == "🏆 Топ бирж")
async def top_exchanges(message: types.Message):
    text = (
        "🔥 **ТОП БИРЖ (Проверено)**\n\n"
        f"1. 🟡 **Bybit** — [Бонусы до $30,000]({REF_BYBIT})\n"
        f"2. 🔵 **BingX** — [Без KYC]({REF_BINGX})\n"
        f"3. ⚫️ **OKX** — [Надежность]({REF_OKX})"
    )
    await message.answer(text, disable_web_page_preview=True)

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
        try: async with ClientSession() as session: async with session.get(APP_URL) as response: pass
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
