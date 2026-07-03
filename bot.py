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
BOT_TOKEN = "8494602735:AAGbzBwtrk1ZycDpubMjOVRhGQWKivQYzzU" # Замени на свой токен
 
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

# --- МИГРАЦИЯ ДАННЫХ (ЗАЩИТА ОТ КРАШЕЙ) ---
def migrate_player_data(p):
    if not p: return p
    rating = float(p.get("rating", 40))
    if "skills" not in p:
        p["skills"] = {"tech": rating, "phys": rating, "shoot": rating, "def": rating, "gk": rating}
    if "wc_stage" not in p: p["wc_stage"] = "Группа 1"
    if "contract_salary" not in p: p["contract_salary"] = 1500
    if "stats_season" not in p: p["stats_season"] = {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0}
    if "stats_total" not in p: p["stats_total"] = {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0}
    if "cup_out" not in p: p["cup_out"] = False
    return p

def retired_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Начать новую карьеру", callback_data="start_new_career")]])
 
async def deny_if_retired_cb(callback: CallbackQuery, p) -> bool:
    if not p:
        await callback.message.answer("⚠️ Профиль не найден. Нажми /start, чтобы начать.", parse_mode="Markdown")
        return True
    if p.get("retired"):
        try:
            await callback.message.edit_text("🏁 **Твоя карьера уже завершена!**", parse_mode="Markdown", reply_markup=retired_keyboard())
        except:
            await callback.message.answer("🏁 **Твоя карьера уже завершена!**", reply_markup=retired_keyboard())
        return True
    return False
 
async def deny_if_retired_msg(message: Message, p) -> bool:
    if not p:
        await message.answer("⚠️ Профиль не найден. Нажми /start, чтобы начать.", parse_mode="Markdown")
        return True
    if p.get("retired"):
        await message.answer("🏁 **Твоя карьера уже завершена!**\nНажми ниже, чтобы начать новую карьеру.", parse_mode="Markdown", reply_markup=retired_keyboard())
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

COPA_NATIONS = ["Аргентина", "Бразилия", "Мексика", "США", "Колумбия", "Уругвай"]
OTHER_NATIONS = ["Марокко", "Сенегал", "Нигерия", "Камерун", "Япония", "Южная Корея", "Австралия", "Иран", "Египет"]
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
 
def get_status_by_trust(trust):
    if 0 <= trust <= 20: return "Глубокий резерв ❌"
    elif 21 <= trust <= 50: return "Скамейка запасных 🪑"
    elif 51 <= trust <= 75: return "Джокер (Замена) ⏱️"
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
    
    leaderboard["top_careers"].append({"name": name, "rating": rating, "trophies": trophies_count})
    leaderboard["top_careers"] = sorted(leaderboard["top_careers"], key=lambda x: (x["rating"], x["trophies"]), reverse=True)[:10]
    await save_data(LEADERBOARD_FILE, leaderboard)

async def track_activity(user_id: str):
    players = await load_data(PLAYERS_FILE)
    if user_id in players:
        players[user_id] = migrate_player_data(players[user_id])
        players[user_id]["activity_ticks"] = players[user_id].get("activity_ticks", 0) + 1
        await save_data(PLAYERS_FILE, players)
 
def _init_tables_internal(tables, user_id, division, player_club=None):
    clubs_list = CLUBS[division].copy()
    if player_club and player_club not in clubs_list:
        clubs_list.append(player_club)
        
    # Защита от дублей в таблицах
    unique_clubs = {c: {"club": c, "points": 0, "wins": 0, "draws": 0, "losses": 0} for c in clubs_list}
    tables.setdefault(user_id, {})
    tables[user_id][division] = list(unique_clubs.values())

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
        
        # Доп проверка от вылетов после перехода
        if not any(row["club"] == player_club for row in table):
            table.append({"club": player_club, "points": 0, "wins": 0, "draws": 0, "losses": 0})

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
        p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
        if p and p.get("tour", 1) > 15:
            season = p.get("season", 1)
            # Евро(3,7,11) или ЧМ(4,8,12)
            if season in [3, 4, 7, 8, 11, 12] and p.get("rating", 40) >= 75 and p.get("wc_stage") not in ["Вылет", "Победитель"]:
                match_btn_text = "🌐 Сборная"
            else:
                match_btn_text = "🏁 Итоги сезона / Контракты"
                
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

    await callback.answer(f"🟢 Сейчас в боте: {online} чел.\n👥 Всего игроков: {total}", show_alert=True)
    
    try:
        await callback.message.edit_text(top_text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
    except:
        await callback.message.answer(top_text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
 
@dp.callback_query(F.data == "menu_support")
async def support_handler(callback: CallbackQuery):
    text = (
        "🛠 **СИСТЕМА ПОДДЕРЖКИ**\n\n"
        "Связь с разработчиком: **@narcisstichniy**\n\n"
        "❤️ **Поддержать разраба на развитие бота:**\n"
        "Реквизиты: `2200701958479393` т-банк"
    )
    try: await callback.message.edit_text(text, reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)), parse_mode="Markdown")
    except: await callback.message.answer(text, reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)), parse_mode="Markdown")

# --- ЛИЧНАЯ ЖИЗНЬ ---
@dp.callback_query(F.data == "menu_personal_life")
@with_user_lock
async def personal_life_menu(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
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

    try: await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="Markdown")
    except: await callback.message.answer(text=text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("personal:"))
@with_user_lock
async def personal_action(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
    if await deny_if_retired_cb(callback, p): return

    action = callback.data.split(":")[1]
    cost = 0; msg = ""

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
                msg = "💃 Ты познакомился с потрясающей девушкой!"
            else: msg = "❌ Не хватает денег на ухаживания."
        else:
            cost = 1000
            if p.get("money", 0) >= cost:
                p["mood"] = min(100, p.get("mood", 100) + 15)
                p["fatigue"] = max(0, p.get("fatigue", 0) - 20)
                msg = "🎁 Ты подарил девушке дорогие украшения! Усталость -20%."
            else: msg = "❌ Не хватает денег на подарок."
    elif action == "car":
        cost = 50000
        if p.get("money", 0) >= cost:
            p["cars"] = p.get("cars", 0) + 1
            p["mood"] = 100
            msg = "🚗 Ты купил роскошный спорткар!"
        else: msg = "❌ Не хватает денег."
    elif action == "house":
        cost = 250000
        if p.get("money", 0) >= cost:
            p["houses"] = p.get("houses", 0) + 1
            p["mood"] = 100
            msg = "🏠 Ты приобрел огромный особняк!"
        else: msg = "❌ Не хватает денег."

    if "❌" not in msg:
        p["money"] -= cost
        p["trust"] = min(100, p["trust"] + 2)

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await callback.answer(msg, show_alert=True)
    await personal_life_menu(callback)
 
# --- АДМИН-ПАНЕЛЬ ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("У вас нет доступа к этой панели.", show_alert=True)
    
    text = "👑 **Админ-панель**\n\nОтправьте мне **ID пользователя** для управления:"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]])
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
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
    p = migrate_player_data(players[target_id])
    val = calculate_player_value(p["rating"], p["division"])
    
    text = (
        f"👑 ПРОФИЛЬ ИГРОКА (ID: `{target_id}`)\n"
        f"🏃‍♂️ {p['name']} | 🌍 {p.get('nation', 'Россия')} | 🎂 {p.get('age', 17)} лет\n"
        f"⚡️ Рейтинг: {p['rating']}/100\n"
        f"🏢 Клуб: {p['club']} ({p['position']})\n"
        f"💵 Баланс: {p.get('money', 0)}$\n"
        f"🏟️ Сезон: {p['season']} | Тур: {p['tour']}/15"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Тур (+1)", callback_data=f"adm_tour:{target_id}"),
         InlineKeyboardButton(text="⏭ Сезон (+1)", callback_data=f"adm_season:{target_id}")],
        [InlineKeyboardButton(text="💰 Выдать деньги", callback_data=f"adm_money:{target_id}"),
         InlineKeyboardButton(text="⚡️ Выдать рейтинг", callback_data=f"adm_rating:{target_id}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])
    
    if isinstance(message_or_call, Message): await message_or_call.answer(text, reply_markup=kb)
    else: await message_or_call.message.edit_text(text, reply_markup=kb)
 
@dp.callback_query(F.data.startswith("adm_tour:"))
async def adm_skip_tour(callback: CallbackQuery):
    target_id = callback.data.split(":")[1]
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            players[target_id] = migrate_player_data(players[target_id])
            players[target_id]["tour"] += 1
            await save_data(PLAYERS_FILE, players)
            await show_admin_user_profile(callback, target_id)
 
@dp.callback_query(F.data.startswith("adm_season:"))
async def adm_skip_season(callback: CallbackQuery):
    target_id = callback.data.split(":")[1]
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            players[target_id] = migrate_player_data(players[target_id])
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
    try: rating = int(message.text.strip())
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
        players[user_id] = migrate_player_data(players[user_id])
        players[user_id]["username_tg"] = callback.from_user.username
        await save_data(PLAYERS_FILE, players)
        try: await callback.message.edit_text(f"👋 **С возвращением, {players[user_id]['name']}!** (Слот {slot})\nТвой ID: `{user_id}`", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")
        except: await callback.message.answer(f"👋 **С возвращением, {players[user_id]['name']}!** (Слот {slot})\nТвой ID: `{user_id}`", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")
    else:
        if user_id in players and players[user_id].get("retired", False):
            history = players[user_id].get("career_history", [])
            await state.update_data(career_history=history)
            text = f"⚽ **Твоя прошлая карьера (Слот {slot}) окончена. Начнем новую!**\nДля начала введи Имя и Фамилию:"
        else:
            text = f"⚽ **Создаем профиль в Слоте {slot}!**\nДля начала введи Имя и Фамилию:"
        
        try: await callback.message.edit_text(text, parse_mode="Markdown")
        except: await callback.message.answer(text, parse_mode="Markdown")
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
    try: await callback.message.edit_text("📋 **Выбери амплуа:**", reply_markup=kb, parse_mode="Markdown")
    except: await callback.message.answer("📋 **Выбери амплуа:**", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_position)
 
@dp.callback_query(PlayerCreation.waiting_for_position, F.data.startswith("pos:"))
async def process_position(callback: CallbackQuery, state: FSMContext):
    await state.update_data(position=callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Россия", callback_data="league:Россия"), InlineKeyboardButton(text="🇫🇷 Франция", callback_data="league:Франция")],
        [InlineKeyboardButton(text="🏴󠁧󠁢󠁥󠁮󠁧󠁿 Англия", callback_data="league:Англия"), InlineKeyboardButton(text="🇪🇸 Испания", callback_data="league:Испания")],
        [InlineKeyboardButton(text="🇮🇹 Италия", callback_data="league:Италия"), InlineKeyboardButton(text="🇩🇪 Германия", callback_data="league:Германия")]
    ])
    try: await callback.message.edit_text("🌍 **В какой стране начнешь карьеру?**", reply_markup=kb, parse_mode="Markdown")
    except: await callback.message.answer("🌍 **В какой стране начнешь карьеру?**", reply_markup=kb, parse_mode="Markdown")
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
    try: await callback.message.edit_text("🔢 **Введи желаемый номер (1 - 99):**", parse_mode="Markdown")
    except: await callback.message.answer("🔢 **Введи желаемый номер (1 - 99):**", parse_mode="Markdown")
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
        "rating": 40,
        "skills": {"tech": 40.0, "phys": 40.0, "shoot": 40.0, "def": 40.0, "gk": 40.0},
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
        "wc_stage": "Группа 1",
        "wc_rivals": [],
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
    text = f"✍️ **КОНТРАКТ ПОДПИСАН!** Добро пожаловать в {player_profile['club']}!\n💰 Твоя зарплата: {player_profile['contract_salary']}$ за матч."
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
 
@dp.callback_query(F.data == "start_new_career")
@with_user_lock
async def start_new_career_handler(callback: CallbackQuery, state: FSMContext):
    players = await load_data(PLAYERS_FILE)
    user_id = await get_uid(callback)
    if user_id in players:
        history = players[user_id].get("career_history", [])
        await state.update_data(career_history=history)
        
    text = "⚽ **Добро пожаловать обратно! Начнем заново!**\nДля начала введи Имя и Фамилию:"
    try: await callback.message.edit_text(text, parse_mode="Markdown")
    except: await callback.message.answer(text, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_name)
 
@dp.callback_query(F.data == "delete_career")
@with_user_lock
async def delete_career_handler(callback: CallbackQuery):
    players = await load_data(PLAYERS_FILE)
    user_id = await get_uid(callback)
    if user_id in players:
        del players[user_id]
        await save_data(PLAYERS_FILE, players)
    try: await callback.message.edit_text("🗑 **Карьера удалена!** Нажми /start, чтобы создать новую.", parse_mode="Markdown")
    except: await callback.message.answer("🗑 **Карьера удалена!** Нажми /start, чтобы создать новую.", parse_mode="Markdown")

# --- ТРЕНИРОВКИ ---
@dp.callback_query(F.data == "menu_train_choice")
@with_user_lock
async def train_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    if await deny_if_retired_cb(callback, p): return
        
    if p.get("injury_tours", 0) > 0:
        return await callback.answer(f"🚑 Вы травмированы! Осталось лечиться туров: {p['injury_tours']}.", show_alert=True)
        
    if p.get("train_done", False):
        return await callback.answer("🚫 Сыграй матч, чтобы открыть тренировку.", show_alert=True)
    
    if p.get("fatigue", 0) >= 90:
        return await callback.answer("🚫 Вы слишком устали! Сходите в ресторан или отдохните.", show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Техника", callback_data="train:tech"), InlineKeyboardButton(text="🏃 Физика", callback_data="train:phys")],
        [InlineKeyboardButton(text="🎯 Удар", callback_data="train:shoot"), InlineKeyboardButton(text="🛡️ Защита", callback_data="train:def")],
        [InlineKeyboardButton(text="🧤 Реакция", callback_data="train:gk"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    text = (
        f"🏋️‍♂️ **ТРЕНИРОВКА**\n"
        f"Твой статус в команде: {get_status_by_trust(p['trust'])}\n\n"
        f"📈 **Твои навыки (влияют на общий рейтинг):**\n"
        f"⚡ Техника: {p['skills']['tech']:.1f} | 🏃 Физика: {p['skills']['phys']:.1f}\n"
        f"🎯 Удар: {p['skills']['shoot']:.1f} | 🛡️ Защита: {p['skills']['def']:.1f}\n"
        f"🧤 Реакция: {p['skills']['gk']:.1f}\n\n"
        f"Выбери навык для тренировки:"
    )
        
    try: await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except: await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
 
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: CallbackQuery):
    try: await callback.message.edit_text("🏠 Главное меню.", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
    except: await callback.message.answer("🏠 Главное меню.", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
 
@dp.callback_query(F.data.startswith("train:"))
@with_user_lock
async def train_execute_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
    if await deny_if_retired_cb(callback, p): return
        
    if p.get("injury_tours", 0) > 0:
        return await callback.answer("🚑 Вы травмированы! Тренировка недоступна.", show_alert=True)
    
    stat_key = callback.data.split(":")[1]
    
    trust_gain = random.randint(6, 14)
    p["trust"] = min(100, p["trust"] + trust_gain)
    p["train_done"] = True
    p["fatigue"] = min(100, p.get("fatigue", 0) + 10)
    
    # Расчет прироста навыка
    stat_gain = round(random.uniform(0.1, 0.4), 1)
    if p["skills"][stat_key] >= 90: stat_gain = round(random.uniform(0.05, 0.15), 1)
    
    p["skills"][stat_key] += stat_gain
    
    # Пересчет общего рейтинга
    old_rating = p["rating"]
    avg_rating = sum(p["skills"].values()) / 5.0
    p["rating"] = min(100, int(avg_rating))
    rating_msg = f"\n⚡ **Твой общий рейтинг вырос до {p['rating']}!**" if p["rating"] > old_rating else ""
    
    if random.random() < 0.015:
        p["injury_tours"] = random.randint(1, 2)
        p["is_injured"] = True
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        msg = f"🚑 **ОЙ!** На тренировке ты потянул мышцу. Выбыл на {p['injury_tours']} тур(а)."
        try: return await callback.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))
        except: return await callback.message.answer(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))
 
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    
    stat_names = {"tech": "Техника", "phys": "Физика", "shoot": "Удар", "def": "Защита", "gk": "Реакция"}
    
    text = (f"💪 **Тренировка успешно завершена!**\n\n"
            f"📈 Навык ({stat_names[stat_key]}) увеличен: **+{stat_gain}**\n"
            f"🤝 Доверие тренера: **+{trust_gain}%** (Статус: {get_status_by_trust(p['trust'])})"
            f"{rating_msg}")
            
    try: await callback.message.edit_text(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))
    except: await callback.message.answer(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))
 
# --- ТАБЛИЦА И ПРОФИЛЬ ---
@dp.callback_query(F.data == "menu_table")
@with_user_lock
async def show_table_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    tables = await load_data(TABLES_FILE)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    if await deny_if_retired_cb(callback, p): return

    if user_id not in tables or p["division"] not in tables.get(user_id, {}): 
        await init_tables_for_user(user_id, p["division"], p["club"])
        tables = await load_data(TABLES_FILE)
        
    table_data = tables[user_id][p["division"]]
    
    text = f"📊 **ТАБЛИЦА: {p['division']}**\n🏆 *Победа — 3 очка, Ничья — 1 очко, Поражение — 0*\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, row in enumerate(table_data, 1):
        is_p = "👉 " if row["club"] == p["club"] else "• "
        text += f"{i}. {is_p}**{row['club']}** — {row['points']} очков ({row['wins']}В / {row['draws']}Н / {row['losses']}П)\n"
        
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
 
@dp.callback_query(F.data == "menu_profile")
@with_user_lock
async def profile_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    if not p:
        return await callback.message.answer("⚠️ Профиль не найден. Нажми /start, чтобы начать.", parse_mode="Markdown")
 
    if p.get("retired"):
        history_str = "\n\n".join(p.get("career_history", [])) or "—"
        text = (
            f"🏁 **КАРЬЕРА ЗАВЕРШЕНА**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🏃‍♂️ {p['name']} | 🌍 {p.get('nation', 'Россия')}\n\n"
            f"📚 **Завершенные карьеры (Статистика):**\n{history_str}\n\n"
            f"Нажми кнопку ниже, чтобы начать новую историю."
        )
        try: return await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=retired_keyboard())
        except: return await callback.message.answer(text, parse_mode="Markdown", reply_markup=retired_keyboard())
 
    val = calculate_player_value(p["rating"], p["division"])
    
    loan_status = f"\n⚠️ *В аренде из {p['parent_club']}* (Осталось: {p['loan_tours_left']} тур.)" if p.get("on_loan") else ""
    injury_status = f"\n🚑 *Травмирован!* (Лечиться еще: {p.get('injury_tours', 0)} тур.)" if p.get("injury_tours", 0) > 0 else ""
    
    if p["position"] == "GK": stats_text = f"🧤 Сейвы: {p['stats_season'].get('saves', 0)}"
    elif p["position"] == "CB": stats_text = f"🛡️ Отборы: {p['stats_season'].get('tackles', 0)} | ⚽ Голы: {p['stats_season'].get('goals', 0)}"
    else: stats_text = f"⚽ Голы: {p['stats_season'].get('goals', 0)} | 🅰️ Ассисты: {p['stats_season'].get('assists', 0)}"
    
    skills_text = f"⚡ Тех: {p['skills']['tech']:.1f} | 🏃 Физ: {p['skills']['phys']:.1f} | 🎯 Удар: {p['skills']['shoot']:.1f}\n🛡️ Защ: {p['skills']['def']:.1f} | 🧤 Реакция: {p['skills']['gk']:.1f}"
    
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
        f"⚡️ Общий рейтинг: {p['rating']}/100\n"
        f"🏢 Клуб: {p['club']} ({p['position']}){loan_status}{injury_status}\n"
        f"💵 Баланс: {p.get('money', 0)}$ | 🏷️ Стоимость: {val:,}$\n"
        f"🤝 Зарплата: {p.get('contract_salary', 1500)}$/матч\n"
        f"💎 Спонсор: {p.get('sponsor', 'Нет')}\n"
        f"📊 Статус: {get_status_by_trust(p['trust'])}\n"
        f"💖 Настроение: {p.get('mood', 100)}% | 🔋 Усталость: {p.get('fatigue', 0)}%\n"
        f"💍 Девушка: {p.get('girlfriend', 'Нет')}\n"
        f"🚗 Авто: {p.get('cars', 0)} | 🏠 Дома: {p.get('houses', 0)}\n"
        f"🏟️ Сезон: {season_display}/13 | Тур Лиги: {tour_display}/15\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 **Навыки:**\n{skills_text}\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **Текущая карьера (за сезон):**\n{stats_text}\n"
        f"📈 **Общая статистика (текущий игрок):**\nВсего игр: {p.get('stats_total', {}).get('games', 0)} | Голов: {p.get('stats_total', {}).get('goals', 0)} | Ассистов: {p.get('stats_total', {}).get('assists', 0)}"
        f"{history_str}"
    )
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: await callback.message.answer(text, reply_markup=kb)
 
@dp.callback_query(F.data == "menu_sponsors")
@with_user_lock
async def sponsors_menu(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    if await deny_if_retired_cb(callback, p): return
    if p["rating"] < 65:
        return await callback.answer("❌ Прокачай рейтинг до 65 для контрактов!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥤 «Литвин»", callback_data="sponsor:Литвин"), InlineKeyboardButton(text="💎 «Самосвет»", callback_data="sponsor:Самосвет")],
        [InlineKeyboardButton(text="🍺 «Жигули»", callback_data="sponsor:Жигули"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    try: await callback.message.edit_text("💰 **Рекламные контракты**", reply_markup=kb, parse_mode="Markdown")
    except: await callback.message.answer("💰 **Рекламные контракты**", reply_markup=kb, parse_mode="Markdown")
 
@dp.callback_query(F.data.startswith("sponsor:"))
@with_user_lock
async def sponsor_sign(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
    if await deny_if_retired_cb(callback, p): return
    sp = callback.data.split(":")[1]
    players[user_id]["sponsor"] = sp
    await save_data(PLAYERS_FILE, players)
    
    try: await callback.message.edit_text(f"🤝 **Контракт с {sp} подписан!**", parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    except: await callback.message.answer(f"🤝 **Контракт с {sp} подписан!**", parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
 
@dp.callback_query(F.data == "menu_donate")
@with_user_lock
async def donate_menu(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏘 Города", callback_data="don_dest:city"), InlineKeyboardButton(text="🧒 Детдомы", callback_data="don_dest:kids")],
        [InlineKeyboardButton(text="⚽ Академии", callback_data="don_dest:academy"), InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]
    ])
    try: await callback.message.edit_text("❤️ **Благотворительность**\nКуда направить средства?", reply_markup=kb, parse_mode="Markdown")
    except: await callback.message.answer("❤️ **Благотворительность**\nКуда направить средства?", reply_markup=kb, parse_mode="Markdown")
 
@dp.callback_query(F.data.startswith("don_dest:"))
async def donate_dest(callback: CallbackQuery, state: FSMContext):
    await state.update_data(dest=callback.data.split(":")[1])
    try: await callback.message.edit_text("💵 Введи сумму (в $):")
    except: await callback.message.answer("💵 Введи сумму (в $):")
    await state.set_state(Donation.waiting_for_amount)
 
@dp.message(Donation.waiting_for_amount)
@with_user_lock
async def process_donation(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Введите число.")
    amount = int(message.text)
    user_id = await get_uid(message)
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
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
    
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
 
# --- ОБРАБОТКА ВЫБОРА КЛУБА ПОСЛЕ СКАНДАЛА ИЛИ УХОДА ---
@dp.callback_query(F.data.startswith("scandal_club:"))
@with_user_lock
async def scandal_club_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
    if await deny_if_retired_cb(callback, p): return
    new_club = callback.data.split(":")[1]
    
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
    
    try: await callback.message.delete()
    except: pass
    await callback.message.answer(
        text=f"✍️ Ты успешно перешел в **{new_club}**!\n💵 Твоя новая зарплата: **{p['contract_salary']}$/матч**.\nПора доказывать фанатам свою преданность!",
        parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
    )
 
# --- МАТЧИ, МЕЖДУНАРОДНЫЕ КУБКИ И КОНТРАКТЫ ---
@dp.callback_query(F.data == "menu_match")
@with_user_lock
async def match_handler(callback: CallbackQuery, state: FSMContext):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
    if await deny_if_retired_cb(callback, p): return
    
    if p.get("fatigue", 0) >= 95:
        return await callback.answer("🚫 Ты смертельно устал! Сходи в ресторан или отдохни.", show_alert=True)
        
    # --- ОБРАБОТКА ТРАВМЫ ---
    if p.get("injury_tours", 0) > 0:
        p["injury_tours"] -= 1
        if p["injury_tours"] == 0: p["is_injured"] = False
        
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
        if p["injury_tours"] > 0: msg += f"Осталось лечиться туров: {p['injury_tours']}."
        else: msg += "✅ **Ты полностью восстановился и готов к следующему матчу!**"
            
        try: return await callback.message.edit_text(msg, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
        except: return await callback.message.answer(msg, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    
    # 1. МЕЖДУНАРОДНЫЕ ТУРНИРЫ (Перед началом нового сезона, если tour > 15)
    if p["tour"] > 15:
        season = p.get("season", 1)
        is_wc = season in [4, 8, 12]
        is_copa = season in [3, 7, 11]
        
        if (is_wc or is_copa) and p["rating"] >= 75:
            # Если еще не вылетел и не выиграл
            if p.get("wc_stage") not in ["Вылет", "Победитель"]:
                cup_name = "ЧЕМПИОНАТ МИРА" if is_wc else "ЕВРО" if p.get("nation") in EURO_NATIONS else "КОПА АМЕРИКА"
                return await process_international_cup(callback, state, p, user_id, players, cup_name)

        # 2. КОНЕЦ СЕЗОНА: ПРЕДЛОЖЕНИЯ (5 ячеек)
        all_clubs = []
        for l in CLUBS.values(): all_clubs.extend(l)
        
        # Подбираем предложения в диапазоне +/- 10 рейтинга из ЛЮБЫХ лиг
        possible_clubs = [c for c in all_clubs if abs(CLUB_RATINGS.get(c, 50) - p["rating"]) <= 10 and c != p["club"]]
        if len(possible_clubs) < 4: possible_clubs = random.sample(all_clubs, 4)
        offers = random.sample(possible_clubs, 4)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🤝 Продлить ({p['club']})", callback_data=f"transfer:{p['club']}")],
            [InlineKeyboardButton(text=f"✈️ {offers[0]}", callback_data=f"transfer:{offers[0]}")],
            [InlineKeyboardButton(text=f"✈️ {offers[1]}", callback_data=f"transfer:{offers[1]}")],
            [InlineKeyboardButton(text=f"✈️ {offers[2]}", callback_data=f"transfer:{offers[2]}")],
            [InlineKeyboardButton(text=f"✈️ {offers[3]}", callback_data=f"transfer:{offers[3]}")]
        ])
        
        try: await callback.message.edit_text("🏁 **СЕЗОН ЗАВЕРШЕН!**\nТебе поступили предложения. Выбери клуб для продолжения карьеры:", reply_markup=kb, parse_mode="Markdown")
        except: await callback.message.answer("🏁 **СЕЗОН ЗАВЕРШЕН!**\nТебе поступили предложения. Выбери клуб для продолжения карьеры:", reply_markup=kb)
        return

    # 3. КЛУБНЫЙ МАТЧ И ПРОВЕРКА ДОВЕРИЯ (РЕЗЕРВ/БАНКА)
    if p["trust"] <= 20:
        # Глубокий резерв - скипаем матч
        p["tour"] += 1
        p["train_done"] = False
        p["fatigue"] = max(0, p.get("fatigue", 0) - 10)
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        
        msg = "❌ **Матч пропущен!**\nТренер оставил тебя в глубоком резерве. Тренируйся, чтобы повысить доверие и пробиться в состав."
        try: return await callback.message.edit_text(msg, reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")
        except: return await callback.message.answer(msg, reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")

    event_str, p = check_random_events(p)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

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
        for l in country_leagues: rival_pool.extend(CLUBS[l])
            
        played_cup_rivals = p.get("cup_rivals", [])
        rival_pool = [c for c in rival_pool if c != p["club"] and c not in played_cup_rivals]
        
        if not rival_pool: rival_pool = ["Случайная команда"]
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
        "total_moments": random.randint(2, 4),
        "current_moment": 1,
        "minute": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0, "yellow_cards": 0,
        "my_team_score": 0, "rival_team_score": 0,
        "is_cup": is_cup_match, "cup_stage": cup_stg if is_cup_match else None,
        "is_national": False, "log": ""
    }
    
    # Банка (замена)
    if 21 <= p["trust"] <= 50:
        match_data["minute"] = random.randint(60, 75)
        match_data["total_moments"] = random.randint(1, 2)
        match_data["log"] += f"🔄 **{match_data['minute']}'** | Тренер выпускает тебя на замену!\n"

    await state.update_data(match=match_data)
    
    match_title = f"🏆 НАЦИОНАЛЬНЫЙ КУБОК ({cup_stg}) 🏆" if is_cup_match else f"🏟️ РЕГУЛЯРНЫЙ ЧЕМПИОНАТ ({p['division']})"
    intro_text = f"{event_str}\n\n" if event_str else ""
    
    try: await callback.message.delete()
    except: pass
    
    msg = await callback.message.answer(f"{intro_text}⚽ **{match_title}**\n⚔️ **{p['club']}** vs **{match_data['rival']}**\nСудья дает свисток!", parse_mode="Markdown")
    await asyncio.sleep(2)
    try: await msg.delete()
    except: pass
    await generate_moment(callback, state, user_id)

@dp.callback_query(F.data.startswith("transfer:"))
@with_user_lock
async def process_transfer(callback: CallbackQuery, state: FSMContext):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    
    new_club = callback.data.split(":")[1]
    is_extension = (new_club == p["club"])
    
    p["club"] = new_club
    p["division"] = get_division(new_club)
    p["trust"] = 50 if is_extension else 30
    p["contract_salary"] = int(calculate_player_value(p["rating"], p["division"]) * 0.005) # ЗП зависит от стоимости
    if p["contract_salary"] < 1500: p["contract_salary"] = 1500
    
    p["season"] += 1
    p["tour"] = 1
    p["age"] += 1
    p["wc_stage"] = "Группа 1"
    p["cup_out"] = False
    p["cup_stage"] = "1/16"
    p["stats_season"] = {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0}
    
    if p["season"] > 13:
        p["retired"] = True
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        msg = "🏁 **Карьера завершена!** Ты провел 13 сезонов."
        try: return await callback.message.edit_text(msg, reply_markup=retired_keyboard(), parse_mode="Markdown")
        except: return await callback.message.answer(msg, reply_markup=retired_keyboard(), parse_mode="Markdown")
        
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    
    msg = f"✍️ **КОНТРАКТ ПОДПИСАН!**\nКлуб: **{new_club}**.\nНачинается сезон {p['season']}! Твоя ЗП: {p['contract_salary']}$/матч."
    try: await callback.message.edit_text(msg, reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")
    except: await callback.message.answer(msg, reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")

# --- СИМУЛЯТОР СБОРНЫХ ---
async def process_international_cup(callback, state, p, user_id, players, cup_name):
    # Строгая турнирная сетка без зацикливаний
    stages = ["Группа 1", "Группа 2", "Группа 3", "1/8 Финала", "1/4 Финала", "Полуфинал", "Финал"]
    curr = p.get("wc_stage", "Группа 1")
    
    if curr in ["Вылет", "Победитель"]: 
        p["wc_stage"] = "Группа 1"
        return await match_handler(callback, state) 

    rival = random.choice([n for n in NATIONS if n != p.get("nation", "Россия")])
    match_data = {
        "rival": rival, "total_moments": random.randint(2, 4), "current_moment": 1,
        "minute": 0, "goals": 0, "assists": 0, "my_team_score": 0, "rival_team_score": 0, 
        "saves": 0, "tackles": 0, "yellow_cards": 0,
        "log": "", "is_int_cup": True, "stage": curr, "cup_name": cup_name
    }
    
    await state.update_data(match=match_data)
    text = f"🏆 **{cup_name}: {curr}**\n⚔️ **{p.get('nation', 'Россия')}** vs **{rival}**\nСудья дает свисток!"
    try: await callback.message.edit_text(text, parse_mode="Markdown")
    except: await callback.message.answer(text, parse_mode="Markdown")
    await asyncio.sleep(2)
    await generate_moment(callback, state, user_id)

async def generate_moment(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    if "match" not in data: return
    m = data["match"]
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
 
    m["minute"] += random.randint(15, 25)
    if m["minute"] > 90: m["minute"] = 90
    
    is_nat = m.get("is_int_cup", False)
    my_name = p.get("nation", "Россия") if is_nat else p["club"]
    
    my_rating = NATION_RATINGS.get(my_name, 75) if is_nat else CLUB_RATINGS.get(p["club"], 50)
    rival_rating = NATION_RATINGS.get(m["rival"], 75) if is_nat else CLUB_RATINGS.get(m["rival"], 50)
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
            "🔥 Красивый финт в центре поля обостряет игру.", "📐 Подача углового, но защита выносит мяч.", 
            "🟨 Судья показывает желтую карточку игроку соперника.", "⚔️ Жесткий стык, но судья не дает свисток."
        ])
        m["log"] += f"⏱ **{m['minute']}'** | {flavor}\n"
 
    if m["current_moment"] > m["total_moments"] or m["minute"] == 90:
        is_knockout = False
        if m.get("is_cup"): is_knockout = True
        if m.get("is_int_cup") and not m.get("stage", "").startswith("Группа"): is_knockout = True
                
        if is_knockout and m["my_team_score"] == m["rival_team_score"]: return await start_penalty_shootout(callback, state, user_id)
        else: return await finish_match(callback, state, user_id)
        
    text = (f"⏱ **{m['minute']}' МИНУТА** | Момент {m['current_moment']}/{m['total_moments']}\n"
            f"⚔️ **{my_name}** vs **{m['rival']}**\n"
            f"Счет: **{m['my_team_score']} : {m['rival_team_score']}**\n\n"
            f"📝 **События:**\n{m['log'] if m['log'] else 'Плотная позиционная борьба...\n'}\n")
    
    m["log"] = "" 
    
    if p["position"] == "GK":
        text += "🚨 **Опасность! Нападающий соперника выходит один на один с тобой! Твои действия?**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧤 Прыгнуть влево", callback_data="gk_act:left"), InlineKeyboardButton(text="🧤 Прыгнуть вправо", callback_data="gk_act:right")],
            [InlineKeyboardButton(text="🏃 Сблизить дистанцию", callback_data="gk_act:rush")]
        ])
    elif p["position"] == "CB":
        text += "🛡️ **Форвард соперника идет на дриблинге прямо в твою зону!**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧲 Жесткий подкат", callback_data="cb_act:tackle_hard"), InlineKeyboardButton(text="🕴️ Встретить корпусом", callback_data="cb_act:tackle_smart")],
            [InlineKeyboardButton(text="📐 Пас", callback_data="act:pass")]
        ])
    else:
        text += "🔥 **Ты контролируешь мяч в атаке! Твое решение?**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Пробить", callback_data="act:shoot_menu"), InlineKeyboardButton(text="📐 Отдать пас", callback_data="act:pass")]
        ])
        
    await state.update_data(match=m)
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
 
@dp.callback_query(F.data.startswith("gk_act:"))
@with_user_lock
async def gk_action_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data: return await callback.answer("⏳ Матч завершен!", show_alert=True)
    m = data["match"]
    action = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    
    rival_rating = NATION_RATINGS.get(m["rival"], 75) if m.get("is_int_cup") else CLUB_RATINGS.get(m["rival"], 50)
    save_chance = 0.35 + ((p["rating"] - rival_rating) * 0.015) + (p["rating"] * 0.004) # Чуть повысил шансы
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
        m["log"] += f"⚡ **{m['minute']}'** | Гол... Оппонент технично переиграл тебя.\n"
        
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)
 
@dp.callback_query(F.data.startswith("cb_act:"))
@with_user_lock
async def cb_action_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data: return await callback.answer("⏳ Матч завершен!", show_alert=True)
    m = data["match"]
    action = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    
    rival_rating = NATION_RATINGS.get(m["rival"], 75) if m.get("is_int_cup") else CLUB_RATINGS.get(m["rival"], 50)
    tackle_chance = 0.35 + ((p["rating"] - rival_rating) * 0.015) + (p["rating"] * 0.003)
    tackle_chance = max(0.1, min(0.90, tackle_chance))
    
    if action == "tackle_hard":
        if random.random() < 0.15:
            m["rival_team_score"] += 1
            m["log"] += f"⚡ **{m['minute']}'** | Фол в штрафной! Соперник забивает пенальти.\n"
        elif random.random() < tackle_chance:
            m["tackles"] += 1
            m["log"] += f"🛡️ **{m['minute']}'** | Чистый подкат! Мяч отобран!\n"
        else:
            m["rival_team_score"] += 1
            m["log"] += f"⚡ **{m['minute']}'** | Ошибка! Нападающий прошел и забил.\n"
    else:
        if random.random() < tackle_chance:
            m["tackles"] += 1
            m["log"] += f"🛡️ **{m['minute']}'** | Ты заблокировал продвижение соперника.\n"
        else:
            m["rival_team_score"] += 1
            m["log"] += f"⚡ **{m['minute']}'** | Тебя легко обыграли на замахе. Гол.\n"
            
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)
 
@dp.callback_query(F.data == "act:shoot_menu")
async def act_shoot_menu_handler(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 В девятку", callback_data="shoot_dir:в девятку"), InlineKeyboardButton(text="👇 Низом в угол", callback_data="shoot_dir:низом в угол")]
    ])
    try: await callback.message.edit_reply_markup(reply_markup=kb)
    except: pass
 
@dp.callback_query(F.data.startswith("shoot_dir:"))
@with_user_lock
async def act_shoot_execute_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data: return await callback.answer("⏳ Матч завершен!", show_alert=True)
    m = data["match"]
    target_dir = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    
    rival_rating = NATION_RATINGS.get(m["rival"], 75) if m.get("is_int_cup") else CLUB_RATINGS.get(m["rival"], 50)
    score_chance = 0.35 + ((p["rating"] - rival_rating) * 0.015) # БАФНУТО НА +15%
    score_chance = max(0.1, min(0.95, score_chance))
    
    if random.random() < score_chance:
        m["goals"] += 1; m["my_team_score"] += 1
        m["log"] += f"⚽ **{m['minute']}'** | ГОЛ! Твой шикарный удар {target_dir} разрывает сетку!\n"
    else:
        m["log"] += f"❌ **{m['minute']}'** | Ты пробил {target_dir}, но голкипер парировал твой удар!\n"
            
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)
 
@dp.callback_query(F.data == "act:pass")
@with_user_lock
async def act_pass_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data: return await callback.answer("⏳ Матч завершен!", show_alert=True)
    m = data["match"]
    user_id = await get_uid(callback)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    
    rival_rating = NATION_RATINGS.get(m["rival"], 75) if m.get("is_int_cup") else CLUB_RATINGS.get(m["rival"], 50)
    pass_chance = 0.40 + ((p["rating"] - rival_rating) * 0.01) + (p["rating"] * 0.003) # БАФНУТО НА +15%
    pass_chance = max(0.1, min(0.95, pass_chance))
    
    if random.random() < pass_chance:
        m["assists"] += 1; m["my_team_score"] += 1
        m["log"] += f"🅰️ **{m['minute']}'** | Роскошный проникающий пас! Партнер замыкает!\n"
    else:
        m["log"] += f"❌ **{m['minute']}'** | Твой пас оказался неточным или был перехвачен.\n"
        
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)

async def start_penalty_shootout(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    m = data["match"]
    m["my_pen_score"], m["rival_pen_score"], m["pen_round"] = 0, 0, 1
    await state.update_data(match=m)
    try: await callback.message.edit_text("⏱ **Ничья!**\n🏆 Начинается Серия Пенальти!", parse_mode="Markdown")
    except: await callback.message.answer("⏱ **Ничья!**\n🏆 Начинается Серия Пенальти!", parse_mode="Markdown")
    await asyncio.sleep(2)
    await next_penalty_kick(callback, state, user_id)
 
async def next_penalty_kick(callback: CallbackQuery, state: FSMContext, user_id: str):
    m = (await state.get_data())["match"]
    if m["pen_round"] > 5 and m["my_pen_score"] != m["rival_pen_score"]:
        status = "\n🎉 ПОБЕДА ПО ПЕНАЛЬТИ!" if m["my_pen_score"] > m["rival_pen_score"] else "\n❌ Поражение по пенальти."
        if m["my_pen_score"] > m["rival_pen_score"]: m["my_team_score"] += 1
        else: m["rival_team_score"] += 1
        return await finish_match(callback, state, user_id, cup_status=status)
 
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎯 Налево", callback_data="pen_dir:left"), InlineKeyboardButton(text="🎯 По центру", callback_data="pen_dir:center"), InlineKeyboardButton(text="🎯 Направо", callback_data="pen_dir:right")]])
    text = f"🥅 **ПЕНАЛЬТИ — Раунд {m['pen_round']}**\nСчет: **{m['my_pen_score']} : {m['rival_pen_score']}**\nБей/Тащи:"
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: await callback.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("pen_dir:"))
@with_user_lock
async def execute_penalty_kick(callback: CallbackQuery, state: FSMContext):
    m = (await state.get_data())["match"]
    choice = callback.data.split(":")[1]
    
    if choice != random.choice(["left", "center", "right"]):
        m["my_pen_score"] += 1; my_res = "✅ Ты забил пенальти!"
    else: my_res = "❌ Вратарь потащил!"
        
    if random.choice(["left", "center", "right"]) != random.choice(["left", "center", "right"]):
        m["rival_pen_score"] += 1; rival_res = "⚽ Соперник забил."
    else: rival_res = "🧤 ТЫ ОТРАЗИЛ УДАР!"
        
    m["pen_round"] += 1
    m["log"] = f"{my_res}\n{rival_res}"
    await state.update_data(match=m)
    
    try: await callback.message.edit_text(f"📊 **Итог:**\n{m['log']}")
    except: await callback.message.answer(f"📊 **Итог:**\n{m['log']}")
    await asyncio.sleep(2)
    await next_penalty_kick(callback, state, callback.from_user.id) # ID passthrough
 
async def finish_match(callback: CallbackQuery, state: FSMContext, user_id: str, cup_status: str = ""):
    data = await state.get_data()
    m = data.get("match")
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
    
    my_score = m.get("my_team_score", 0)
    rival_score = m.get("rival_team_score", 0)
    
    p["stats_season"]["goals"] += m.get("goals", 0)
    p["stats_season"]["assists"] += m.get("assists", 0)
    p["stats_season"]["saves"] += m.get("saves", 0)
    p["stats_season"]["tackles"] += m.get("tackles", 0)
    
    p["stats_total"]["games"] += 1
    p["stats_total"]["goals"] += m.get("goals", 0)
    p["stats_total"]["assists"] += m.get("assists", 0)
    p["stats_total"]["saves"] += m.get("saves", 0)
    p["stats_total"]["tackles"] += m.get("tackles", 0)
    
    outcome = "draw"
    if my_score > rival_score:
        outcome = "win"
        p["trust"] = min(100, p["trust"] + random.randint(5, 10))
        p["mood"] = min(100, p.get("mood", 100) + 10)
    elif my_score < rival_score:
        outcome = "loss"
        p["trust"] = max(0, p["trust"] - random.randint(5, 15))
        p["mood"] = max(0, p.get("mood", 100) - 10)
    else:
        p["trust"] = min(100, p["trust"] + random.randint(1, 5))

    status = cup_status
    
    # Сетка Сборных
    if m.get("is_int_cup"):
        stages = ["Группа 1", "Группа 2", "Группа 3", "1/8 Финала", "1/4 Финала", "Полуфинал", "Финал"]
        idx = stages.index(m["stage"]) if m["stage"] in stages else 0
        
        if "Группа" in m["stage"]:
            if idx + 1 < len(stages):
                p["wc_stage"] = stages[idx + 1]
                status += f"\n🌐 **{m['cup_name']}:** Переход в {p['wc_stage']}"
        else:
            if outcome == "loss": 
                p["wc_stage"] = "Вылет"
                status += f"\n🌐 **{m['cup_name']}:** Вы вылетели с турнира."
            else:
                if m["stage"] == "Финал":
                    p["wc_stage"] = "Победитель"
                    status += f"\n🏆 **{m['cup_name']}:** ТЫ ВЫИГРАЛ ТУРНИР!"
                else:
                    if idx + 1 < len(stages):
                        p["wc_stage"] = stages[idx + 1]
                        status += f"\n🌐 **{m['cup_name']}:** Проход в {p['wc_stage']}"
        p["train_done"] = False
    else:
        # Логика кубков клуба
        if m.get("is_cup"):
            if outcome == "loss":
                p["cup_out"] = True
            else:
                stages = CUP_STAGES
                curr_idx = stages.index(p["cup_stage"]) if p["cup_stage"] in stages else 0
                if curr_idx < len(stages) - 1:
                    p["cup_stage"] = stages[curr_idx + 1]
                else:
                    if "trophies" not in p: p["trophies"] = []
                    p["trophies"].append("Национальный Кубок")
                    p["cup_out"] = True
                    status += "\n🏆 ВЫ ВЫИГРАЛИ НАЦИОНАЛЬНЫЙ КУБОК!"
                    p["trust"] = 100
                    
        p["money"] += p.get("contract_salary", 1500)
        p["tour"] += 1
        p["train_done"] = False
        await simulate_table_tour(user_id, p["division"], p["club"], m["rival"], outcome)
    
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    
    text = (f"🏁 **МАТЧ ЗАВЕРШЕН**\n"
            f"Счет: **{my_score} : {rival_score}**{status}\n\n"
            f"📊 Твоя статистика:\n"
            f"⚽ Голы: {m.get('goals', 0)} | 🅰️ Ассисты: {m.get('assists', 0)}\n"
            f"🧤 Сейвы: {m.get('saves', 0)} | 🛡️ Отборы: {m.get('tackles', 0)}\n\n"
            f"📈 Тренерское доверие: {get_status_by_trust(p['trust'])}")
            
    await state.clear()
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def main():
    print("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): print("Бот остановлен.")
