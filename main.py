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

# --- СЛОВАРЬ (РАСШИРЕННЫЙ) ---
BESTCHANGE_CODES = {
    # Крипта
    'BTC': 'bitcoin', 'БИТКОИН': 'bitcoin', 'БИТОК': 'bitcoin',
    'ETH': 'ethereum', 'ЭФИР': 'ethereum',
    'USDT': 'tether-trc20', 'TRC20': 'tether-trc20', 'ТЕЗЕР': 'tether-trc20', 'USD': 'tether-trc20',
    'TON': 'toncoin', 'ТОН': 'toncoin',
    'LTC': 'litecoin',
    'XMR': 'monero',
    
    # Банки РФ
    'SBER': 'sberbank', 'СБЕР': 'sberbank', 'RUB': 'sberbank', 'РУБЛЬ': 'sberbank', 'РУБ': 'sberbank',
    'TINKOFF': 'tinkoff', 'ТИНЬКОФФ': 'tinkoff', 'ТИНЬКА': 'tinkoff',
    'SBP': 'sbp', 'СБП': 'sbp',
    
    # Банки Украина (UAH)
    'MONO': 'monobank', 'МОНО': 'monobank', 'UAH': 'monobank', 'ГРИВНА': 'monobank', 'ГРН': 'monobank',
    'PRIVAT': 'privat24-uah', 'ПРИВАТ': 'privat24-uah',
    'PUMB': 'pumb', 'ПУМБ': 'pumb',
    
    # Банки Казахстан (KZT)
    'KASPI': 'kaspi-bank', 'КАСПИ': 'kaspi-bank', 'KZT': 'kaspi-bank', 'ТЕНГЕ': 'kaspi-bank',
    
    # Наличные
    'CASH': 'cash-usd', 'НАЛ': 'cash-usd', 'НАЛИЧНЫЕ': 'cash-usd', 'ДОЛЛАР': 'cash-usd',
    'CASHRUB': 'cash-rub', 'НАЛРУБ': 'cash-rub',
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

# --- ГЕНЕРАЦИЯ ССЫЛКИ BESTCHANGE ---
def get_smart_link(user_text):
    # Ищем слова в тексте
    words = re.findall(r'\w+', user_text.upper())
    found_codes = []
    
    # Особая проверка для пар типа "Нал Рубли"
    if "НАЛ" in user_text.upper() and "РУБ" in user_text.upper():
        found_codes.append('cash-rub')
    
    for word in words:
        if word in BESTCHANGE_CODES:
            # Если уже нашли cash-rub, не добавляем просто rub (sberbank)
            if 'cash-rub' in found_codes and BESTCHANGE_CODES[word] == 'sberbank':
                continue
            found_codes.append(BESTCHANGE_CODES[word])
            
    # Если нашли 2 кода
    if len(found_codes) >= 2:
        give = found_codes[0] # Отдаю
        get = found_codes[-1] # Получаю
        if give == get: return "https://www.bestchange.ru/"
        return f"https://www.bestchange.ru/{give}-to-{get}.html"
    
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
        "Напиши пару через пробел (Валюты, Банки или Крипта).\n"
        "Примеры:\n"
        "🇺🇦 `Моно USDT` (или `Гривна Тезер`)\n"
        "🇷🇺 `Сбер BTC` (или `Руб Биткоин`)\n"
        "🇰🇿 `Каспи ETH`\n"
        "💵 `Наличные USDT`", 
        reply_markup=cancel_keyboard
    )
    await state.set_state(BotStates.exchange_pair)

@dp.message(BotStates.exchange_pair)
async def exchange_get_pair(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return
    
    await state.update_data(pair=message.text)
    await message.answer("🏙 **Город?**\n(Напиши `Москва`, `Киев`, `Варшава` или `Онлайн`)", reply_markup=cancel_keyboard)
    await state.set_state(BotStates.exchange_city)

@dp.message(BotStates.exchange_city)
async def exchange_finish(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear(); await message.answer("Отмена.", reply_markup=main_keyboard); return

    data = await state.get_data()
    pair_text = data['pair']
    city = message.text.strip()
    
    # 1. Генерируем ссылку BestChange
    smart_link = get_smart_link(pair_text)
    
    # 2. Определяем тип (Онлайн или Город)
    is_online = city.lower() in ['онлайн', 'online', 'интернет']
    
    rows = []
    
    # Кнопка BestChange
    if smart_link == "https://www.bestchange.ru/":
        # Если не поняли пару
        btn_text = "🟢 Выбрать вручную на BestChange"
    else:
        # Если ссылка прямая
        btn_text = f"🟢 Открыть пару {pair_text.upper()}"
    
    rows.append([InlineKeyboardButton(text=btn_text, url=smart_link)])
    
    if is_online:
        rows.append([InlineKeyboardButton(text="🟡 Bybit P2P", url="https://www.bybit.com/fiat/trade/otc")])
    else:
        # 3. ИСПРАВЛЕННАЯ ССЫЛКА НА GOOGLE MAPS
        # Используем универсальный поиск
        maps_url = f"https://www.google.com/maps/search/crypto+exchange+{city}"
        rows.append([InlineKeyboardButton(text=f"📍 Карта обменников ({city})", url=maps_url)])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    await message.answer(
        f"🔎 **Пара:** `{pair_text}`\n"
        f"📍 **Локация:** `{city}`\n\n"
        "Готово! Выбери вариант:", 
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
        await message.answer("⚠️ Не нашел. Попробуй тикер (например BTC).", reply_markup=main_keyboard)
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
