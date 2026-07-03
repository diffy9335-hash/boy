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
            logging.error(f"Файл {filename} был поврежден ({e}) и переименован. Создан новый.")
            return {}
    return {}
 
def _save_data_sync(filename, data):
    tmp_path = f"{filename}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_path, filename)
 
_cache_locks = {}
def get_cache_lock(filename):
    if filename not in _cache_locks: _cache_locks[filename] = asyncio.Lock()
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
    if user_id not in _user_locks: _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

def get_table_lock() -> asyncio.Lock:
    global _table_lock
    if _table_lock is None: _table_lock = asyncio.Lock()
    return _table_lock
 
def with_user_lock(func):
    @functools.wraps(func)
    async def wrapper(event, *args, **kwargs):
        user_id = await get_uid(event)
        lock = get_user_lock(user_id)
        async with lock:
            return await func(event, *args, **kwargs)
    return wrapper

# --- МИГРАЦИЯ ДАННЫХ (Защита от крашей старых карьер) ---
def migrate_player_data(p):
    if not p: return p
    rating = float(p.get("rating", 40))
    if "skills" not in p:
        p["skills"] = {"tech": rating, "phys": rating, "shoot": rating, "def": rating, "gk": rating}
    if "wc_stage" not in p: p["wc_stage"] = "Группа 1"
    if "contract_salary" not in p: p["contract_salary"] = 1500
    if "stats_season" not in p: p["stats_season"] = {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0}
    if "stats_total" not in p: p["stats_total"] = {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0}
    return p

def retired_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Начать новую карьеру", callback_data="start_new_career")]])
 
async def deny_if_retired_cb(callback: CallbackQuery, p) -> bool:
    if not p:
        await callback.message.answer("⚠️ Профиль не найден. Нажми /start, чтобы начать.", parse_mode="Markdown")
        return True
    if p.get("retired"):
        try: await callback.message.edit_text("🏁 **Твоя карьера уже завершена!**", parse_mode="Markdown", reply_markup=retired_keyboard())
        except: await callback.message.answer("🏁 **Твоя карьера уже завершена!**", reply_markup=retired_keyboard())
        return True
    return False

# --- СОСТОЯНИЯ FSM ---
class PlayerCreation(StatesGroup):
    waiting_for_name, waiting_for_nation, waiting_for_position = State(), State(), State()
    waiting_for_country_league, waiting_for_number, waiting_for_club = State(), State(), State()
 
class AdminPanel(StatesGroup):
    waiting_for_user_id, waiting_for_money, waiting_for_rating = State(), State(), State()
 
class Donation(StatesGroup):
    waiting_for_dest, waiting_for_amount = State(), State()

# --- СПРАВОЧНИКИ ---
EURO_NATIONS = ["Россия", "Франция", "Италия", "Испания", "Германия", "Англия", "Португалия", "Нидерланды", "Бельгия", "Украина", "Хорватия", "Дания", "Швейцария", "Польша", "Швеция", "Норвегия", "Сербия", "Турция"]
COPA_NATIONS = ["Аргентина", "Бразилия", "Мексика", "США", "Колумбия", "Уругвай"]
OTHER_NATIONS = ["Марокко", "Сенегал", "Нигерия", "Камерун", "Япония", "Южная Корея", "Австралия", "Иран", "Египет"]
NATIONS = EURO_NATIONS + COPA_NATIONS + OTHER_NATIONS

NATION_RATINGS = {
    "Аргентина": 89, "Франция": 89, "Бразилия": 88, "Англия": 88, "Испания": 87, "Португалия": 87, "Италия": 86, "Германия": 86,
    "Нидерланды": 84, "Бельгия": 83, "Хорватия": 82, "Уругвай": 81, "Колумбия": 80, "Дания": 79, "Швейцария": 79, "Марокко": 78,
    "Сенегал": 78, "Мексика": 77, "Сербия": 77, "Норвегия": 77, "США": 76, "Турция": 76, "Украина": 76, "Польша": 76,
    "Япония": 76, "Швеция": 75, "Россия": 74, "Южная Корея": 75, "Нигерия": 75, "Камерун": 74, "Иран": 74, "Египет": 74, "Австралия": 73
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
POSITIONS = {"⚽ Нападающий": "ST", "🪄 Полузащитник": "CM", "🛡️ Защитник": "CB", "🧤 Вратарь": "GK"}
 
def get_division(club_name):
    for div, clubs in CLUBS.items():
        if club_name in clubs: return div
    return "ФНЛ 2"
 
def get_status_by_trust(trust):
    if trust <= 20: return "Глубокий резерв ❌"
    elif trust <= 50: return "Скамейка запасных 🪑"
    elif trust <= 75: return "Джокер (Выход на замену) ⏱️"
    return "Игрок старта 🔥"
 
def calculate_player_value(rating, division):
    mult = {
        "ФНЛ 2": 12500, "Насьональ": 12500, "Первая лига Англии": 15000,
        "Сегунда": 35000, "Серия Б": 35000, "Вторая Бундеслига": 40000,
        "ФНЛ": 45000, "Лига 2": 45000, "Чемпионшип": 55000,
        "РПЛ": 250000, "Лига 1": 250000, "АПЛ": 350000, "Ла Лига": 350000, "Серия А": 300000, "Бундеслига": 320000
    }
    return int(rating * mult.get(division, 15000) * (1 + (rating - 40) / 30))
 
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
        
    tables.setdefault(user_id, {})
    # Защита от дубликатов (Сеты)
    unique_clubs = list(set(clubs_list))
    tables[user_id][division] = [{"club": c, "points": 0, "wins": 0, "draws": 0, "losses": 0} for c in unique_clubs]

async def simulate_table_tour(user_id, division, player_club, player_match_rival, player_match_outcome):
    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        if user_id not in tables or division not in tables.get(user_id, {}):
            _init_tables_internal(tables, user_id, division, player_club)
            
        table = tables[user_id][division]
        
        # Проверяем, есть ли наш клуб в таблице после трансфера
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
     
        tables[user_id][division] = sorted(table, key=lambda x: x["points"], reverse=True)
        await save_data(TABLES_FILE, tables)

async def add_to_retired_leaderboard(name, rating, trophies_count):
    leaderboard = await load_data(LEADERBOARD_FILE)
    if "top_careers" not in leaderboard: leaderboard["top_careers"] = []
    leaderboard["top_careers"].append({"name": name, "rating": rating, "trophies": trophies_count})
    leaderboard["top_careers"] = sorted(leaderboard["top_careers"], key=lambda x: (x["rating"], x["trophies"]), reverse=True)[:10]
    await save_data(LEADERBOARD_FILE, leaderboard)

# --- ГЛАВНОЕ МЕНЮ ---
async def main_menu_keyboard(username: str = None, user_id: str = None):
    match_btn_text = "🎮 Матч"
    if user_id:
        p = (await load_data(PLAYERS_FILE)).get(user_id)
        if p and p.get("tour", 1) > 15:
            # ЧМ / ЕВРО проверка перед контрактами
            if p.get("season") in [3, 4, 7, 8, 11, 12] and p.get("rating", 40) >= 75 and p.get("wc_stage") not in ["Вылет", "Победитель"]:
                match_btn_text = "🌐 Сборная"
            else:
                match_btn_text = "🏁 Итоги сезона / Контракты"
                
    kb = [
        [InlineKeyboardButton(text="🏋️‍♂️ Тренировка", callback_data="menu_train_choice"), InlineKeyboardButton(text=match_btn_text, callback_data="menu_match")],
        [InlineKeyboardButton(text="📊 Таблица", callback_data="menu_table"), InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")],
        [InlineKeyboardButton(text="🍷 Личная жизнь", callback_data="menu_personal_life"), InlineKeyboardButton(text="🏆 Зал Славы", callback_data="menu_leaderboard")],
        [InlineKeyboardButton(text="💰 Спонсоры", callback_data="menu_sponsors"), InlineKeyboardButton(text="🟢 Онлайн / Топ", callback_data="menu_online")]
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
    top_text = "\n\n🔥 **Топ игроков по активности:**\n"
    for i, p in enumerate(top_active, 1): top_text += f"{i}. {p['name']} ({p.get('activity_ticks', 0)} очков)\n"

    try: await callback.message.edit_text(f"🟢 Сейчас в боте: {online} чел.\n👥 Всего в базе: {total}{top_text}", parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))
    except: await callback.message.answer(f"🟢 Сейчас в боте: {online} чел.\n👥 Всего в базе: {total}{top_text}", parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, await get_uid(callback)))

# --- ЛИЧНАЯ ЖИЗНЬ ---
@dp.callback_query(F.data == "menu_personal_life")
@with_user_lock
async def personal_life_menu(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    if await deny_if_retired_cb(callback, p): return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 Ресторан (-500$)", callback_data="personal:rest")],
        [InlineKeyboardButton(text="💃 Найти девушку (-2000$)" if p.get("girlfriend", "Нет") == "Нет" else "🎁 Подарок девушке (-1000$)", callback_data="personal:girl")],
        [InlineKeyboardButton(text="🚗 Купить авто (-50,000$)", callback_data="personal:car"), InlineKeyboardButton(text="🏠 Купить дом (-250,000$)", callback_data="personal:house")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    text = f"🍷 **ЛИЧНАЯ ЖИЗНЬ**\n💵 Баланс: {p.get('money', 0)}$\n💖 Настроение: {p.get('mood', 100)}%\n🔋 Усталость: {p.get('fatigue', 0)}%\n"
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
    cost, msg = 0, ""

    if action == "rest":
        cost = 500
        if p.get("money", 0) >= cost:
            p["mood"] = min(100, p.get("mood", 100) + 10); p["fatigue"] = max(0, p.get("fatigue", 0) - 15)
            msg = "🍽 Усталость -15%."
        else: msg = "❌ Нет денег."
    elif action == "girl":
        cost = 2000 if p.get("girlfriend", "Нет") == "Нет" else 1000
        if p.get("money", 0) >= cost:
            p["girlfriend"] = "Есть"; p["mood"] = min(100, p.get("mood", 100) + 30); p["fatigue"] = max(0, p.get("fatigue", 0) - 20)
            msg = "💖 Настроение повышено!"
        else: msg = "❌ Нет денег."
    elif action == "car":
        cost = 50000
        if p.get("money", 0) >= cost: p["cars"] = p.get("cars", 0) + 1; p["mood"] = 100; msg = "🚗 Ты купил спорткар!"
        else: msg = "❌ Нет денег."
    elif action == "house":
        cost = 250000
        if p.get("money", 0) >= cost: p["houses"] = p.get("houses", 0) + 1; p["mood"] = 100; msg = "🏠 Куплен особняк!"
        else: msg = "❌ Нет денег."

    if "❌" not in msg:
        p["money"] -= cost
        p["trust"] = min(100, p["trust"] + 2)

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await callback.answer(msg, show_alert=True)
    await personal_life_menu(callback)

# --- СТАРТ И СОЗДАНИЕ ---
@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"), InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]])
    await message.answer("⚽ **Добро пожаловать в симулятор футболиста!**\nВыбери слот:", reply_markup=kb, parse_mode="Markdown")

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
        try: await callback.message.edit_text(f"👋 С возвращением, {players[user_id]['name']}!", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
        except: await callback.message.answer(f"👋 С возвращением, {players[user_id]['name']}!", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    else:
        try: await callback.message.edit_text("⚽ **Создаем профиль!**\nВведи Имя и Фамилию:")
        except: await callback.message.answer("⚽ **Создаем профиль!**\nВведи Имя и Фамилию:")
        await state.set_state(PlayerCreation.waiting_for_name)

@dp.message(PlayerCreation.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=NATIONS[i], callback_data=f"nat:{NATIONS[i]}"), InlineKeyboardButton(text=NATIONS[i+1] if i + 1 < len(NATIONS) else NATIONS[i], callback_data=f"nat:{NATIONS[i+1] if i + 1 < len(NATIONS) else NATIONS[i]}")] for i in range(0, 12, 2)])
    await message.answer("🌍 **Выбери национальность:**", reply_markup=kb, parse_mode="Markdown")
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
        [InlineKeyboardButton(text="🏴󠁧󠁢󠁥󠁮󠁧󠁿 Англия", callback_data="league:Англия"), InlineKeyboardButton(text="🇪🇸 Испания", callback_data="league:Испания")]
    ])
    try: await callback.message.edit_text("🌍 **Где начнешь карьеру?**", reply_markup=kb, parse_mode="Markdown")
    except: await callback.message.answer("🌍 **Где начнешь карьеру?**", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_country_league)
 
@dp.callback_query(PlayerCreation.waiting_for_country_league, F.data.startswith("league:"))
async def process_country_league(callback: CallbackQuery, state: FSMContext):
    lc = callback.data.split(":")[1]
    divs = {"Россия": "ФНЛ 2", "Франция": "Насьональ", "Англия": "Первая лига Англии", "Испания": "Сегунда"}
    await state.update_data(start_division=divs.get(lc, "ФНЛ 2"))
    user_data = await state.get_data()
    available_clubs = random.sample(CLUBS[user_data["start_division"]], 3)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🏢 {c}", callback_data=f"club:{c}")] for c in available_clubs])
    try: await callback.message.edit_text(f"📉 Клубы, которые предлагают контракт:", reply_markup=kb, parse_mode="Markdown")
    except: await callback.message.answer(f"📉 Клубы, которые предлагают контракт:", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_club)
 
@dp.callback_query(PlayerCreation.waiting_for_club, F.data.startswith("club:"))
@with_user_lock
async def process_club(callback: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    user_id = await get_uid(callback)
    chosen_club = callback.data.split(":")[1]
    
    player_profile = {
        "name": user_data["name"], "nation": user_data.get("nation", "Россия"),
        "position": user_data["position"], "club": chosen_club,
        "division": get_division(chosen_club), "rating": 40, "trust": 15,
        "mood": 100, "fatigue": 0, "girlfriend": "Нет", "age": 17, "season": 1, "tour": 1,
        "money": 5000, "contract_salary": 1500, "stats_season": {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0},
        "stats_total": {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0},
        "skills": {"tech": 40.0, "phys": 40.0, "shoot": 40.0, "def": 40.0, "gk": 40.0},
        "train_done": False, "is_injured": False, "injury_tours": 0,
        "username_tg": callback.from_user.username, "retired": False, "activity_ticks": 0,
        "wc_stage": "Группа 1"
    }
    
    players = await load_data(PLAYERS_FILE)
    players[user_id] = player_profile
    await save_data(PLAYERS_FILE, players)
    
    tables = await load_data(TABLES_FILE)
    _init_tables_internal(tables, user_id, player_profile["division"], player_profile["club"])
    await save_data(TABLES_FILE, tables)
    
    await state.clear()
    try: await callback.message.edit_text(f"✍️ **КОНТРАКТ ПОДПИСАН!** Добро пожаловать в {player_profile['club']}!", parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    except: await callback.message.answer(f"✍️ **КОНТРАКТ ПОДПИСАН!** Добро пожаловать в {player_profile['club']}!", parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))

@dp.callback_query(F.data == "start_new_career")
@with_user_lock
async def start_new_career_handler(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.edit_text("⚽ **Новая история!** Введи Имя и Фамилию:")
    except: await callback.message.answer("⚽ **Новая история!** Введи Имя и Фамилию:")
    await state.set_state(PlayerCreation.waiting_for_name)

# --- ТРЕНИРОВКИ ---
@dp.callback_query(F.data == "menu_train_choice")
@with_user_lock
async def train_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    if await deny_if_retired_cb(callback, p): return
        
    if p.get("injury_tours", 0) > 0: return await callback.answer(f"🚑 Травма! Лечиться еще {p['injury_tours']} тур.", show_alert=True)
    if p.get("train_done", False): return await callback.answer("🚫 Сыграй матч, чтобы открыть тренировку.", show_alert=True)
    if p.get("fatigue", 0) >= 90: return await callback.answer("🚫 Ты слишком устал!", show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Техника", callback_data="train:tech"), InlineKeyboardButton(text="🏃 Физика", callback_data="train:phys")],
        [InlineKeyboardButton(text="🎯 Удар", callback_data="train:shoot"), InlineKeyboardButton(text="🛡️ Защита", callback_data="train:def")],
        [InlineKeyboardButton(text="🧤 Реакция", callback_data="train:gk"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    text = (f"🏋️‍♂️ **ТРЕНИРОВКА**\nТвой статус в команде: {get_status_by_trust(p['trust'])}\n\n"
            f"📈 **Текущие навыки:**\n"
            f"⚡ Техника: {p['skills']['tech']:.1f} | 🏃 Физика: {p['skills']['phys']:.1f}\n"
            f"🎯 Удар: {p['skills']['shoot']:.1f} | 🛡️ Защита: {p['skills']['def']:.1f}\n"
            f"🧤 Вратарь: {p['skills']['gk']:.1f}\n\n"
            "Выбери, что качать:")
            
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
    
    stat_key = callback.data.split(":")[1]
    
    trust_gain = random.randint(6, 14)
    p["trust"] = min(100, p["trust"] + trust_gain)
    p["train_done"] = True
    p["fatigue"] = min(100, p.get("fatigue", 0) + 10)
    
    # Система Саб-статов (прирост зависит от текущего скилла)
    stat_gain = round(random.uniform(0.1, 0.4), 1)
    if p["skills"][stat_key] >= 90: stat_gain = round(random.uniform(0.05, 0.15), 1)
    
    p["skills"][stat_key] += stat_gain
    
    # Пересчет общего рейтинга (среднее значение всех 5 навыков)
    old_rating = p["rating"]
    avg_rating = sum(p["skills"].values()) / 5.0
    p["rating"] = min(100, int(avg_rating))
    
    rating_msg = f"\n⚡ **ОБЩИЙ РЕЙТИНГ ПОВЫШЕН ДО {p['rating']}!**" if p["rating"] > old_rating else ""
    
    if random.random() < 0.015:
        p["injury_tours"] = random.randint(1, 2)
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        msg = f"🚑 **ОЙ!** На тренировке ты потянул мышцу. Выбыл на {p['injury_tours']} тур(а)."
        try: return await callback.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))
        except: return await callback.message.answer(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    
    text = (f"💪 **Тренировка успешно завершена!**\n\n"
            f"📈 Навык увеличен: **+{stat_gain}**\n"
            f"🤝 Доверие тренера: **+{trust_gain}%** (Статус: {get_status_by_trust(p['trust'])})"
            f"{rating_msg}")
            
    try: await callback.message.edit_text(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))
    except: await callback.message.answer(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]]))

# --- ПРОФИЛЬ И ТАБЛИЦА ---
@dp.callback_query(F.data == "menu_table")
@with_user_lock
async def show_table_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    tables = await load_data(TABLES_FILE)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    
    if user_id not in tables or p["division"] not in tables.get(user_id, {}):
        _init_tables_internal(tables, user_id, p["division"], p["club"])
        await save_data(TABLES_FILE, tables)
        
    table_data = tables[user_id][p["division"]]
    text = f"📊 **ТАБЛИЦА: {p['division']}**\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, row in enumerate(table_data, 1):
        is_p = "👉 " if row["club"] == p["club"] else "• "
        text += f"{i}. {is_p}**{row['club']}** — {row['points']} очков\n"
        
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
 
@dp.callback_query(F.data == "menu_profile")
@with_user_lock
async def profile_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    if await deny_if_retired_cb(callback, p): return
 
    val = calculate_player_value(p["rating"], p["division"])
    
    if p["position"] == "GK": stats_text = f"🧤 Сейвы: {p['stats_season'].get('saves', 0)}"
    elif p["position"] == "CB": stats_text = f"🛡️ Отборы: {p['stats_season'].get('tackles', 0)} | ⚽ Голы: {p['stats_season'].get('goals', 0)}"
    else: stats_text = f"⚽ Голы: {p['stats_season'].get('goals', 0)} | 🅰️ Ассисты: {p['stats_season'].get('assists', 0)}"
    
    skills_text = f"⚡ Тех: {p['skills']['tech']:.1f} | 🏃 Физ: {p['skills']['phys']:.1f} | 🎯 Удар: {p['skills']['shoot']:.1f}\n🛡️ Защ: {p['skills']['def']:.1f} | 🧤 Реакция: {p['skills']['gk']:.1f}"
    
    text = (
        f"👑 ПРОФИЛЬ ИГРОКА\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃‍♂️ {p['name']} | 🌍 {p.get('nation', 'Россия')} | 🎂 {p['age']} лет\n"
        f"⚡️ Общий рейтинг: {p['rating']}/100\n"
        f"🏢 Клуб: {p['club']} ({p['position']})\n"
        f"💵 Баланс: {p.get('money', 0)}$ | 🏷️ Стоимость: {val:,}$\n"
        f"🤝 Зарплата: {p.get('contract_salary', 1500)}$/матч\n"
        f"📊 Статус: {get_status_by_trust(p['trust'])}\n"
        f"🏟️ Сезон: {min(p['season'], 13)}/13 | Тур Лиги: {min(p['tour'], 15)}/15\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 **Навыки:**\n{skills_text}\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **Статистика (Сезон):** {stats_text}"
    )
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try: await callback.message.edit_text(text, reply_markup=kb)
    except: await callback.message.answer(text, reply_markup=kb)

# --- МАТЧИ, ТУРНИРЫ, КОНТРАКТЫ ---
@dp.callback_query(F.data == "menu_match")
@with_user_lock
async def match_handler(callback: CallbackQuery, state: FSMContext):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
    if await deny_if_retired_cb(callback, p): return
    
    if p.get("fatigue", 0) >= 95: return await callback.answer("🚫 Ты смертельно устал!", show_alert=True)
    if p.get("injury_tours", 0) > 0: return await callback.answer(f"🚑 Травма! Лечиться еще {p['injury_tours']} тур.", show_alert=True)

    # 1. ЛЕТНЯЯ ФАЗА: ЧМ / ЕВРО / КОПА
    if p["tour"] > 15:
        is_wc = p["season"] in [4, 8, 12]
        is_copa = p["season"] in [3, 7, 11]
        
        if (is_wc or is_copa) and p["rating"] >= 75:
            if p.get("wc_stage") not in ["Вылет", "Победитель"]:
                cup_name = "ЧЕМПИОНАТ МИРА" if is_wc else "ЕВРО" if p.get("nation") in EURO_NATIONS else "КОПА АМЕРИКА"
                return await process_international_cup(callback, state, p, user_id, players, cup_name)

        # 2. ОКОНЧАНИЕ СЕЗОНА: ТРАНСФЕРЫ И КОНТРАКТЫ
        all_clubs = []
        for l in CLUBS.values(): all_clubs.extend(l)
        
        # Подбор клубов по рейтингу (+- 10) из любых лиг
        possible = [c for c in all_clubs if abs(CLUB_RATINGS.get(c, 50) - p["rating"]) <= 10 and c != p["club"]]
        if len(possible) < 4: possible = random.sample(all_clubs, 4)
        offers = random.sample(possible, 4)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🤝 Продлить контракт ({p['club']})", callback_data=f"transfer:{p['club']}")],
            [InlineKeyboardButton(text=f"✈️ {offers[0]}", callback_data=f"transfer:{offers[0]}")],
            [InlineKeyboardButton(text=f"✈️ {offers[1]}", callback_data=f"transfer:{offers[1]}")],
            [InlineKeyboardButton(text=f"✈️ {offers[2]}", callback_data=f"transfer:{offers[2]}")],
            [InlineKeyboardButton(text=f"✈️ {offers[3]}", callback_data=f"transfer:{offers[3]}")]
        ])
        
        text = "🏁 **СЕЗОН ЗАВЕРШЕН!**\nТебе поступили предложения от клубов. Выбери, где продолжишь карьеру (или останься в текущем):"
        try: await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except: await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        return

    # 3. КЛУБНЫЙ МАТЧ (ГЛУБОКИЙ РЕЗЕРВ И БАНКА)
    if p["trust"] <= 20:
        p["tour"] += 1
        p["train_done"] = False
        p["fatigue"] = max(0, p.get("fatigue", 0) - 10)
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        msg = "❌ **Матч пропущен!**\nТренер оставил тебя в глубоком резерве. Тренируйся, чтобы повысить доверие."
        try: return await callback.message.edit_text(msg, reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")
        except: return await callback.message.answer(msg, reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")

    p["stats_season"]["games"] += 1
    p["fatigue"] = min(100, p.get("fatigue", 0) + 15)
    
    rival_pool = [c for c in CLUBS[p["division"]] if c != p["club"]]
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
        
    match_data = {
        "rival": random.choice(rival_pool),
        "total_moments": random.randint(2, 4), "current_moment": 1,
        "minute": 0, "goals": 0, "assists": 0, "my_team_score": 0, "rival_team_score": 0, "log": ""
    }
    
    # Банка (Выход на замену)
    if 21 <= p["trust"] <= 50:
        match_data["minute"] = random.randint(60, 75)
        match_data["total_moments"] = random.randint(1, 2)
        match_data["log"] += f"🔄 **{match_data['minute']}'** | Тренер выпускает тебя на замену во втором тайме!\n"

    await state.update_data(match=match_data)
    try: await callback.message.edit_text(f"⚽ **МАТЧ: {p['division']}**\n⚔️ **{p['club']}** vs **{match_data['rival']}**", parse_mode="Markdown")
    except: await callback.message.answer(f"⚽ **МАТЧ: {p['division']}**\n⚔️ **{p['club']}** vs **{match_data['rival']}**", parse_mode="Markdown")
    await asyncio.sleep(1)
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
    p["contract_salary"] = int(p["rating"] * 45) # ЗП зависит от рейтинга
    
    p["season"] += 1
    p["tour"] = 1
    p["age"] += 1
    p["wc_stage"] = "Группа 1"
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
    
    msg = f"✍️ **КОНТРАКТ ПОДПИСАН!**\nТвой клуб: **{new_club}**.\nНовый сезон ({p['season']}) начался! Зарплата: {p['contract_salary']}$/матч."
    try: await callback.message.edit_text(msg, reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")
    except: await callback.message.answer(msg, reply_markup=await main_menu_keyboard(callback.from_user.username, user_id), parse_mode="Markdown")

# --- СИМУЛЯТОР МЕЖДУНАРОДНЫХ КУБКОВ ---
async def process_international_cup(callback, state, p, user_id, players, cup_name):
    curr = p.get("wc_stage", "Группа 1")
    
    # Если турнир завершен или сброшен — отправляем обратно в клуб
    if curr in ["Вылет", "Победитель"]: 
        p["wc_stage"] = "Группа 1"
        return await match_handler(callback, state) 

    rival = random.choice([n for n in NATIONS if n != p.get("nation", "Россия")])
    match_data = {
        "rival": rival, "total_moments": random.randint(2, 4), "current_moment": 1,
        "minute": 0, "goals": 0, "assists": 0, "my_team_score": 0, "rival_team_score": 0, 
        "log": "", "is_int_cup": True, "stage": curr, "cup_name": cup_name
    }
    
    await state.update_data(match=match_data)
    text = f"🏆 **{cup_name}: {curr}**\n⚔️ **{p.get('nation', 'Россия')}** vs **{rival}**"
    try: await callback.message.edit_text(text, parse_mode="Markdown")
    except: await callback.message.answer(text, parse_mode="Markdown")
    await asyncio.sleep(1)
    await generate_moment(callback, state, user_id)

async def generate_moment(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    m = data["match"]
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
 
    m["minute"] += random.randint(15, 25)
    if m["minute"] >= 90: m["minute"] = 90
    
    my_name = p.get("nation", "Россия") if m.get("is_int_cup") else p["club"]
    
    if random.random() < 0.65:
        if random.random() < 0.5:
            m["rival_team_score"] += 1
            m["log"] += f"⚡ **{m['minute']}'** | Ошибка в защите! Соперник забивает мяч!\n"
        else:
            m["my_team_score"] += 1
            m["log"] += f"⚽ **{m['minute']}'** | ГОЛ! Твоя команда забивает!\n"

    # Пенальти для кубков
    if m["current_moment"] > m["total_moments"] or m["minute"] == 90:
        is_knockout = False
        if m.get("is_int_cup") and not m.get("stage", "").startswith("Группа"):
            is_knockout = True
            
        if is_knockout and m["my_team_score"] == m["rival_team_score"]:
            return await start_penalty_shootout(callback, state, user_id)
        else:
            return await finish_match(callback, state, user_id)
        
    text = (f"⏱ **{m['minute']}' МИНУТА** | Момент {m['current_moment']}/{m['total_moments']}\n"
            f"⚔️ **{my_name}** vs **{m['rival']}**\n"
            f"Счет: **{m['my_team_score']} : {m['rival_team_score']}**\n\n"
            f"📝 **События:**\n{m['log']}\n🔥 **Мяч у тебя!**")
    m["log"] = "" 
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Пробить", callback_data="act:shoot"), InlineKeyboardButton(text="📐 Пас", callback_data="act:pass")]
    ])
    await state.update_data(match=m)
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data == "act:shoot")
@with_user_lock
async def act_shoot_execute_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    m = data["match"]
    user_id = await get_uid(callback)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    
    # Повышенный шанс гола
    score_chance = 0.45 + (p["rating"] * 0.003)
    if random.random() < score_chance:
        m["goals"] += 1; m["my_team_score"] += 1
        m["log"] += f"⚽ **{m['minute']}'** | ГОЛ! Фантастический удар!\n"
    else:
        m["log"] += f"❌ **{m['minute']}'** | Вратарь потащил твой удар.\n"
            
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)

@dp.callback_query(F.data == "act:pass")
@with_user_lock
async def act_pass_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    m = data["match"]
    user_id = await get_uid(callback)
    p = migrate_player_data((await load_data(PLAYERS_FILE)).get(user_id))
    
    # Повышенный шанс паса
    pass_chance = 0.55 + (p["rating"] * 0.003)
    if random.random() < pass_chance:
        m["assists"] += 1; m["my_team_score"] += 1
        m["log"] += f"🅰️ **{m['minute']}'** | Шикарный ассист! Партнер забивает!\n"
    else:
        m["log"] += f"❌ **{m['minute']}'** | Передача перехвачена.\n"
        
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)

async def finish_match(callback: CallbackQuery, state: FSMContext, user_id: str, cup_status: str = ""):
    data = await state.get_data()
    m = data.get("match")
    players = await load_data(PLAYERS_FILE)
    p = migrate_player_data(players.get(user_id))
    
    my_score, rival_score = m.get("my_team_score", 0), m.get("rival_team_score", 0)
    
    if my_score > rival_score:
        p["trust"] = min(100, p["trust"] + 8); outcome = "win"
    elif my_score < rival_score:
        p["trust"] = max(0, p["trust"] - 12); outcome = "loss"
    else:
        p["trust"] = min(100, p["trust"] + 2); outcome = "draw"
        
    status = cup_status
    
    # Прогрессия сборных
    if m.get("is_int_cup"):
        stages = ["Группа 1", "Группа 2", "Группа 3", "1/8 Финала", "1/4 Финала", "Полуфинал", "Финал"]
        idx = stages.index(m["stage"])
        if "Группа" in m["stage"]:
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
                    p["wc_stage"] = stages[idx + 1]
                    status += f"\n🌐 **{m['cup_name']}:** Проход в {p['wc_stage']}"
        # Не увеличиваем tour, чтобы игрок остался в летней фазе
        p["train_done"] = False
    else:
        # Стандартный клубный матч
        p["money"] += p.get("contract_salary", 1500)
        p["tour"] += 1
        p["train_done"] = False
        await simulate_table_tour(user_id, p["division"], p["club"], m["rival"], outcome)
    
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    
    text = f"🏁 **МАТЧ ЗАВЕРШЕН**\nСчет: **{my_score} : {rival_score}**{status}\n\nТвоя статистика:\n⚽ Голы: {m.get('goals', 0)} | 🅰️ Ассисты: {m.get('assists', 0)}"
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    
    await state.clear()
    try: await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except: await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)

# --- ПЕНАЛЬТИ ---
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
    await next_penalty_kick(callback, state, callback.from_user.id) # user_id pass bypassed

async def main():
    print("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): print("Бот остановлен.")
