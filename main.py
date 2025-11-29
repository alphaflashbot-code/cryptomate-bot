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

# --- СЛОВАРЬ ВАЛЮТ ---
CURRENCY_MAP = {
    # КРИПТА
    'USDT': 'tether-trc20', 'TRC20': 'tether-trc20', 'ТЕЗЕР': 'tether-trc20',
    'ERC20': 'tether-erc20',
    'BTC': 'bitcoin', 'BITCOIN': 'bitcoin', 'БИТОК': 'bitcoin',
    'ETH': 'ethereum', 'ЭФИР': 'ethereum',
    'LTC': 'litecoin', 'TON': 'toncoin', 'XMR': 'monero',
    'DOGE': 'dogecoin', 'SOL': 'solana', 'TRX': 'tron',

    # ФИАТ (ДЛЯ ОБМЕННИКА И КУРСОВ)
    'USD': 'USD', 'ДОЛЛАР': 'USD', 'DOL': 'USD', 'BUCKS': 'USD',
    'EUR': 'EUR', 'ЕВРО': 'EUR',
    'RUB': 'RUB', 'РУБ': 'RUB', 'РУБЛЬ': 'RUB', 'RUR': 'RUB',
    'UAH': 'UAH', 'ГРН': 'UAH', 'ГРИВНА': 'UAH',
    'KZT': 'KZT', 'ТЕНГЕ': 'KZT',
    'AED': 'AED', 'ДИРХАМ': 'AED',
    'TRY': 'TRY', 'LIRA': 'TRY', 'ЛИРА': 'TRY',
    'PLN': 'PLN', 'ZLOTY': 'PLN', 'ЗЛОТЫЙ': 'PLN',
    'GBP': 'GBP', 'POUND': 'GBP', 'ФУНТ': 'GBP',
    'GEL': 'GEL', 'ЛАРИ': 'GEL',
    'CNY': 'CNY', 'YUAN': 'CNY', 'ЮАНЬ': 'CNY',
    'BYN': 'BYN', 'БЕЛРУБ': 'BYN',
    'JPY': 'JPY', 'ЙЕНА': 'JPY',

    # БАНКИ (ДЛЯ ОБМЕННИКА)
    'SBER': 'sberbank', 'СБЕР': 'sberbank',
    'TINKOFF': 'tinkoff', 'ТИНЬКОФФ': 'tinkoff',
    'MONO': 'monobank', 'МОНО': 'monobank',
    'PRIVAT': 'privat24-uah', 'ПРИВАТ': 'privat24-uah',
    'KASPI': 'kaspi-bank', 'КАСПИ': 'kaspi-bank',
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

# --- РЕЗОЛВЕР BESTCHANGE ---
def resolve_bestchange_code(user_word, method):
    word = user_word.upper()
    # Сначала пытаемся найти в словаре
    code = CURRENCY_MAP.get(word, word.lower()) # Если нет, берем как есть
    
    # Это фиат из словаря?
    is_fiat = code in ['USD', 'EUR', 'RUB', 'UAH', 'KZT', 'AED', 'TRY', 'PLN', 'GBP', 'GEL', 'CNY']

    # Если это код банка (sberbank) или крипты (bitcoin) - возвращаем сразу
    if len(code) > 4 and code not in ['GENERIC_USD']: 
        return code

    # === ЛОГИКА ДЛЯ ФИАТА ===
    if is_fiat:
        if method == 'cash':
            if code == 'USD': return 'dollar-cash'
            if code == 'EUR': return 'euro-cash'
            if code == 'RUB': return 'ruble-cash'
            if code == 'UAH': return 'hryvna-cash'
            if code == 'AED': return 'dirham'
            if code == 'TRY': return 'lira'
            if code == 'PLN': return 'zloty'
            if code == 'GBP': return 'pound'
            if code == 'KZT': return 'tenge-cash'
            if code == 'GEL': return 'gel'
            if code == 'CNY': return 'yuan'
            return 'dollar-cash'

        if method == 'card':
            if code == 'USD': return 'visa-mastercard-usd'
            if code == 'EUR': return 'visa-mastercard-eur'
            if code == 'RUB': return 'sberbank'
            if code == 'UAH': return 'visa-mastercard-uah'
            if code == 'KZT': return 'visa-mastercard-kzt'
            if code == 'TRY': return 'visa-mastercard-try'
            if code == 'CNY': return 'alipay'
            return 'visa-mastercard-usd'

    return 'tether-trc20'

# --- API FOREX (ОБЫЧНЫЕ ДЕНЬГИ) ---
async def get_forex_rate(base, quote):
    # API Европейского Центробанка (бесплатно, без ключей)
    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        async with ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    rates = data.get('rates', {})
                    if quote in rates:
                        return float(rates[quote])
                return None
    except: return None

# --- API BINANCE (КРИПТА) ---
async def get_raw_binance_price(symbol):
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
# ЛОГИКА 1: ОБМЕННИК
# =================================================

@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer("🔄 **Новая заявка**\n\nНапиши пару (например: `AED USD` или `UAH USDT`).", reply_markup=cancel_keyboard)
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
# ЛОГИКА 2: КУРС КРИПТОВАЛЮТ (Coin -> USDT)
# =================================================

@dp.message(F.text == "🪙 Курс криптовалют")
async def crypto_rates_start(message: types.Message, state: FSMContext):
    await message.answer("🪙 Введи тикер (BTC, ETH, TON):", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.crypto_price_wait)

@dp.message(BotStates.crypto_price_wait)
async def crypto_rates_result(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    
    coin = message.text.upper().replace(" ", "")
    if not coin.endswith("USDT"): pair = coin + "USDT"
    else: pair = coin
        
    price = await get_raw_binance_price(pair)
    
    if price:
        await message.answer(f"📊 **{coin}/USDT:** `{price:,.2f} $`", reply_markup=main_keyboard)
    else:
        await message.answer("⚠️ Не нашел. Попробуй тикер (например BTC).", reply_markup=main_keyboard)
    await state.clear()

# =================================================
# ЛОГИКА 3: КУРС ФИАТНЫХ ВАЛЮТ (FOREX) - ИСПРАВЛЕНО
# =================================================

@dp.message(F.text == "💵 Курс валют")
async def fiat_rates_start(message: types.Message, state: FSMContext):
    await message.answer(
        "💵 **Мировой конвертер валют**\n\n"
        "Напиши пару через пробел (любые валюты).\n"
        "Пример: `EUR USD` или `RUB KZT`",
        reply_markup=cancel_keyboard
    )
    await state.set_state(BotStates.fiat_price_wait)

@dp.message(BotStates.fiat_price_wait)
async def fiat_rates_result(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    
    words = re.findall(r'\w+', message.text.upper())
    if len(words) < 2:
        await message.answer("⚠️ Напиши ДВЕ валюты. Например: `USD RUB`", reply_markup=main_keyboard)
        return

    # Берем коды из словаря или используем то, что написал юзер (если 3 буквы)
    base_raw = words[0]
    quote_raw = words[1]
    
    base = CURRENCY_MAP.get(base_raw, base_raw) # Например РУБ -> RUB
    quote = CURRENCY_MAP.get(quote_raw, quote_raw)
    
    # Запрос к API Центробанков (Forex)
    rate = await get_forex_rate(base, quote)
    
    if rate:
        await message.answer(
            f"💱 **Курс ЦБ / Forex:**\n\n"
            f"1 {base} = **{rate:,.2f}** {quote}",
            reply_markup=main_keyboard
        )
    else:
        await message.answer(
            f"⚠️ Не удалось найти курс `{base}` -> `{quote}`.\n"
            f"Попробуй международные коды: USD, EUR, RUB, KZT, CNY.", 
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
