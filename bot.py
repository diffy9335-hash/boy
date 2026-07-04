import asyncio
import functools
import logging
import random
import json
import os
import time
from collections import defaultdict
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
 
# --- НАСТРОЙКА ЛОГОВ И ТОКЕНА ---
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8979310355:AAHAwTEzkj6crT8nr5GrxPKeHAoilhrrdZc"
 
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
 
# --- СПИСОК АДМИНИСТРАТОРОВ ---
ADMINS = ["Diffysh1", "SilentRagex"]
 
# --- ФАЙЛЫ ДАННЫХ ---
PLAYERS_FILE = "players.json"
LEADERBOARD_FILE = "leaderboard.json"
TABLES_FILE = "tables.json"
SLOTS_FILE = "slots.json"

def _load_data_sync(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            backup_name = f"{filename}.corrupted_{int(time.time())}"
            os.replace(filename, backup_name)
            logging.error(f"Файл {filename} был поврежден ({e}) и переименован в {backup_name}. Создан новый.")
            return {}
    return {}
 
def _save_data_sync(filename, data):
    tmp_path = f"{filename}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_path, filename)
 
# --- СИСТЕМА КЭШИРОВАНИЯ И БЕЗОПАСНЫЕ БЛОКИРОВКИ ---
_cache_locks = {}

def get_cache_lock(filename):
    if filename not in _cache_locks:
        _cache_locks[filename] = asyncio.Lock()
    return _cache_locks[filename]

async def load_data(filename):
    return await asyncio.to_thread(_load_data_sync, filename)
 
async def save_data(filename, data):
    lock = get_cache_lock(filename)
    async with lock:
        await asyncio.to_thread(_save_data_sync, filename, data)

async def get_active_slot(user_id: str):
    slots = await load_data(SLOTS_FILE)
    return slots.get(str(user_id), "1")

async def set_active_slot(user_id: str, slot: str):
    slots = await load_data(SLOTS_FILE)
    slots[str(user_id)] = slot
    await save_data(SLOTS_FILE, slots)

async def get_uid(event):
    tg_id = str(event.from_user.id)
    slot = await get_active_slot(tg_id)
    return f"{tg_id}_{slot}"

_user_locks = {}
_table_lock = None
 
def get_user_lock(user_id: str) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

def get_table_lock() -> asyncio.Lock:
    global _table_lock
    if _table_lock is None:
        _table_lock = asyncio.Lock()
    return _table_lock
 
def with_user_lock(func):
    @functools.wraps(func)
    async def wrapper(event, *args, **kwargs):
        user_id = await get_uid(event)
        lock = get_user_lock(user_id)
        async with lock:
            return await func(event, *args, **kwargs)
    return wrapper
 
def retired_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Начать новую карьеру", callback_data="start_new_career")]])
 
async def deny_if_retired_cb(callback: CallbackQuery, p) -> bool:
    if not p:
        await callback.message.answer("⚠️ Профиль не найден. Нажми /start, чтобы начать.", parse_mode="Markdown")
        return True
    if p.get("retired"):
        try:
            await callback.message.edit_text(
                "🏁 **Твоя карьера уже завершена!**\nЭта кнопка осталась от старого меню — нажми ниже, чтобы начать новую карьеру.",
                parse_mode="Markdown", reply_markup=retired_keyboard()
            )
        except:
            await callback.message.answer("🏁 **Твоя карьера уже завершена!**", reply_markup=retired_keyboard())
        return True
    return False
 
async def deny_if_retired_msg(message: Message, p) -> bool:
    if not p:
        await message.answer("⚠️ Профиль не найден. Нажми /start, чтобы начать.", parse_mode="Markdown")
        return True
    if p.get("retired"):
        await message.answer(
            "🏁 **Твоя карьера уже завершена!**\nНажми ниже, чтобы начать новую карьеру.",
            parse_mode="Markdown", reply_markup=retired_keyboard()
        )
        return True
    return False
 
# --- СОСТОЯНИЯ FSM ---
class PlayerCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_nation = State()
    waiting_for_position = State()
    waiting_for_country_league = State()
    waiting_for_number = State()
    waiting_for_club = State()
 
class ContractNegotiation(StatesGroup):
    waiting_for_salary = State()
 
class Donation(StatesGroup):
    waiting_for_dest = State()
    waiting_for_amount = State()
 
class AdminPanel(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_money = State()
    waiting_for_rating = State()
 
# --- ДАННЫЕ И СПРАВОЧНИКИ ---
EURO_NATIONS = [
    "Россия", "Франция", "Италия", "Испания", "Германия", "Англия",
    "Португалия", "Нидерланды", "Бельгия", "Украина", "Хорватия",
    "Дания", "Швейцария", "Польша", "Швеция", "Норвегия", "Сербия", "Турция"
]

COPA_NATIONS = [
    "Аргентина", "Бразилия", "Мексика", "США", "Колумбия", "Уругвай"
]

OTHER_NATIONS = [
    "Марокко", "Сенегал", "Нигерия", "Камерун", "Япония", "Южная Корея", "Австралия", "Иран", "Египет"
]

NATIONS = EURO_NATIONS + COPA_NATIONS + OTHER_NATIONS

NATION_RATINGS = {
    "Аргентина": 89, "Франция": 89, "Бразилия": 88, "Англия": 88,
    "Испания": 87, "Португалия": 87, "Италия": 86, "Германия": 86,
    "Нидерланды": 84, "Бельгия": 83, "Хорватия": 82, "Уругвай": 81,
    "Колумбия": 80, "Дания": 79, "Швейцария": 79, "Марокко": 78,
    "Сенегал": 78, "Мексика": 77, "Сербия": 77, "Норвегия": 77,
    "США": 76, "Турция": 76, "Украина": 76, "Польша": 76,
    "Япония": 76, "Швеция": 75, "Россия": 74, "Южная Корея": 75,
    "Нигерия": 75, "Камерун": 74, "Иран": 74, "Египет": 74, "Австралия": 73
}
 
CLUBS = {
    "ФНЛ 2": ["Знамя Труда", "Сатурн Раменское", "Коломна", "Зенит-2", "Спартак-2", "Амкар Пермь", "Динамо Киров", "Рубин-2", "Торпедо Владимир", "Тверь", "Химик Дзержинск", "Иркутск"],
    "ФНЛ": ["Черноморец", "Шинник", "Урал", "Сочи", "Балтика", "Родина", "Торпедо М", "Арсенал Тула", "КАМАЗ", "Енисей", "Нефтехимик", "СКА-Хабаровск", "Уфа", "Тюмень", "Ротор", "Сокол", "Чайка", "Алания"],
    "РПЛ": ["Зенит", "Краснодар", "Динамо М", "Локомотив", "Спартак", "ЦСКА", "Ростов", "Рубин", "Крылья Советов", "Ахмат", "Факел", "Оренбург", "Пари НН", "Химки", "Акрон", "Динамо Мх"],
    
    "Насьональ": ["Ред Стар", "Ним", "Дижон", "Сошо", "Руан", "Ле Ман", "Версаль", "Нанси", "Шатору", "Кевийи", "Орлеан", "Булонь"],
    "Лига 2": ["Пари ФК", "Кан", "Генгам", "Амьен", "Бастия", "Бордо", "Труа", "Мец", "Аяччо", "Лорьян", "Клермон", "Анси", "Гренобль", "Дюнкерк", "По", "Родез", "Лаваль", "Ньор"],
    "Лига 1": ["ПСЖ", "Монако", "Брест", "Лилль", "Ницца", "Лион", "Ланс", "Марсель", "Ренн", "Реймс", "Тулуза", "Монпелье", "Страсбур", "Нант", "Гавр", "Осер", "Анже", "Сент-Этьен"],
    
    "Первая лига Англии": ["Рединг", "Уиган", "Болтон", "Чарльтон", "Барнсли", "Питерборо", "Блэкпул", "Портсмут", "Дерби Каунти", "Стивенедж", "Линкольн", "Шрусбери"],
    "Чемпионшип": ["Лестер", "Лидс", "Саутгемптон", "Ипсвич", "Вест Бромвич", "Норвич", "Халл Сити", "Ковентри", "Престон", "Мидлсбро", "Кардифф", "Бристоль Сити", "Сандерленд", "Суонси", "Уотфорд", "Миллуолл", "КПР", "Блэкберн"],
    "АПЛ": ["Манчестер Сити", "Арсенал", "Ливерпуль", "Астон Вилла", "Тоттенхэм", "Челси", "Ньюкасл", "Манчестер Юнайтед", "Вест Хэм", "Борнмут", "Кристал Пэлас", "Брайтон", "Фулхэм", "Вулверхэмптон", "Эвертон", "Брентфорд", "Ноттингем Форест", "Шеффилд Юнайтед"],

    "Сегунда": ["Эспаньол", "Сарагоса", "Леванте", "Эйбар", "Спортинг Хихон", "Вальядолид", "Тенерифе", "Овьедо", "Расинг", "Альбасете", "Картахена", "Бургос"],
    "Ла Лига": ["Реал Мадрид", "Барселона", "Атлетико", "Жирона", "Атлетик", "Реал Сосьедад", "Бетис", "Вильярреал", "Валенсия", "Алавес", "Осасуна", "Хетафе", "Сельта", "Севилья", "Мальорка", "Лас-Пальмас"],

    "Серия Б": ["Сампдория", "Парма", "Палермо", "Венеция", "Бари", "Кремонезе", "Комо", "Пиза", "Брешия", "Катандзаро", "Специя", "Тернана"],
    "Серия А": ["Интер", "Милан", "Ювентус", "Аталанта", "Болонья", "Рома", "Лацио", "Фиорентина", "Торино", "Наполи", "Дженоа", "Монца", "Лечче", "Удинезе", "Кальяри", "Эмполи"],

    "Вторая Бундеслига": ["Кёльн", "Дармштадт", "Гамбург", "Фортуна Д", "Ганновер", "Падерборн", "Герта", "Шальке", "Эльферсберг", "Нюрнберг", "Кайзерслаутерн", "Магдебург"],
    "Бундеслига": ["Бавария", "Боруссия Д", "Байер", "РБ Лейпциг", "Штутгарт", "Айнтрахт Ф", "Хоффенхайм", "Фрайбург", "Вердер", "Аугсбург", "Вольфсбург", "Боруссия М", "Унион Берлин", "Майнц", "Хайденхайм", "Санкт-Паули"]
}
 
CLUB_RATINGS = {
    "Знамя Труда": 40, "Сатурн Раменское": 45, "Коломна": 38, "Зенит-2": 52, "Спартак-2": 50, "Амкар Пермь": 48, "Динамо Киров": 42, "Рубин-2": 44, "Торпедо Владимир": 41, "Тверь": 39, "Химик Дзержинск": 43, "Иркутск": 40,
    "Черноморец": 60, "Шинник": 62, "Урал": 68, "Сочи": 69, "Балтика": 67, "Родина": 65, "Торпедо М": 66, "Арсенал Тула": 64, "КАМАЗ": 58, "Енисей": 63, "Нефтехимик": 61, "СКА-Хабаровск": 60, "Уфа": 59, "Тюмень": 57, "Ротор": 62, "Сокол": 56, "Чайка": 55, "Алания": 64,
    "Зенит": 85, "Краснодар": 83, "Динамо М": 81, "Локомотив": 80, "Спартак": 82, "ЦСКА": 81, "Ростов": 77, "Рубин": 75, "Крылья Советов": 76, "Ахмат": 74, "Факел": 72, "Оренбург": 73, "Пари НН": 71, "Химки": 70, "Акрон": 69, "Динамо Мх": 68,
    
    "Ред Стар": 45, "Ним": 44, "Дижон": 46, "Сошо": 47, "Руан": 42, "Ле Ман": 43, "Версаль": 41, "Нанси": 48, "Шатору": 40, "Кевийи": 45, "Орлеан": 42, "Булонь": 39,
    "Пари ФК": 65, "Кан": 64, "Генгам": 62, "Амьен": 61, "Бастия": 60, "Бордо": 66, "Труа": 63, "Мец": 68, "Аяччо": 59, "Лорьян": 67, "Клермон": 65, "Анси": 58, "Гренобль": 62, "Дюнкерк": 57, "По": 56, "Родез": 61, "Лаваль": 60, "Ньор": 55,
    "ПСЖ": 90, "Монако": 83, "Брест": 79, "Лилль": 82, "Ницца": 80, "Лион": 83, "Ланс": 81, "Марсель": 82, "Ренн": 80, "Реймс": 77, "Тулуза": 76, "Монпелье": 75, "Страсбур": 76, "Нант": 75, "Гавр": 73, "Осер": 72, "Анже": 71, "Сент-Этьен": 74,

    "Рединг": 50, "Уиган": 52, "Болтон": 51, "Чарльтон": 49, "Барнсли": 53, "Питерборо": 50, "Блэкпул": 48, "Портсмут": 54, "Дерби Каунти": 55, "Стивенедж": 46, "Линкольн": 47, "Шрусбери": 45,
    "Лестер": 75, "Лидс": 74, "Саутгемптон": 73, "Ипсвич": 70, "Вест Бромвич": 69, "Норвич": 68, "Халл Сити": 67, "Ковентри": 68, "Престон": 66, "Мидлсбро": 69, "Кардифф": 65, "Бристоль Сити": 64, "Сандерленд": 68, "Суонси": 66, "Уотфорд": 70, "Миллуолл": 65, "КПР": 64, "Блэкберн": 66,
    "Манчестер Сити": 92, "Арсенал": 89, "Ливерпуль": 89, "Астон Вилла": 84, "Тоттенхэм": 85, "Челси": 84, "Ньюкасл": 83, "Манчестер Юнайтед": 84, "Вест Хэм": 81, "Борнмут": 78, "Кристал Пэлас": 78, "Брайтон": 80, "Фулхэм": 79, "Вулверхэмптон": 78, "Эвертон": 77, "Брентфорд": 78, "Ноттингем Форест": 76, "Шеффилд Юнайтед": 75,

    "Эспаньол": 72, "Сарагоса": 70, "Леванте": 71, "Эйбар": 71, "Спортинг Хихон": 69, "Вальядолид": 72, "Тенерифе": 68, "Овьедо": 68, "Расинг": 67, "Альбасете": 66, "Картахена": 65, "Бургос": 64,
    "Реал Мадрид": 93, "Барселона": 90, "Атлетико": 87, "Жирона": 83, "Атлетик": 82, "Реал Сосьедад": 82, "Бетис": 81, "Вильярреал": 80, "Валенсия": 79, "Алавес": 77, "Осасуна": 78, "Хетафе": 77, "Сельта": 78, "Севилья": 80, "Мальорка": 76, "Лас-Пальмас": 75,

    "Сампдория": 70, "Парма": 72, "Палермо": 71, "Венеция": 71, "Бари": 69, "Кремонезе": 72, "Комо": 70, "Пиза": 68, "Брешия": 67, "Катандзаро": 66, "Специя": 69, "Тернана": 65,
    "Интер": 90, "Милан": 86, "Ювентус": 86, "Аталанта": 84, "Болонья": 82, "Рома": 83, "Лацио": 82, "Фиорентина": 81, "Торино": 79, "Наполи": 84, "Дженоа": 77, "Монца": 76, "Лечче": 75, "Удинезе": 76, "Кальяри": 75, "Эмполи": 74,

    "Кёльн": 72, "Дармштадт": 69, "Гамбург": 72, "Фортуна Д": 71, "Ганновер": 70, "Падерборн": 68, "Герта": 71, "Шальке": 70, "Эльферсберг": 66, "Нюрнберг": 67, "Кайзерслаутерн": 68, "Магдебург": 66,
    "Бавария": 91, "Боруссия Д": 86, "Байер": 88, "РБ Лейпциг": 86, "Штутгарт": 82, "Айнтрахт Ф": 81, "Хоффенхайм": 78, "Фрайбург": 79, "Вердер": 77, "Аугсбург": 76, "Вольфсбург": 78, "Боруссия М": 77, "Унион Берлин": 76, "Майнц": 75, "Хайденхайм": 76, "Санкт-Паули": 74
}

CUP_STAGES = ["1/16", "1/8", "1/4", "Полуфинал", "Финал"]
 
POSITIONS = {
    "⚽ Нападающий": "ST", 
    "🪄 Полузащитник": "CM", 
    "🛡️ Защитник": "CB",
    "🧤 Вратарь": "GK"
}
 
def get_division(club_name):
    for div, clubs in CLUBS.items():
        if club_name in clubs:
            return div
    return "ФНЛ 2"

# --- ЛЕСТНИЦЫ ДИВИЗИОНОВ (для повышения/понижения в классе по итогам сезона) ---
DIVISION_LADDERS = [
    ["ФНЛ 2", "ФНЛ", "РПЛ"],
    ["Насьональ", "Лига 2", "Лига 1"],
    ["Первая лига Англии", "Чемпионшип", "АПЛ"],
    ["Сегунда", "Ла Лига"],
    ["Серия Б", "Серия А"],
    ["Вторая Бундеслига", "Бундеслига"],
]

def get_ladder(division):
    for ladder in DIVISION_LADDERS:
        if division in ladder:
            return ladder
    return [division]
 
def get_status_by_trust(trust):
    if 0 <= trust <= 20: return "Глубокий резерв ❌"
    elif 21 <= trust <= 50: return "Скамейка запасных 🪑"
    elif 51 <= trust <= 75: return "Джокер (Выход на замену) ⏱️"
    return "Игрок старта 🔥"
 
def calculate_player_value(rating, division):
    mult = {
        "ФНЛ 2": 12500, "Насьональ": 12500, "Первая лига Англии": 15000,
        "Сегунда": 35000, "Серия Б": 35000, "Вторая Бундеслига": 40000,
        "ФНЛ": 45000, "Лига 2": 45000, "Чемпионшип": 55000,
        "РПЛ": 250000, "Лига 1": 250000, "АПЛ": 350000, "Ла Лига": 350000, "Серия А": 300000, "Бундеслига": 320000
    }
    base = mult.get(division, 15000)
    return int(rating * base * (1 + (rating - 40) / 30))
 
async def add_to_retired_leaderboard(name, rating, trophies_count):
    leaderboard = await load_data(LEADERBOARD_FILE)
    if "top_careers" not in leaderboard:
        leaderboard["top_careers"] = []
    
    leaderboard["top_careers"].append({
        "name": name,
        "rating": rating,
        "trophies": trophies_count
    })
    
    leaderboard["top_careers"] = sorted(leaderboard["top_careers"], key=lambda x: (x["rating"], x["trophies"]), reverse=True)[:10]
    await save_data(LEADERBOARD_FILE, leaderboard)

async def track_activity(user_id: str):
    players = await load_data(PLAYERS_FILE)
    if user_id in players:
        players[user_id]["activity_ticks"] = players[user_id].get("activity_ticks", 0) + 1
        await save_data(PLAYERS_FILE, players)
 
def _init_tables_internal(tables, user_id, division, player_club=None):
    clubs_list = CLUBS[division].copy()
    if player_club and player_club not in clubs_list:
        clubs_list[-1] = player_club
        
    division_table = [{"club": club, "points": 0, "wins": 0, "draws": 0, "losses": 0} for club in clubs_list]
    if user_id not in tables:
        tables[user_id] = {}
    tables[user_id][division] = division_table

async def init_tables_for_user(user_id, division, player_club=None):
    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        _init_tables_internal(tables, user_id, division, player_club)
        await save_data(TABLES_FILE, tables)
 
async def simulate_table_tour(user_id, division, player_club, player_match_rival, player_match_outcome):
    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        if user_id not in tables or division not in tables[user_id]:
            _init_tables_internal(tables, user_id, division, player_club)
            
        table = tables[user_id][division]
        
        for row in table:
            if row["club"] == player_club:
                if player_match_outcome == "win": row["points"] += 3; row["wins"] += 1
                elif player_match_outcome == "draw": row["points"] += 1; row["draws"] += 1
                else: row["losses"] += 1
            elif row["club"] == player_match_rival:
                if player_match_outcome == "win": row["losses"] += 1
                elif player_match_outcome == "draw": row["points"] += 1; row["draws"] += 1
                else: row["points"] += 3; row["wins"] += 1
     
        other_clubs = [row for row in table if row["club"] not in (player_club, player_match_rival)]
        random.shuffle(other_clubs)
        
        while len(other_clubs) >= 2:
            c1 = other_clubs.pop()
            c2 = other_clubs.pop()
            r1, r2 = CLUB_RATINGS.get(c1["club"], 50), CLUB_RATINGS.get(c2["club"], 50)
            chance_w1 = 0.35 + ((r1 - r2) * 0.01)
            chance_w2 = 0.35 + ((r2 - r1) * 0.01)
            rand = random.random()
            
            if rand < chance_w1: c1["points"] += 3; c1["wins"] += 1; c2["losses"] += 1
            elif rand < chance_w1 + chance_w2: c2["points"] += 3; c2["wins"] += 1; c1["losses"] += 1
            else: c1["points"] += 1; c1["draws"] += 1; c2["points"] += 1; c2["draws"] += 1
     
        if other_clubs:
            c = other_clubs.pop()
            res = random.choice(["win", "draw", "loss"])
            if res == "win": c["points"] += 3; c["wins"] += 1
            elif res == "draw": c["points"] += 1; c["draws"] += 1
            else: c["losses"] += 1
     
        tables[user_id][division] = sorted(table, key=lambda x: x["points"], reverse=True)
        await save_data(TABLES_FILE, tables)

async def simulate_background_division(user_id, division):
    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        if user_id not in tables or division not in tables[user_id]:
            _init_tables_internal(tables, user_id, division)
        table = tables[user_id][division]
        
        clubs = table.copy()
        random.shuffle(clubs)
        while len(clubs) >= 2:
            c1 = clubs.pop()
            c2 = clubs.pop()
            r1, r2 = CLUB_RATINGS.get(c1["club"], 50), CLUB_RATINGS.get(c2["club"], 50)
            chance_w1 = 0.35 + ((r1 - r2) * 0.01)
            chance_w2 = 0.35 + ((r2 - r1) * 0.01)
            rand = random.random()
            if rand < chance_w1: c1["points"] += 3; c1["wins"] += 1; c2["losses"] += 1
            elif rand < chance_w1 + chance_w2: c2["points"] += 3; c2["wins"] += 1; c1["losses"] += 1
            else: c1["points"] += 1; c1["draws"] += 1; c2["points"] += 1; c2["draws"] += 1
 
        if clubs:
            c = clubs.pop()
            res = random.choice(["win", "draw", "loss"])
            if res == "win": c["points"] += 3; c["wins"] += 1
            elif res == "draw": c["points"] += 1; c["draws"] += 1
            else: c["losses"] += 1
 
        tables[user_id][division] = sorted(table, key=lambda x: x["points"], reverse=True)
        await save_data(TABLES_FILE, tables)

def check_random_events(p):
    event_msg = ""
    if random.random() < 0.10:
        events = [
            ("📸 Отличная рекламная интеграция!", 0, 500, 0),
            ("😡 Стычка на тренировке с тренером...", -15, 0, 0),
            ("🤝 Помог одноклубнику с адаптацией.", 10, 0, 0),
            ("👟 Потерял счастливые бутсы.", -5, -100, 0),
            ("🎙 Дал отличное интервью после прошлого матча.", 5, 0, 0)
        ]
        ev = random.choice(events)
        event_msg = f"\n\n🎲 **Случайное событие:** {ev[0]}"
        p["trust"] = max(0, min(100, p["trust"] + ev[1]))
        p["money"] = max(0, p.get("money", 0) + ev[2])
    return event_msg, p
 
# --- ГЛАВНОЕ МЕНЮ ---
async def main_menu_keyboard(username: str = None, user_id: str = None):
    match_btn_text = "🎮 Матч"
    if user_id:
        p = (await load_data(PLAYERS_FILE)).get(user_id)
        if p and p.get("tour", 1) > 15:
            match_btn_text = "🏁 Итоги сезона"
                
    kb = [
        [InlineKeyboardButton(text="🏋️‍♂️ Тренировка", callback_data="menu_train_choice"), InlineKeyboardButton(text=match_btn_text, callback_data="menu_match")],
        [InlineKeyboardButton(text="📊 Таблица", callback_data="menu_table"), InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")],
        [InlineKeyboardButton(text="🍷 Личная жизнь", callback_data="menu_personal_life"), InlineKeyboardButton(text="🏆 Зал Славы", callback_data="menu_leaderboard")],
        [InlineKeyboardButton(text="💰 Спонсоры", callback_data="menu_sponsors"), InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")],
        [InlineKeyboardButton(text="🟢 Онлайн / Топ", callback_data="menu_online")]
    ]
    
    if username and username.replace("@", "") in ADMINS:
        kb.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
        
    return InlineKeyboardMarkup(inline_keyboard=kb)
 
@dp.callback_query(F.data == "menu_online")
async def online_handler(callback: CallbackQuery):
    players = await load_data(PLAYERS_FILE)
    total = len(players)
    online = max(1, int(total * 0.15) + random.randint(1, 4))
    
    top_active = sorted(players.values(), key=lambda x: x.get("activity_ticks", 0), reverse=True)[:5]
    top_text = "\n\n🔥 **Топ игроков по активности (за неделю):**\n"
    for i, p in enumerate(top_active, 1):
        top_text += f"{i}. {p['name']} ({p.get('activity_ticks', 0)} очков)\n"

    await callback.answer(f"🟢 Сейчас в боте: {online} чел.\n👥 Всего игроков в базе: {total}", show_alert=True)
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(top_text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
    else:
        await callback.message.edit_text(top_text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
 
@dp.callback_query(F.data == "menu_support")
async def support_handler(callback: CallbackQuery):
    text = (
        "🛠 **СИСТЕМА ПОДДЕРЖКИ**\n\n"
        "Связь с разработчиком: **@narcisstichniy**\n\n"
        "❤️ **Поддержать разраба на развитие бота:**\n"
        "Реквизиты: `2200701958479393` т-банк"
    )
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)), parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)), parse_mode="Markdown")

# --- ЛИЧНАЯ ЖИЗНЬ ---
@dp.callback_query(F.data == "menu_personal_life")
@with_user_lock
async def personal_life_menu(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p): return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 В ресторан (-500$)", callback_data="personal:rest")],
        [InlineKeyboardButton(text="💃 Найти девушку (-2000$)" if p.get("girlfriend", "Нет") == "Нет" else "🎁 Подарок девушке (-1000$)", callback_data="personal:girl")],
        [InlineKeyboardButton(text="🚗 Купить авто (-50,000$)", callback_data="personal:car"), InlineKeyboardButton(text="🏠 Купить дом (-250,000$)", callback_data="personal:house")],
        [InlineKeyboardButton(text="❤️ Пожертвовать", callback_data="menu_donate"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

    text = (f"🍷 **ЛИЧНАЯ ЖИЗНЬ**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Баланс: {p.get('money', 0)}$\n"
            f"💖 Настроение: {p.get('mood', 100)}%\n"
            f"🔋 Усталость: {p.get('fatigue', 0)}%\n\n"
            f"Трать деньги, чтобы улучшать настроение и снижать усталость!")

    await callback.message.delete()
    await callback.message.answer(text=text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("personal:"))
@with_user_lock
async def personal_action(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p): return

    action = callback.data.split(":")[1]
    cost = 0
    msg = ""

    if action == "rest":
        cost = 500
        if p.get("money", 0) >= cost:
            p["mood"] = min(100, p.get("mood", 100) + 10)
            p["fatigue"] = max(0, p.get("fatigue", 0) - 15)
            msg = "🍽 Ты отлично поужинал! Настроение +10%, Усталость -15%."
        else: msg = "❌ Не хватает денег."
    elif action == "girl":
        if p.get("girlfriend", "Нет") == "Нет":
            cost = 2000
            if p.get("money", 0) >= cost:
                p["girlfriend"] = "Есть"
                p["mood"] = min(100, p.get("mood", 100) + 30)
                msg = "💃 Ты познакомился с потрясающей девушкой! Настроение взлетело!"
            else: msg = "❌ Не хватает денег на красивые ухаживания."
        else:
            cost = 1000
            if p.get("money", 0) >= cost:
                p["mood"] = min(100, p.get("mood", 100) + 15)
                p["fatigue"] = max(0, p.get("fatigue", 0) - 20)
                msg = "🎁 Ты подарил девушке дорогие украшения! Настроение +15%, Усталость -20%."
            else: msg = "❌ Не хватает денег на достойный подарок."
    elif action == "car":
        cost = 50000
        if p.get("money", 0) >= cost:
            p["cars"] = p.get("cars", 0) + 1
            p["mood"] = 100
            msg = "🚗 Ты купил роскошный спорткар!"
        else: msg = "❌ Не хватает денег на авто."
    elif action == "house":
        cost = 250000
        if p.get("money", 0) >= cost:
            p["houses"] = p.get("houses", 0) + 1
            p["mood"] = 100
            msg = "🏠 Ты приобрел огромный особняк!"
        else: msg = "❌ Не хватает денег на недвижимость."

    if "❌" not in msg:
        p["money"] -= cost
        p["trust"] = min(100, p["trust"] + 2)

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await callback.answer(msg, show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 В ресторан (-500$)", callback_data="personal:rest")],
        [InlineKeyboardButton(text="💃 Найти девушку (-2000$)" if p.get("girlfriend", "Нет") == "Нет" else "🎁 Подарок девушке (-1000$)", callback_data="personal:girl")],
        [InlineKeyboardButton(text="🚗 Купить авто (-50,000$)", callback_data="personal:car"), InlineKeyboardButton(text="🏠 Купить дом (-250,000$)", callback_data="personal:house")],
        [InlineKeyboardButton(text="❤️ Пожертвовать", callback_data="menu_donate"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    text = (f"🍷 **ЛИЧНАЯ ЖИЗНЬ**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Баланс: {p.get('money', 0)}$\n"
            f"💖 Настроение: {p.get('mood', 100)}%\n"
            f"🔋 Усталость: {p.get('fatigue', 0)}%\n\n"
            f"Трать деньги, чтобы улучшать настроение и статус!")
    await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="Markdown")
 
# --- АДМИН-ПАНЕЛЬ ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("У вас нет доступа к этой панели.", show_alert=True)
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(
            "👑 **Админ-панель**\n\nОтправьте мне **ID пользователя** (например 123456_1) для управления:", 
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]])
        )
    else:
        await callback.message.edit_text(
            "👑 **Админ-панель**\n\nОтправьте мне **ID пользователя** для управления:", 
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]])
        )
    await state.set_state(AdminPanel.waiting_for_user_id)
 
@dp.message(AdminPanel.waiting_for_user_id)
async def admin_user_management(message: Message, state: FSMContext):
    target_id = message.text.strip()
    players = await load_data(PLAYERS_FILE)
    
    if target_id not in players or players[target_id].get("retired"):
        return await message.answer("❌ Активный игрок с таким ID не найден.", reply_markup=await main_menu_keyboard(message.from_user.username, await get_uid(message)))
    
    await show_admin_user_profile(message, target_id)
    await state.clear()
 
async def show_admin_user_profile(message_or_call, target_id):
    players = await load_data(PLAYERS_FILE)
    p = players[target_id]
    val = calculate_player_value(p["rating"], p["division"])
    
    stats_text = ""
    if p["position"] == "GK": stats_text = f"🧤 Сейвы: {p['stats_season'].get('saves', 0)}"
    elif p["position"] == "CB": stats_text = f"🛡️ Отборы: {p['stats_season'].get('tackles', 0)} | ⚽ Голы: {p['stats_season'].get('goals', 0)}"
    else: stats_text = f"⚽ Голы: {p['stats_season'].get('goals', 0)} | 🅰️ Ассисты: {p['stats_season'].get('assists', 0)}"
 
    text = (
        f"👑 ПРОФИЛЬ ИГРОКА (ID: `{target_id}`)\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃‍♂️ {p['name']} | 🌍 {p.get('nation', 'Россия')} | 🎂 {p.get('age', 17)} лет\n"
        f"⚡️ Рейтинг: {p['rating']}/100\n"
        f"🏢 Клуб: {p['club']} ({p['position']})\n"
        f"💵 Баланс: {p.get('money', 0)}$ | 🏷️ Стоимость: {val:,}$\n"
        f"🏟️ Сезон: {p['season']} | Тур: {p['tour']}/15\n━━━━━━━━━━━━━━━━━━━━\n{stats_text}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Тур (+1)", callback_data=f"adm_tour:{target_id}"),
         InlineKeyboardButton(text="⏭ Сезон (+1)", callback_data=f"adm_season:{target_id}")],
        [InlineKeyboardButton(text="💰 Выдать деньги", callback_data=f"adm_money:{target_id}"),
         InlineKeyboardButton(text="⚡️ Выдать рейтинг", callback_data=f"adm_rating:{target_id}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])
    
    if isinstance(message_or_call, Message):
        await message_or_call.answer(text, reply_markup=kb)
    else:
        await message_or_call.message.edit_text(text, reply_markup=kb)
 
@dp.callback_query(F.data.startswith("adm_tour:"))
async def adm_skip_tour(callback: CallbackQuery):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("Ошибка доступа.", show_alert=True)
    target_id = callback.data.split(":")[1]
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            players[target_id]["tour"] += 1
            await save_data(PLAYERS_FILE, players)
            await show_admin_user_profile(callback, target_id)
 
@dp.callback_query(F.data.startswith("adm_season:"))
async def adm_skip_season(callback: CallbackQuery):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("Ошибка доступа.", show_alert=True)
    target_id = callback.data.split(":")[1]
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            players[target_id]["season"] += 1
            players[target_id]["tour"] = 1
            await save_data(PLAYERS_FILE, players)
            await show_admin_user_profile(callback, target_id)
 
@dp.callback_query(F.data.startswith("adm_money:"))
async def adm_money_btn(callback: CallbackQuery, state: FSMContext):
    target_id = callback.data.split(":")[1]
    await state.update_data(adm_target_id=target_id)
    await callback.message.edit_text("💰 Введите сумму долларов для выдачи:", parse_mode="Markdown")
    await state.set_state(AdminPanel.waiting_for_money)
 
@dp.message(AdminPanel.waiting_for_money)
async def adm_process_money(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("adm_target_id")
    try: amount = int(message.text.strip())
    except: return await message.answer("❌ Число!")
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            players[target_id]["money"] = players[target_id].get("money", 0) + amount
            await save_data(PLAYERS_FILE, players)
            await show_admin_user_profile(message, target_id)
    await state.clear()
 
@dp.callback_query(F.data.startswith("adm_rating:"))
async def adm_rating_btn(callback: CallbackQuery, state: FSMContext):
    target_id = callback.data.split(":")[1]
    await state.update_data(adm_target_id=target_id)
    await callback.message.edit_text("⚡️ Введите новый РЕЙТИНГ (1-100):", parse_mode="Markdown")
    await state.set_state(AdminPanel.waiting_for_rating)
 
@dp.message(AdminPanel.waiting_for_rating)
async def adm_process_rating(message: Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("adm_target_id")
    try: rating = float(message.text.strip())
    except: return await message.answer("❌ Число!")
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            players[target_id]["rating"] = rating
            await save_data(PLAYERS_FILE, players)
            await show_admin_user_profile(message, target_id)
    await state.clear()
 
# --- СТАРТ И СОЗДАНИЕ ---
@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"), InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])
    await message.answer("⚽ **Добро пожаловать в симулятор футболиста!**\nВыбери слот для игры:", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("select_slot:"))
async def select_slot_handler(callback: CallbackQuery, state: FSMContext):
    slot = callback.data.split(":")[1]
    tg_id = str(callback.from_user.id)
    await set_active_slot(tg_id, slot)
    
    user_id = f"{tg_id}_{slot}"
    players = await load_data(PLAYERS_FILE)
    
    if user_id in players and not players[user_id].get("retired", False):
        players[user_id]["username_tg"] = callback.from_user.username
        await save_data(PLAYERS_FILE, players)
        await callback.message.edit_text(f"👋 **С возвращением, {players[user_id]['name']}!** (Слот {slot})\nТвой ID: `{user_id}`", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")
    else:
        if user_id in players and players[user_id].get("retired", False):
            history = players[user_id].get("career_history", [])
            await state.update_data(career_history=history)
            await callback.message.edit_text(f"⚽ **Твоя прошлая карьера (Слот {slot}) окончена. Начнем новую!**\nДля начала введи Имя и Фамилию:", parse_mode="Markdown")
        else:
            await callback.message.edit_text(f"⚽ **Создаем профиль в Слоте {slot}!**\nДля начала введи Имя и Фамилию:", parse_mode="Markdown")
        await state.set_state(PlayerCreation.waiting_for_name)

@dp.message(PlayerCreation.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=NATIONS[i], callback_data=f"nat:{NATIONS[i]}"),
         InlineKeyboardButton(text=NATIONS[i+1] if i + 1 < len(NATIONS) else NATIONS[i], callback_data=f"nat:{NATIONS[i+1] if i + 1 < len(NATIONS) else NATIONS[i]}")]
        for i in range(0, min(len(NATIONS), 12), 2)
    ])
    await message.answer("🌍 **Выбери свою национальность (основные страны):**", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_nation)
 
@dp.callback_query(PlayerCreation.waiting_for_nation, F.data.startswith("nat:"))
async def process_nation(callback: CallbackQuery, state: FSMContext):
    await state.update_data(nation=callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=pos, callback_data=f"pos:{POSITIONS[pos]}")] for pos in POSITIONS.keys()])
    await callback.message.edit_text("📋 **Выбери амплуа:**", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_position)
 
@dp.callback_query(PlayerCreation.waiting_for_position, F.data.startswith("pos:"))
async def process_position(callback: CallbackQuery, state: FSMContext):
    await state.update_data(position=callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Россия", callback_data="league:Россия"), InlineKeyboardButton(text="🇫🇷 Франция", callback_data="league:Франция")],
        [InlineKeyboardButton(text="🏴󠁧󠁢󠁥󠁮󠁧󠁿 Англия", callback_data="league:Англия"), InlineKeyboardButton(text="🇪🇸 Испания", callback_data="league:Испания")],
        [InlineKeyboardButton(text="🇮🇹 Италия", callback_data="league:Италия"), InlineKeyboardButton(text="🇩🇪 Германия", callback_data="league:Германия")]
    ])
    await callback.message.edit_text("🌍 **В какой стране начнешь карьеру?**", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_country_league)
 
@dp.callback_query(PlayerCreation.waiting_for_country_league, F.data.startswith("league:"))
async def process_country_league(callback: CallbackQuery, state: FSMContext):
    league_country = callback.data.split(":")[1]
    if league_country == "Россия": div = "ФНЛ 2"
    elif league_country == "Франция": div = "Насьональ"
    elif league_country == "Англия": div = "Первая лига Англии"
    elif league_country == "Испания": div = "Сегунда"
    elif league_country == "Германия": div = "Вторая Бундеслига"
    else: div = "Серия Б"
    
    await state.update_data(start_division=div)
    await callback.message.edit_text("🔢 **Введи номер (1 - 99):**", parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_number)
 
@dp.message(PlayerCreation.waiting_for_number)
async def process_number(message: Message, state: FSMContext):
    if not message.text.isdigit() or not (1 <= int(message.text) <= 99):
        return await message.answer("🚫 Выбери номер от 1 до 99:")
    
    await state.update_data(number=int(message.text))
    user_data = await state.get_data()
    start_div = user_data["start_division"]
    
    available_clubs = random.sample(CLUBS[start_div], 3)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🏢 {club}", callback_data=f"club:{club}")] for club in available_clubs])
    await message.answer(f"📉 Тобой интересуются клубы из лиги: **{start_div}**. Где начнешь?", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_club)
 
@dp.callback_query(PlayerCreation.waiting_for_club, F.data.startswith("club:"))
@with_user_lock
async def process_club(callback: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    user_id = await get_uid(callback)
    chosen_club = callback.data.split(":")[1]
    
    player_profile = {
        "name": user_data["name"],
        "nation": user_data.get("nation", "Россия"),
        "position": user_data["position"],
        "number": user_data["number"],
        "club": chosen_club,
        "division": get_division(chosen_club),
        "rating": 40.0,
        "trust": 15,
        "mood": 100,
        "fatigue": 0,
        "girlfriend": "Нет",
        "cars": 0,
        "houses": 0,
        "age": 17,
        "season": 1,
        "tour": 1,
        "money": 5000,
        "contract_salary": 1500,
        "sponsor": None,
        "on_loan": False,
        "parent_club": None,
        "loan_tours_left": 0,
        "cup_out": False,
        "cup_stage": "1/16",
        "cup_rivals": [],
        "played_league_rivals": [],
        "trophies": [],
        "stats_season": {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0},
        "stats_total": {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0},
        "train_done": False,
        "is_injured": False,
        "injury_tours": 0,
        "username_tg": callback.from_user.username,
        "career_history": user_data.get("career_history", []),
        "retired": False,
        "activity_ticks": 0
    }
    
    players = await load_data(PLAYERS_FILE)
    players[user_id] = player_profile
    await save_data(PLAYERS_FILE, players)
    await init_tables_for_user(user_id, player_profile["division"], player_profile["club"])
    
    await state.clear()
    await callback.message.edit_text(f"✍️ **КОНТРАКТ ПОДПИСАН!** Добро пожаловать в {player_profile['club']}!\n💰 Твоя зарплата: {player_profile['contract_salary']}$ за матч.", parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
 
@dp.callback_query(F.data == "start_new_career")
@with_user_lock
async def start_new_career_handler(callback: CallbackQuery, state: FSMContext):
    players = await load_data(PLAYERS_FILE)
    user_id = await get_uid(callback)
    if user_id in players:
        history = players[user_id].get("career_history", [])
        await state.update_data(career_history=history)
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer("⚽ **Добро пожаловать обратно! Начнем заново!**\nДля начала введи Имя и Фамилию:", parse_mode="Markdown")
    else:
        await callback.message.edit_text("⚽ **Добро пожаловать обратно! Начнем заново!**\nДля начала введи Имя и Фамилию:", parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_name)
 
@dp.callback_query(F.data == "delete_career")
@with_user_lock
async def delete_career_handler(callback: CallbackQuery):
    players = await load_data(PLAYERS_FILE)
    user_id = await get_uid(callback)
    if user_id in players:
        del players[user_id]
        await save_data(PLAYERS_FILE, players)
    await callback.message.edit_text("🗑 **Карьера удалена!** Нажми /start, чтобы создать новую.", parse_mode="Markdown")

# --- ТРЕНИРОВКИ, ТАБЛИЦЫ, СЛУЖЕБНЫЕ МЕНЮ ---
@dp.callback_query(F.data == "menu_train_choice")
@with_user_lock
async def train_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p): return
        
    if p.get("injury_tours", 0) > 0:
        return await callback.answer(f"🚑 Вы травмированы! Осталось лечиться туров: {p['injury_tours']}.", show_alert=True)
        
    if p.get("train_done", False):
        return await callback.answer("🚫 Сыграй матч, чтобы открыть тренировку.", show_alert=True)
    
    if p.get("fatigue", 0) >= 90:
        return await callback.answer("🚫 Вы слишком устали! Сходите в ресторан или отдохните.", show_alert=True)

    if p["position"] == "GK":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧤 Реакция", callback_data="train:tech"), InlineKeyboardButton(text="🏃 Физика", callback_data="train:phys")],
            [InlineKeyboardButton(text="⚽ Игра ногами", callback_data="train:shoot"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Техника", callback_data="train:tech"), InlineKeyboardButton(text="🏃 Физика", callback_data="train:phys")],
            [InlineKeyboardButton(text="🎯 Удар / Отбор", callback_data="train:shoot"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
        
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer("🏋️‍♂️ **ТРЕНИРОВКА**", reply_markup=kb, parse_mode="Markdown")
    else:
        await callback.message.edit_text("🏋️‍♂️ **ТРЕНИРОВКА**", reply_markup=kb, parse_mode="Markdown")
 
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: CallbackQuery):
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer("🏠 Главное меню.", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
    else:
        await callback.message.edit_text("🏠 Главное меню.", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
 
@dp.callback_query(F.data.startswith("train:"))
@with_user_lock
async def train_execute_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p): return
        
    if p.get("injury_tours", 0) > 0:
        return await callback.answer("🚑 Вы травмированы! Тренировка недоступна.", show_alert=True)
    
    p["trust"] = min(100, p["trust"] + random.randint(6, 14))
    p["train_done"] = True
    p["fatigue"] = min(100, p.get("fatigue", 0) + 10)
    
    if random.random() < 0.015:
        p["injury_tours"] = random.randint(1, 2)
        p["is_injured"] = True
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        await callback.message.delete()
        return await callback.message.answer(text=f"🚑 **ОЙ!** На тренировке ты потянул мышцу. Выбыл на {p['injury_tours']} тур(а).", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))
    
    # Расчет прогресса рейтинга
    rating_gain = round(random.uniform(-0.1, 0.3), 1)
    p["rating"] = max(1.0, min(100.0, round(p.get("rating", 40.0) + rating_gain, 1)))
 
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await callback.message.delete()
    
    gain_str = f"+{rating_gain}" if rating_gain > 0 else f"{rating_gain}"
    msg_text = f"💪 **Тренировка завершена!**\n\n📈 **Прогресс:** Рейтинг {gain_str} | Усталость +10%\n⚡ Текущий рейтинг: **{p['rating']}**"
    
    await callback.message.answer(text=msg_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))
 
@dp.callback_query(F.data == "menu_table")
@with_user_lock
async def show_table_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    tables = await load_data(TABLES_FILE)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p): return

    if user_id not in tables or p["division"] not in tables[user_id]: 
        await init_tables_for_user(user_id, p["division"], p["club"])
        tables = await load_data(TABLES_FILE)
        
    table_data = tables[user_id][p["division"]]
    
    text = f"📊 **ТАБЛИЦА: {p['division']}**\n🏆 *Победа — 3 очка, Ничья — 1 очко, Поражение — 0*\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, row in enumerate(table_data, 1):
        is_p = "👉 " if row["club"] == p["club"] else "• "
        text += f"{i}. {is_p}**{row['club']}** — {row['points']} очков ({row['wins']}В / {row['draws']}Н / {row['losses']}П)\n"
        
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    else:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
 
@dp.callback_query(F.data == "menu_profile")
@with_user_lock
async def profile_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        await callback.message.answer("⚠️ Профиль не найден. Нажми /start, чтобы начать.", parse_mode="Markdown")
        return
 
    if p.get("retired"):
        history_str = "\n\n".join(p.get("career_history", [])) or "—"
        text = (
            f"🏁 **КАРЬЕРА ЗАВЕРШЕНА**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🏃‍♂️ {p['name']} | 🌍 {p.get('nation', 'Россия')}\n\n"
            f"📚 **Завершенные карьеры (Статистика):**\n{history_str}\n\n"
            f"Нажми кнопку ниже, чтобы начать новую историю."
        )
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=retired_keyboard())
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=retired_keyboard())
        return
 
    val = calculate_player_value(p["rating"], p["division"])
    
    loan_status = f"\n⚠️ *В аренде из {p['parent_club']}* (Осталось: {p['loan_tours_left']} тур.)" if p.get("on_loan") else ""
    injury_status = f"\n🚑 *Травмирован!* (Лечиться еще: {p.get('injury_tours', 0)} тур.)" if p.get("injury_tours", 0) > 0 else ""
    
    if p["position"] == "GK": stats_text = f"🧤 Сейвы: {p['stats_season'].get('saves', 0)}"
    elif p["position"] == "CB": stats_text = f"🛡️ Отборы: {p['stats_season'].get('tackles', 0)} | ⚽ Голы: {p['stats_season'].get('goals', 0)}"
    else: stats_text = f"⚽ Голы: {p['stats_season'].get('goals', 0)} | 🅰️ Ассисты: {p['stats_season'].get('assists', 0)}"
    
    history_str = ""
    if p.get("career_history"):
        history_str = "\n\n📚 **Прошлые карьеры:**\n" + "\n\n".join(p["career_history"])
 
    season_display = min(p['season'], 13) 
    tour_display = min(p['tour'], 15)
 
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Удалить карьеру", callback_data="delete_career")])

    text = (
        f"👑 ПРОФИЛЬ ИГРОКА\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃‍♂️ {p['name']} | 🌍 {p.get('nation', 'Россия')} | 🎂 {p.get('age', 17)} лет\n"
        f"⚡️ Рейтинг: {p['rating']}/100\n"
        f"🏢 Клуб: {p['club']} ({p['position']}){loan_status}{injury_status}\n"
        f"💵 Баланс: {p.get('money', 0)}$ | 🏷️ Стоимость: {val:,}$\n"
        f"🤝 Зарплата: {p.get('contract_salary', 0)}$/матч\n"
        f"💎 Спонсор: {p.get('sponsor', 'Нет')}\n"
        f"📊 Статус: {get_status_by_trust(p['trust'])}\n"
        f"💖 Настроение: {p.get('mood', 100)}% | 🔋 Усталость: {p.get('fatigue', 0)}%\n"
        f"💍 Девушка: {p.get('girlfriend', 'Нет')}\n"
        f"🚗 Авто: {p.get('cars', 0)} | 🏠 Дома: {p.get('houses', 0)}\n"
        f"🏟️ Сезон: {season_display}/13 | Тур Лиги: {tour_display}/15\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **Текущая карьера (за сезон):**\n{stats_text}\n"
        f"📈 **Общая статистика (текущий игрок):**\nВсего игр: {p.get('stats_total', {}).get('games', 0)} | Голов: {p.get('stats_total', {}).get('goals', 0)} | Ассистов: {p.get('stats_total', {}).get('assists', 0)}"
        f"{history_str}"
    )
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb)
    else:
        await callback.message.edit_text(text, reply_markup=kb)
 
# --- ДАННЫЕ СПОНСОРОВ ---
# income_per_match: доход за каждый сыгранный матч
SPONSORS_DATA = {
    "Литвин":    {"emoji": "🥤", "min_rating": 40, "income_per_match": 500,   "sign_bonus": 2_000},
    "Самосвет":  {"emoji": "💎", "min_rating": 50, "income_per_match": 800,   "sign_bonus": 3_000},
    "Жигули":    {"emoji": "🍺", "min_rating": 55, "income_per_match": 1_000, "sign_bonus": 4_000},
    "Найк":      {"emoji": "👟", "min_rating": 67, "income_per_match": 3_000, "sign_bonus": 15_000},
    "Пума":      {"emoji": "🐆", "min_rating": 67, "income_per_match": 2_500, "sign_bonus": 12_000},
    "Рибок":     {"emoji": "🏅", "min_rating": 67, "income_per_match": 2_200, "sign_bonus": 10_000},
    "ПСБ банк":  {"emoji": "🏦", "min_rating": 67, "income_per_match": 2_800, "sign_bonus": 13_000},
}

@dp.callback_query(F.data == "menu_sponsors")
@with_user_lock
async def sponsors_menu(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p): return

    rating = p.get("rating", 40)
    current_sponsor = p.get("sponsor")

    lines = []
    buttons = []
    row = []
    for name, info in SPONSORS_DATA.items():
        locked = rating < info["min_rating"]
        status = "✅ Активен" if name == current_sponsor else ("🔒" if locked else "")
        label = f"{info['emoji']} {name} {status}"
        lines.append(
            f"{info['emoji']} **{name}** — {info['income_per_match']}$/матч"
            + (f" | бонус при подписании: {info['sign_bonus']}$" if not locked else f" (нужен рейтинг {info['min_rating']})")
        )
        if not locked and name != current_sponsor:
            row.append(InlineKeyboardButton(text=label, callback_data=f"sponsor:{name}"))
            if len(row) == 2:
                buttons.append(row); row = []
        else:
            row.append(InlineKeyboardButton(text=label, callback_data="noop"))
            if len(row) == 2:
                buttons.append(row); row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    text = (
        f"💰 **РЕКЛАМНЫЕ КОНТРАКТЫ**\n"
        f"Твой рейтинг: **{rating}**\n"
        f"Активный спонсор: **{current_sponsor or 'Нет'}**\n"
        f"Доход зачисляется автоматически за каждый матч.\n\n"
        + "\n".join(lines)
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        else:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.warning(f"sponsors_menu edit error: {e}")
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("sponsor:"))
@with_user_lock
async def sponsor_sign(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p): return

    sp = callback.data.split(":")[1]
    info = SPONSORS_DATA.get(sp)
    if not info:
        return await callback.answer("❌ Неизвестный спонсор.", show_alert=True)
    if p.get("rating", 40) < info["min_rating"]:
        return await callback.answer(f"❌ Нужен рейтинг {info['min_rating']}!", show_alert=True)

    p["sponsor"] = sp
    p["money"] = p.get("money", 0) + info["sign_bonus"]
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    text = (f"🤝 **Контракт с {info['emoji']} {sp} подписан!**\n"
            f"💵 Бонус при подписании: +{info['sign_bonus']}$\n"
            f"📈 Доход за каждый матч: +{info['income_per_match']}$")
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    except Exception as e:
        logging.warning(f"sponsor_sign edit error: {e}")
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
 
@dp.callback_query(F.data == "menu_donate")
@with_user_lock
async def donate_menu(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏘 Города", callback_data="don_dest:city"), InlineKeyboardButton(text="🧒 Детдомы", callback_data="don_dest:kids")],
        [InlineKeyboardButton(text="⚽ Академии", callback_data="don_dest:academy"), InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]
    ])
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer("❤️ **Благотворительность**\nКуда направить средства?", reply_markup=kb, parse_mode="Markdown")
    else:
        await callback.message.edit_text("❤️ **Благотворительность**\nКуда направить средства?", reply_markup=kb, parse_mode="Markdown")
 
@dp.callback_query(F.data.startswith("don_dest:"))
async def donate_dest(callback: CallbackQuery, state: FSMContext):
    await state.update_data(dest=callback.data.split(":")[1])
    await callback.message.edit_text("💵 Введи сумму (в $):")
    await state.set_state(Donation.waiting_for_amount)
 
@dp.message(Donation.waiting_for_amount)
@with_user_lock
async def process_donation(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число.")
    amount = int(message.text)
    user_id = await get_uid(message)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_msg(message, p): return await state.clear()
    
    if p.get("money", 0) < amount or amount <= 0:
        await message.answer("❌ Недостаточно средств.", reply_markup=await main_menu_keyboard(message.from_user.username, user_id))
        return await state.clear()
 
    p["money"] -= amount
    p["trust"] = min(100, p["trust"] + 5)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    
    await message.answer(f"❤️ Пожертвовано **{amount}$**! Твой баланс: {p['money']}$", reply_markup=await main_menu_keyboard(message.from_user.username, user_id), parse_mode="Markdown")
    await state.clear()
 
@dp.callback_query(F.data == "menu_leaderboard")
async def leaderboard_handler(callback: CallbackQuery):
    leaderboard = (await load_data(LEADERBOARD_FILE)).get("top_careers", [])
    text = "🏆 **ЗАЛ СЛАВЫ (ЗАВЕРШЕННЫЕ КАРЬЕРЫ)**\n━━━━━━━━━━━━━━━━━━━━\n"
    if not leaderboard:
        text += "Пока нет ни одной завершенной карьеры."
    for i, item in enumerate(leaderboard, 1):
        text += f"`{i}.` 👤 **{item['name']}** — Рейтинг: **{item['rating']}** | Трофеев: **{item['trophies']}**\n"
    
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
    else:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
 
# --- ОБРАБОТКА ВЫБОРА КЛУБА ПОСЛЕ СКАНДАЛА ИЛИ УХОДА ---
@dp.callback_query(F.data.startswith("scandal_club:"))
@with_user_lock
async def scandal_club_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p): return
    new_club = callback.data.split(":")[1]
    
    old_division = p.get("division")
    p["club"] = new_club
    p["division"] = get_division(new_club)
    p["trust"] = 25
    
    base_salaries = {
        "ФНЛ 2": 1500, "Насьональ": 1500, "Первая лига Англии": 1800,
        "ФНЛ": 6000, "Лига 2": 6000, "Чемпионшип": 8000, "Сегунда": 8000, "Серия Б": 8000, "Вторая Бундеслига": 7500,
        "РПЛ": 30000, "Лига 1": 30000, "АПЛ": 50000, "Ла Лига": 50000, "Серия А": 45000, "Бундеслига": 48000
    }
    p["contract_salary"] = int(base_salaries.get(p["division"], 1500) * (p["rating"] / 45))
    
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    if old_division != p["division"]:
        await init_tables_for_user(user_id, p["division"], p["club"])
        p["played_league_rivals"] = []
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
    
    await callback.message.delete()
    await callback.message.answer(
        text=f"✍️ Ты успешно перешел в **{new_club}**!\n💵 Твоя новая зарплата: **{p['contract_salary']}$/матч**.\nПора доказывать фанатам свою преданность!",
        parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
    )
 
# --- МАТЧИ И СИМУЛЯЦИЯ МОМЕНТОВ ---
@dp.callback_query(F.data == "menu_match")
@with_user_lock
async def match_handler(callback: CallbackQuery, state: FSMContext):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p): return
    
    if p.get("fatigue", 0) >= 95:
        return await callback.answer("🚫 Ты смертельно устал! Сходи в ресторан или отдохни.", show_alert=True)
        
    # --- ОБРАБОТКА ТРАВМЫ ---
    if p.get("injury_tours", 0) > 0:
        p["injury_tours"] -= 1
        if p["injury_tours"] == 0:
            p["is_injured"] = False
        
        p["tour"] += 1
        p["money"] = p.get("money", 0) + p.get("contract_salary", 1500)
        p["train_done"] = False
        p["fatigue"] = max(0, p.get("fatigue", 0) - 10)
        
        played_rivals = p.get("played_league_rivals", [])
        rival_pool = [c for c in CLUBS[p["division"]] if c != p["club"] and c not in played_rivals]
        if not rival_pool:
            rival_pool = [c for c in CLUBS[p["division"]] if c != p["club"]]
            p["played_league_rivals"] = []
            
        rival = random.choice(rival_pool)
        p["played_league_rivals"].append(rival)
        outcome = random.choice(["win", "draw", "loss"])
        
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        
        await simulate_table_tour(user_id, p["division"], p["club"], rival, outcome)
        if p.get("on_loan") and p.get("parent_club"):
            parent_div = get_division(p["parent_club"])
            if parent_div != p["division"]:
                await simulate_background_division(user_id, parent_div)
                
        msg = f"🚑 **ТЫ ПРОПУСТИЛ ТУР ИЗ-ЗА ТРАВМЫ**\nКоманда сыграла против **{rival}**. Итог для твоего клуба: **{'Победа' if outcome=='win' else 'Ничья' if outcome=='draw' else 'Поражение'}**.\n"
        if p["injury_tours"] > 0:
            msg += f"Осталось лечиться туров: {p['injury_tours']}."
        else:
            msg += "✅ **Ты полностью восстановился и готов к следующему матчу!**"
            
        if callback.message.photo:
            await callback.message.delete()
            return await callback.message.answer(msg, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
        else:
            return await callback.message.edit_text(msg, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    
    # --- СИСТЕМА ДИНАМИЧЕСКИХ ПЕРЕХОДОВ В БУНДЕСЛИГУ ПО РЕЙТИНГУ ---
    current_rating = p.get("rating", 40)
    if p["division"] not in ["Бундеслига", "Вторая Бундеслига"] and random.random() < 0.15:
        if current_rating >= 74:
            ger_offers = random.sample(CLUBS["Бундеслига"], 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🇩🇪 {c}", callback_data=f"scandal_club:{c}")] for c in ger_offers
            ] + [[InlineKeyboardButton(text="❌ Отклонить предложение", callback_data="back_to_menu")]])
            await callback.message.delete()
            return await callback.message.answer(
                text=f"📈 **ТРАНСФЕРНОЕ ПРЕДЛОЖЕНИЕ!** Твой высокий рейтинг ({current_rating}) привлек внимание клубов из Германии! Тебе предлагают контракт в **Бундеслиге**:",
                reply_markup=kb, parse_mode="Markdown"
            )
        elif current_rating >= 55:
            ger_offers = random.sample(CLUBS["Вторая Бундеслига"], 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🇩🇪 {c}", callback_data=f"scandal_club:{c}")] for c in ger_offers
            ] + [[InlineKeyboardButton(text="❌ Отклонить предложение", callback_data="back_to_menu")]])
            await callback.message.delete()
            return await callback.message.answer(
                text=f"📈 **ТРАНСФЕРНОЕ ПРЕДЛОЖЕНИЕ!** На основе твоего рейтинга ({current_rating}) команды из Германии предлагают тебе контракт во **Второй Бундеслиге**:",
                reply_markup=kb, parse_mode="Markdown"
            )

    if p["tour"] > 15:
        return await season_results_handler(callback)
    
    # --- КЛУБНЫЙ МАТЧ ---
    event_str, p = check_random_events(p)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    if random.random() < 0.01:
        div_clubs = [c for c in CLUBS[p["division"]] if c != p["club"]]
        available_clubs = random.sample(div_clubs, min(len(div_clubs), 2))
        
        top_leagues = ["РПЛ", "Лига 1", "АПЛ", "Ла Лига", "Серия А", "Бундеслига"]
        my_top_league = "РПЛ"
        if p["division"] in ["Насьональ", "Лига 2", "Лига 1"]: my_top_league = "Лига 1"
        elif p["division"] in ["Первая лига Англии", "Чемпионшип", "АПЛ"]: my_top_league = "АПЛ"
        elif p["division"] in ["Сегунда", "Ла Лига"]: my_top_league = "Ла Лига"
        elif p["division"] in ["Серия Б", "Серия А"]: my_top_league = "Серия А"
        elif p["division"] in ["Вторая Бундеслига", "Бундеслига"]: my_top_league = "Бундеслига"
        
        alt_leagues = [l for l in top_leagues if l != my_top_league]
        alt_league = random.choice(alt_leagues) if alt_leagues else "РПЛ"
        available_clubs.append(random.choice(CLUBS[alt_league]))
        random.shuffle(available_clubs)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text=f"🏢 {club}", callback_data=f"scandal_club:{club}")] for club in available_clubs]])
        
        await callback.message.delete()
        return await callback.message.answer(
            text=f"🤬 **СКАНДАЛ С РУКОВОДСТВОМ!** Твой контракт с {p['club']} разорван.\nИнтерес к тебе проявили клубы. Выбери новую команду:",
            reply_markup=kb, parse_mode="Markdown"
        )
        
    p["stats_season"]["games"] += 1
    p["fatigue"] = min(100, p.get("fatigue", 0) + 15)
    
    cup_stg = p.get("cup_stage", "1/16")
    is_cup_match = (not p.get("cup_out", False)) and (cup_stg in CUP_STAGES) and random.random() < 0.20
    
    if is_cup_match:
        country_leagues = []
        if p["division"] in ["ФНЛ 2", "ФНЛ", "РПЛ"]: country_leagues = ["ФНЛ 2", "ФНЛ", "РПЛ"]
        elif p["division"] in ["Насьональ", "Лига 2", "Лига 1"]: country_leagues = ["Насьональ", "Лига 2", "Лига 1"]
        elif p["division"] in ["Первая лига Англии", "Чемпионшип", "АПЛ"]: country_leagues = ["Первая лига Англии", "Чемпионшип", "АПЛ"]
        elif p["division"] in ["Сегунда", "Ла Лига"]: country_leagues = ["Сегунда", "Ла Лига"]
        elif p["division"] in ["Серия Б", "Серия А"]: country_leagues = ["Серия Б", "Серия А"]
        elif p["division"] in ["Вторая Бундеслига", "Бундеслига"]: country_leagues = ["Вторая Бундеслига", "Бундеслига"]
        
        rival_pool = []
        for l in country_leagues:
            rival_pool.extend(CLUBS[l])
            
        played_cup_rivals = p.get("cup_rivals", [])
        rival_pool = [c for c in rival_pool if c != p["club"] and c not in played_cup_rivals]
        
        if not rival_pool:
            rival_pool = ["Случайная команда"]
    else:
        played_rivals = p.get("played_league_rivals", [])
        rival_pool = [c for c in CLUBS[p["division"]] if c != p["club"] and c not in played_rivals]
        
        if not rival_pool: 
            rival_pool = [c for c in CLUBS[p["division"]] if c != p["club"]]
            p["played_league_rivals"] = []
            
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        
    match_data = {
        "rival": random.choice(rival_pool),
        "total_moments": random.randint(1, 4),
        "current_moment": 1,
        "minute": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0, "yellow_cards": 0,
        "my_team_score": 0, "rival_team_score": 0,
        "is_cup": is_cup_match, "cup_stage": cup_stg if is_cup_match else None,
        "log": ""
    }
    await state.update_data(match=match_data)
    
    match_title = f"🏆 НАЦИОНАЛЬНЫЙ КУБОК ({cup_stg}) 🏆" if is_cup_match else f"🏟️ РЕГУЛЯРНЫЙ ЧЕМПИОНАТ ({p['division']})"
    intro_text = f"{event_str}\n\n" if event_str else ""
    
    if callback.message.photo: await callback.message.delete()
    
    msg = await callback.message.answer(f"{intro_text}⚽ **{match_title}**\n⚔️ **{p['club']}** vs **{match_data['rival']}**\nСудья дает свисток к началу игры!", parse_mode="Markdown")
    await asyncio.sleep(2)
    await msg.delete()
    await generate_moment(callback, state, user_id)
 
async def generate_moment(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    if "match" not in data:
        return
    m = data["match"]
    p = (await load_data(PLAYERS_FILE)).get(user_id)
 
    m["minute"] += random.randint(15, 25)
    if m["minute"] > 90: m["minute"] = 90
    
    my_rating = CLUB_RATINGS.get(p["club"], 50)
    rival_rating = CLUB_RATINGS.get(m["rival"], 50)
    rating_diff = my_rating - rival_rating
 
    if random.random() < 0.65:
        if random.random() < 0.5:
            rival_score_chance = 0.40 - (rating_diff * 0.02)
            if random.random() < max(0.05, min(0.95, rival_score_chance)):
                m["rival_team_score"] += 1
                m["log"] += f"⚡ **{m['minute']}'** | ГОЛ! Соперник забивает мяч в ваши ворота.\n"
        else:
            team_score_chance = 0.40 + (rating_diff * 0.02)
            if random.random() < max(0.05, min(0.95, team_score_chance)):
                m["my_team_score"] += 1
                m["log"] += f"⚽ **{m['minute']}'** | ГОЛ! Твоя команда забивает отличный гол!\n"

    if random.random() < 0.4:
        flavor = random.choice([
            "🔥 Красивый финт в центре поля обостряет игру.", 
            "📐 Подача углового, но защита выносит мяч.", 
            "🟨 Судья показывает желтую карточку игроку соперника.",
            "⚔️ Жесткий стык, но судья не дает свисток.",
            "👐 Вратарь уверенно забирает мяч после навеса."
        ])
        m["log"] += f"⏱ **{m['minute']}'** | {flavor}\n"

    if random.random() < 0.08:
        card_roll = random.random()
        if card_roll < 0.15:
            m["log"] += f"🟥 **{m['minute']}'** | ПРЯМАЯ КРАСНАЯ! Грубейший фол, ты удален с поля!\n"
            m["minute"] = 90
        else:
            m["log"] += f"🟨 **{m['minute']}'** | Судья показывает тебе желтую карточку за срыв атаки.\n"
            m["yellow_cards"] = m.get("yellow_cards", 0) + 1
            if m["yellow_cards"] >= 2:
                m["log"] += f"🟥 **{m['minute']}'** | ВТОРАЯ ЖЕЛТАЯ! ТЕБЯ УДАЛЯЮТ С ПОЛЯ!\n"
                m["minute"] = 90
 
    if m["current_moment"] > m["total_moments"] or m["minute"] == 90:
        is_knockout = False
        if m["is_cup"]:
            is_knockout = True
                
        if is_knockout and m["my_team_score"] == m["rival_team_score"]:
            await start_penalty_shootout(callback, state, user_id)
        else:
            await finish_match(callback, state, user_id)
        return
        
    text = (f"⏱ **{m['minute']}' МИНУТА** | Момент {m['current_moment']}/{m['total_moments']}\n"
            f"⚔️ **{p['club']}** vs **{m['rival']}**\n"
            f"Счет: **{m['my_team_score']} : {m['rival_team_score']}**\n\n"
            f"📝 **События матча:**\n{m['log'] or 'Идет плотная позиционная борьба...'}\n")
    
    m["log"] = "" 
    
    if p["position"] == "GK":
        text += "🚨 **Опасность! Нападающий соперника выходит один на один с тобой! Твои действия?**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧤 Прыгнуть в левый угол", callback_data="gk_act:left"), InlineKeyboardButton(text="🧤 Прыгнуть в правый угол", callback_data="gk_act:right")],
            [InlineKeyboardButton(text="🏃 Сблизить дистанцию", callback_data="gk_act:rush")]
        ])
    elif p["position"] == "CB":
        if random.random() < 0.75:
            text += "🛡️ **Форвард соперника идет на дриблинге прямо в твою зону!**"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🧲 Жесткий подкат", callback_data="cb_act:tackle_hard"), InlineKeyboardButton(text="🕴️ Встретить корпусом", callback_data="cb_act:tackle_smart")],
                [InlineKeyboardButton(text="📐 Отдать пас ближнему", callback_data="act:pass")]
            ])
        else:
            text += "🔥 **Ты подключился на угловой! Мяч летит к тебе!**"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Пробить головой", callback_data="act:shoot_menu"), InlineKeyboardButton(text="📐 Сбросить под удар партнеру", callback_data="act:pass")]
            ])
    else:
        text += "🔥 **Ты контролируешь мяч на подступах к штрафной! Твое решение?**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Пробить по воротам", callback_data="act:shoot_menu"), InlineKeyboardButton(text="📐 Отдать пас", callback_data="act:pass")]
        ])
        
    await state.update_data(match=m)
    
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
 
@dp.callback_query(F.data.startswith("gk_act:"))
@with_user_lock
async def gk_action_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data:
        return await callback.answer("⏳ Матч уже завершен!", show_alert=True)
    m = data["match"]
    action = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    
    rival_rating = CLUB_RATINGS.get(m["rival"], 50)
    save_chance = 0.30 + ((p["rating"] - rival_rating) * 0.015) + (p["rating"] * 0.004)
    save_chance = max(0.1, min(0.95, save_chance))
    
    opp_shoot_dir = random.choice(["left", "right", "center"])
    
    is_saved = False
    if action == "rush":
        if random.random() < (save_chance + 0.1): is_saved = True
    else:
        if action == opp_shoot_dir or random.random() < save_chance * 0.8: is_saved = True
        
    if is_saved:
        m["saves"] += 1
        m["log"] += f"🧤 **{m['minute']}'** | БЕЗУМНЫЙ СЕЙВ! Ты вытаскиваешь мертвейший мяч!\n"
    else:
        m["rival_team_score"] += 1
        m["log"] += f"⚡ **{m['minute']}'** | Гол... Оппонент технично переиграл тебя на противоходе.\n"
        
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)
 
@dp.callback_query(F.data.startswith("cb_act:"))
@with_user_lock
async def cb_action_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data:
        return await callback.answer("⏳ Матч уже завершен!", show_alert=True)
    m = data["match"]
    action = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    
    rival_rating = CLUB_RATINGS.get(m["rival"], 50)
    tackle_chance = 0.30 + ((p["rating"] - rival_rating) * 0.015) + (p["rating"] * 0.003)
    tackle_chance = max(0.1, min(0.90, tackle_chance))
    
    if action == "tackle_hard":
        if random.random() < 0.15:
            m["rival_team_score"] += 1
            m["log"] += f"⚡ **{m['minute']}'** | Фол в штрафной! Ты сфолил, соперник забивает пенальти.\n"
        elif random.random() < tackle_chance:
            m["tackles"] += 1
            m["log"] += f"🛡️ **{m['minute']}'** | Мощнейший чистый подкат! Форвард лежит, мяч отобран!\n"
        else:
            m["rival_team_score"] += 1
            m["log"] += f"⚡ **{m['minute']}'** | Ошибка! Нападающий пробросил мяч мимо тебя и забил.\n"
    else:
        if random.random() < tackle_chance:
            m["tackles"] += 1
            m["log"] += f"🛡️ **{m['minute']}'** | Отличный выбор позиции. Ты заблокировал продвижение соперника.\n"
        else:
            m["rival_team_score"] += 1
            m["log"] += f"⚡ **{m['minute']}'** | Тебя легко обыграли на замахе. Гол.\n"
            
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)
 
@dp.callback_query(F.data == "act:shoot_menu")
async def act_shoot_menu_handler(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 Левый верхний (Девятка)", callback_data="shoot_dir:в левую девятку"), InlineKeyboardButton(text="📐 Правый верхний (Девятка)", callback_data="shoot_dir:в правую девятку")],
        [InlineKeyboardButton(text="👇 Левый нижний", callback_data="shoot_dir:низом в левый угол"), InlineKeyboardButton(text="👇 Правый нижний", callback_data="shoot_dir:низом в правый угол")]
    ])
    await callback.message.edit_reply_markup(reply_markup=kb)
 
@dp.callback_query(F.data.startswith("shoot_dir:"))
@with_user_lock
async def act_shoot_execute_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data:
        return await callback.answer("⏳ Матч уже завершен!", show_alert=True)
    m = data["match"]
    target_dir = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    
    rival_rating = CLUB_RATINGS.get(m["rival"], 50)
    score_chance = 0.20 + ((p["rating"] - rival_rating) * 0.015)
    
    gk_dive = random.choice(["в левую девятку", "в правую девятку", "низом в левый угол", "низом в правый угол"])
    
    if gk_dive == target_dir:
        score_chance -= 0.25
        gk_guessed = True
    else:
        score_chance += 0.10
        gk_guessed = False
        
    score_chance = max(0.05, min(0.92, score_chance))
    
    if random.random() < score_chance:
        m["goals"] += 1; m["my_team_score"] += 1
        await callback.message.delete()
        tmp_msg = await callback.message.answer(text=f"⚽ **{m['minute']}'** | ГОЛ! Твой шикарный удар {target_dir} разрывает сетку ворот!", parse_mode="Markdown")
        await asyncio.sleep(2)
        await tmp_msg.delete()
        m["log"] += f"⚽ **{m['minute']}'** | ГОЛ! Твой шикарный удар!\n"
    else:
        if gk_guessed: m["log"] += f"❌ **{m['minute']}'** | Ты пробил {target_dir}, но голкипер парировал твой удар!\n"
        else: m["log"] += f"❌ **{m['minute']}'** | Целился {target_dir}, но мяч пролетел мимо (не хватило техники)!\n"
            
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)
 
@dp.callback_query(F.data == "act:pass")
@with_user_lock
async def act_pass_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data:
        return await callback.answer("⏳ Матч уже завершен!", show_alert=True)
    m = data["match"]
    user_id = await get_uid(callback)
    
    # Добавленная логика паса, чтобы скрипт был полноценным и рабочим
    if random.random() < 0.70:
        m["assists"] += 1
        m["log"] += f"✅ **{m['minute']}'** | Шикарный точный пас на партнера!\n"
    else:
        m["log"] += f"❌ **{m['minute']}'** | Пас оказался слишком сильным, перехват соперника.\n"
        
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)

# --- ЗАВЕРШЕНИЕ МАТЧА, СЕРИЯ ПЕНАЛЬТИ И ИТОГИ СЕЗОНА ---
async def _clear_match_state(state: FSMContext):
    data = await state.get_data()
    data.pop("match", None)
    await state.set_data(data)

async def start_penalty_shootout(callback: CallbackQuery, state: FSMContext, user_id: str):
    """Быстрая симуляция серии пенальти для кубковых матчей, закончившихся вничью."""
    data = await state.get_data()
    m = data.get("match")
    if not m:
        return await _clear_match_state(state)

    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        return await _clear_match_state(state)

    rival_rating = CLUB_RATINGS.get(m["rival"], 50)
    my_chance = 0.5 + ((p.get("rating", 40) - rival_rating) * 0.01)
    my_chance = max(0.25, min(0.75, my_chance))

    my_score, rival_score = 0, 0
    for _ in range(5):
        if random.random() < 0.75:
            my_score += 1
        if random.random() < 0.75:
            rival_score += 1
    while my_score == rival_score:
        if random.random() < my_chance:
            my_score += 1
        else:
            rival_score += 1

    won_shootout = my_score > rival_score
    m["log"] += f"\n🥅 **СЕРИЯ ПЕНАЛЬТИ:** {my_score} : {rival_score} — {'ТЫ ПРОШЕЛ ДАЛЬШЕ!' if won_shootout else 'вы вылетаете...'}\n"

    if won_shootout:
        m["my_team_score"] += 1
    else:
        m["rival_team_score"] += 1

    await state.update_data(match=m)
    await finish_match(callback, state, user_id, penalty_result=(my_score, rival_score, won_shootout))

async def finish_match(callback: CallbackQuery, state: FSMContext, user_id: str, penalty_result=None):
    data = await state.get_data()
    m = data.get("match")
    if not m:
        return await callback.message.answer(
            "⚠️ Данные матча были потеряны. Возвращаю в главное меню.",
            reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
        )

    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        await _clear_match_state(state)
        return

    if m["my_team_score"] > m["rival_team_score"]:
        outcome = "win"
        outcome_text = "🏆 **ПОБЕДА!**"
        p["trust"] = min(100, p.get("trust", 0) + 5)
    elif m["my_team_score"] == m["rival_team_score"]:
        outcome = "draw"
        outcome_text = "🤝 **НИЧЬЯ**"
        p["trust"] = min(100, p.get("trust", 0) + 1)
    else:
        outcome = "loss"
        outcome_text = "❌ **ПОРАЖЕНИЕ**"
        p["trust"] = max(0, p.get("trust", 0) - 4)

    # --- Начисление личной статистики ---
    p.setdefault("stats_season", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})
    p.setdefault("stats_total", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})
    for stat in ("goals", "assists", "saves", "tackles"):
        p["stats_season"][stat] = p["stats_season"].get(stat, 0) + m.get(stat, 0)
        p["stats_total"][stat] = p["stats_total"].get(stat, 0) + m.get(stat, 0)
    p["stats_total"]["games"] = p["stats_total"].get("games", 0) + 1

    # --- Изменение рейтинга по итогам матча (макс ±0.1 за матч) ---
    goals   = m.get("goals", 0)
    assists = m.get("assists", 0)
    saves   = m.get("saves", 0)
    tackles = m.get("tackles", 0)
    conceded = m.get("rival_team_score", 0)

    # Нормируем перформанс в диапазон -1..+1, затем масштабируем до ±0.1
    raw = (goals * 0.35 + assists * 0.25 + saves * 0.25 + tackles * 0.15
           - conceded * 0.10
           + (0.20 if outcome == "win" else (-0.15 if outcome == "loss" else 0.0)))
    raw = max(-1.0, min(1.0, raw))
    rating_delta = round(raw * 0.1, 2)          # масштаб: итог от -0.1 до +0.1
    p["rating"] = round(max(1.0, min(100.0, p.get("rating", 40.0) + rating_delta)), 2)

    # --- Доход: зарплата + спонсор ---
    money_gain = p.get("contract_salary", 1500)
    sponsor_income = 0
    sp_name = p.get("sponsor")
    if sp_name and sp_name in SPONSORS_DATA:
        sponsor_income = SPONSORS_DATA[sp_name]["income_per_match"]
        money_gain += sponsor_income
    p["money"] = p.get("money", 0) + money_gain
    p["train_done"] = False

    cup_summary = ""
    if m.get("is_cup"):
        p["cup_rivals"] = p.get("cup_rivals", []) + [m["rival"]]
        if outcome == "win":
            stages = CUP_STAGES
            current_stage = m.get("cup_stage") or p.get("cup_stage", "1/16")
            idx = stages.index(current_stage) if current_stage in stages else -1
            if idx == len(stages) - 1:
                p["trophies"] = p.get("trophies", []) + [f"🏆 Кубок сезона {p.get('season', 1)}"]
                p["money"] += 100000
                p["rating"] = max(1.0, min(100.0, round(p["rating"] + 2, 1)))
                p["cup_out"] = True
                cup_summary = "\n\n🏆 **ТЫ ВЫИГРАЛ НАЦИОНАЛЬНЫЙ КУБОК!!!** 🎉"
            else:
                p["cup_stage"] = stages[idx + 1]
                cup_summary = f"\n\n➡️ Ты прошел в стадию **{p['cup_stage']}** Кубка!"
        else:
            p["cup_out"] = True
            cup_summary = "\n\n🚫 Твоя команда вылетела из Кубка на этой стадии."
    else:
        p["tour"] = p.get("tour", 1) + 1
        p["played_league_rivals"] = p.get("played_league_rivals", []) + [m["rival"]]
        await simulate_table_tour(user_id, p["division"], p["club"], m["rival"], outcome)
        if p.get("on_loan") and p.get("parent_club"):
            parent_div = get_division(p["parent_club"])
            if parent_div != p["division"]:
                await simulate_background_division(user_id, parent_div)

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await _clear_match_state(state)

    penalty_line = ""
    if penalty_result:
        my_pen, rival_pen, _ = penalty_result
        penalty_line = f"🥅 Пенальти: {my_pen} : {rival_pen}\n"

    sponsor_line = (f"💼 Доход от {p.get('sponsor')}: +{sponsor_income}$\n"
                    if sponsor_income else "")
    text = (
        f"🏁 **МАТЧ ЗАВЕРШЕН!**\n"
        f"⚔️ **{p['club']} {m['my_team_score']} : {m['rival_team_score']} {m['rival']}**\n"
        f"{penalty_line}{outcome_text}\n\n"
        f"⚽ Голы: {m.get('goals', 0)} | 🅰️ Ассисты: {m.get('assists', 0)} | "
        f"🧤 Сейвы: {m.get('saves', 0)} | 🛡️ Отборы: {m.get('tackles', 0)}\n"
        f"💰 Зарплата: +{p.get('contract_salary', 1500)}$\n"
        f"{sponsor_line}"
        f"📈 Рейтинг: {p['rating']} ({'+' if rating_delta >= 0 else ''}{rating_delta})"
        f"{cup_summary}"
    )

    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        if callback.message.photo:
            await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)

def _pick_offers_by_rating(rating: float, current_club: str, current_division: str) -> list[dict]:
    """
    Подбирает 4 клуба из разных лиг, ориентируясь на рейтинг игрока.
    Возвращает список dict(club, division, salary).
    """
    # Определяем диапазон рейтингов команд, которые реально заинтересованы в игроке
    low  = max(0,   int(rating) - 15)
    high = min(100, int(rating) + 20)

    candidates = []
    for div, clubs in CLUBS.items():
        for club in clubs:
            cr = CLUB_RATINGS.get(club, 50)
            if low <= cr <= high and club != current_club:
                candidates.append({"club": club, "division": div, "club_rating": cr})

    # Если кандидатов мало — расширяем диапазон
    if len(candidates) < 4:
        candidates = [
            {"club": c, "division": d, "club_rating": CLUB_RATINGS.get(c, 50)}
            for d, clubs in CLUBS.items()
            for c in clubs
            if c != current_club
        ]

    # Перемешиваем, берём по одному клубу из разных лиг (не больше 4)
    random.shuffle(candidates)
    seen_divs: set = set()
    offers: list[dict] = []
    for cand in candidates:
        if cand["division"] not in seen_divs:
            seen_divs.add(cand["division"])
            salary = max(1500, int(cand["club_rating"] * 150 + rating * 50))
            cand["salary"] = salary
            offers.append(cand)
        if len(offers) == 4:
            break

    # Если уникальных лиг не хватило, добиваем без ограничения по дивизиону
    if len(offers) < 4:
        used = {o["club"] for o in offers}
        for cand in candidates:
            if cand["club"] not in used:
                salary = max(1500, int(cand["club_rating"] * 150 + rating * 50))
                cand["salary"] = salary
                offers.append(cand)
                used.add(cand["club"])
            if len(offers) == 4:
                break

    return offers


async def season_results_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    # --- Определяем место в таблице ---
    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        table = tables.get(user_id, {}).get(p["division"], [])
    table_sorted = sorted(table, key=lambda x: x["points"], reverse=True)
    total_clubs = max(len(table_sorted), 1)
    position = next((i + 1 for i, row in enumerate(table_sorted) if row["club"] == p["club"]), total_clubs)

    season_num = p.get("season", 1)

    # --- Результат сезона ---
    ladder = get_ladder(p["division"])
    idx_in_ladder = ladder.index(p["division"]) if p["division"] in ladder else 0

    promotion_div = None
    relegation_div = None
    trophy_added = False

    if position == 1:
        result_text = f"🥇 **ЧЕМПИОНСТВО!** 1 место из {total_clubs} в **{p['division']}**!"
        p["trophies"] = p.get("trophies", []) + [f"🥇 Чемпион «{p['division']}» (Сезон {season_num})"]
        trophy_added = True
        if idx_in_ladder < len(ladder) - 1:
            promotion_div = ladder[idx_in_ladder + 1]
            result_text += f"\n📈 Открылся доступ в **{promotion_div}**!"
    elif position <= 2 and idx_in_ladder < len(ladder) - 1:
        promotion_div = ladder[idx_in_ladder + 1]
        result_text = (f"🎉 **ВЫХОД В ВЫСШИЙ ДИВИЗИОН!** {position} место из {total_clubs}.\n"
                       f"Предложения из **{promotion_div}** уже ждут!")
        p["trophies"] = p.get("trophies", []) + [f"⬆️ Выход в «{promotion_div}» (Сезон {season_num})"]
        trophy_added = True
    elif position >= total_clubs - 1 and total_clubs > 2 and idx_in_ladder > 0:
        relegation_div = ladder[idx_in_ladder - 1]
        result_text = (f"📉 **ВЫЛЕТ!** {position} место из {total_clubs}.\n"
                       f"Придётся искать клуб в **{relegation_div}**.")
    else:
        result_text = f"📊 {position} место из {total_clubs} в **{p['division']}**."

    stats = p.get("stats_season", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})
    pos_code = p.get("position", "ST")
    if pos_code == "GK":
        stats_text = f"🎮 {stats.get('games',0)} матчей | 🧤 {stats.get('saves',0)} сейвов"
    elif pos_code == "CB":
        stats_text = f"🎮 {stats.get('games',0)} матчей | 🛡️ {stats.get('tackles',0)} отборов | ⚽ {stats.get('goals',0)} голов"
    else:
        stats_text = f"🎮 {stats.get('games',0)} матчей | ⚽ {stats.get('goals',0)} голов | 🅰️ {stats.get('assists',0)} ассистов"

    # --- Проверка завершения карьеры ---
    p["age"] = p.get("age", 17) + 1
    retired_now = False
    if p["age"] >= 36 and random.random() < 0.35:
        retired_now = True
        p["retired"] = True
        career_summary = (f"📌 {p['name']} | Рейтинг: {p['rating']} | "
                          f"Клуб: {p['club']} | Трофеев: {len(p.get('trophies', []))}")
        p["career_history"] = p.get("career_history", []) + [career_summary]
        await add_to_retired_leaderboard(p["name"], p["rating"], len(p.get("trophies", [])))

    if retired_now:
        # --- Завершение карьеры: сразу сбрасываем без выбора клуба ---
        _apply_new_season_reset(p)
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        text = (
            f"🏁 **ИТОГИ СЕЗОНА {season_num}**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{result_text}\n\n"
            f"📊 {stats_text}\n\n"
            f"🏁 **В {p['age']} лет ты завершаешь карьеру. Спасибо за игру!**"
        )
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=retired_keyboard())
        except Exception:
            if callback.message.photo: await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=retired_keyboard())
        return

    # --- Генерируем 4 предложения по рейтингу ---
    # Если повышение/понижение — обязательно включаем клубы из нужного дивизиона
    rating = p.get("rating", 40.0)
    offers = _pick_offers_by_rating(rating, p["club"], p["division"])

    # Если есть обязательный дивизион (повышение/вылет), заменяем первый оффер на клуб оттуда
    forced_div = promotion_div or relegation_div
    if forced_div:
        forced_club = random.choice([c for c in CLUBS.get(forced_div, []) if c != p["club"]] or CLUBS.get(forced_div, [p["club"]]))
        forced_salary = max(1500, int(CLUB_RATINGS.get(forced_club, 50) * 150 + rating * 50))
        forced_offer = {"club": forced_club, "division": forced_div,
                        "club_rating": CLUB_RATINGS.get(forced_club, 50), "salary": forced_salary}
        # Убираем из обычных офферов, если такой клуб/дивизион уже есть
        offers = [o for o in offers if o["division"] != forced_div][:3]
        offers.insert(0, forced_offer)

    # --- Сохраняем предложения во временное поле (будет применено при выборе) ---
    p["_season_offers"] = offers
    p["_season_num"]    = season_num
    p["_season_result_text"] = result_text
    p["_season_stats_text"]  = stats_text
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    # --- Строим клавиатуру: 4 предложения + продлить ---
    current_salary = p.get("contract_salary", 1500)
    renew_salary   = max(current_salary, int(current_salary * 1.15))  # +15% при продлении
    buttons = []
    for i, o in enumerate(offers):
        label = f"🏟 {o['club']} ({o['division']}) — {o['salary']}$/матч"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"season_choice:{i}")])
    buttons.append([InlineKeyboardButton(
        text=f"🔄 Продлить контракт с {p['club']} — {renew_salary}$/матч",
        callback_data="season_choice:renew"
    )])

    text = (
        f"🏁 **ИТОГИ СЕЗОНА {season_num}**\n━━━━━━━━━━━━━━━━━━━━\n"
        f"{result_text}\n\n"
        f"📊 {stats_text}\n\n"
        f"📋 **Выбери, где продолжить карьеру:**"
    )

    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await callback.message.edit_text(text, parse_mode="Markdown",
                                             reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        logging.warning(f"season_results_handler send error: {e}")
        await callback.message.answer(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


def _apply_new_season_reset(p: dict):
    """Сбрасывает данные игрока для нового сезона (кроме клуба/дивизиона — они уже выбраны)."""
    p["season"]   = p.get("_season_num", p.get("season", 1)) + 1
    p["tour"]     = 1
    p["stats_season"]          = {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0}
    p["played_league_rivals"]  = []
    p["cup_out"]   = False
    p["cup_stage"] = "1/16"
    p["cup_rivals"] = []
    p["train_done"] = False
    p["fatigue"]    = max(0, p.get("fatigue", 0) - 30)
    # Чистим временные поля
    for key in ("_season_offers", "_season_num", "_season_result_text", "_season_stats_text"):
        p.pop(key, None)


@dp.callback_query(F.data.startswith("season_choice:"))
@with_user_lock
async def season_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        return await callback.answer("⚠️ Профиль не найден. Нажми /start.", show_alert=True)

    offers = p.get("_season_offers", [])
    choice = callback.data.split(":")[1]
    season_num = p.get("_season_num", p.get("season", 1))

    if choice == "renew":
        # Продление контракта: клуб и дивизион не меняются, зарплата +15%
        old_salary = p.get("contract_salary", 1500)
        p["contract_salary"] = max(old_salary, int(old_salary * 1.15))
        club_line = f"🔄 Ты продлил контракт с **{p['club']}**!\n💰 Новая зарплата: **{p['contract_salary']}$/матч**"
    else:
        # Выбор нового клуба
        try:
            idx = int(choice)
        except ValueError:
            return await callback.answer("❌ Неверный выбор.", show_alert=True)
        if idx < 0 or idx >= len(offers):
            return await callback.answer("❌ Предложение недоступно.", show_alert=True)
        offer = offers[idx]
        p["club"]            = offer["club"]
        p["division"]        = offer["division"]
        p["contract_salary"] = offer["salary"]
        club_line = (f"✍️ Контракт подписан!\n"
                     f"🏟 Клуб: **{p['club']}** ({p['division']})\n"
                     f"💰 Зарплата: **{p['contract_salary']}$/матч**")

    # Применяем сброс сезона
    _apply_new_season_reset(p)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await init_tables_for_user(user_id, p["division"], p["club"])

    text = (
        f"🎉 **СЕЗОН {season_num} ЗАВЕРШЁН!**\n━━━━━━━━━━━━━━━━━━━━\n"
        f"{club_line}\n\n"
        f"➡️ Начинается **Сезон {p['season']}**!\n"
        f"Удачи!"
    )
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logging.warning(f"season_choice_handler edit error: {e}")
        if callback.message.photo: await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)

# --- ЗАПУСК БОТА ---
async def main():
    print("Бот запущен и ожидает сообщений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
