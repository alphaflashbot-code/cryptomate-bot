import os
import asyncio
import logging
import sys
import re # Для обработки текста
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

# --- СЛОВАРЬ BESTCHANGE (ПЕРЕВОДЧИК) ---
# Бот ищет эти слова в тексте пользователя и превращает их в коды ссылки
BESTCHANGE_CODES = {
    # Крипта
    'BTC': 'bitcoin', 'БИТКОИН': 'bitcoin', 'BITCOIN': 'bitcoin',
    'ETH': 'ethereum', 'ЭФИР': 'ethereum', 'ETHER': 'ethereum',
    'USDT': 'tether-trc20', 'TEZER': 'tether-trc20', 'ТЕЗЕР': 'tether-trc20', # По умолчанию TRC20 (самый частый)
    'ERC20': 'tether-erc20',
    'TON': 'toncoin', 'ТОН': 'toncoin',
    'LTC': 'litecoin', 'ЛАЙТ': 'litecoin',
    'XMR': 'monero', 'МОНЕРО': 'monero',
    'DOGE': 'dogecoin',
    'TRX': 'tron', 'ТРОН': 'tron',
    
    # Банки РФ
    'SBER': 'sberbank', 'СБЕР': 'sberbank',
    'TINKOFF': 'tinkoff', 'ТИНЬКОФФ': 'tinkoff', 'ТИНЬКА': 'tinkoff',
    'ALFA': 'alfabank', 'АЛЬФА': 'alfabank',
    'VTB': 'vtb', 'ВТБ': 'vtb',
    'RUB': 'sberbank', 'РУБЛЬ': 'sberbank', 'РУБ': 'sberbank', # Если пишут просто РУБ, предлагаем Сбер как самый частый
    'CARD': 'visa-mastercard-rub', 'КАРТА': 'visa-mastercard-rub',
    'SBP': 'sbp', 'СБП': 'sbp',
    
    # Банки Украины
    'MONO': 'monobank', 'МОНО': 'monobank',
    'PRIVAT': 'privat24-uah', 'ПРИВАТ': 'privat24-uah',
    'UAH': 'monobank', 'ГРИВНА': 'monobank', # По дефолту Моно
    
    # Наличные (Города)
    'CASH': 'cash-usd', 'НАЛ': 'cash-usd', 'НАЛИЧНЫЕ': 'cash-usd',
    'USD': 'cash-usd', 'ДОЛЛАР': 'cash-usd'
}

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

# --- ФУНКЦИЯ ГЕНЕРАЦИИ ССЫЛКИ ---
def get_smart_link(user_text):
    # Разбиваем текст на слова, убираем лишнее, переводим в верхний регистр
    # Пример: "BTC на Сбер" -> ['BTC', 'СБЕР']
    words = re.findall(r'\w+', user_text.upper())
    
    found_codes = []
    
    for word in words:
        if word in BESTCHANGE_CODES:
            found_codes.append(BESTCHANGE_CODES[word])
            
    # Если нашли ровно 2 кода (Откуда -> Куда), делаем прямую ссылку
    if len(found_codes) >= 2:
        # Берем первый и последний код (на случай если слов больше)
        give = found_codes[0]
        get = found_codes[-1]
        
        # Если коды одинаковые (Сбер -> Сбер), то ссылка не нужна
        if give == get: return "https://www.bestchange.ru/"
        
        return f"https://www.bestchange.ru/{give}-to-{get}.html"
    
    # Если не поняли пару, возвращаем главную
    return "https://www.bestchange.ru/"

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
# ЛОГИКА ОБМЕННИКА
# =================================================

@dp.message(F.text == "💱 Обменник")
async def exchange_start(message: types.Message, state: FSMContext):
    await message.answer(
        "🔄 **Подбор пары**\n\n"
        "Напиши пару ключевыми словами (через пробел).\n"
        "Примеры:\n"
        "🔸 `BTC Сбер`\n"
        "🔸 `USDT Тинькофф`\n"
        "🔸 `ETH Наличные`\n"
        "🔸 `Моно Тон`", 
        reply_markup=cancel_keyboard
    )
    await state.set_state(BotStates.exchange_pair)

@dp.message(BotStates.exchange_pair)
async def exchange_get_pair(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    
    await state.update_data(pair=message.text)
    await message.answer("🏙 **Город?**\n(Напиши `Москва`, `Варшава` или `Онлайн`)", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.exchange_city)

@dp.message(BotStates.exchange_city)
async def exchange_finish(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return

    data = await state.get_data()
    pair_text = data['pair']
    city = message.text.strip()
    
    # Генерируем УМНУЮ ссылку
    smart_link = get_smart_link(pair_text)
    
    is_online = city.lower() in ['онлайн', 'online', 'интернет']
    rows = []
    
    # Кнопка BestChange (теперь умная)
    if smart_link == "https://www.bestchange.ru/":
        btn_text = "🟢 Выбрать вручную на BestChange"
    else:
        btn_text = f"🟢 Курсы {pair_text.upper()} (BestChange)"
    
    rows.append([InlineKeyboardButton(text=btn_text, url=smart_link)])
    
    if is_online:
        rows.append([InlineKeyboardButton(text="🟡 Bybit P2P", url="https://www.bybit.com/fiat/trade/otc")])
    else:
        # Для наличных добавляем карту
        maps_url = f"https://www.google.com/maps/search/crypto+exchange+{city}"
        rows.append([InlineKeyboardButton(text=f"📍 Карта обменников ({city})", url=maps_url)])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    await message.answer(
        f"🔎 **Результат для:** `{pair_text}`\n"
        f"📍 Локация: `{city}`\n\n"
        "Я сформировал прямую ссылку на лучшие курсы:", 
        reply_markup=keyboard
    )
    
    # Возвращаем меню
    await message.answer("Главное меню:", reply_markup=main_keyboard)
    await state.clear()

# =================================================
# ОСТАЛЬНОЕ
# =================================================

@dp.message(F.text == "🪙 Кур
