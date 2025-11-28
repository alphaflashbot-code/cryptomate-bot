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

# --- СЛОВАРЬ ВАЛЮТ (БАЗОВЫЙ) ---
# Здесь мы просто сопоставляем слово пользователя с типом валюты
CURRENCY_MAP = {
    # Рубли
    'RUB': 'rub', 'РУБ': 'rub', 'РУБЛЬ': 'rub', 'RUR': 'rub', 'СБЕР': 'rub', 'ТИНЬКОФФ': 'rub',
    # Гривны
    'UAH': 'uah', 'ГРН': 'uah', 'ГРИВНА': 'uah', 'МОНО': 'uah', 'ПРИВАТ': 'uah',
    # Доллары (Фиат)
    'USD': 'usd', 'ДОЛЛАР': 'usd', 'БАКИ': 'usd',
    # Евро
    'EUR': 'eur', 'ЕВРО': 'eur',
    # Тенге
    'KZT': 'kzt', 'ТЕНГЕ': 'kzt', 'КАСПИ': 'kzt',
    # Крипта (ей все равно на нал/безнал, код всегда один)
    'USDT': 'tether-trc20', 'TRC20': 'tether-trc20', 'ТЕЗЕР': 'tether-trc20',
    'BTC': 'bitcoin', 'БИТОК': 'bitcoin',
    'ETH': 'ethereum', 'ЭФИР': 'ethereum',
    'TON': 'toncoin', 'LTC': 'litecoin'
}

# --- МАШИНА СОСТОЯНИЙ ---
class BotStates(StatesGroup):
    exchange_pair = State()   # Ждем текст пары
    exchange_method = State() # Ждем нажатие кнопки (Нал/Карта)
    exchange_city = State()   # Ждем город
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

# Клавиатура выбора метода
method_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💳 Карта / Банк / Онлайн", callback_data="method_card")],
    [InlineKeyboardButton(text="💵 Наличные (Cash)", callback_data="method_cash")],
    [InlineKeyboardButton(text="🪙 Это Криптовалюта", callback_data="method_crypto")]
])

# --- ЛОГИКА КОДОВ BESTCHANGE ---
def resolve_code(currency_raw, method):
    # 1. Нормализуем название валюты через словарь
    cur = currency_raw.upper()
    code_base = CURRENCY_MAP.get(cur, cur.lower()) # Если нет в словаре, берем как есть
    
    # 2. Если это КРИПТА (уже имеет сложный код типа tether-trc20), метод не важен
    if '-' in code_base or code_base in ['bitcoin', 'ethereum', 'toncoin', 'litecoin', 'monero']:
        return code_base

    # 3. Применяем метод (Нал или Карта)
    if method == 'cash':
        # Для нала добавляем cash-
        return f"cash-{code_base}"
    
    elif method == 'card':
        # Для карт выбираем самые популярные банки по умолчанию
        if code_base == 'rub': return 'sberbank' # Дефолт для РФ
        if code_base == 'uah': return 'visa-mastercard-uah' # Дефолт для Украины
        if code_base == 'kzt': return 'visa-mastercard-kzt'
        if code_base == 'usd': return 'visa-mastercard-usd'
        return code_base # Если не знаем, оставляем как есть
        
    return code_base

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

# 1. СТАРТ: Просим пару
@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer(
        "🔄 **Новая заявка**\n\n"
        "Напиши пару (просто названия валют).\n"
        "Примеры: `Гривна USDT` или `Рубль Биткоин`", 
        reply_markup=cancel_keyboard
    )
    await state.set_state(BotStates.exchange_pair)

# 2. ПОЛУЧАЕМ ПАРУ -> ПРОСИМ МЕТОД
@dp.message(BotStates.exchange_pair)
async def exchange_get_pair(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    
    # Пытаемся разбить текст на 2 слова
    words = re.findall(r'\w+', message.text)
    if len(words) < 2:
        await message.answer("⚠️ Нужно написать две валюты через пробел. Попробуй еще раз (например: UAH USDT).")
        return

    # Сохраняем "сырые" слова
    await state.update_data(give_raw=words[0], get_raw=words[1])
    
    # Спрашиваем метод для ПЕРВОЙ валюты
    await message.answer(
        f"💳 Как вы отдаете **{words[0].upper()}**?", 
        reply_markup=method_keyboard
    )
    await state.set_state(BotStates.exchange_method)

# 3. ПОЛУЧАЕМ МЕТОД (Кнопка) -> ПРОСИМ ГОРОД
@dp.callback_query(F.data.startswith("method_"), BotStates.exchange_method)
async def exchange_save_method(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1] # cash, card или crypto
    await state.update_data(method=method)
    
    await callback.message.answer("🏙 **В каком городе вы находитесь?**\n(Напиши `Москва`, `Варшава` или `Онлайн`)", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.exchange_city)
    await callback.answer()

# 4. ФИНАЛ: ГЕНЕРИРУЕМ ССЫЛКУ
@dp.message(BotStates.exchange_city)
async def exchange_finish(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return

    data = await state.get_data()
    city = message.text.strip()
    
    # Достаем данные
    give_raw = data['give_raw']
    get_raw = data['get_raw']
    method = data['method'] # cash, card, crypto
    
    # Генерируем коды BestChange
    code_give = resolve_code(give_raw, method)
    
    # Для второй валюты метод обычно такой же или "карта", если это онлайн.
    # Но для простоты вторую валюту берем как Крипту или Карту по умолчанию,
    # если пользователь не написал "Нал" явно во втором слове.
    # (Упрощенная логика для стабильности ссылки)
    code_get = resolve_code(get_raw, 'crypto' if method == 'crypto' else 'card')
    
    # Если пользователь выбрал "Нал" для первой, а вторая - USD, то вторая скорее всего тоже Нал
    if method == 'cash' and 'cash' not in code_get and code_get in ['usd', 'eur', 'rub']:
         code_get = f"cash-{code_get}"

    # Ссылка
    if code_give == code_get:
        final_link = "https://www.bestchange.ru/"
    else:
        final_link = f"https://www.bestchange.ru/{code_give}-to-{code_get}.html"
        
    # Кнопки
    is_online = city.lower() in ['онлайн', 'online', 'интернет']
    rows = []
    
    rows.append([InlineKeyboardButton(text="🟢 Открыть обменники (BestChange)", url=final_link)])
    
    if is_online:
        rows.append([InlineKeyboardButton(text="🟡 Bybit P2P", url="https://www.bybit.com/fiat/trade/otc")])
    else:
        maps_url = f"https://www.google.com/maps/search/crypto+exchange+{city}"
        rows.append([InlineKeyboardButton(text=f"📍 Карта обменников ({city})", url=maps_url)])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    pair_display = f"{give_raw.upper()} -> {get_raw.upper()}"
    method_display = "Наличные" if method == 'cash' else "Карта/Банк"
    
    await message.answer(
        f"🔎 **Пара:** `{pair_display}`\n"
        f"💳 **Метод:** {method_display}\n"
        f"📍 **Локация:** `{city}`\n\n"
        "👇 Результат поиска:", 
        reply_markup=keyboard
    )
    
    await message.answer("Меню:", reply_markup=main_keyboard)
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
