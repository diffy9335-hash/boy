import asyncio
import functools
import logging
import random
import json
import os
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8979310355:AAGPshB3WEGHVx33ZPjd9uIxQpY8wrGmy_8"

SPONSOR_CHANNEL_ID = "@jdoauqh"
SPONSOR_CHANNEL_URL = "https://t.me/jdoauqh"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

ADMINS = ["Diffysh1", "SilentRagex"]

PLAYERS_FILE = "players.json"
LEADERBOARD_FILE = "leaderboard.json"
TABLES_FILE = "tables.json"
SLOTS_FILE = "slots.json"
EURO_FILE = "euro_qualification.json"
AWARDS_FILE = "awards.json"
NPC_FILE = "npc_players.json"


def _load_data_sync(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            backup_name = f"{filename}.corrupted_{int(time.time())}"
            os.replace(filename, backup_name)
            logging.error(f"Файл {filename} повреждён ({e}) → {backup_name}. Создан новый.")
            return {}
    return {}


def _save_data_sync(filename, data):
    tmp_path = f"{filename}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_path, filename)


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


async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=SPONSOR_CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return False


def sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на Спонсора", url=SPONSOR_CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался (Проверить)", callback_data="check_sub_callback")]
    ])


def with_user_lock(func):
    @functools.wraps(func)
    async def wrapper(event, *args, **kwargs):
        user_id = await get_uid(event)
        lock = get_user_lock(user_id)
        async with lock:
            return await func(event, *args, **kwargs)
    return wrapper


def retired_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Начать новую карьеру", callback_data="start_new_career")]
    ])


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
        except Exception:
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


class PlayerCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_nation = State()
    waiting_for_position = State()
    waiting_for_country_league = State()
    waiting_for_number = State()
    waiting_for_club = State()


class AdminPanel(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_money = State()
    waiting_for_rating = State()


class InterviewState(StatesGroup):
    waiting_for_answer = State()


EURO_NATIONS = [
    "Россия", "Франция", "Италия", "Испания", "Германия", "Англия",
    "Португалия", "Нидерланды", "Бельгия", "Украина", "Хорватия",
    "Дания", "Швейцария", "Польша", "Швеция", "Норвегия", "Сербия", "Турция"
]

NATIONS = EURO_NATIONS

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
    "Бундеслига": ["Бавария", "Боруссия Д", "Байер", "РБ Лейпциг", "Штутгарт", "Айнтрахт Ф", "Хоффенхайм", "Фрайбург", "Вердер", "Аугсбург", "Вольфсбург", "Боруссия М", "Унион Берлин", "Майнц", "Хайденхайм", "Санкт-Паули"],
    "Сегунда лига": ["Тондела", "Визела", "Академика", "Лейшойнш", "Оливейренсе", "Фейренсе", "Варзин", "Ковильян", "Трофенсе", "Амадора", "Мануэл да Круш", "Насьонал"],
    "Примейра": ["Порту", "Бенфика", "Спортинг", "Брага", "Витория", "Фамаликан", "Риу Аве", "Арока", "Жил Висенте", "Эшторил", "Боавишта", "Пасуш де Феррейра", "Санта-Клара", "Портимоненсе", "Морейренсе", "Насьонал"],
    "Бразильская Серия А": ["Фламенго", "Палмейрас", "Сантос", "Коринтианс", "Сан-Паулу", "Интернасьонал", "Гремио", "Атлетико Минейро", "Крузейро", "Ботафого", "Васко да Гама", "Флуминенсе", "Баия", "Форталеза", "Куяба", "Атлетико Паранаэнсе", "Гояс", "Спорт Ресифи", "Сеара", "Америка Минейро"],
    "Эрстедивизи": ["Йонг Аякс", "Йонг ПСВ", "Йонг Утрехт", "Ден Босх", "Камбюр", "Де Графсхап", "Дордрехт", "Эйндховен", "Эммен", "Гронинген", "Хелмонд Спорт", "Хераклес", "Маастрихт", "Осс", "Рода", "Телстар", "Венло", "Виллем II", "Зволле", "Алмере Сити"],
    "Эредивизи": ["Аякс", "ПСВ", "Фейеноорд", "АЗ Алкмаар", "Твенте", "Утрехт", "Витесс", "Спарта Роттердам", "Херенвен", "Фортуна Ситтард", "НЕК", "Гоу Эхед Иглз", "Валвейк", "Эксельсиор", "Волендам", "Эммен", "Камбюр", "Гронинген"],
    "Jupiler Pro League": ["Андерлехт", "Брюгге", "Генк", "Гент", "Стандард Льеж", "Шарлеруа", "Мехелен", "Антверпен", "Серкль Брюгге", "Зюлте-Варегем", "Остенде", "Кортрейк", "Эйпен", "Лёвен", "Вестерло", "Беерсхот"],
    "Беларусь Первая лига": ["Локомотив Гомель", "Барановичи", "Лида", "Молодечно", "Орша", "Осиповичи", "Волна Пинск", "Жодино-Южное", "Слоним-2017", "Гомель-2", "Минск-2", "Динамо-Минск-2"],
    "Беларусь Высшая лига": ["Динамо Минск", "БАТЭ", "Шахтер Солигорск", "Торпедо-БелАЗ", "Неман Гродно", "Славия Мозырь", "Ислочь", "Минск", "Гомель", "Сморгонь", "Нафтан Новополоцк", "Слуцк", "Витебск", "Днепр-Могилев", "Арсенал Дзержинск", "Брест"],
    "Турция Первая лига": ["Гёзтепе", "Алтай", "Аданаспор", "Бурсаспор", "Денизлиспор", "Эскишехирспор", "Гиресунспор", "Истанбулспор", "Коджаэлиспор", "Манисаспор", "Менеменспор", "Самсунспор", "Тузласпор", "Умраниеспор", "Бандырмаспор", "ББ Эрзурумспор", "Сакарьяспор", "Кечиоренгюджю"],
    "Турция Суперлига": ["Галатасарай", "Фенербахче", "Бешикташ", "Трабзонспор", "Истанбул Башакшехир", "Адана Демирспор", "Аланьяспор", "Антальяспор", "Газиантеп", "Ризеспор", "Сивасспор", "Кайсериспор", "Коньяспор", "Самсунспор", "Касымпаша", "Хатайспор", "Анкарагюджю", "Пендикспор", "Эюпспор", "Бодрумспор"],
    "Казахстан Премьер-лига": ["Актобе", "Астана", "Кайрат", "Тобол", "Ордабасы", "Кызыл-Жар", "Тараз", "Шахтер-Караганда", "Жетысу", "Елимай", "Кайсар", "Туран", "Атырау", "Женис", "Улытау", "Каспий"]
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
    "Бавария": 91, "Боруссия Д": 86, "Байер": 88, "РБ Лейпциг": 86, "Штутгарт": 82, "Айнтрахт Ф": 81, "Хоффенхайм": 78, "Фрайбург": 79, "Вердер": 77, "Аугсбург": 76, "Вольфсбург": 78, "Боруссия М": 77, "Унион Берлин": 76, "Майнц": 75, "Хайденхайм": 76, "Санкт-Паули": 74,
    "Тондела": 62, "Визела": 63, "Академика": 60, "Лейшойнш": 59, "Оливейренсе": 58, "Фейренсе": 61, "Варзин": 57, "Ковильян": 56, "Трофенсе": 55, "Амадора": 64, "Мануэл да Круш": 54, "Насьонал": 68,
    "Порту": 88, "Бенфика": 86, "Спортинг": 87, "Брага": 80, "Витория": 76, "Фамаликан": 74, "Риу Аве": 72, "Арока": 70, "Жил Висенте": 71, "Эшторил": 69, "Боавишта": 73, "Пасуш де Феррейра": 68, "Санта-Клара": 67, "Портимоненсе": 70, "Морейренсе": 72, "Насьонал": 68,
    "Фламенго": 85, "Палмейрас": 84, "Сантос": 80, "Коринтианс": 79, "Сан-Паулу": 78,
    "Интернасьонал": 77, "Гремио": 76, "Атлетико Минейро": 75, "Крузейро": 74, "Ботафого": 73,
    "Васко да Гама": 72, "Флуминенсе": 72, "Баия": 71, "Форталеза": 70, "Куяба": 69,
    "Атлетико Паранаэнсе": 70, "Гояс": 68, "Спорт Ресифи": 69, "Сеара": 68, "Америка Минейро": 67,
    "Йонг Аякс": 58, "Йонг ПСВ": 56, "Йонг Утрехт": 52, "Ден Босх": 55, "Камбюр": 62, "Де Графсхап": 60,
    "Дордрехт": 54, "Эйндховен": 57, "Эммен": 63, "Гронинген": 66, "Хелмонд Спорт": 53, "Хераклес": 65,
    "Маастрихт": 56, "Осс": 51, "Рода": 59, "Телстар": 52, "Венло": 58, "Виллем II": 64, "Зволле": 63, "Алмере Сити": 55,
    "Аякс": 89, "ПСВ": 88, "Фейеноорд": 86, "АЗ Алкмаар": 82, "Твенте": 79, "Утрехт": 77, "Витесс": 76,
    "Спарта Роттердам": 74, "Херенвен": 73, "Фортуна Ситтард": 72, "НЕК": 72, "Гоу Эхед Иглз": 70,
    "Валвейк": 69, "Эксельсиор": 68, "Волендам": 67, "Камбюр": 62, "Гронинген": 66,
    "Андерлехт": 82, "Брюгге": 84, "Генк": 80, "Гент": 78, "Стандард Льеж": 76, "Шарлеруа": 74,
    "Мехелен": 73, "Антверпен": 75, "Серкль Брюгге": 72, "Зюлте-Варегем": 70, "Остенде": 71,
    "Кортрейк": 69, "Эйпен": 68, "Лёвен": 67, "Вестерло": 69, "Беерсхот": 66,
    "Локомотив Гомель": 45, "Барановичи": 43, "Лида": 42, "Молодечно": 41, "Орша": 40, "Осиповичи": 39,
    "Волна Пинск": 38, "Жодино-Южное": 37, "Слоним-2017": 36, "Гомель-2": 35, "Минск-2": 34, "Динамо-Минск-2": 33,
    "Динамо Минск": 72, "БАТЭ": 70, "Шахтер Солигорск": 68, "Торпедо-БелАЗ": 66, "Неман Гродно": 65, "Славия Мозырь": 63,
    "Ислочь": 62, "Минск": 61, "Гомель": 60, "Сморгонь": 58, "Нафтан Новополоцк": 57, "Слуцк": 56, "Витебск": 55,
    "Днепр-Могилев": 54, "Арсенал Дзержинск": 53, "Брест": 52,
    "Гёзтепе": 52, "Алтай": 51, "Аданаспор": 50, "Бурсаспор": 49, "Денизлиспор": 48, "Эскишехирспор": 47,
    "Гиресунспор": 46, "Истанбулспор": 45, "Коджаэлиспор": 44, "Манисаспор": 43, "Менеменспор": 42, "Самсунспор": 41,
    "Тузласпор": 40, "Умраниеспор": 39, "Бандырмаспор": 38, "ББ Эрзурумспор": 37, "Сакарьяспор": 36, "Кечиоренгюджю": 35,
    "Галатасарай": 82, "Фенербахче": 81, "Бешикташ": 80, "Трабзонспор": 78, "Истанбул Башакшехир": 76,
    "Адана Демирспор": 74, "Аланьяспор": 73, "Антальяспор": 72, "Газиантеп": 71, "Ризеспор": 70, "Сивасспор": 69,
    "Кайсериспор": 68, "Коньяспор": 67, "Самсунспор": 66, "Касымпаша": 65, "Хатайспор": 64, "Анкарагюджю": 63,
    "Пендикспор": 62, "Эюпспор": 61, "Бодрумспор": 60,
    "Актобе": 68, "Астана": 70, "Кайрат": 69, "Тобол": 67, "Ордабасы": 66, "Кызыл-Жар": 65, "Тараз": 63, "Шахтер-Караганда": 64,
    "Жетысу": 62, "Елимай": 61, "Кайсар": 60, "Туран": 59, "Атырау": 58, "Женис": 57, "Улытау": 56, "Каспий": 55
}

CUP_STAGES = ["1/16", "1/8", "1/4", "Полуфинал", "Финал"]

SPONSORS_DATA = {
    "Литвин":   {"emoji": "🥤", "min_rating": 40, "income_per_match": 500,   "sign_bonus": 2_000},
    "Самосвет": {"emoji": "💎", "min_rating": 50, "income_per_match": 800,   "sign_bonus": 3_000},
    "Жигули":   {"emoji": "🍺", "min_rating": 55, "income_per_match": 1_000, "sign_bonus": 4_000},
    "Найк":     {"emoji": "👟", "min_rating": 67, "income_per_match": 3_000, "sign_bonus": 15_000},
    "Пума":     {"emoji": "🐆", "min_rating": 67, "income_per_match": 2_500, "sign_bonus": 12_000},
    "Рибок":    {"emoji": "🏅", "min_rating": 67, "income_per_match": 2_200, "sign_bonus": 10_000},
    "ПСБ банк": {"emoji": "🏦", "min_rating": 67, "income_per_match": 2_800, "sign_bonus": 13_000},
}

POSITIONS = {
    "⚽ Нападающий": "ST",
    "🪄 Полузащитник": "CM",
    "🛡️ Защитник": "CB",
    "🧤 Вратарь": "GK"
}

QUESTS_DATA = {
    "q1": {"name": "Первая кровь", "desc": "Забить 1 гол", "reward": 0.05, "type": "goals", "target": 1},
    "q2": {"name": "Бомбардир", "desc": "Забить 10 голов", "reward": 0.08, "type": "goals", "target": 10},
    "q3": {"name": "Снайпер", "desc": "Забить 50 голов", "reward": 0.15, "type": "goals", "target": 50},
    "q4": {"name": "Легендарный голеадор", "desc": "Забить 100 голов", "reward": 0.3, "type": "goals", "target": 100},
    "q5": {"name": "Первый ассист", "desc": "Отдать 1 голевой пас", "reward": 0.05, "type": "assists", "target": 1},
    "q6": {"name": "Командный игрок", "desc": "Отдать 20 ассистов", "reward": 0.08, "type": "assists", "target": 20},
    "q7": {"name": "Маэстро паса", "desc": "Отдать 50 ассистов", "reward": 0.15, "type": "assists", "target": 50},
    "q8": {"name": "Надежный щит", "desc": "10 отборов/сейвов", "reward": 0.05, "type": "def", "target": 10},
    "q9": {"name": "Министр обороны", "desc": "50 отборов/сейвов", "reward": 0.15, "type": "def", "target": 50},
    "q10": {"name": "Стена", "desc": "150 отборов/сейвов", "reward": 0.3, "type": "def", "target": 150},
    "q11": {"name": "Вкус победы", "desc": "Выиграть 1 трофей", "reward": 0.1, "type": "trophies", "target": 1},
    "q12": {"name": "Коллекционер", "desc": "Выиграть 3 трофея", "reward": 0.25, "type": "trophies", "target": 3},
    "q13": {"name": "Опытный", "desc": "Сыграть 50 матчей", "reward": 0.1, "type": "games", "target": 50},
    "q14": {"name": "Ветеран", "desc": "Сыграть 150 матчей", "reward": 0.25, "type": "games", "target": 150},
    "q15": {"name": "Миллионер", "desc": "Накопить 1,000,000$", "reward": 0.3, "type": "money", "target": 1000000}
}


def get_quest_progress(p, q_type):
    st = p.get("stats_total", {})
    if q_type == "goals": return st.get("goals", 0)
    elif q_type == "assists": return st.get("assists", 0)
    elif q_type == "def": return st.get("tackles", 0) + st.get("saves", 0)
    elif q_type == "trophies": return len(p.get("trophies", []))
    elif q_type == "money": return p.get("money", 0)
    elif q_type == "games": return st.get("games", 0)
    return 0


def get_division(club_name):
    for div, clubs in CLUBS.items():
        if club_name in clubs:
            return div
    return "ФНЛ 2"


DIVISION_LADDERS = [
    ["ФНЛ 2", "ФНЛ", "РПЛ"],
    ["Насьональ", "Лига 2", "Лига 1"],
    ["Первая лига Англии", "Чемпионшип", "АПЛ"],
    ["Сегунда", "Ла Лига"],
    ["Серия Б", "Серия А"],
    ["Вторая Бундеслига", "Бундеслига"],
    ["Сегунда лига", "Примейра"],
    ["Бразильская Серия А"],
    ["Эрстедивизи", "Эредивизи"],
    ["Jupiler Pro League"],
    ["Беларусь Первая лига", "Беларусь Высшая лига"],
    ["Турция Первая лига", "Турция Суперлига"],
    ["Казахстан Премьер-лига"]
]


def get_ladder(division):
    for ladder in DIVISION_LADDERS:
        if division in ladder:
            return ladder
    return [division]


def get_status_by_trust(trust):
    if 0 <= trust <= 20:
        return "Глубокий резерв ❌"
    elif 21 <= trust <= 50:
        return "Скамейка запасных 🪑"
    elif 51 <= trust <= 75:
        return "Джокер ⏱️"
    else:
        return "Игрок старта 🔥"


def calculate_player_value(rating, division):
    mult = {
        "ФНЛ 2": 12500, "Насьональ": 12500, "Первая лига Англии": 15000,
        "Сегунда": 35000, "Серия Б": 35000, "Вторая Бундеслига": 40000,
        "ФНЛ": 45000, "Лига 2": 45000, "Чемпионшип": 55000,
        "РПЛ": 250000, "Лига 1": 250000, "АПЛ": 350000, "Ла Лига": 350000, "Серия А": 300000, "Бундеслига": 320000,
        "Примейра": 280000, "Сегунда лига": 40000,
        "Бразильская Серия А": 250000,
        "Эрстедивизи": 35000, "Эредивизи": 280000,
        "Jupiler Pro League": 280000,
        "Беларусь Первая лига": 15000,
        "Беларусь Высшая лига": 40000,
        "Турция Первая лига": 20000,
        "Турция Суперлига": 200000,
        "Казахстан Премьер-лига": 40000
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

    leaderboard["top_careers"] = sorted(
        leaderboard["top_careers"], key=lambda x: (x["rating"], x["trophies"]), reverse=True
    )[:10]
    await save_data(LEADERBOARD_FILE, leaderboard)


async def track_activity(user_id: str):
    players = await load_data(PLAYERS_FILE)
    if user_id in players:
        p = players[user_id]
        current_week = datetime.now().isocalendar()[1]

        if p.get("activity_week", current_week) != current_week:
            p["activity_minutes"] = 0
            p["activity_week"] = current_week

        p["activity_minutes"] = p.get("activity_minutes", 0) + random.randint(1, 5)
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)


def _init_tables_internal(tables, user_id, division, player_club=None):
    clubs_list = CLUBS[division].copy()
    if player_club and player_club not in clubs_list:
        clubs_list[-1] = player_club

    division_table = [
        {"club": club, "points": 0, "wins": 0, "draws": 0, "losses": 0} for club in clubs_list
    ]
    if user_id not in tables:
        tables[user_id] = {}
    tables[user_id][division] = division_table


async def init_tables_for_user(user_id, division, player_club=None):
    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        _init_tables_internal(tables, user_id, division, player_club)
        await save_data(TABLES_FILE, tables)




async def simulate_table_until_tour(user_id, division, player_club, current_tour):
    """
    Создаёт таблицу и симулирует все туры до current_tour.
    Используется при переходе в новый клуб посреди сезона.
    """
    await init_tables_for_user(user_id, division, player_club)

    tables = await load_data(TABLES_FILE)
    table = tables[user_id][division]

    clubs = [row["club"] for row in table]

    for tour in range(1, current_tour):
        random.shuffle(clubs)

        for i in range(0, len(clubs) - 1, 2):
            c1_club = clubs[i]
            c2_club = clubs[i + 1]

            r1 = CLUB_RATINGS.get(c1_club, 50)
            r2 = CLUB_RATINGS.get(c2_club, 50)

            chance_w1 = 0.35 + ((r1 - r2) * 0.01)
            chance_w2 = 0.35 + ((r2 - r1) * 0.01)
            rand = random.random()

            c1 = next(r for r in table if r["club"] == c1_club)
            c2 = next(r for r in table if r["club"] == c2_club)

            if rand < chance_w1:
                c1["points"] += 3; c1["wins"] += 1; c2["losses"] += 1
            elif rand < chance_w1 + chance_w2:
                c2["points"] += 3; c2["wins"] += 1; c1["losses"] += 1
            else:
                c1["points"] += 1; c1["draws"] += 1
                c2["points"] += 1; c2["draws"] += 1

    tables[user_id][division] = sorted(table, key=lambda x: x["points"], reverse=True)
    await save_data(TABLES_FILE, tables)


async def simulate_table_tour(user_id, division, player_club, player_match_rival, player_match_outcome):
    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        if user_id not in tables or division not in tables[user_id]:
            _init_tables_internal(tables, user_id, division, player_club)

        table = tables[user_id][division]

        for row in table:
            if row["club"] == player_club:
                if player_match_outcome == "win":
                    row["points"] += 3; row["wins"] += 1
                elif player_match_outcome == "draw":
                    row["points"] += 1; row["draws"] += 1
                else:
                    row["losses"] += 1
            elif row["club"] == player_match_rival:
                if player_match_outcome == "win":
                    row["losses"] += 1
                elif player_match_outcome == "draw":
                    row["points"] += 1; row["draws"] += 1
                else:
                    row["points"] += 3; row["wins"] += 1

        other_clubs = [row for row in table if row["club"] not in (player_club, player_match_rival)]
        random.shuffle(other_clubs)

        while len(other_clubs) >= 2:
            c1 = other_clubs.pop()
            c2 = other_clubs.pop()
            r1, r2 = CLUB_RATINGS.get(c1["club"], 50), CLUB_RATINGS.get(c2["club"], 50)
            chance_w1 = 0.35 + ((r1 - r2) * 0.01)
            chance_w2 = 0.35 + ((r2 - r1) * 0.01)
            rand = random.random()

            if rand < chance_w1:
                c1["points"] += 3; c1["wins"] += 1; c2["losses"] += 1
            elif rand < chance_w1 + chance_w2:
                c2["points"] += 3; c2["wins"] += 1; c1["losses"] += 1
            else:
                c1["points"] += 1; c1["draws"] += 1
                c2["points"] += 1; c2["draws"] += 1

        if other_clubs:
            c = other_clubs.pop()
            res = random.choice(["win", "draw", "loss"])
            if res == "win":
                c["points"] += 3; c["wins"] += 1
            elif res == "draw":
                c["points"] += 1; c["draws"] += 1
            else:
                c["losses"] += 1

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
            if rand < chance_w1:
                c1["points"] += 3; c1["wins"] += 1; c2["losses"] += 1
            elif rand < chance_w1 + chance_w2:
                c2["points"] += 3; c2["wins"] += 1; c1["losses"] += 1
            else:
                c1["points"] += 1; c1["draws"] += 1
                c2["points"] += 1; c2["draws"] += 1

        if clubs:
            c = clubs.pop()
            res = random.choice(["win", "draw", "loss"])
            if res == "win":
                c["points"] += 3; c["wins"] += 1
            elif res == "draw":
                c["points"] += 1; c["draws"] += 1
            else:
                c["losses"] += 1

        tables[user_id][division] = sorted(table, key=lambda x: x["points"], reverse=True)
        await save_data(TABLES_FILE, tables)


TRAINING_CONFIG = {
    "ST": {
        "tech": {"name": "Дриблинг", "base_gain": 0.05, "fatigue": 15},
        "phys": {"name": "Скорость", "base_gain": 0.05, "fatigue": 15},
        "special": {"name": "Завершение", "base_gain": 0.08, "fatigue": 18}
    },
    "CM": {
        "tech": {"name": "Пас", "base_gain": 0.05, "fatigue": 15},
        "phys": {"name": "Выносливость", "base_gain": 0.05, "fatigue": 15},
        "special": {"name": "Видение поля", "base_gain": 0.08, "fatigue": 18}
    },
    "CB": {
        "tech": {"name": "Отбор", "base_gain": 0.05, "fatigue": 15},
        "phys": {"name": "Сила", "base_gain": 0.05, "fatigue": 15},
        "special": {"name": "Позиция", "base_gain": 0.08, "fatigue": 18}
    },
    "GK": {
        "tech": {"name": "Реакция", "base_gain": 0.05, "fatigue": 15},
        "phys": {"name": "Прыжок", "base_gain": 0.05, "fatigue": 15},
        "special": {"name": "Игра ногами", "base_gain": 0.08, "fatigue": 18}
    }
}

STREAK_BONUSES = {5: 0.1, 10: 0.2, 15: 0.3, 20: 0.5}

TRAIN_ACHIEVEMENTS = {
    "train_25": {"name": "🏅 Трудяга", "desc": "25 тренировок", "reward": 0.1},
    "train_50": {"name": "🏅 Профи", "desc": "50 тренировок", "reward": 0.2},
    "train_100": {"name": "🏅 Легенда тренировок", "desc": "100 тренировок", "reward": 0.3},
    "streak_5": {"name": "🔥 Дисциплина", "desc": "5 тренировок подряд", "reward": 0.1},
    "streak_10": {"name": "🔥 Железная воля", "desc": "10 тренировок подряд", "reward": 0.2},
    "streak_20": {"name": "🔥 Монах", "desc": "20 тренировок подряд", "reward": 0.3},
}


def get_train_cost(rating: float) -> int:
    return int(200 + (rating * 5))


def get_streak_bonus(streak: int) -> float:
    bonus = 0.0
    for s, b in sorted(STREAK_BONUSES.items()):
        if streak >= s:
            bonus = b
    return bonus


def check_train_achievements(p: dict, train_count: int, streak: int) -> tuple:
    unlocked = []
    total_reward = 0.0

    train_achievements = p.get("train_achievements", [])

    for key, ach in TRAIN_ACHIEVEMENTS.items():
        if key in train_achievements:
            continue

        if key == "train_25" and train_count >= 25:
            unlocked.append(ach); total_reward += ach["reward"]
        elif key == "train_50" and train_count >= 50:
            unlocked.append(ach); total_reward += ach["reward"]
        elif key == "train_100" and train_count >= 100:
            unlocked.append(ach); total_reward += ach["reward"]
        elif key == "streak_5" and streak >= 5:
            unlocked.append(ach); total_reward += ach["reward"]
        elif key == "streak_10" and streak >= 10:
            unlocked.append(ach); total_reward += ach["reward"]
        elif key == "streak_20" and streak >= 20:
            unlocked.append(ach); total_reward += ach["reward"]

    return unlocked, total_reward


async def heal_injury_if_needed(user_id: str):
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        return

    if p.get("injury_tours", 0) > 0:
        p["injury_tours"] -= 1
        if p["injury_tours"] <= 0:
            p["is_injured"] = False
            p["injury_tours"] = 0
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)


# ============================================================
# СИСТЕМА НОМИНАЦИЙ (NPC + Awards)
# ============================================================

FIRST_NAMES = [
    "Александр", "Дмитрий", "Максим", "Иван", "Артём", "Никита", "Егор", "Кирилл",
    "Лука", "Матео", "Лео", "Марко", "Диего", "Пабло", "Хуан", "Карлос",
    "Томас", "Лукас", "Ян", "Петер", "Андрей", "Юрий", "Сергей", "Владимир",
    "Мухаммед", "Али", "Юсуф", "Кевин", "Джон", "Майкл", "Давид", "Симон",
    "Рафаэль", "Габриэль", "Фелипе", "Родриго", "Тьяго", "Бруно", "Жоао",
    "Хамес", "Харри", "Оливер", "Джек", "Чарли", "Джордж", "Томас", "Артур"
]

LAST_NAMES = [
    "Смирнов", "Иванов", "Кузнецов", "Попов", "Соколов", "Лебедев", "Козлов",
    "Гарсия", "Родригес", "Мартинес", "Лопес", "Гонсалес", "Перес",
    "Мюллер", "Шмидт", "Вернер", "Кох", "Рихтер",
    "Дюпон", "Дюран", "Леруа", "Моро", "Готье",
    "Смит", "Джонсон", "Уильямс", "Браун", "Джонс",
    "Силва", "Сантос", "Оливейра", "Коста",
    "де Йонг", "ван Дейк", "Баккер", "Виссер",
    "Ибрагимов", "Ахмедов", "Ковач", "Новак", "Петрович"
]

NPC_POSITIONS = ["ST", "ST", "CM", "CM", "CB", "CB", "GK"]


def generate_npc_player(club_rating, position):
    base_rating = club_rating + random.randint(-10, 10)
    base_rating = max(30, min(99, base_rating))

    return {
        "name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        "position": position,
        "rating": round(base_rating + random.uniform(-2, 2), 1),
    }


def generate_npc_stats(player, club_rating, season_length=30):
    pos = player["position"]
    rating = player["rating"]

    games = random.randint(int(season_length * 0.7), season_length)

    skill = rating / 70.0
    skill = max(0.4, min(1.3, skill))

    if pos == "ST":
        max_goals = int(games * 0.9)
        max_assists = int(games * 0.5)
        goals = random.randint(0, max(1, int(max_goals * skill)))
        assists = random.randint(0, max(1, int(max_assists * skill)))
        saves = 0
        tackles = 0
    elif pos == "CM":
        max_goals = int(games * 0.4)
        max_assists = int(games * 0.7)
        max_tackles = int(games * 1.2)
        goals = random.randint(0, max(1, int(max_goals * skill)))
        assists = random.randint(0, max(1, int(max_assists * skill)))
        saves = 0
        tackles = random.randint(0, max(1, int(max_tackles * skill)))
    elif pos == "CB":
        max_goals = int(games * 0.15)
        max_assists = int(games * 0.1)
        max_tackles = int(games * 2.5)
        goals = random.randint(0, max(1, int(max_goals * skill)))
        assists = random.randint(0, max(1, int(max_assists * skill)))
        saves = 0
        tackles = random.randint(int(max_tackles * 0.3), max(1, int(max_tackles * skill)))
    elif pos == "GK":
        max_saves = int(games * 3.5)
        goals = 0
        assists = 0
        saves = random.randint(int(max_saves * 0.3), max(1, int(max_saves * skill)))
        tackles = 0
    else:
        goals = assists = saves = tackles = 0

    return {
        "games": games,
        "goals": goals,
        "assists": assists,
        "saves": saves,
        "tackles": tackles
    }


async def generate_all_npc_players(season_num):
    npc_file = await load_data(NPC_FILE)
    if npc_file and npc_file.get("season") == season_num:
        return npc_file["data"]

    npc_data = {}
    for division, clubs in CLUBS.items():
        for club in clubs:
            club_rating = CLUB_RATINGS.get(club, 50)
            players = []
            for pos in NPC_POSITIONS:
                npc = generate_npc_player(club_rating, pos)
                npc["stats"] = generate_npc_stats(npc, club_rating)
                npc["club"] = club
                npc["division"] = division
                players.append(npc)
            npc_data[club] = players

    await save_data(NPC_FILE, {"season": season_num, "data": npc_data})
    return npc_data


async def get_league_players(division, exclude_user_id=None):
    players = await load_data(PLAYERS_FILE)
    npc_data = await generate_all_npc_players(1)

    result = []

    for uid, pdata in players.items():
        if pdata.get("retired"):
            continue
        if pdata.get("division") != division:
            continue

        result.append({
            "name": pdata["name"],
            "position": pdata.get("position", "ST"),
            "club": pdata.get("club"),
            "rating": pdata.get("rating", 40),
            "stats": pdata.get("stats_season", {}),
            "is_player": True,
            "user_id": uid,
        })

    for club, npc_list in npc_data.items():
        for npc in npc_list:
            if npc.get("division") != division:
                continue
            result.append({
                "name": npc["name"],
                "position": npc["position"],
                "club": club,
                "rating": npc["rating"],
                "stats": npc["stats"],
                "is_player": False,
            })

    return result


async def calculate_player_awards(user_id, season_num):
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        return None

    npc_data = await generate_all_npc_players(season_num)

    all_candidates = []

    all_candidates.append({
        "name": p["name"],
        "position": p.get("position", "ST"),
        "rating": p.get("rating", 40),
        "club": p.get("club"),
        "stats": p.get("stats_season", {}),
        "trophies": len(p.get("trophies", [])),
        "is_player": True
    })

    for club, npc_list in npc_data.items():
        for npc in npc_list:
            all_candidates.append({
                "name": npc["name"],
                "position": npc["position"],
                "rating": npc["rating"],
                "club": club,
                "stats": npc["stats"],
                "trophies": 0,
                "is_player": False
            })

        zm = []
    for c in all_candidates:
        s = c["stats"]
        score = (
            c["rating"] * 7 +
            s.get("goals", 0) * 5 +
            s.get("assists", 0) * 3 +
            c["trophies"] * 18
        )
        if c.get("is_player"):
            score += 30
        zm.append({**c, "score": round(score, 1)})
    golden_ball = max(zm, key=lambda x: x["score"]) if zm else None

    zp = [
        {**c, "score": round(c["stats"].get("saves", 0) * 5 + c["rating"] * 8, 1)}
        for c in all_candidates if c["position"] == "GK"
    ]
    golden_glove = max(zp, key=lambda x: x["score"]) if zp else None

    lz = [
        {**c, "score": round(
            c["stats"].get("tackles", 0) * 5 +
            c["rating"] * 8 +
            c["stats"].get("goals", 0) * 3, 1
        )}
        for c in all_candidates if c["position"] == "CB"
    ]
    best_defender = max(lz, key=lambda x: x["score"]) if lz else None

    la = [
        {**c, "score": round(c["stats"].get("assists", 0) * 10 + c["rating"] * 2, 1)}
        for c in all_candidates
    ]
    best_assistant = max(la, key=lambda x: x["score"]) if la else None

    tables = await load_data(TABLES_FILE)
    euro_data = await load_data(EURO_FILE)

    DIVISION_WEIGHT = {
        "АПЛ": 100, "Ла Лига": 100, "Серия А": 100, "Бундеслига": 100,
        "Лига 1": 95, "РПЛ": 90, "Примейра": 90, "Эредивизи": 85,
        "Бразильская Серия А": 85, "Jupiler Pro League": 80,
        "Турция Суперлига": 80, "Казахстан Премьер-лига": 60,
        "Беларусь Высшая лига": 55,
        "ФНЛ": 50, "Лига 2": 50, "Чемпионшип": 55, "Сегунда": 50,
        "Серия Б": 50, "Вторая Бундеслига": 50, "Сегунда лига": 45,
        "Эрстедивизи": 45, "Беларусь Первая лига": 35,
        "Турция Первая лига": 40,
        "ФНЛ 2": 25, "Насьональ": 25, "Первая лига Англии": 30,
    }

    def trophy_weight(trophy: str) -> int:
        t = trophy.lower()
        if "лига чемпионов" in t:
            return 500
        if "лига европы" in t:
            return 350
        if "лига конференций" in t:
            return 200
        if "🥇 чемпион" in t:
            return 150
        if "🏆 кубок" in t:
            return 120
        if "⬆️ выход" in t:
            return 80
        if "🥇 золотой мяч" in t or "🧤 золотая перчатка" in t:
            return 0
        return 30

    club_scores = {}

    for uid, pdata in players.items():
        if pdata.get("retired"):
            continue
        club = pdata.get("club")
        division = pdata.get("division")
        if not club or not division:
            continue
        if uid not in tables or division not in tables[uid]:
            continue

        table = tables[uid][division]
        row = next((r for r in table if r["club"] == club), None)
        if not row:
            continue

        points = row["points"]
        wins = row["wins"]

        club_trophies = pdata.get("trophies", [])
        trophy_score = sum(trophy_weight(t) for t in club_trophies)

        div_weight = DIVISION_WEIGHT.get(division, 30)

        euro_bonus = 0
        if euro_data:
            tournament = pdata.get("euro_tournament")
            if tournament and tournament != "none" and tournament in euro_data:
                euro_bonus += 100
                if euro_data.get("status") == "playoff":
                    euro_bonus += 150
                stage = pdata.get("euro_playoff_stage")
                if stage == "round_16":
                    euro_bonus += 100
                elif stage == "quarter":
                    euro_bonus += 200
                elif stage == "semi":
                    euro_bonus += 350
                elif stage == "final":
                    euro_bonus += 500

        score = (
            points * 2 +
            wins * 3 +
            div_weight * 2 +
            trophy_score +
            euro_bonus
        )

        if club not in club_scores or score > club_scores[club]["score"]:
            club_scores[club] = {
                "club": club,
                "points": points,
                "wins": wins,
                "division": division,
                "trophies": len(club_trophies),
                "euro_bonus": euro_bonus,
                "score": score
            }

    for club, npc_list in npc_data.items():
        if club in club_scores:
            continue
        division = None
        for d, clubs in CLUBS.items():
            if club in clubs:
                division = d
                break
        if not division:
            continue

        club_rating = CLUB_RATINGS.get(club, 50)
        div_weight = DIVISION_WEIGHT.get(division, 30)

        score = club_rating * 1.5 + div_weight * 2

        club_scores[club] = {
            "club": club,
            "points": 0,
            "wins": 0,
            "division": division,
            "trophies": 0,
            "euro_bonus": 0,
            "score": score
        }

    best_club = max(club_scores.values(), key=lambda x: x["score"]) if club_scores else None

    awards = {
        "season": season_num,
        "best_club": best_club,
        "golden_ball": golden_ball,
        "golden_glove": golden_glove,
        "best_defender": best_defender,
        "best_assistant": best_assistant
    }

    all_awards = await load_data(AWARDS_FILE)
    if user_id not in all_awards:
        all_awards[user_id] = {}
    all_awards[user_id][f"season_{season_num}"] = awards
    await save_data(AWARDS_FILE, all_awards)

    return awards


async def apply_awards_bonuses(user_id, awards, season_num):
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        return []

    bonuses = []

    gb = awards.get("golden_ball")
    if gb and gb.get("is_player"):
        p["rating"] = min(100, p["rating"] + 1.0)
        p["money"] = p.get("money", 0) + 500000
        p["trophies"] = p.get("trophies", []) + [f"🥇 Золотой мяч (Сезон {season_num})"]
        bonuses.append("🥇 Золотой мяч: +1.0 рейтинг, +500,000$")

    gg = awards.get("golden_glove")
    if gg and gg.get("is_player"):
        p["rating"] = min(100, p["rating"] + 0.5)
        p["money"] = p.get("money", 0) + 300000
        p["trophies"] = p.get("trophies", []) + [f"🧤 Золотая перчатка (Сезон {season_num})"]
        bonuses.append("🧤 Золотая перчатка: +0.5 рейтинг, +300,000$")

    bd = awards.get("best_defender")
    if bd and bd.get("is_player"):
        p["rating"] = min(100, p["rating"] + 0.5)
        p["money"] = p.get("money", 0) + 300000
        p["trophies"] = p.get("trophies", []) + [f"🛡️ Лучший защитник (Сезон {season_num})"]
        bonuses.append("🛡️ Лучший защитник: +0.5 рейтинг, +300,000$")

    ba = awards.get("best_assistant")
    if ba and ba.get("is_player"):
        p["rating"] = min(100, p["rating"] + 0.3)
        p["money"] = p.get("money", 0) + 200000
        p["trophies"] = p.get("trophies", []) + [f"🅰️ Лучший ассистент (Сезон {season_num})"]
        bonuses.append("🅰️ Лучший ассистент: +0.3 рейтинг, +200,000$")

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    return bonuses


# ========== ЕВРОКУБКИ - СПРАВОЧНИКИ ==========

EURO_TOURNAMENTS = {
    "champions_league": {
        "name": "🏆 Лига Чемпионов", "emoji": "🏆",
        "prize_win": 150000, "prize_draw": 50000,
        "prize_top8": 500000, "prize_winner": 5000000,
        "rating_bonus_winner": 2.0
    },
    "europa_league": {
        "name": "🥈 Лига Европы", "emoji": "🥈",
        "prize_win": 100000, "prize_draw": 30000,
        "prize_top8": 300000, "prize_winner": 2500000,
        "rating_bonus_winner": 1.0
    },
    "conference_league": {
        "name": "🥉 Лига Конференций", "emoji": "🥉",
        "prize_win": 50000, "prize_draw": 15000,
        "prize_top8": 150000, "prize_winner": 1000000,
        "rating_bonus_winner": 0.5
    }
}

EURO_TOTAL_TOURS = 8


def get_club_country(club):
    for div, clubs in CLUBS.items():
        if club in clubs:
            if div in ["ФНЛ 2", "ФНЛ", "РПЛ"]: return "Россия"
            elif div in ["Насьональ", "Лига 2", "Лига 1"]: return "Франция"
            elif div in ["Первая лига Англии", "Чемпионшип", "АПЛ"]: return "Англия"
            elif div in ["Сегунда", "Ла Лига"]: return "Испания"
            elif div in ["Серия Б", "Серия А"]: return "Италия"
            elif div in ["Вторая Бундеслига", "Бундеслига"]: return "Германия"
            elif div in ["Сегунда лига", "Примейра"]: return "Португалия"
            elif div in ["Эрстедивизи", "Эредивизи"]: return "Нидерланды"
            elif div == "Jupiler Pro League": return "Бельгия"
            elif div in ["Беларусь Первая лига", "Беларусь Высшая лига"]: return "Беларусь"
            elif div in ["Турция Первая лига", "Турция Суперлига"]: return "Турция"
            elif div == "Казахстан Премьер-лига": return "Казахстан"
            elif div == "Бразильская Серия А": return "Бразилия"
    return "Неизвестно"


def get_euro_tournament_by_position(division, position):
    top_leagues_champions = ["РПЛ", "АПЛ", "Ла Лига", "Серия А", "Бундеслига", "Лига 1", "Примейра", "Эредивизи"]
    second_leagues = ["ФНЛ", "Лига 2", "Чемпионшип", "Сегунда", "Серия Б", "Вторая Бундеслига",
                      "Сегунда лига", "Эрстедивизи", "Jupiler Pro League", "Беларусь Высшая лига",
                      "Турция Суперлига", "Казахстан Премьер-лига", "Бразильская Серия А"]
    third_leagues = ["ФНЛ 2", "Насьональ", "Первая лига Англии", "Беларусь Первая лига", "Турция Первая лига"]

    if division in third_leagues:
        return None

    if division in top_leagues_champions:
        if position <= 4: return "champions_league"
        elif position <= 6: return "europa_league"
        elif position <= 8: return "conference_league"
    elif division in second_leagues:
        if position == 1: return "europa_league"
        elif position <= 3: return "conference_league"

    return None


async def generate_euro_data(season):
    euro_data = {
        "season": season,
        "champions_league": {"clubs": [], "table": {}, "fixtures": {}, "played": 0, "current_tour": 1},
        "europa_league": {"clubs": [], "table": {}, "fixtures": {}, "played": 0, "current_tour": 1},
        "conference_league": {"clubs": [], "table": {}, "fixtures": {}, "played": 0, "current_tour": 1},
        "playoffs": {
            "champions_league": {"round_16": [], "quarter": [], "semi": [], "final": None, "current_stage": "round_16", "top8": [], "playoff_round": [], "playoff_winners": []},
            "europa_league": {"round_16": [], "quarter": [], "semi": [], "final": None, "current_stage": "round_16", "top8": [], "playoff_round": [], "playoff_winners": []},
            "conference_league": {"round_16": [], "quarter": [], "semi": [], "final": None, "current_stage": "round_16", "top8": [], "playoff_round": [], "playoff_winners": []}
        },
        "status": "group",
        "tour_played": {i: False for i in range(1, EURO_TOTAL_TOURS + 1)}
    }

    participants = await determine_euro_participants(season)

    for tournament in ["champions_league", "europa_league", "conference_league"]:
        clubs = participants.get(tournament, [])
        euro_data[tournament]["clubs"] = clubs

        for club in clubs:
            euro_data[tournament]["table"][club] = {
                "points": 0, "goals_for": 0, "goals_against": 0,
                "played": 0, "wins": 0, "draws": 0, "losses": 0
            }

    for tournament in ["champions_league", "europa_league", "conference_league"]:
        clubs = euro_data[tournament]["clubs"]
        if len(clubs) >= 8:
            euro_data[tournament]["fixtures"] = generate_swiss_fixtures(clubs)

    await save_data(EURO_FILE, euro_data)
    return euro_data


async def determine_euro_participants(season):
    tables = await load_data(TABLES_FILE)
    players = await load_data(PLAYERS_FILE)

    all_club_positions = {}

    for user_id, p in players.items():
        if p.get("retired"):
            continue

        club = p.get("club")
        division = p.get("division")

        if not club or not division:
            continue

        if user_id in tables and division in tables[user_id]:
            table = tables[user_id][division]
            position = next((i + 1 for i, row in enumerate(table) if row["club"] == club), None)
            if position:
                if club not in all_club_positions or position < all_club_positions[club]["position"]:
                    all_club_positions[club] = {"division": division, "position": position, "user_id": user_id}

    champions, europa, conference = [], [], []

    for club, info in all_club_positions.items():
        t = get_euro_tournament_by_position(info["division"], info["position"])
        if t == "champions_league": champions.append(club)
        elif t == "europa_league": europa.append(club)
        elif t == "conference_league": conference.append(club)

    champions = list(set(champions))
    europa = list(set(europa))
    conference = list(set(conference))

    all_top_clubs = []
    for league in ["РПЛ", "АПЛ", "Ла Лига", "Серия А", "Бундеслига", "Лига 1", "Примейра", "Эредивизи"]:
        all_top_clubs.extend(CLUBS.get(league, []))
    all_top_clubs = list(set(all_top_clubs))

    used_clubs = set(champions + europa + conference)
    available = [c for c in all_top_clubs if c not in used_clubs]
    random.shuffle(available)

    while len(champions) < 36 and available: champions.append(available.pop())
    while len(europa) < 36 and available: europa.append(available.pop())
    while len(conference) < 36 and available: conference.append(available.pop())

    return {
        "champions_league": champions[:36],
        "europa_league": europa[:36],
        "conference_league": conference[:36]
    }


def generate_swiss_fixtures(clubs):
    if len(clubs) < 8:
        return {}

    clubs = list(clubs)
    random.shuffle(clubs)

    if len(clubs) % 2 == 1:
        clubs.append("__BYE__")

    n = len(clubs)
    fixtures = {club: [] for club in clubs if club != "__BYE__"}

    fixed = clubs[0]
    rotating = clubs[1:]

    tour_num = 0

    for r in range(n - 1):
        if tour_num >= EURO_TOTAL_TOURS:
            break

        round_pairs = [(fixed, rotating[0])]
        for i in range(1, n // 2):
            round_pairs.append((rotating[i], rotating[n - 1 - i]))

        valid_pairs = [(a, b) for a, b in round_pairs if a != "__BYE__" and b != "__BYE__"]

        if not valid_pairs:
            rotating = [rotating[-1]] + rotating[:-1]
            continue

        tour_num += 1

        for a, b in valid_pairs:
            home_a = random.choice([True, False])

            fixtures[a].append({
                "opponent": b,
                "home": home_a,
                "tour": tour_num,
                "played": False,
                "goals_for": 0,
                "goals_against": 0,
                "result": None
            })
            fixtures[b].append({
                "opponent": a,
                "home": not home_a,
                "tour": tour_num,
                "played": False,
                "goals_for": 0,
                "goals_against": 0,
                "result": None
            })

        rotating = [rotating[-1]] + rotating[:-1]

    for club in fixtures:
        fixtures[club].sort(key=lambda m: m["tour"])

    return fixtures


async def get_euro_fixture(user_id):
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        return None

    euro_data = await load_data(EURO_FILE)
    if not euro_data or euro_data.get("status") != "group":
        return None

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        return None

    fixtures = euro_data[tournament]["fixtures"].get(p["club"], [])
    if not fixtures:
        return None

    for fixture in fixtures:
        if not fixture.get("played", False):
            return fixture

    return None


async def get_euro_position(user_id):
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        return None

    euro_data = await load_data(EURO_FILE)
    if not euro_data:
        return None

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        return None

    table = euro_data[tournament]["table"]
    sorted_table = sorted(
        table.items(),
        key=lambda x: (x[1]["points"], x[1]["goals_for"] - x[1]["goals_against"]),
        reverse=True
    )

    for i, (club, _) in enumerate(sorted_table, 1):
        if club == p["club"]:
            return i

    return None


def get_euro_name(tournament):
    names = {
        "champions_league": "🏆 Лига Чемпионов",
        "europa_league": "🥈 Лига Европы",
        "conference_league": "🥉 Лига Конференций"
    }
    return names.get(tournament, "❌ Нет")


def get_euro_stage_name(stage):
    names = {
        "playoff_round": "Стыковые матчи",
        "round_16": "1/8 финала",
        "quarter": "1/4 финала",
        "semi": "Полуфинал",
        "final": "Финал"
    }
    return names.get(stage, stage)


async def simulate_euro_match(club1, club2, home_advantage=True):
    rating1 = CLUB_RATINGS.get(club1, 50)
    rating2 = CLUB_RATINGS.get(club2, 50)

    if home_advantage:
        rating1 += 5
    else:
        rating2 += 5

    win_chance = 0.4 + ((rating1 - rating2) * 0.005)
    win_chance = max(0.1, min(0.9, win_chance))

    rand = random.random()

    if rand < win_chance:
        goals1 = random.randint(1, 3)
        goals2 = random.randint(0, goals1 - 1)
        return goals1, goals2, "win1"
    elif rand < win_chance + 0.15:
        goals = random.randint(0, 2)
        return goals, goals, "draw"
    else:
        goals2 = random.randint(1, 3)
        goals1 = random.randint(0, goals2 - 1)
        return goals1, goals2, "win2"


async def simulate_euro_tour(euro_data, tournament, tour_number):
    fixtures = euro_data[tournament]["fixtures"]
    table = euro_data[tournament]["table"]

    tour_matches = []
    seen_pairs = set()
    for club, matches in fixtures.items():
        for match in matches:
            if match["tour"] != tour_number:
                continue
            if match.get("played", False):
                continue
            pair_key = tuple(sorted([club, match["opponent"]]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            tour_matches.append({
                "club1": club,
                "club2": match["opponent"],
                "home1": match["home"],
            })

    if not tour_matches:
        return euro_data

    for match_info in tour_matches:
        club1 = match_info["club1"]
        club2 = match_info["club2"]
        home1 = match_info["home1"]

        goals1, goals2, result = await simulate_euro_match(club1, club2, home1)

        if club1 in table:
            table[club1]["goals_for"] += goals1
            table[club1]["goals_against"] += goals2
            table[club1]["played"] += 1
            if result == "win1":
                table[club1]["points"] += 3; table[club1]["wins"] += 1
            elif result == "draw":
                table[club1]["points"] += 1; table[club1]["draws"] += 1
            else:
                table[club1]["losses"] += 1

        if club2 in table:
            table[club2]["goals_for"] += goals2
            table[club2]["goals_against"] += goals1
            table[club2]["played"] += 1
            if result == "win2":
                table[club2]["points"] += 3; table[club2]["wins"] += 1
            elif result == "draw":
                table[club2]["points"] += 1; table[club2]["draws"] += 1
            else:
                table[club2]["losses"] += 1

        for club in (club1, club2):
            for m in fixtures.get(club, []):
                if m["tour"] == tour_number and m["opponent"] == (club2 if club == club1 else club1):
                    m["played"] = True
                    if club == club1:
                        m["goals_for"] = goals1
                        m["goals_against"] = goals2
                        m["result"] = result if result == "win1" else ("draw" if result == "draw" else "loss")
                    else:
                        m["goals_for"] = goals2
                        m["goals_against"] = goals1
                        m["result"] = result if result == "win2" else ("draw" if result == "draw" else "loss")

    euro_data[tournament]["played"] += len(tour_matches)
    euro_data["tour_played"][tour_number] = True
    return euro_data


async def simulate_euro_playoff_match(club1, club2):
    rating1 = CLUB_RATINGS.get(club1, 50)
    rating2 = CLUB_RATINGS.get(club2, 50)

    win_chance = 0.45 + ((rating1 - rating2) * 0.005)
    win_chance = max(0.15, min(0.85, win_chance))

    rand = random.random()

    if rand < win_chance:
        goals1 = random.randint(1, 3)
        goals2 = random.randint(0, goals1 - 1)
        return goals1, goals2, club1
    elif rand < win_chance + 0.15:
        goals = random.randint(0, 2)
        if random.random() < 0.5:
            return goals, goals, club1
        else:
            return goals, goals, club2
    else:
        goals2 = random.randint(1, 3)
        goals1 = random.randint(0, goals2 - 1)
        return goals1, goals2, club2


async def simulate_euro_playoff_match_pair(club1, club2):
    return await simulate_euro_playoff_match(club1, club2)


async def generate_euro_playoffs(euro_data, tournament):
    table = euro_data[tournament]["table"]
    sorted_table = sorted(
        table.items(),
        key=lambda x: (x[1]["points"], x[1]["goals_for"] - x[1]["goals_against"]),
        reverse=True
    )

    top8 = [club for club, _ in sorted_table[:8]]
    playoff_teams = [club for club, _ in sorted_table[8:24]]

    random.shuffle(playoff_teams)
    playoff_pairs = []
    for i in range(0, len(playoff_teams), 2):
        if i + 1 < len(playoff_teams):
            playoff_pairs.append((playoff_teams[i], playoff_teams[i + 1]))

    euro_data["playoffs"][tournament]["playoff_round"] = playoff_pairs
    euro_data["playoffs"][tournament]["playoff_winners"] = []
    euro_data["playoffs"][tournament]["round_16"] = []
    euro_data["playoffs"][tournament]["quarter"] = []
    euro_data["playoffs"][tournament]["semi"] = []
    euro_data["playoffs"][tournament]["final"] = None
    euro_data["playoffs"][tournament]["current_stage"] = "playoff_round"
    euro_data["playoffs"][tournament]["top8"] = top8

    await save_data(EURO_FILE, euro_data)


async def simulate_playoff_round(euro_data, tournament, player_club=None, player_won=None):
    playoffs = euro_data["playoffs"][tournament]
    pairs = playoffs.get("playoff_round", [])
    if not pairs:
        return []

    winners = []
    for a, b in pairs:
        if player_club and player_club in (a, b):
            if player_won is True:
                winners.append(player_club)
            elif player_won is False:
                winners.append(b if a == player_club else a)
            else:
                _, _, w = await simulate_euro_playoff_match(a, b)
                winners.append(w)
        else:
            _, _, w = await simulate_euro_playoff_match(a, b)
            winners.append(w)

    playoffs["playoff_winners"] = winners

    top8 = playoffs.get("top8", [])
    round_16_teams = top8 + winners

    random.shuffle(round_16_teams)
    round_16 = []
    for i in range(0, len(round_16_teams), 2):
        if i + 1 < len(round_16_teams):
            round_16.append((round_16_teams[i], round_16_teams[i + 1]))

    playoffs["round_16"] = round_16
    playoffs["current_stage"] = "round_16"

    await save_data(EURO_FILE, euro_data)
    return winners


async def simulate_playoff_round_without_player(euro_data, tournament):
    playoffs = euro_data["playoffs"][tournament]
    pairs = playoffs.get("playoff_round", [])
    if not pairs:
        return []

    winners = []
    for a, b in pairs:
        _, _, w = await simulate_euro_playoff_match(a, b)
        winners.append(w)

    playoffs["playoff_winners"] = winners

    top8 = playoffs.get("top8", [])
    round_16_teams = top8 + winners

    random.shuffle(round_16_teams)
    round_16 = []
    for i in range(0, len(round_16_teams), 2):
        if i + 1 < len(round_16_teams):
            round_16.append((round_16_teams[i], round_16_teams[i + 1]))

    playoffs["round_16"] = round_16
    playoffs["current_stage"] = "round_16"

    await save_data(EURO_FILE, euro_data)
    return winners


async def advance_playoff_round(euro_data, tournament, from_stage, player_club=None, player_won=None):
    stage_order = ["round_16", "quarter", "semi", "final"]
    if from_stage not in stage_order:
        return euro_data

    idx = stage_order.index(from_stage)
    if idx >= len(stage_order) - 1:
        return euro_data

    next_stage = stage_order[idx + 1]
    pairs = euro_data["playoffs"][tournament].get(from_stage, [])
    if not pairs:
        return euro_data

    existing_next = euro_data["playoffs"][tournament].get(next_stage)
    if existing_next:
        return euro_data

    winners = []
    for a, b in pairs:
        if player_club and player_club in (a, b):
            if player_won is True:
                winners.append(player_club)
            elif player_won is False:
                winners.append(b if a == player_club else a)
            else:
                _, _, w = await simulate_euro_playoff_match(a, b)
                winners.append(w)
        else:
            _, _, w = await simulate_euro_playoff_match(a, b)
            winners.append(w)

    random.shuffle(winners)
    next_pairs = []
    for i in range(0, len(winners), 2):
        if i + 1 < len(winners):
            next_pairs.append((winners[i], winners[i + 1]))

    euro_data["playoffs"][tournament][next_stage] = next_pairs
    euro_data["playoffs"][tournament]["current_stage"] = next_stage
    await save_data(EURO_FILE, euro_data)
    return euro_data


# ========== ГЛАВНОЕ МЕНЮ ==========

async def main_menu_keyboard(username: str = None, user_id: str = None):
    match_btn_text = "🎮 Матч"
    euro_button = None

    if user_id:
        p = (await load_data(PLAYERS_FILE)).get(user_id)
        if p:
            if p.get("tour", 1) > 30:
                match_btn_text = "🏁 Итоги сезона"
            if p.get("euro_tournament") and p.get("euro_tournament") != "none":
                euro_button = [InlineKeyboardButton(text="🌍 Еврокубки", callback_data="menu_euro")]

    kb = [
        [InlineKeyboardButton(text="🏋️‍♂️ Тренировка", callback_data="menu_train_choice"),
         InlineKeyboardButton(text=match_btn_text, callback_data="menu_match")],
        [InlineKeyboardButton(text="📊 Таблица", callback_data="menu_table"),
         InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")],
        [InlineKeyboardButton(text="🍷 Личная жизнь", callback_data="menu_personal_life"),
         InlineKeyboardButton(text="🏆 Зал Славы", callback_data="menu_leaderboard")],
        [InlineKeyboardButton(text="🎯 Квесты", callback_data="menu_quests"),
         InlineKeyboardButton(text="💰 Спонсоры", callback_data="menu_sponsors")],
        [InlineKeyboardButton(text="🏆 Номинации сезона", callback_data="menu_awards")],
        [InlineKeyboardButton(text="📊 Статистика лиги", callback_data="menu_league_stats")],
        [InlineKeyboardButton(text="🟢 Онлайн / Топ", callback_data="menu_online")]
    ]

    if euro_button:
        kb.insert(3, euro_button)

    if username and username.replace("@", "") in ADMINS:
        kb.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


async def send_auto_delete_message(message: Message, text: str, parse_mode: str = "Markdown",
                                    reply_markup=None, delay: int = 3):
    sent = await message.answer(text, parse_mode=parse_mode, reply_markup=reply_markup)
    await asyncio.sleep(delay)
    try:
        await sent.delete()
    except Exception:
        pass


# ============================================================
# НОМИНАЦИИ СЕЗОНА
# ============================================================

@dp.callback_query(F.data == "menu_awards")
@with_user_lock
async def awards_menu_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    all_awards = await load_data(AWARDS_FILE)
    player_awards = all_awards.get(user_id, {})

    if not player_awards:
        await callback.message.edit_text(
            "🏆 **НОМИНАЦИИ СЕЗОНА**\n\n"
            "Номинации за этот сезон ещё не подведены.\n"
            "Они появятся после завершения сезона!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
            ])
        )
        return

    latest = sorted(player_awards.keys(), key=lambda x: int(x.split("_")[1]))[-1]
    awards = player_awards[latest]
    season_num = latest.split("_")[1]

    text = f"🏆 **НОМИНАЦИИ СЕЗОНА {season_num}**\n━━━━━━━━━━━━━━━━━━━━\n\n"

    if awards.get("best_club"):
        bc = awards["best_club"]
        text += f"🏟 **Лучший клуб:** {bc['club']}\n"
        text += f"   Очки: {bc['points']} | Победы: {bc['wins']}\n"
        if bc.get("division"):
            text += f"   Дивизион: {bc['division']}\n"
        if bc.get("trophies"):
            text += f"   Трофеев: {bc['trophies']}\n"
        if bc.get("euro_bonus"):
            text += f"   Еврокубки: +{bc['euro_bonus']} очков\n"
        text += "\n"

    if awards.get("golden_ball"):
        gb = awards["golden_ball"]
        mark = "⭐ " if gb.get("is_player") else ""
        text += f"🥇 **Золотой мяч:** {mark}{gb['name']} ({gb['club']})\n"
        text += f"   Рейтинг: {gb['rating']} | Голы: {gb['stats'].get('goals', 0)} | Ассисты: {gb['stats'].get('assists', 0)}\n\n"

    if awards.get("golden_glove"):
        gg = awards["golden_glove"]
        mark = "⭐ " if gg.get("is_player") else ""
        text += f"🧤 **Золотая перчатка:** {mark}{gg['name']} ({gg['club']})\n"
        text += f"   Сейвы: {gg['stats'].get('saves', 0)} | Рейтинг: {gg['rating']}\n\n"

    if awards.get("best_defender"):
        bd = awards["best_defender"]
        mark = "⭐ " if bd.get("is_player") else ""
        text += f"🛡️ **Лучший защитник:** {mark}{bd['name']} ({bd['club']})\n"
        text += f"   Отборы: {bd['stats'].get('tackles', 0)} | Рейтинг: {bd['rating']}\n\n"

    if awards.get("best_assistant"):
        ba = awards["best_assistant"]
        mark = "⭐ " if ba.get("is_player") else ""
        text += f"🅰️ **Лучший ассистент:** {mark}{ba['name']} ({ba['club']})\n"
        text += f"   Ассисты: {ba['stats'].get('assists', 0)} | Рейтинг: {ba['rating']}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Прошлые сезоны", callback_data="awards_history")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "awards_history")
@with_user_lock
async def awards_history_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    all_awards = await load_data(AWARDS_FILE)
    player_awards = all_awards.get(user_id, {})

    if not player_awards:
        await callback.answer("Пока нет данных", show_alert=True)
        return

    text = "📜 **ИСТОРИЯ НОМИНАЦИЙ**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for season_key in sorted(player_awards.keys(), key=lambda x: int(x.split("_")[1])):
        season_num = season_key.split("_")[1]
        awards = player_awards[season_key]
        text += f"**Сезон {season_num}:**\n"
        if awards.get("golden_ball"):
            gb = awards["golden_ball"]
            mark = "⭐ " if gb.get("is_player") else ""
            text += f"🥇 ЗМ: {mark}{gb['name']}\n"
        if awards.get("golden_glove"):
            gg = awards["golden_glove"]
            mark = "⭐ " if gg.get("is_player") else ""
            text += f"🧤 ЗП: {mark}{gg['name']}\n"
        if awards.get("best_defender"):
            bd = awards["best_defender"]
            mark = "⭐ " if bd.get("is_player") else ""
            text += f"🛡️ ЛЗ: {mark}{bd['name']}\n"
        if awards.get("best_assistant"):
            ba = awards["best_assistant"]
            mark = "⭐ " if ba.get("is_player") else ""
            text += f"🅰️ ЛА: {mark}{ba['name']}\n"
        if awards.get("best_club"):
            text += f"🏟 Клуб: {awards['best_club']['club']}\n"
        text += "\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_awards")]
    ])
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest:
        pass


# ============================================================
# СТАТИСТИКА ЛИГИ
# ============================================================

@dp.callback_query(F.data == "menu_league_stats")
@with_user_lock
async def league_stats_menu_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    division = p.get("division", "ФНЛ 2")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚽ Бомбардиры", callback_data="league_top:goals"),
         InlineKeyboardButton(text="🅰️ Ассистенты", callback_data="league_top:assists")],
        [InlineKeyboardButton(text="🧤 Вратари (сейвы)", callback_data="league_top:saves"),
         InlineKeyboardButton(text="🛡️ Защитники (отборы)", callback_data="league_top:tackles")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

    text = (
        f"📊 **СТАТИСТИКА ЛИГИ: {division}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Выбери, что хочешь посмотреть:\n\n"
        "⚽ **Бомбардиры** — топ по голам\n"
        "🅰️ **Ассистенты** — топ по голевым пасам\n"
        "🧤 **Вратари** — топ по сейвам\n"
        "🛡️ **Защитники** — топ по отборам"
    )

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data.startswith("league_top:"))
@with_user_lock
async def league_top_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    stat_type = callback.data.split(":")[1]
    division = p.get("division", "ФНЛ 2")

    all_players = await get_league_players(division, exclude_user_id=user_id)

    if stat_type == "saves":
        candidates = [x for x in all_players if x["position"] == "GK"]
        stat_label = "СЕЙВЫ"
        stat_key = "saves"
        stat_emoji = "🧤"
    elif stat_type == "tackles":
        candidates = [x for x in all_players if x["position"] == "CB"]
        stat_label = "ОТБОРЫ"
        stat_key = "tackles"
        stat_emoji = "🛡️"
    elif stat_type == "assists":
        candidates = all_players
        stat_label = "АССИСТЫ"
        stat_key = "assists"
        stat_emoji = "🅰️"
    else:
        candidates = all_players
        stat_label = "ГОЛЫ"
        stat_key = "goals"
        stat_emoji = "⚽"

    candidates = sorted(
        candidates,
        key=lambda x: x["stats"].get(stat_key, 0),
        reverse=True
    )

    player_position = None
    for i, c in enumerate(candidates, 1):
        if c.get("is_player") and c.get("user_id") == user_id:
            player_position = i
            break

    text = f"{stat_emoji} **ТОП-15 {stat_label}**\n"
    text += f"📊 Лига: **{division}**\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 12
    for i, c in enumerate(candidates[:15], 1):
        value = c["stats"].get(stat_key, 0)
        club = c.get("club", "—")
        is_me = c.get("is_player") and c.get("user_id") == user_id
        marker = "👉 " if is_me else ""
        name_display = f"**{c['name']}**" if is_me else c['name']
        text += f"{medals[i-1]} {marker}{name_display} ({club}) — **{value}**\n"

    if player_position and player_position > 15:
        player_data = next((c for c in candidates if c.get("is_player") and c.get("user_id") == user_id), None)
        if player_data:
            value = player_data["stats"].get(stat_key, 0)
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
            text += f"👉 **Ты:** {player_position} место — {value} {stat_key}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К выбору", callback_data="menu_league_stats")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]
    ])

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


# ============================================================
# ЕВРОКУБКИ - МЕНЮ
# ============================================================

@dp.callback_query(F.data == "menu_euro")
@with_user_lock
async def euro_menu_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data or not euro_data.get("status"):
        try:
            await callback.message.edit_text(
                "🌍 Еврокубки еще не начались.\nДождись окончания сезона!",
                reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
            )
        except TelegramBadRequest:
            pass
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament == "none" or tournament not in euro_data:
        try:
            await callback.message.edit_text(
                "🌍 Твой клуб не участвует в еврокубках в этом сезоне.",
                reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
            )
        except TelegramBadRequest:
            pass
        return

    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    table = euro_data[tournament]["table"]
    fixtures = euro_data[tournament]["fixtures"].get(p["club"], [])

    played = sum(1 for f in fixtures if f.get("played", False))
    total = len(fixtures) if fixtures else EURO_TOTAL_TOURS

    position = await get_euro_position(user_id)
    status_text = "Групповой этап" if euro_data.get("status") == "group" else "Плей-офф"

    text = f"{euro_info.get('emoji', '🌍')} **{euro_info.get('name', 'Еврокубки')}**\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 Статус: {status_text}\n"
    text += f"📈 Твое место: {position if position else '?'} из {len(table)}\n"
    text += f"📅 Сыграно туров: {played}/{total}\n"

    if p["club"] in table:
        stats = table[p["club"]]
        text += f"📊 Очки: {stats['points']} | Голы: {stats['goals_for']}:{stats['goals_against']}\n"

    if fixtures:
        text += "\n📋 **Календарь:**\n"
        for i, f in enumerate(fixtures[:EURO_TOTAL_TOURS], 1):
            status = "✅" if f.get("played") else "⏳"
            home = "🏠" if f.get("home") else "✈️"
            result = ""
            if f.get("played"):
                gf = f.get("goals_for", 0)
                ga = f.get("goals_against", 0)
                result = "✅ Победа" if gf > ga else ("🤝 Ничья" if gf == ga else "❌ Поражение")
            text += f"{status} Тур {i}: {home} {f['opponent']} {result}\n"

    buttons = []

    next_match = next((f for f in fixtures if not f.get("played", False)), None)

    if next_match and euro_data.get("status") == "group":
        if p.get("trust", 15) >= 21:
            buttons.append([InlineKeyboardButton(text="▶️ Следующий матч", callback_data="euro_play_match")])
        else:
            buttons.append([InlineKeyboardButton(text="▶️ Смотреть матч (ты в резерве)",
                                                 callback_data="euro_simulate_match")])

    if euro_data.get("status") == "group" and played >= total and total > 0:
        buttons.append([InlineKeyboardButton(text="📊 Итоги группового этапа",
                                             callback_data="euro_group_results")])

    if euro_data.get("status") == "playoff":
        if p.get("euro_tournament") and p.get("euro_tournament") != "none" \
                and p.get("euro_playoff_stage") not in (None, "eliminated"):
            buttons.append([InlineKeyboardButton(text="🏆 Плей-офф (сыграть матч)",
                                                 callback_data="euro_playoff_menu")])
        else:
            buttons.append([InlineKeyboardButton(text="🏆 Плей-офф", callback_data="euro_playoff_menu")])

    buttons.append([InlineKeyboardButton(text="📊 Полная таблица", callback_data="euro_table_full")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "euro_simulate_match")
@with_user_lock
async def euro_simulate_match_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data or euro_data.get("status") != "group":
        await callback.answer("Групповой этап уже завершен")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    fixture = await get_euro_fixture(user_id)
    if not fixture:
        await callback.answer("Все матчи сыграны!")
        return

    tour = fixture["tour"]

    euro_data = await simulate_euro_tour(euro_data, tournament, tour)
    await save_data(EURO_FILE, euro_data)

    gf = ga = 0
    for match in euro_data[tournament]["fixtures"].get(p["club"], []):
        if match["tour"] == tour:
            gf = match.get("goals_for", 0)
            ga = match.get("goals_against", 0)
            result_text = "🏆 **ПОБЕДА!**" if gf > ga else ("🤝 **НИЧЬЯ**" if gf == ga else "❌ **ПОРАЖЕНИЕ**")
            break

    p["euro_matches"] = p.get("euro_matches", 0) + 1
    players = await load_data(PLAYERS_FILE)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    fixtures = euro_data[tournament]["fixtures"].get(p["club"], [])
    all_played = all(f.get("played", False) for f in fixtures)

    extra = ""
    if all_played and len(fixtures) >= EURO_TOTAL_TOURS:
        euro_data["status"] = "playoff"
        await generate_euro_playoffs(euro_data, tournament)
        await save_data(EURO_FILE, euro_data)
        position = await get_euro_position(user_id)

        if position and position <= 8:
            p["euro_playoff_stage"] = "round_16"
            p["playoff_round_played"] = True
            extra = "\n\n🎉 Ты прошёл в 1/8 финала!"
        elif position and position <= 24:
            p["euro_playoff_stage"] = "playoff_round"
            extra = "\n\n⚔️ Ты попал в стыковые матчи!"
        else:
            p["euro_tournament"] = "none"
            p["euro_playoff_stage"] = "eliminated"
            extra = "\n\n😔 Ты вылетел из еврокубков."

        players[user_id] = p
        await save_data(PLAYERS_FILE, players)

    try:
        await callback.message.edit_text(
            f"📊 **МАТЧ СИМУЛИРОВАН!**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚔️ **{p['club']}** vs **{fixture['opponent']}**\n"
            f"Счет: **{gf} : {ga}**\n"
            f"{result_text}\n\n"
            f"🪑 Ты был в резерве и не участвовал в матче.{extra}",
            parse_mode="Markdown",
            reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "euro_table_full")
@with_user_lock
async def euro_table_full_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data:
        await callback.answer("Еврокубки не начались")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    await _render_euro_table(callback, user_id, p, euro_data, tournament, page=1)


@dp.callback_query(F.data.startswith("euro_table_page:"))
@with_user_lock
async def euro_table_page_handler(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    tournament = p.get("euro_tournament")
    if not euro_data or not tournament or tournament not in euro_data:
        await callback.answer("Еврокубки не начались")
        return

    await _render_euro_table(callback, user_id, p, euro_data, tournament, page)


async def _render_euro_table(callback, user_id, p, euro_data, tournament, page):
    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    table = euro_data[tournament]["table"]
    sorted_table = sorted(
        table.items(),
        key=lambda x: (x[1]["points"], x[1]["goals_for"] - x[1]["goals_against"]),
        reverse=True
    )

    per_page = 15
    total_pages = max(1, (len(sorted_table) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    text = f"📊 **ТАБЛИЦА {euro_info.get('name', '')}**\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "🏆 *Победа — 3 очка, Ничья — 1 очко*\n\n"

    start = (page - 1) * per_page
    end = min(start + per_page, len(sorted_table))

    for i, (club, stats) in enumerate(sorted_table[start:end], start + 1):
        is_p = "👉 " if club == p["club"] else "• "
        text += (f"{i}. {is_p}**{club}** — {stats['points']} очков "
                 f"({stats['played']} игр: {stats['wins']}В/{stats['draws']}Н/{stats['losses']}П)\n")

    text += f"\n📄 Страница {page}/{total_pages}"

    buttons = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"euro_table_page:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"euro_table_page:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "euro_play_match")
@with_user_lock
async def euro_play_match_handler(callback: CallbackQuery, state: FSMContext):
    user_id = await get_uid(callback)
    await track_activity(user_id)

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    if p.get("trust", 15) < 21:
        await callback.answer("❌ Ты в резерве! Подними доверие до 21, чтобы играть.", show_alert=True)
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data or euro_data.get("status") != "group":
        await callback.answer("Групповой этап уже завершен")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    fixture = await get_euro_fixture(user_id)
    if not fixture:
        await callback.answer("Все матчи сыграны!")
        return

    match_data = {
        "tournament": tournament,
        "opponent": fixture["opponent"],
        "home": fixture["home"],
        "tour": fixture["tour"],
        "goals": 0, "assists": 0, "saves": 0, "tackles": 0, "yellow_cards": 0,
        "my_score": 0, "opponent_score": 0,
        "log": "",
        "moment": 0,
        "total_moments": random.randint(2, 4),
        "minute": 0,
        "is_playoff": False,
        "stage": None,
        "stage_name": None,
    }
    await state.update_data(euro_match=match_data)

    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    home_text = "🏠 Дома" if fixture["home"] else "✈️ В гостях"

    text = (
        f"{euro_info.get('emoji', '🌍')} **{euro_info.get('name', 'Еврокубки')}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚔️ **{p['club']}** vs **{match_data['opponent']}**\n"
        f"📍 {home_text}\n"
        f"📅 Тур {match_data['tour']}/{EURO_TOTAL_TOURS}\n\n"
        f"🏟️ **Матч начался!**\n"
        f"🔥 Ты в основном составе!"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="euro_moment_next")]
    ])

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "euro_moment_next")
@with_user_lock
async def euro_moment_next_handler(callback: CallbackQuery, state: FSMContext):
    user_id = await get_uid(callback)
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        await callback.answer("Матч не найден")
        return
    if match.get("is_playoff"):
        await euro_playoff_moment(callback, state, user_id)
    else:
        await generate_euro_moment(callback, state, user_id)


async def generate_euro_moment(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        return

    match["minute"] = min(90, match.get("minute", 0) + random.randint(10, 25))

    my_rating = CLUB_RATINGS.get(p["club"], 50)
    rival_rating = CLUB_RATINGS.get(match["opponent"], 50)
    rating_diff = my_rating - rival_rating

    if random.random() < 0.45:
        if random.random() < 0.5:
            if random.random() < max(0.05, min(0.95, 0.40 - rating_diff * 0.02)):
                match["opponent_score"] += 1
                match["log"] += f"⚡ **{match['minute']}'** | ГОЛ! Соперник забивает!\n"
        else:
            if random.random() < max(0.05, min(0.95, 0.40 + rating_diff * 0.02)):
                match["my_score"] += 1
                match["log"] += f"⚽ **{match['minute']}'** | ГОЛ! Твоя команда забивает!\n"

    if random.random() < 0.35:
        flavor = random.choice([
            "🔥 Красивый финт в центре поля обостряет игру.",
            "📐 Подача углового, но защита выносит мяч.",
            "🟨 Судья показывает желтую карточку игроку соперника.",
            "⚔️ Жесткий стык, но судья не дает свисток.",
            "👐 Вратарь уверенно забирает мяч после навеса."
        ])
        match["log"] += f"⏱ **{match['minute']}'** | {flavor}\n"

    if random.random() < 0.06:
        if random.random() < 0.15:
            match["log"] += f"🟥 **{match['minute']}'** | ПРЯМАЯ КРАСНАЯ! Ты удален с поля!\n"
            match["minute"] = 90
        else:
            match["log"] += f"🟨 **{match['minute']}'** | Желтая карточка тебе.\n"
            match["yellow_cards"] = match.get("yellow_cards", 0) + 1
            if match["yellow_cards"] >= 2:
                match["log"] += f"🟥 **{match['minute']}'** | ВТОРАЯ ЖЕЛТАЯ — УДАЛЕНИЕ!\n"
                match["minute"] = 90

    if match["moment"] >= match["total_moments"] or match["minute"] >= 90:
        await finish_euro_match(callback, state, user_id)
        return

    match["moment"] += 1
    await state.update_data(euro_match=match)

    text = (
        f"⏱ **{match['minute']}' МИНУТА** | Момент {match['moment']}/{match['total_moments']}\n"
        f"⚔️ **{p['club']}** vs **{match['opponent']}**\n"
        f"Счет: **{match['my_score']} : {match['opponent_score']}**\n\n"
        f"📝 **События матча:**\n{match['log'] or 'Идет плотная позиционная борьба...'}\n"
    )

    match["log"] = ""
    await state.update_data(euro_match=match)

    position = p.get("position", "ST")

    if position == "GK":
        text += "🚨 **Опасность! Нападающий соперника выходит один на один с тобой!**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧤 Прыгнуть в левый угол", callback_data="euro_gk:left"),
             InlineKeyboardButton(text="🧤 Прыгнуть в правый угол", callback_data="euro_gk:right")],
            [InlineKeyboardButton(text="🏃 Сблизить дистанцию", callback_data="euro_gk:rush")]
        ])
    elif position == "CB":
        if random.random() < 0.75:
            text += "🛡️ **Форвард соперника идет на дриблинге прямо в твою зону!**"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🧲 Жесткий подкат", callback_data="euro_cb:tackle_hard"),
                 InlineKeyboardButton(text="🕴️ Встретить корпусом", callback_data="euro_cb:tackle_smart")],
                [InlineKeyboardButton(text="📐 Отдать пас ближнему", callback_data="euro_act_pass")]
            ])
        else:
            text += "🔥 **Ты подключился на угловой! Мяч летит к тебе!**"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Пробить головой", callback_data="euro_shoot_menu"),
                 InlineKeyboardButton(text="📐 Сбросить под удар", callback_data="euro_act_pass")]
            ])
    else:
        text += "🔥 **Ты контролируешь мяч на подступах к штрафной! Твое решение?**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Пробить по воротам", callback_data="euro_shoot_menu"),
             InlineKeyboardButton(text="📐 Отдать пас", callback_data="euro_act_pass")]
        ])

    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "euro_group_results")
@with_user_lock
async def euro_group_results_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data:
        await callback.answer("Еврокубки не начались")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    position = await get_euro_position(user_id)
    euro_info = EURO_TOURNAMENTS.get(tournament, {})

    text = f"📊 **ИТОГИ ГРУППОВОГО ЭТАПА**\n"
    text += f"{euro_info.get('emoji', '')} {euro_info.get('name', '')}\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📈 Твое место: {position if position else '?'} из {len(euro_data[tournament]['table'])}\n\n"

    progressed = False
    if position and position <= 8:
        text += "🎉 **Поздравляю!**\nТы напрямую прошел в 1/8 финала!"
        p["euro_playoff_stage"] = "round_16"
        p["playoff_round_played"] = True
        progressed = True
    elif position and position <= 24:
        text += "⚔️ **Ты попал в стыковые матчи!**\nСыграй стык, чтобы выйти в 1/8 финала."
        p["euro_playoff_stage"] = "playoff_round"
        progressed = True
    else:
        text += "😔 **Вылет из еврокубков.**\nСосредоточься на следующем сезоне!"
        p["euro_tournament"] = "none"
        p["euro_playoff_stage"] = "eliminated"

    players = await load_data(PLAYERS_FILE)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    buttons = []
    if progressed:
        buttons.append([InlineKeyboardButton(text="🏆 Перейти к плей-офф", callback_data="euro_playoff_menu")])
    buttons.append([InlineKeyboardButton(text="📊 Полная таблица", callback_data="euro_table_full")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "euro_playoff_menu")
@with_user_lock
async def euro_playoff_menu_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data or euro_data.get("status") != "playoff":
        await callback.answer("Плей-офф еще не начался")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    playoffs = euro_data["playoffs"][tournament]
    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    current_stage = playoffs.get("current_stage", "playoff_round")
    top8 = playoffs.get("top8", []) or []

    # Если игрок вылетел
    if p.get("euro_tournament") == "none" or p.get("euro_playoff_stage") == "eliminated":
        try:
            await callback.message.edit_text(
                f"🏆 **ПЛЕЙ-ОФФ {euro_info.get('name', '')}**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "😔 Ты вылетел из турнира.\n"
                "Сосредоточься на следующем сезоне!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")]
                ])
            )
        except TelegramBadRequest:
            pass
        return

    # Ищем соперника игрока в текущей стадии
    player_in_stage = False
    opponent = None
    pairs_to_show = playoffs.get(current_stage, []) or []
    for pair in pairs_to_show:
        if p["club"] in pair:
            player_in_stage = True
            opponent = pair[0] if pair[1] == p["club"] else pair[1]
            break

    text = f"🏆 **ПЛЕЙ-ОФФ {euro_info.get('name', '')}**\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"

    stage_names = {
        "playoff_round": "Стыковые матчи",
        "round_16": "1/8 финала",
        "quarter": "1/4 финала",
        "semi": "Полуфинал",
        "final": "Финал"
    }
    text += f"📅 Текущая стадия: **{stage_names.get(current_stage, current_stage)}**\n\n"

    if player_in_stage and opponent:
        text += f"⚔️ Твой соперник: **{opponent}**\n\n"

    if pairs_to_show:
        text += f"**{stage_names.get(current_stage, current_stage)}:**\n"
        for pair in pairs_to_show[:8]:
            is_my = "👉 " if p["club"] in pair else "• "
            text += f"{is_my}{pair[0]} vs {pair[1]}\n"
        if len(pairs_to_show) > 8:
            text += f"... и ещё {len(pairs_to_show) - 8} пар\n"

    buttons = []

    # === ЕСЛИ СТАДИЯ СТЫКОВ ===
    if current_stage == "playoff_round":
        if p["club"] in top8:
            text += "\n🎉 Ты в топ-8 и **пропускаешь стыковые матчи**!\n"
            text += "Нажми кнопку ниже, чтобы симулировать стыки и перейти в 1/8 финала."
            buttons.append([InlineKeyboardButton(
                text="⏭ Пропустить стыки (я в топ-8)",
                callback_data="euro_skip_playoff_round"
            )])
        elif player_in_stage:
            if p.get("trust", 15) >= 21:
                buttons.append([InlineKeyboardButton(
                    text="▶️ Сыграть стыковой матч",
                    callback_data="euro_play_playoff_round"
                )])
            else:
                buttons.append([InlineKeyboardButton(
                    text="▶️ Смотреть стык (ты в резерве)",
                    callback_data="euro_sim_playoff_round"
                )])
        else:
            text += "\n😔 Ты вылетел из турнира."
            buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")])
            try:
                await callback.message.edit_text(text, parse_mode="Markdown",
                                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
            except TelegramBadRequest:
                pass
            return
    # === ЕСЛИ СТАДИЯ НЕ СТЫКОВ ===
    else:
        if player_in_stage:
            if p.get("trust", 15) >= 21:
                cb_map = {
                    "round_16": ("▶️ Сыграть 1/8 финала", "euro_play_round16"),
                    "quarter": ("▶️ Сыграть 1/4 финала", "euro_play_quarter"),
                    "semi": ("▶️ Сыграть полуфинал", "euro_play_semi"),
                    "final": ("🏆 Сыграть финал!", "euro_play_final"),
                }
                label, cb = cb_map.get(current_stage, ("▶️ Сыграть", "noop"))
                buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])
            else:
                cb_map = {
                    "round_16": ("▶️ Смотреть 1/8 (ты в резерве)", "euro_simulate_round16"),
                    "quarter": ("▶️ Смотреть 1/4 (ты в резерве)", "euro_simulate_quarter"),
                    "semi": ("▶️ Смотреть полуфинал (ты в резерве)", "euro_simulate_semi"),
                    "final": ("🏆 Смотреть финал (ты в резерве)", "euro_simulate_final"),
                }
                label, cb = cb_map.get(current_stage, ("▶️ Смотреть", "noop"))
                buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])
        else:
            text += "\n⏳ Ожидай следующую стадию плей-офф."
            buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="euro_playoff_menu")])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "euro_skip_playoff_round")
@with_user_lock
async def euro_skip_playoff_round_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data or euro_data.get("status") != "playoff":
        await callback.answer("Плей-офф еще не начался")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    playoffs = euro_data["playoffs"][tournament]
    current_stage = playoffs.get("current_stage", "playoff_round")

    if current_stage != "playoff_round":
        await callback.answer("Стыковые матчи уже сыграны")
        return

    top8 = playoffs.get("top8", [])
    if p["club"] not in top8:
        await callback.answer("Ты не в топ-8, стыки пропустить нельзя", show_alert=True)
        return

    await simulate_playoff_round_without_player(euro_data, tournament)

    euro_info = EURO_TOURNAMENTS.get(tournament, {})

    try:
        await callback.message.edit_text(
            f"⏭ **СТЫКОВЫЕ МАТЧИ СИМУЛИРОВАНЫ!**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 {euro_info.get('name', 'Еврокубки')}\n\n"
            "Ты был в топ-8 и пропустил стыки.\n"
            "Победители стыков присоединились к тебе в 1/8 финала.\n\n"
            "➡️ Переходи к плей-офф!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏆 Перейти к 1/8 финала", callback_data="euro_playoff_menu")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
            ])
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "euro_simulate_round16")
@with_user_lock
async def euro_simulate_round16_handler(callback: CallbackQuery):
    await euro_simulate_playoff_match(callback, "round_16")


@dp.callback_query(F.data == "euro_simulate_quarter")
@with_user_lock
async def euro_simulate_quarter_handler(callback: CallbackQuery):
    await euro_simulate_playoff_match(callback, "quarter")


@dp.callback_query(F.data == "euro_simulate_semi")
@with_user_lock
async def euro_simulate_semi_handler(callback: CallbackQuery):
    await euro_simulate_playoff_match(callback, "semi")


@dp.callback_query(F.data == "euro_simulate_final")
@with_user_lock
async def euro_simulate_final_handler(callback: CallbackQuery):
    await euro_simulate_playoff_match(callback, "final")


async def euro_simulate_playoff_match(callback: CallbackQuery, stage: str):
    user_id = await get_uid(callback)
    await track_activity(user_id)

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data or euro_data.get("status") != "playoff":
        await callback.answer("Плей-офф еще не начался")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    playoffs = euro_data["playoffs"][tournament]
    pairs = playoffs.get(stage, [])

    opponent = None
    for pair in pairs:
        if p["club"] in pair:
            opponent = pair[0] if pair[1] == p["club"] else pair[1]
            break

    if not opponent:
        await callback.answer("Ты не участвуешь в этой стадии")
        return

    goals1, goals2, winner = await simulate_euro_playoff_match(p["club"], opponent)

    p[f"{stage}_played"] = True

    if winner == p["club"]:
        result_text = "🏆 **ПОБЕДА! ТЫ ПРОШЕЛ ДАЛЬШЕ!**"
        prize = EURO_TOURNAMENTS[tournament]["prize_win"] * 2

        stage_order = ["round_16", "quarter", "semi", "final"]
        current_idx = stage_order.index(stage) if stage in stage_order else -1

        if current_idx < len(stage_order) - 1:
            p["euro_playoff_stage"] = stage_order[current_idx + 1]
        else:
            p["trophies"] = p.get("trophies", []) + [
                f"🏆 {EURO_TOURNAMENTS[tournament]['name']} (Сезон {p.get('season', 1)})"
            ]
            p["money"] = p.get("money", 0) + EURO_TOURNAMENTS[tournament]["prize_winner"]
            p["rating"] = min(100.0, p["rating"] + EURO_TOURNAMENTS[tournament]["rating_bonus_winner"])
            p["euro_tournament"] = "none"
            p["euro_playoff_stage"] = None
    else:
        result_text = "❌ **ПОРАЖЕНИЕ. ТЫ ВЫЛЕТАЕШЬ ИЗ ТУРНИРА.**"
        prize = 0
        p["euro_tournament"] = "none"
        p["euro_playoff_stage"] = "eliminated"

    rating_bonus = 0.1 if winner == p["club"] else -0.1
    p["rating"] = max(1.0, min(100.0, round(p["rating"] + rating_bonus, 1)))
    p["money"] = p.get("money", 0) + prize
    p["euro_matches"] = p.get("euro_matches", 0) + 1

    players = await load_data(PLAYERS_FILE)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    if stage in ["round_16", "quarter", "semi"]:
        await advance_playoff_round(
            euro_data, tournament, stage,
            player_club=p["club"], player_won=(winner == p["club"])
        )
    await save_data(EURO_FILE, euro_data)

    try:
        await callback.message.edit_text(
            f"🏁 **МАТЧ СИМУЛИРОВАН!**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚔️ **{p['club']} {goals1} : {goals2} {opponent}**\n"
            f"{result_text}\n\n"
            "🪑 Ты был в резерве и не участвовал в матче.\n"
            f"💰 Призовые: +{prize}$\n"
            f"📈 Рейтинг: {p['rating']} ({'+' if rating_bonus >= 0 else ''}{round(rating_bonus, 1)})",
            parse_mode="Markdown",
            reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "euro_play_round16")
@with_user_lock
async def euro_play_round16_handler(callback: CallbackQuery, state: FSMContext):
    await euro_playoff_match_handler(callback, state, "round_16", "1/8 финала")


@dp.callback_query(F.data == "euro_play_quarter")
@with_user_lock
async def euro_play_quarter_handler(callback: CallbackQuery, state: FSMContext):
    await euro_playoff_match_handler(callback, state, "quarter", "1/4 финала")


@dp.callback_query(F.data == "euro_play_semi")
@with_user_lock
async def euro_play_semi_handler(callback: CallbackQuery, state: FSMContext):
    await euro_playoff_match_handler(callback, state, "semi", "Полуфинал")


@dp.callback_query(F.data == "euro_play_final")
@with_user_lock
async def euro_play_final_handler(callback: CallbackQuery, state: FSMContext):
    await euro_playoff_match_handler(callback, state, "final", "Финал")


@dp.callback_query(F.data == "euro_sim_playoff_round")
@with_user_lock
async def euro_sim_playoff_round_handler(callback: CallbackQuery):
    await euro_simulate_playoff_round(callback)


async def euro_simulate_playoff_round(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data or euro_data.get("status") != "playoff":
        await callback.answer("Плей-офф еще не начался")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    playoffs = euro_data["playoffs"][tournament]
    pairs = playoffs.get("playoff_round", [])

    opponent = None
    for pair in pairs:
        if p["club"] in pair:
            opponent = pair[0] if pair[1] == p["club"] else pair[1]
            break

    if not opponent:
        await callback.answer("Ты не участвуешь в стыковых матчах")
        return

    goals1, goals2, winner = await simulate_euro_playoff_match(p["club"], opponent)
    won = winner == p["club"]

    p["playoff_round_played"] = True

    if won:
        result_text = "🏆 **ПОБЕДА! ТЫ ПРОШЕЛ В 1/8 ФИНАЛА!**"
        prize = EURO_TOURNAMENTS[tournament]["prize_win"] * 2
        p["euro_playoff_stage"] = "round_16"
    else:
        result_text = "❌ **ПОРАЖЕНИЕ. ТЫ ВЫЛЕТАЕШЬ.**"
        prize = 0
        p["euro_tournament"] = "none"
        p["euro_playoff_stage"] = "eliminated"

    p["rating"] = max(1.0, min(100.0, round(p["rating"] + (0.1 if won else -0.1), 1)))
    p["money"] = p.get("money", 0) + prize
    p["euro_matches"] = p.get("euro_matches", 0) + 1

    players = await load_data(PLAYERS_FILE)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    await simulate_playoff_round(
        euro_data, tournament,
        player_club=p["club"], player_won=won
    )

    try:
        await callback.message.edit_text(
            f"🏁 **СТЫКОВОЙ МАТЧ СИМУЛИРОВАН!**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"⚔️ **{p['club']} {goals1} : {goals2} {opponent}**\n"
            f"{result_text}\n\n"
            "🪑 Ты был в резерве и не участвовал в матче.\n"
            f"💰 Призовые: +{prize}$\n"
            f"📈 Рейтинг: {p['rating']}",
            parse_mode="Markdown",
            reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "euro_play_playoff_round")
@with_user_lock
async def euro_play_playoff_round_handler(callback: CallbackQuery, state: FSMContext):
    await euro_playoff_match_handler(callback, state, "playoff_round", "Стыковой матч")


async def euro_playoff_match_handler(callback: CallbackQuery, state: FSMContext, stage: str, stage_name: str):
    user_id = await get_uid(callback)
    await track_activity(user_id)

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    if p.get("trust", 15) < 21:
        await callback.answer("❌ Ты в резерве! Подними доверие до 21, чтобы играть.", show_alert=True)
        return

    euro_data = await load_data(EURO_FILE)
    if not euro_data or euro_data.get("status") != "playoff":
        await callback.answer("Плей-офф еще не начался")
        return

    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь в еврокубках")
        return

    playoffs = euro_data["playoffs"][tournament]

    if stage == "playoff_round":
        pairs = playoffs.get("playoff_round", [])
    else:
        pairs = playoffs.get(stage, [])

    opponent = None
    for pair in pairs:
        if p["club"] in pair:
            opponent = pair[0] if pair[1] == p["club"] else pair[1]
            break

    if not opponent:
        await callback.answer("Ты не участвуешь в этой стадии")
        return

    if p.get(f"{stage}_played", False):
        # Проверяем, что матч реально был в этом сезоне
        if p.get("euro_playoff_stage") != stage:
            # Игрок в этой стадии — значит флаг устаревший
            p.pop(f"{stage}_played", None)
        else:
            await callback.answer("Ты уже сыграл этот матч!")
            return

    match_data = {
        "tournament": tournament,
        "opponent": opponent,
        "home": random.choice([True, False]),
        "tour": 0,
        "goals": 0, "assists": 0, "saves": 0, "tackles": 0, "yellow_cards": 0,
        "my_score": 0, "opponent_score": 0,
        "log": "",
        "moment": 0,
        "total_moments": random.randint(2, 4),
        "minute": 0,
        "is_playoff": True,
        "stage": stage,
        "stage_name": stage_name,
    }
    await state.update_data(euro_match=match_data)

    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    home_text = "🏠 Дома" if match_data["home"] else "✈️ В гостях"

    text = (
        f"{euro_info.get('emoji', '🌍')} **{euro_info.get('name', 'Еврокубки')}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **{stage_name}**\n"
        f"⚔️ **{p['club']}** vs **{opponent}**\n"
        f"📍 {home_text}\n\n"
        "🏟️ **Матч начался!**\n"
        "🔥 Ты в основном составе!"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="euro_moment_next")]
    ])

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            pass


async def euro_playoff_moment(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        return

    match["minute"] = min(90, match.get("minute", 0) + random.randint(10, 25))

    my_rating = CLUB_RATINGS.get(p["club"], 50)
    rival_rating = CLUB_RATINGS.get(match["opponent"], 50)
    rating_diff = my_rating - rival_rating

    if random.random() < 0.5:
        if random.random() < 0.5:
            if random.random() < max(0.05, min(0.95, 0.45 - rating_diff * 0.02)):
                match["opponent_score"] += 1
                match["log"] += f"⚡ **{match['minute']}'** | ГОЛ! Соперник забивает!\n"
        else:
            if random.random() < max(0.05, min(0.95, 0.45 + rating_diff * 0.02)):
                match["my_score"] += 1
                match["log"] += f"⚽ **{match['minute']}'** | ГОЛ! Твоя команда забивает!\n"

    if random.random() < 0.35:
        flavor = random.choice([
            "🔥 Красивый финт обостряет игру.",
            "📐 Подача углового, защита выносит.",
            "🟨 Желтая карточка игроку соперника.",
            "⚔️ Жесткий стык, судья молчит.",
            "👐 Вратарь уверенно забирает мяч."
        ])
        match["log"] += f"⏱ **{match['minute']}'** | {flavor}\n"

    if random.random() < 0.08:
        if random.random() < 0.15:
            match["log"] += f"🟥 **{match['minute']}'** | ПРЯМАЯ КРАСНАЯ! Ты удален!\n"
            match["minute"] = 90
        else:
            match["log"] += f"🟨 **{match['minute']}'** | Желтая карточка тебе.\n"
            match["yellow_cards"] = match.get("yellow_cards", 0) + 1
            if match["yellow_cards"] >= 2:
                match["log"] += f"🟥 **{match['minute']}'** | ВТОРАЯ ЖЕЛТАЯ — УДАЛЕНИЕ!\n"
                match["minute"] = 90

    if match["moment"] >= match["total_moments"] or match["minute"] >= 90:
        await finish_euro_playoff_match(callback, state, user_id)
        return

    match["moment"] += 1
    await state.update_data(euro_match=match)

    text = (
        f"⏱ **{match['minute']}' МИНУТА** | Момент {match['moment']}/{match['total_moments']}\n"
        f"⚔️ **{p['club']}** vs **{match['opponent']}**\n"
        f"Счет: **{match['my_score']} : {match['opponent_score']}**\n\n"
        f"📝 **События матча:**\n{match['log'] or 'Идет плотная позиционная борьба...'}\n"
    )

    match["log"] = ""
    await state.update_data(euro_match=match)

    position = p.get("position", "ST")

    if position == "GK":
        text += "🚨 **Опасность! Нападающий выходит один на один!**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧤 Прыгнуть в левый угол", callback_data="euro_gk:left"),
             InlineKeyboardButton(text="🧤 Прыгнуть в правый угол", callback_data="euro_gk:right")],
            [InlineKeyboardButton(text="🏃 Сблизить дистанцию", callback_data="euro_gk:rush")]
        ])
    elif position == "CB":
        if random.random() < 0.75:
            text += "🛡️ **Форвард идет на дриблинге прямо в твою зону!**"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🧲 Жесткий подкат", callback_data="euro_cb:tackle_hard"),
                 InlineKeyboardButton(text="🕴️ Встретить корпусом", callback_data="euro_cb:tackle_smart")],
                [InlineKeyboardButton(text="📐 Отдать пас ближнему", callback_data="euro_act_pass")]
            ])
        else:
            text += "🔥 **Ты подключился на угловой! Мяч летит к тебе!**"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Пробить головой", callback_data="euro_shoot_menu"),
                 InlineKeyboardButton(text="📐 Сбросить под удар", callback_data="euro_act_pass")]
            ])
    else:
        text += "🔥 **Ты контролируешь мяч на подступах к штрафной! Твое решение?**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Пробить по воротам", callback_data="euro_shoot_menu"),
             InlineKeyboardButton(text="📐 Отдать пас", callback_data="euro_act_pass")]
        ])

    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "euro_shoot_menu")
@with_user_lock
async def euro_shoot_menu_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("euro_match"):
        return await callback.answer("Матч уже завершен!", show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 Левый верхний (Девятка)", callback_data="euro_shoot_dir:в левую девятку"),
         InlineKeyboardButton(text="📐 Правый верхний (Девятка)", callback_data="euro_shoot_dir:в правую девятку")],
        [InlineKeyboardButton(text="👇 Левый нижний", callback_data="euro_shoot_dir:низом в левый угол"),
         InlineKeyboardButton(text="👇 Правый нижний", callback_data="euro_shoot_dir:низом в правый угол")]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


@dp.callback_query(F.data.startswith("euro_shoot_dir:"))
@with_user_lock
async def euro_shoot_execute_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return await callback.answer("Матч уже завершен!", show_alert=True)

    target_dir = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)

    rival_rating = CLUB_RATINGS.get(match["opponent"], 50)
    score_chance = 0.60 + ((p["rating"] - rival_rating) * 0.015)
    gk_dive = random.choice(["в левую девятку", "в правую девятку", "низом в левый угол", "низом в правый угол"])

    if gk_dive == target_dir:
        score_chance -= 0.15
        gk_guessed = True
    else:
        score_chance += 0.10
        gk_guessed = False
    score_chance = max(0.05, min(0.95, score_chance))

    if random.random() < score_chance:
        match["goals"] += 1
        match["my_score"] += 1
        match["log"] += f"⚽ **{match['minute']}'** | ГОЛ! Твой шикарный удар {target_dir}!\n"
    else:
        if gk_guessed:
            match["log"] += f"❌ **{match['minute']}'** | Ты пробил {target_dir}, но голкипер парировал удар!\n"
        else:
            match["log"] += f"❌ **{match['minute']}'** | Целился {target_dir}, но мяч пролетел мимо!\n"

    await state.update_data(euro_match=match)

    if match.get("is_playoff"):
        await euro_playoff_moment(callback, state, user_id)
    else:
        await generate_euro_moment(callback, state, user_id)


@dp.callback_query(F.data == "euro_act_pass")
@with_user_lock
async def euro_act_pass_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return await callback.answer("Матч уже завершен!", show_alert=True)

    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)

    rival_rating = CLUB_RATINGS.get(match["opponent"], 50)
    pass_chance = 0.60 + ((p["rating"] - rival_rating) * 0.015)
    pass_chance = max(0.05, min(0.95, pass_chance))

    if random.random() < pass_chance:
        match["assists"] += 1
        match["my_score"] += 1
        match["log"] += f"✅ **{match['minute']}'** | Шикарный точный пас, партнер забивает! ГОЛ!\n"
    else:
        match["log"] += f"❌ **{match['minute']}'** | Пас перехвачен соперником.\n"

    await state.update_data(euro_match=match)

    if match.get("is_playoff"):
        await euro_playoff_moment(callback, state, user_id)
    else:
        await generate_euro_moment(callback, state, user_id)


@dp.callback_query(F.data == "euro_act_skip")
@with_user_lock
async def euro_act_skip_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return await callback.answer("Матч уже завершен!", show_alert=True)

    user_id = await get_uid(callback)
    match["log"] += f"⏱ **{match['minute']}'** | Ты пропускаешь момент.\n"
    await state.update_data(euro_match=match)

    if match.get("is_playoff"):
        await euro_playoff_moment(callback, state, user_id)
    else:
        await generate_euro_moment(callback, state, user_id)


@dp.callback_query(F.data.startswith("euro_gk:"))
@with_user_lock
async def euro_gk_action_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return await callback.answer("Матч уже завершен!", show_alert=True)

    action = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)

    rival_rating = CLUB_RATINGS.get(match["opponent"], 50)
    save_chance = 0.30 + ((p["rating"] - rival_rating) * 0.015) + (p["rating"] * 0.004)
    save_chance = max(0.1, min(0.95, save_chance))

    opp_shoot_dir = random.choice(["left", "right", "center"])
    if action == "rush":
        is_saved = random.random() < (save_chance + 0.1)
    else:
        is_saved = (action == opp_shoot_dir) or (random.random() < save_chance * 0.8)

    if is_saved:
        match["saves"] += 1
        match["log"] += f"🧤 **{match['minute']}'** | БЕЗУМНЫЙ СЕЙВ!\n"
    else:
        match["opponent_score"] += 1
        match["log"] += f"⚡ **{match['minute']}'** | Гол... Оппонент переиграл тебя.\n"

    await state.update_data(euro_match=match)

    if match.get("is_playoff"):
        await euro_playoff_moment(callback, state, user_id)
    else:
        await generate_euro_moment(callback, state, user_id)


@dp.callback_query(F.data.startswith("euro_cb:"))
@with_user_lock
async def euro_cb_action_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return await callback.answer("Матч уже завершен!", show_alert=True)

    action = callback.data.split(":")[1]
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)

    rival_rating = CLUB_RATINGS.get(match["opponent"], 50)
    tackle_chance = 0.30 + ((p["rating"] - rival_rating) * 0.015) + (p["rating"] * 0.003)
    tackle_chance = max(0.1, min(0.90, tackle_chance))

    if action == "tackle_hard":
        if random.random() < 0.15:
            match["opponent_score"] += 1
            match["log"] += f"⚡ **{match['minute']}'** | Фол в штрафной! Пенальти, гол.\n"
        elif random.random() < tackle_chance:
            match["tackles"] += 1
            match["log"] += f"🛡️ **{match['minute']}'** | Мощнейший чистый подкат!\n"
        else:
            match["opponent_score"] += 1
            match["log"] += f"⚡ **{match['minute']}'** | Ошибка! Нападающий забил.\n"
    else:
        if random.random() < tackle_chance:
            match["tackles"] += 1
            match["log"] += f"🛡️ **{match['minute']}'** | Отличный выбор позиции!\n"
        else:
            match["opponent_score"] += 1
            match["log"] += f"⚡ **{match['minute']}'** | Тебя обыграли на замахе. Гол.\n"

    await state.update_data(euro_match=match)

    if match.get("is_playoff"):
        await euro_playoff_moment(callback, state, user_id)
    else:
        await generate_euro_moment(callback, state, user_id)


async def finish_euro_match(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return

    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    euro_data = await load_data(EURO_FILE)

    tournament = match["tournament"]
    my_club = p["club"]
    opponent = match["opponent"]
    my_tour = match["tour"]

    if match["my_score"] > match["opponent_score"]:
        result = "win"; points = 3
        result_text = "🏆 **ПОБЕДА!**"
        prize = EURO_TOURNAMENTS[tournament]["prize_win"]
    elif match["my_score"] == match["opponent_score"]:
        result = "draw"; points = 1
        result_text = "🤝 **НИЧЬЯ**"
        prize = EURO_TOURNAMENTS[tournament]["prize_draw"]
    else:
        result = "loss"; points = 0
        result_text = "❌ **ПОРАЖЕНИЕ**"
        prize = 0

    table = euro_data[tournament]["table"]

    if my_club in table:
        table[my_club]["points"] += points
        table[my_club]["goals_for"] += match["my_score"]
        table[my_club]["goals_against"] += match["opponent_score"]
        table[my_club]["played"] += 1
        if result == "win":
            table[my_club]["wins"] += 1
        elif result == "draw":
            table[my_club]["draws"] += 1
        else:
            table[my_club]["losses"] += 1

    fixtures = euro_data[tournament]["fixtures"].get(my_club, [])
    for f in fixtures:
        if f["tour"] == my_tour and f["opponent"] == opponent:
            f["played"] = True
            f["goals_for"] = match["my_score"]
            f["goals_against"] = match["opponent_score"]
            f["result"] = result
            break

    for m in euro_data[tournament]["fixtures"].get(opponent, []):
        if m["tour"] == my_tour and m["opponent"] == my_club:
            m["played"] = True
            m["goals_for"] = match["opponent_score"]
            m["goals_against"] = match["my_score"]
            m["result"] = "win" if result == "loss" else ("draw" if result == "draw" else "loss")
            break

    if opponent in table:
        table[opponent]["points"] += (3 if result == "loss" else (1 if result == "draw" else 0))
        table[opponent]["goals_for"] += match["opponent_score"]
        table[opponent]["goals_against"] += match["my_score"]
        table[opponent]["played"] += 1
        if result == "loss":
            table[opponent]["wins"] += 1
        elif result == "draw":
            table[opponent]["draws"] += 1
        else:
            table[opponent]["losses"] += 1

    euro_data = await simulate_euro_tour(euro_data, tournament, my_tour)
    await save_data(EURO_FILE, euro_data)

    p["money"] = p.get("money", 0) + prize
    p["euro_goals"] = p.get("euro_goals", 0) + match.get("goals", 0)
    p["euro_assists"] = p.get("euro_assists", 0) + match.get("assists", 0)
    p["euro_matches"] = p.get("euro_matches", 0) + 1

    p.setdefault("stats_season", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})
    p.setdefault("stats_total", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})

    for stat in ("goals", "assists", "saves", "tackles"):
        p["stats_season"][stat] = p["stats_season"].get(stat, 0) + match.get(stat, 0)
        p["stats_total"][stat] = p["stats_total"].get(stat, 0) + match.get(stat, 0)

    p["stats_season"]["games"] = p["stats_season"].get("games", 0) + 1
    p["stats_total"]["games"] = p["stats_total"].get("games", 0) + 1

    rating_bonus = (
        match.get("goals", 0) * 0.1 +
        match.get("assists", 0) * 0.05 +
        match.get("saves", 0) * 0.05 +
        match.get("tackles", 0) * 0.03
    )
    if result == "win":
        rating_bonus += 0.1
    elif result == "loss":
        rating_bonus -= 0.05
    p["rating"] = max(1.0, min(100.0, round(p["rating"] + rating_bonus, 1)))

    fixtures = euro_data[tournament]["fixtures"].get(my_club, [])
    all_played = all(f.get("played", False) for f in fixtures) and len(fixtures) >= EURO_TOTAL_TOURS

    playoff_text = ""
    if all_played:
        euro_data["status"] = "playoff"
        await generate_euro_playoffs(euro_data, tournament)
        await save_data(EURO_FILE, euro_data)
        position = await get_euro_position(user_id)

        if position and position <= 8:
            p["euro_playoff_stage"] = "round_16"
            p["playoff_round_played"] = True
            playoff_text = "\n\n🎉 **Ты прошел напрямую в 1/8 финала!**"
        elif position and position <= 24:
            p["euro_playoff_stage"] = "playoff_round"
            playoff_text = "\n\n⚔️ **Ты попал в стыковые матчи!**"
        else:
            p["euro_tournament"] = "none"
            p["euro_playoff_stage"] = "eliminated"
            playoff_text = "\n\n😔 **Ты вылетел из еврокубков.**"

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    text = (
        f"🏁 **МАТЧ ЗАВЕРШЕН!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⚔️ **{p['club']} {match['my_score']} : {match['opponent_score']} {match['opponent']}**\n"
        f"{result_text}\n\n"
        "📊 **Твоя статистика:**\n"
        f"⚽ Голы: {match.get('goals', 0)}\n"
        f"🅰️ Ассисты: {match.get('assists', 0)}\n"
        f"🧤 Сейвы: {match.get('saves', 0)}\n"
        f"🛡️ Отборы: {match.get('tackles', 0)}\n\n"
        f"💰 Призовые: +{prize}$\n"
        f"📈 Рейтинг: {p['rating']} ({'+' if rating_bonus >= 0 else ''}{round(rating_bonus, 1)})"
        f"{playoff_text}"
    )

    await state.clear()
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        if callback.message.photo:
            await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def finish_euro_playoff_match(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return

    won = False
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    euro_data = await load_data(EURO_FILE)

    stage = match.get("stage")
    stage_name = match.get("stage_name", "Матч")
    tournament = match["tournament"]

    if match["my_score"] == match["opponent_score"]:
        match["log"] += "\n⏱ **ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ!**\n"
        await state.update_data(euro_match=match)
        try:
            await callback.message.edit_text(
                f"⏱ **ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ!**\n"
                f"Счет: **{match['my_score']} : {match['opponent_score']}**\n"
                f"Начинается дополнительное время!",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await asyncio.sleep(2)

        for period in range(2):
            if random.random() < 0.3:
                if random.random() < 0.5:
                    match["my_score"] += 1
                    match["log"] += "⚽ **ДОП. ВРЕМЯ!** Твоя команда забивает!\n"
                else:
                    match["opponent_score"] += 1
                    match["log"] += "⚡ **ДОП. ВРЕМЯ!** Соперник забивает!\n"
            await state.update_data(euro_match=match)
            try:
                await callback.message.edit_text(
                    f"⏱ **ДОП. ВРЕМЯ — ПЕРИОД {period + 1}/2**\n"
                    f"Счет: **{match['my_score']} : {match['opponent_score']}**\n\n"
                    f"📝 {match['log'] or 'Игра продолжается...'}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            await asyncio.sleep(2)
            match["log"] = ""
            await state.update_data(euro_match=match)

        if match["my_score"] == match["opponent_score"]:
            try:
                await callback.message.edit_text(
                    f"🥅 **СЕРИЯ ПЕНАЛЬТИ!**\n"
                    f"Счет: **{match['my_score']} : {match['opponent_score']}**\n"
                    f"Начинается серия пенальти!",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            await asyncio.sleep(2)

            my_pen = 0
            opp_pen = 0
            pen_log = ""
            for i in range(5):
                if random.random() < 0.75:
                    my_pen += 1
                    pen_log += f"✅ Удар {i + 1}: ГОЛ! (твоя команда)\n"
                else:
                    pen_log += f"❌ Удар {i + 1}: МИМО! (твоя команда)\n"
                if random.random() < 0.75:
                    opp_pen += 1
                    pen_log += f"✅ Удар {i + 1}: ГОЛ! (соперник)\n"
                else:
                    pen_log += f"❌ Удар {i + 1}: МИМО! (соперник)\n"

            while my_pen == opp_pen:
                if random.random() < 0.75:
                    my_pen += 1
                    pen_log += "✅ Доп. удар: ГОЛ! (твоя команда)\n"
                else:
                    pen_log += "❌ Доп. удар: МИМО! (твоя команда)\n"
                if random.random() < 0.75:
                    opp_pen += 1
                    pen_log += "✅ Доп. удар: ГОЛ! (соперник)\n"
                else:
                    pen_log += "❌ Доп. удар: МИМО! (соперник)\n"

            won = my_pen > opp_pen
            try:
                await callback.message.edit_text(
                    f"🥅 **РЕЗУЛЬТАТ ПЕНАЛЬТИ!**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"{pen_log}\n"
                    f"Итог: **{my_pen} : {opp_pen}**\n"
                    f"{'🏆 ТЫ ПОБЕДИЛ В СЕРИИ ПЕНАЛЬТИ!' if won else '😔 ТЫ ПРОИГРАЛ В СЕРИИ ПЕНАЛЬТИ.'}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            await asyncio.sleep(2)
            if won:
                match["my_score"] += 1
            else:
                match["opponent_score"] += 1
            await state.update_data(euro_match=match)

    won = match["my_score"] > match["opponent_score"]

    if won:
        result_text = "🏆 **ПОБЕДА! ТЫ ПРОШЕЛ ДАЛЬШЕ!**"
        prize = EURO_TOURNAMENTS[tournament]["prize_win"] * 2

        if stage == "playoff_round":
            p["euro_playoff_stage"] = "round_16"
            p["playoff_round_played"] = True
            await simulate_playoff_round(
                euro_data, tournament,
                player_club=p["club"], player_won=True
            )
        else:
            stage_order = ["round_16", "quarter", "semi", "final"]
            current_idx = stage_order.index(stage) if stage in stage_order else -1

            if current_idx < len(stage_order) - 1:
                p["euro_playoff_stage"] = stage_order[current_idx + 1]
            else:
                p["trophies"] = p.get("trophies", []) + [
                    f"🏆 {EURO_TOURNAMENTS[tournament]['name']} (Сезон {p.get('season', 1)})"
                ]
                p["money"] = p.get("money", 0) + EURO_TOURNAMENTS[tournament]["prize_winner"]
                p["rating"] = min(100.0, p["rating"] + EURO_TOURNAMENTS[tournament]["rating_bonus_winner"])
                p["euro_tournament"] = "none"
                p["euro_playoff_stage"] = None
    else:
        result_text = "❌ **ПОРАЖЕНИЕ. ТЫ ВЫЛЕТАЕШЬ ИЗ ТУРНИРА.**"
        prize = 0
        p["euro_tournament"] = "none"
        p["euro_playoff_stage"] = "eliminated"

    p[f"{stage}_played"] = True

    p.setdefault("stats_season", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})
    p.setdefault("stats_total", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})

    for stat in ("goals", "assists", "saves", "tackles"):
        p["stats_season"][stat] = p["stats_season"].get(stat, 0) + match.get(stat, 0)
        p["stats_total"][stat] = p["stats_total"].get(stat, 0) + match.get(stat, 0)

    p["stats_season"]["games"] = p["stats_season"].get("games", 0) + 1
    p["stats_total"]["games"] = p["stats_total"].get("games", 0) + 1

    p["euro_matches"] = p.get("euro_matches", 0) + 1
    p["euro_goals"] = p.get("euro_goals", 0) + match.get("goals", 0)
    p["euro_assists"] = p.get("euro_assists", 0) + match.get("assists", 0)

    rating_bonus = (
        match.get("goals", 0) * 0.1 +
        match.get("assists", 0) * 0.05 +
        match.get("saves", 0) * 0.05 +
        match.get("tackles", 0) * 0.03
    )
    if won:
        rating_bonus += 0.3
    else:
        rating_bonus -= 0.1

    p["rating"] = max(1.0, min(100.0, round(p["rating"] + rating_bonus, 1)))
    p["money"] = p.get("money", 0) + prize

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    if stage in ["round_16", "quarter", "semi"]:
        await advance_playoff_round(
            euro_data, tournament, stage,
            player_club=p["club"], player_won=won
        )
    await save_data(EURO_FILE, euro_data)

    text = (
        f"🏁 **МАТЧ ЗАВЕРШЕН!**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⚔️ **{p['club']} {match['my_score']} : {match['opponent_score']} {match['opponent']}**\n"
        f"{result_text}\n\n"
        "📊 **Твоя статистика:**\n"
        f"⚽ Голы: {match.get('goals', 0)}\n"
        f"🅰️ Ассисты: {match.get('assists', 0)}\n"
        f"🧤 Сейвы: {match.get('saves', 0)}\n"
        f"🛡️ Отборы: {match.get('tackles', 0)}\n\n"
        f"💰 Призовые: +{prize}$\n"
        f"📈 Рейтинг: {p['rating']} ({'+' if rating_bonus >= 0 else ''}{round(rating_bonus, 1)})"
    )

    await state.clear()
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        if callback.message.photo:
            await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


# ============================================================
# ОСТАЛЬНЫЕ ОБРАБОТЧИКИ
# ============================================================

@dp.callback_query(F.data == "menu_online")
async def online_handler(callback: CallbackQuery):
    players = await load_data(PLAYERS_FILE)
    total = len(players)
    online = max(1, int(total * 0.15) + random.randint(1, 4))

    top_active = sorted(players.values(), key=lambda x: x.get("activity_minutes", 0), reverse=True)[:5]
    top_text = "\n\n🔥 **Топ игроков по активности (за эту неделю):**\n"
    for i, p in enumerate(top_active, 1):
        mins = p.get('activity_minutes', 0)
        hours = mins // 60
        minutes = mins % 60
        time_str = f"{hours} ч. {minutes} мин." if hours > 0 else f"{minutes} мин."
        top_text += f"{i}. {p['name']} — {time_str}\n"

    await callback.answer(f"🟢 Сейчас в боте: {online} чел.\n👥 Всего игроков в базе: {total}", show_alert=True)

    user_id = await get_uid(callback)
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(top_text, parse_mode="Markdown",
                                      reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    else:
        try:
            await callback.message.edit_text(top_text, parse_mode="Markdown",
                                             reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "menu_leaderboard")
async def leaderboard_handler(callback: CallbackQuery):
    try:
        leaderboard = await load_data(LEADERBOARD_FILE)
        careers = leaderboard.get("top_careers", [])
        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 10
        if not careers:
            text = (
                "🏆 **ЗАЛ СЛАВЫ**\n━━━━━━━━━━━━━━━━━━━━\n"
                "Здесь появятся лучшие игроки, завершившие карьеру.\n"
                "Стань первым легендой!"
            )
        else:
            lines = ["🏆 **ЗАЛ СЛАВЫ — Легенды игры**\n━━━━━━━━━━━━━━━━━━━━"]
            for i, c in enumerate(careers[:10]):
                lines.append(
                    f"{medals[i]} {c['name']} | "
                    f"⭐ Рейтинг: {c['rating']} | "
                    f"🏆 Трофеев: {c['trophies']}"
                )
            text = "\n".join(lines)
    except Exception as e:
        logging.warning(f"leaderboard_handler load error: {e}")
        text = "⚠️ Не удалось загрузить Зал Славы. Попробуй позже."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logging.warning(f"leaderboard_handler send error: {e}")
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "menu_sponsors")
@with_user_lock
async def sponsors_menu(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    rating = p.get("rating", 40)
    current_sponsor = p.get("sponsor")
    reputation = p.get("reputation", 50)

    lines = []
    buttons = []
    row = []
    for name, info in SPONSORS_DATA.items():
        locked = rating < info["min_rating"]
        bonus = " ⭐+5%" if reputation > 70 and not locked else ""

        if name == current_sponsor:
            status = "✅"
        elif locked:
            status = f"🔒 (рейт. {info['min_rating']})"
        else:
            status = ""
        lines.append(
            f"{info['emoji']} **{name}** {status} — {info['income_per_match']}$/матч{bonus}"
            + (f", бонус {info['sign_bonus']}$" if not locked else "")
        )
        label = f"{info['emoji']} {name} {status}"
        cb = "noop" if (locked or name == current_sponsor) else f"sponsor:{name}"
        row.append(InlineKeyboardButton(text=label, callback_data=cb))
        if len(row) == 2:
            buttons.append(row); row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    text = (
        f"💰 **РЕКЛАМНЫЕ КОНТРАКТЫ**\n"
        f"Твой рейтинг: **{rating}** | ⭐ Репутация: {reputation}\n"
        f"Активный спонсор: **{current_sponsor or 'Нет'}**\n"
        f"Доход начисляется за каждый матч автоматически.\n\n"
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
        logging.warning(f"sponsors_menu error: {e}")
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
    if await deny_if_retired_cb(callback, p):
        return

    sp = callback.data.split(":")[1]
    info = SPONSORS_DATA.get(sp)
    if not info:
        return await callback.answer("❌ Неизвестный спонсор.", show_alert=True)
    if p.get("rating", 40) < info["min_rating"]:
        return await callback.answer(f"❌ Нужен рейтинг {info['min_rating']}!", show_alert=True)

    p["sponsor"] = sp
    bonus_mult = 1.05 if p.get("reputation", 50) > 70 else 1.0
    sign_bonus = int(info["sign_bonus"] * bonus_mult)
    p["money"] = p.get("money", 0) + sign_bonus
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    text = (f"🤝 **Контракт с {info['emoji']} {sp} подписан!**\n"
            f"💵 Бонус при подписании: +{sign_bonus}$\n"
            f"📈 Доход за каждый матч: +{info['income_per_match']}$")
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logging.warning(f"sponsor_sign error: {e}")
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "menu_quests")
@with_user_lock
async def quests_menu_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    completed = p.get("completed_quests", [])
    has_claimable = False

    text = "🎯 **КВЕСТЫ И ДОСТИЖЕНИЯ**\nВыполняй задания и получай прибавку к рейтингу!\n\n"

    for q_id, q in QUESTS_DATA.items():
        if q_id in completed:
            text += f"✅ ~~{q['name']}~~ (+{q['reward']})\n"
        else:
            prog = get_quest_progress(p, q['type'])
            if prog >= q['target']:
                text += f"🎁 **{q['name']}** — ГОТОВО! (+{q['reward']})\n"
                has_claimable = True
            else:
                text += f"⏳ **{q['name']}**: {prog}/{q['target']} | Награда: +{q['reward']}\n"

    kb = []
    if has_claimable:
        kb.append([InlineKeyboardButton(text="🎁 Забрать награды", callback_data="claim_quests")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])

    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")


@dp.callback_query(F.data == "claim_quests")
@with_user_lock
async def claim_quests_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    completed = p.get("completed_quests", [])
    total_reward = 0.0

    for q_id, q in QUESTS_DATA.items():
        if q_id not in completed:
            if get_quest_progress(p, q['type']) >= q['target']:
                total_reward += q['reward']
                completed.append(q_id)

    if total_reward > 0:
        p["completed_quests"] = completed
        p["rating"] = min(100.0, round(p.get("rating", 40.0) + total_reward, 1))
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)

        await callback.answer(f"🎉 Награды получены!\n\nТвой рейтинг вырос на +{round(total_reward, 1)}", show_alert=True)
        kb = await main_menu_keyboard(callback.from_user.username, user_id)
        await callback.message.edit_text("🏠 Главное меню", reply_markup=kb)
    else:
        await callback.answer("Нет доступных наград.", show_alert=True)


@dp.callback_query(F.data == "menu_personal_life")
@with_user_lock
async def personal_life_menu(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 В ресторан (-500$)", callback_data="personal:rest")],
        [InlineKeyboardButton(text="💃 Найти девушку (-2000$)" if p.get("girlfriend", "Нет") == "Нет" else "🎁 Подарок девушке (-1000$)", callback_data="personal:girl")],
        [InlineKeyboardButton(text="🧘 Йога (-300$)", callback_data="personal:yoga")],
        [InlineKeyboardButton(text="🪂 Парашют (-1500$)", callback_data="personal:parachute")],
        [InlineKeyboardButton(text="🎁 Благотворительность (-1000$)", callback_data="personal:charity")],
        [InlineKeyboardButton(text="🎉 Вечеринка (-800$)", callback_data="personal:party")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

    text = (f"🍷 **ЛИЧНАЯ ЖИЗНЬ**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Баланс: {p.get('money', 0)}$\n"
            f"🔋 Усталость: {p.get('fatigue', 0)}%\n"
            f"❤️ Доверие: {p.get('trust', 0)}%\n\n"
            f"Трать деньги, чтобы снижать усталость!")

    await callback.message.delete()
    await callback.message.answer(text=text, reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("personal:"))
@with_user_lock
async def personal_action(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    action = callback.data.split(":")[1]
    cost = 0
    msg = ""
    fatigue_reduction = 0
    trust_boost = 0

    if action == "rest":
        cost = 500; fatigue_reduction = 15
        msg = "🍽 Ты отлично поужинал! Усталость -15%."
    elif action == "girl":
        if p.get("girlfriend", "Нет") == "Нет":
            cost = 2000
            if p.get("money", 0) >= cost:
                p["girlfriend"] = "Есть"
                msg = "💃 Ты познакомился с потрясающей девушкой!"
            else:
                msg = "❌ Не хватает денег на красивые ухаживания."
        else:
            cost = 1000; fatigue_reduction = 20
            msg = "🎁 Ты подарил девушке дорогие украшения! Усталость -20%."
    elif action == "yoga":
        cost = 300; fatigue_reduction = 20; trust_boost = 1
        msg = "🧘 Йога помогла тебе расслабиться! Усталость -20%."
    elif action == "parachute":
        cost = 1500; fatigue_reduction = 25; trust_boost = 5
        msg = "🪂 Адреналин зарядил тебя энергией! Усталость -25%."
    elif action == "charity":
        cost = 1000; trust_boost = 10
        msg = "🎁 Благотворительность повысила авторитет! Доверие +10."
    elif action == "party":
        cost = 800; fatigue_reduction = 15; trust_boost = -2
        msg = "🎉 Вечеринка удалась! Усталость -15%, но болельщики недовольны."

    if "❌" not in msg:
        if p.get("money", 0) >= cost:
            p["money"] -= cost
            p["fatigue"] = max(0, p.get("fatigue", 0) - fatigue_reduction)
            p["trust"] = min(100, max(0, p.get("trust", 15) + trust_boost))
        else:
            msg = "❌ Не хватает денег."

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await callback.answer(msg, show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 В ресторан (-500$)", callback_data="personal:rest")],
        [InlineKeyboardButton(text="💃 Найти девушку (-2000$)" if p.get("girlfriend", "Нет") == "Нет" else "🎁 Подарок девушке (-1000$)", callback_data="personal:girl")],
        [InlineKeyboardButton(text="🧘 Йога (-300$)", callback_data="personal:yoga")],
        [InlineKeyboardButton(text="🪂 Парашют (-1500$)", callback_data="personal:parachute")],
        [InlineKeyboardButton(text="🎁 Благотворительность (-1000$)", callback_data="personal:charity")],
        [InlineKeyboardButton(text="🎉 Вечеринка (-800$)", callback_data="personal:party")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    text = (f"🍷 **ЛИЧНАЯ ЖИЗНЬ**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Баланс: {p.get('money', 0)}$\n"
            f"🔋 Усталость: {p.get('fatigue', 0)}%\n"
            f"❤️ Доверие: {p.get('trust', 0)}%\n\n"
            f"Трать деньги, чтобы снижать усталость!")
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text=text, reply_markup=kb, parse_mode="Markdown")


# ============================================================
# АДМИН-ПАНЕЛЬ
# ============================================================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("У вас нет доступа к этой панели.", show_alert=True)

    text = (
        "👑 **Админ-панель**\n\n"
        "Отправьте мне **ID пользователя** (например `123456_1`) для управления:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]
    ])
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await state.set_state(AdminPanel.waiting_for_user_id)


@dp.message(AdminPanel.waiting_for_user_id)
async def admin_user_management(message: Message, state: FSMContext):
    target_input = message.text.strip()
    players = await load_data(PLAYERS_FILE)

    if target_input in players and not players[target_input].get("retired"):
        target_id = target_input
    else:
        found = [uid for uid, p in players.items()
                 if uid.startswith(target_input + "_") and not p.get("retired")]

        if not found:
            return await message.answer(
                "❌ Активный игрок с таким ID не найден.\n"
                "Попробуй скопировать полный ID из профиля (например: `123456789_1`)",
                reply_markup=await main_menu_keyboard(message.from_user.username, await get_uid(message)),
                parse_mode="Markdown"
            )

        if len(found) > 1:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"Слот {uid.split('_')[1]}: {players[uid]['name']} ({players[uid].get('rating', 40)})",
                    callback_data=f"admin_select:{uid}"
                )] for uid in found
            ])
            await message.answer("Найдено несколько профилей. Выбери нужный:", reply_markup=kb)
            return

        target_id = found[0]

    await show_admin_user_profile(message, target_id)
    await state.clear()


@dp.callback_query(F.data.startswith("admin_select:"))
async def admin_select_handler(callback: CallbackQuery, state: FSMContext):
    target_id = callback.data.split(":")[1]
    await show_admin_user_profile(callback, target_id)
    await state.clear()


async def show_admin_user_profile(message_or_call, target_id):
    players = await load_data(PLAYERS_FILE)
    p = players[target_id]
    val = calculate_player_value(p["rating"], p["division"])

    parts = target_id.split("_")
    tg_id = parts[0]
    slot = parts[1] if len(parts) > 1 else "?"

    if p["position"] == "GK":
        stats_text = f"🧤 Сейвы: {p['stats_season'].get('saves', 0)}"
    elif p["position"] == "CB":
        stats_text = f"🛡️ Отборы: {p['stats_season'].get('tackles', 0)} | ⚽ Голы: {p['stats_season'].get('goals', 0)}"
    else:
        stats_text = f"⚽ Голы: {p['stats_season'].get('goals', 0)} | 🅰️ Ассисты: {p['stats_season'].get('assists', 0)}"

    text = (
        f"👑 ПРОФИЛЬ ИГРОКА\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 Telegram ID: `{tg_id}`\n"
        f"💾 Полный ID: `{target_id}`\n"
        f"📁 Слот: {slot}\n"
        f"🏃‍♂️ {p['name']} | 🌍 {p.get('nation', 'Россия')} | 🎂 {p.get('age', 17)} лет\n"
        f"⚡️ Рейтинг: {p['rating']}/100\n"
        f"🏢 Клуб: {p['club']} ({p['position']})\n"
        f"💵 Баланс: {p.get('money', 0)}$ | 🏷️ Стоимость: {val:,}$\n"
        f"🏟️ Сезон: {p['season']} | Тур: {p['tour']}/30\n"
        f"🌍 Еврокубки: {get_euro_name(p.get('euro_tournament', 'none'))}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n{stats_text}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Тур (+1)", callback_data=f"adm_tour:{target_id}"),
         InlineKeyboardButton(text="⏭ Сезон (+1)", callback_data=f"adm_season:{target_id}")],
        [InlineKeyboardButton(text="💰 Выдать деньги", callback_data=f"adm_money:{target_id}"),
         InlineKeyboardButton(text="⚡️ Выдать рейтинг", callback_data=f"adm_rating:{target_id}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])

    if isinstance(message_or_call, Message):
        await message_or_call.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        try:
            await message_or_call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data.startswith("adm_tour:"))
async def adm_skip_tour(callback: CallbackQuery):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("Ошибка доступа.", show_alert=True)
    target_id = callback.data.split(":")[1]
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            p = players[target_id]
            p["tour"] += 1
            p["money"] = p.get("money", 0) + p.get("contract_salary", 1500)
            p["train_done"] = False

            played_rivals = p.get("played_league_rivals", [])
            rival_pool = [c for c in CLUBS[p["division"]] if c != p["club"] and c not in played_rivals]
            if not rival_pool:
                rival_pool = [c for c in CLUBS[p["division"]] if c != p["club"]]
                p["played_league_rivals"] = []

            rival = random.choice(rival_pool)
            p["played_league_rivals"].append(rival)
            outcome = random.choice(["win", "draw", "loss"])

            p["stats_season"]["games"] += 1
            p["stats_total"]["games"] = p["stats_total"].get("games", 0) + 1

            if p["position"] in ["ST", "CM"]:
                goals = random.randint(0, 2) if outcome != "loss" else 0
                assists = random.randint(0, 1) if outcome != "loss" else 0
                p["stats_season"]["goals"] = p["stats_season"].get("goals", 0) + goals
                p["stats_season"]["assists"] = p["stats_season"].get("assists", 0) + assists
                p["stats_total"]["goals"] = p["stats_total"].get("goals", 0) + goals
                p["stats_total"]["assists"] = p["stats_total"].get("assists", 0) + assists
            elif p["position"] == "CB":
                tackles = random.randint(1, 5)
                goals = random.randint(0, 1) if outcome == "win" else 0
                p["stats_season"]["tackles"] = p["stats_season"].get("tackles", 0) + tackles
                p["stats_season"]["goals"] = p["stats_season"].get("goals", 0) + goals
                p["stats_total"]["tackles"] = p["stats_total"].get("tackles", 0) + tackles
                p["stats_total"]["goals"] = p["stats_total"].get("goals", 0) + goals
            elif p["position"] == "GK":
                saves = random.randint(1, 7)
                p["stats_season"]["saves"] = p["stats_season"].get("saves", 0) + saves
                p["stats_total"]["saves"] = p["stats_total"].get("saves", 0) + saves

            players[target_id] = p
            await save_data(PLAYERS_FILE, players)
            await simulate_table_tour(target_id, p["division"], p["club"], rival, outcome)

            await show_admin_user_profile(callback, target_id)


@dp.callback_query(F.data.startswith("adm_season:"))
async def adm_skip_season(callback: CallbackQuery):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("Ошибка доступа.", show_alert=True)
    target_id = callback.data.split(":")[1]
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            p = players[target_id]

            await generate_euro_data(p.get("season", 1) + 1)

            p["season"] += 1
            p["tour"] = 1

            # Сброс флагов плей-офф
            for k in ["round_16_played", "playoff_round_played", "quarter_played", "semi_played", "final_played"]:
                p.pop(k, None)
            p["euro_playoff_stage"] = None
            p["stats_season"] = {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0}
            p["played_league_rivals"] = []
            p["fatigue"] = max(0, p.get("fatigue", 0) - 30)

            euro_data = await load_data(EURO_FILE)
            if euro_data and euro_data.get("status") == "group":
                tournament = None
                for t in ["champions_league", "europa_league", "conference_league"]:
                    if p["club"] in euro_data[t]["clubs"]:
                        tournament = t
                        break
                if tournament:
                    p["euro_tournament"] = tournament
                    p["euro_playoff_stage"] = None
                    p["euro_goals"] = 0
                    p["euro_assists"] = 0
                    p["euro_matches"] = 0
                else:
                    p["euro_tournament"] = "none"

            await init_tables_for_user(target_id, p["division"], p["club"])

            players[target_id] = p
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
    try:
        amount = int(message.text.strip())
    except Exception:
        return await message.answer("❌ Число!")
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
    try:
        rating = float(message.text.strip())
    except Exception:
        return await message.answer("❌ Число!")
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            players[target_id]["rating"] = rating
            await save_data(PLAYERS_FILE, players)
            await show_admin_user_profile(message, target_id)
    await state.clear()


# ============================================================
# START И СОЗДАНИЕ ПЕРСОНАЖА
# ============================================================

@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()

    if not await check_sub(message.from_user.id):
        return await message.answer(
            "❗️ **Для игры необходимо подписаться на нашего спонсора!**\nСначала подпишитесь, а затем нажмите кнопку проверки.",
            reply_markup=sub_keyboard(), parse_mode="Markdown"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"),
         InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])
    await message.answer("⚽ **Добро пожаловать в симулятор футболиста!**\nВыбери слот для игры:",
                         reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data == "check_sub_callback")
async def check_sub_handler(callback: CallbackQuery, state: FSMContext):
    if not await check_sub(callback.from_user.id):
        return await callback.answer("❌ Вы не подписались! Подпишитесь и попробуйте снова.", show_alert=True)

    await callback.message.delete()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"),
         InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])
    await callback.message.answer("✅ Подписка подтверждена!\n\n⚽ **Добро пожаловать в симулятор футболиста!**\nВыбери слот для игры:",
                                  reply_markup=kb, parse_mode="Markdown")


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
        await callback.message.edit_text(
            f"👋 **С возвращением, {players[user_id]['name']}!** (Слот {slot})\nТвой ID: `{user_id}`",
            reply_markup=await main_menu_keyboard(callback.from_user.username, user_id),
            parse_mode="Markdown"
        )
    else:
        if user_id in players and players[user_id].get("retired", False):
            history = players[user_id].get("career_history", [])
            await state.update_data(career_history=history)
            await callback.message.edit_text(
                f"⚽ **Твоя прошлая карьера (Слот {slot}) окончена. Начнем новую!**\nДля начала введи Имя и Фамилию:",
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                f"⚽ **Создаем профиль в Слоте {slot}!**\nДля начала введи Имя и Фамилию:",
                parse_mode="Markdown"
            )
        await state.set_state(PlayerCreation.waiting_for_name)


@dp.message(PlayerCreation.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=NATIONS[i], callback_data=f"nat:{NATIONS[i]}"),
         InlineKeyboardButton(
             text=NATIONS[i + 1] if i + 1 < len(NATIONS) else NATIONS[i],
             callback_data=f"nat:{NATIONS[i + 1] if i + 1 < len(NATIONS) else NATIONS[i]}"
         )]
        for i in range(0, min(len(NATIONS), 12), 2)
    ])
    await message.answer("🌍 **Выбери свою национальность (основные страны):**",
                         reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_nation)


@dp.callback_query(PlayerCreation.waiting_for_nation, F.data.startswith("nat:"))
async def process_nation(callback: CallbackQuery, state: FSMContext):
    await state.update_data(nation=callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=pos, callback_data=f"pos:{POSITIONS[pos]}")]
        for pos in POSITIONS.keys()
    ])
    await callback.message.edit_text("📋 **Выбери амплуа:**", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_position)


@dp.callback_query(PlayerCreation.waiting_for_position, F.data.startswith("pos:"))
async def process_position(callback: CallbackQuery, state: FSMContext):
    await state.update_data(position=callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Россия", callback_data="league:Россия"),
         InlineKeyboardButton(text="🇫🇷 Франция", callback_data="league:Франция")],
        [InlineKeyboardButton(text="🏴󠁧󠁢󠁥󠁮󠁧󠁿 Англия", callback_data="league:Англия"),
         InlineKeyboardButton(text="🇪🇸 Испания", callback_data="league:Испания")],
        [InlineKeyboardButton(text="🇮🇹 Италия", callback_data="league:Италия"),
         InlineKeyboardButton(text="🇩🇪 Германия", callback_data="league:Германия")],
        [InlineKeyboardButton(text="🇵🇹 Португалия", callback_data="league:Португалия"),
         InlineKeyboardButton(text="🇳🇱 Нидерланды", callback_data="league:Нидерланды")],
        [InlineKeyboardButton(text="🇧🇪 Бельгия", callback_data="league:Бельгия"),
         InlineKeyboardButton(text="🇧🇾 Беларусь", callback_data="league:Беларусь")],
        [InlineKeyboardButton(text="🇹🇷 Турция", callback_data="league:Турция")],
        [InlineKeyboardButton(text="🇰🇿 Казахстан", callback_data="league:Казахстан")]
    ])
    await callback.message.edit_text("🌍 **В какой стране начнешь карьеру?**",
                                     reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_country_league)


@dp.callback_query(PlayerCreation.waiting_for_country_league, F.data.startswith("league:"))
async def process_country_league(callback: CallbackQuery, state: FSMContext):
    league_country = callback.data.split(":")[1]
    mapping = {
        "Россия": "ФНЛ 2", "Франция": "Насьональ", "Англия": "Первая лига Англии",
        "Испания": "Сегунда", "Германия": "Вторая Бундеслига", "Италия": "Серия Б",
        "Португалия": "Сегунда лига", "Нидерланды": "Эрстедивизи",
        "Бельгия": "Jupiler Pro League", "Беларусь": "Беларусь Первая лига",
        "Турция": "Турция Первая лига", "Казахстан": "Казахстан Премьер-лига"
    }
    div = mapping.get(league_country, "ФНЛ 2")

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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏢 {club}", callback_data=f"club:{club}")]
        for club in available_clubs
    ])
    await message.answer(f"📉 Тобой интересуются клубы из лиги: **{start_div}**. Где начнешь?",
                         reply_markup=kb, parse_mode="Markdown")
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
        "fatigue": 0,
        "girlfriend": "Нет",
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
        "completed_quests": [],
        "train_done": False,
        "train_streak": 0,
        "train_count": 0,
        "train_tech_count": 0,
        "train_phys_count": 0,
        "train_special_count": 0,
        "train_achievements": [],
        "is_injured": False,
        "injury_tours": 0,
        "username_tg": callback.from_user.username,
        "career_history": user_data.get("career_history", []),
        "retired": False,
        "activity_minutes": 0,
        "activity_week": datetime.now().isocalendar()[1],
        "reputation": 50,
        "motivation": 50,
        "married": False,
        "children": 0,
        "wife_loyalty": 0,
        "business": None,
        "business_crisis": False,
        "business_crisis_timer": 0,
        "car": None,
        "has_yoga_bonus": False,
        "last_interview_tour": 0,
        "rating_performance": 0,
        "age_penalty_applied": False,
        "euro_tournament": None,
        "euro_goals": 0,
        "euro_assists": 0,
        "euro_matches": 0,
        "euro_playoff_stage": None
    }

    players = await load_data(PLAYERS_FILE)
    players[user_id] = player_profile
    await save_data(PLAYERS_FILE, players)
    await init_tables_for_user(user_id, player_profile["division"], player_profile["club"])

    await state.clear()
    await callback.message.edit_text(
        f"✍️ **КОНТРАКТ ПОДПИСАН!** Добро пожаловать в {player_profile['club']}!\n"
        f"💰 Твоя зарплата: {player_profile['contract_salary']}$ за матч.",
        parse_mode="Markdown",
        reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
    )


@dp.callback_query(F.data == "start_new_career")
@with_user_lock
async def start_new_career_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"),
         InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(
            "⚽ **Добро пожаловать в симулятор футболиста!**\nВыбери слот для игры:",
            reply_markup=kb, parse_mode="Markdown"
        )
    else:
        try:
            await callback.message.edit_text(
                "⚽ **Добро пожаловать в симулятор футболиста!**\nВыбери слот для игры:",
                reply_markup=kb, parse_mode="Markdown"
            )
        except Exception:
            await callback.message.answer(
                "⚽ **Добро пожаловать в симулятор футболиста!**\nВыбери слот для игры:",
                reply_markup=kb, parse_mode="Markdown"
            )


@dp.callback_query(F.data == "delete_career")
@with_user_lock
async def delete_career_confirm(callback: CallbackQuery):
    user_id = await get_uid(callback)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data="delete_career_yes")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(
        "🗑 **Вы уверены, что хотите удалить свою карьеру?**\nЭто действие необратимо!",
        parse_mode="Markdown", reply_markup=kb
    )


@dp.callback_query(F.data == "delete_career_yes")
@with_user_lock
async def delete_career_final(callback: CallbackQuery, state: FSMContext):
    players = await load_data(PLAYERS_FILE)
    user_id = await get_uid(callback)
    if user_id in players:
        del players[user_id]
        await save_data(PLAYERS_FILE, players)

    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"),
         InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])
    await callback.message.edit_text(
        "🗑 **Карьера удалена!**\n\n⚽ **Выбери слот для новой игры:**",
        reply_markup=kb, parse_mode="Markdown"
    )


# ============================================================
# ТРЕНИРОВКИ
# ============================================================

@dp.callback_query(F.data == "menu_train_choice")
@with_user_lock
async def train_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    if p.get("injury_tours", 0) > 0:
        return await callback.answer(f"🚑 Вы травмированы! Осталось лечиться туров: {p['injury_tours']}.", show_alert=True)

    if p.get("train_done", False):
        return await callback.answer("🚫 Сыграй матч, чтобы открыть тренировку.", show_alert=True)

    fatigue = p.get("fatigue", 0)
    if fatigue >= 70:
        return await callback.answer(
            f"🚫 Ты слишком устал! Усталость: {fatigue}%\nСходи в ресторан или отдохни в личной жизни!",
            show_alert=True
        )

    cost = get_train_cost(p.get("rating", 40))
    if p.get("money", 0) < cost:
        return await callback.answer(f"❌ Не хватает денег! Нужно {cost}$, у тебя {p.get('money', 0)}$", show_alert=True)

    position = p.get("position", "ST")
    config = TRAINING_CONFIG.get(position, TRAINING_CONFIG["ST"])

    streak = p.get("train_streak", 0)
    streak_bonus = get_streak_bonus(streak)
    train_count = p.get("train_count", 0)

    fatigue_status = "✅ (можно тренироваться)" if fatigue < 70 else "❌ (отдохни!)"

    text = (
        f"🏋️‍♂️ **ТРЕНИРОВКА**\n━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Рейтинг: **{p['rating']}**\n"
        f"🔋 Усталость: **{fatigue}%** {fatigue_status}\n"
        f"🔥 Серия: **{streak}** тренировок подряд\n"
        f"💪 Бонус за серию: **+{streak_bonus}**\n"
        f"💰 Стоимость: **{cost}$**\n"
        f"📈 Всего тренировок: **{train_count}**\n\n"
        f"**Выбери направление:**"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎯 {config['tech']['name']}", callback_data="train:tech")],
        [InlineKeyboardButton(text=f"🏃 {config['phys']['name']}", callback_data="train:phys")],
        [InlineKeyboardButton(text=f"⭐ {config['special']['name']}", callback_data="train:special")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("train:"))
@with_user_lock
async def train_execute_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    train_type = callback.data.split(":")[1]

    if p.get("injury_tours", 0) > 0:
        return await callback.answer("🚑 Вы травмированы! Тренировка недоступна.", show_alert=True)

    if p.get("train_done", False):
        return await callback.answer("🚫 Сыграй матч, чтобы открыть тренировку.", show_alert=True)

    fatigue = p.get("fatigue", 0)
    if fatigue >= 70:
        return await callback.answer(f"🚫 Ты слишком устал! Усталость: {fatigue}%", show_alert=True)

    cost = get_train_cost(p.get("rating", 40))
    if p.get("money", 0) < cost:
        return await callback.answer(f"❌ Не хватает денег! Нужно {cost}$", show_alert=True)

    position = p.get("position", "ST")
    config = TRAINING_CONFIG.get(position, TRAINING_CONFIG["ST"])
    train_data = config.get(train_type, config["tech"])

    gain = train_data["base_gain"]

    streak = p.get("train_streak", 0)
    streak_bonus = get_streak_bonus(streak)
    total_gain = gain + streak_bonus

    golden = random.random() < 0.05
    if golden:
        total_gain *= 2

    failed = False
    if random.random() < 0.03:
        total_gain = -0.2
        failed = True

    inspiration = random.random() < 0.08

    injury_chance = 0.02 + (fatigue / 100) * 0.05
    injured = False
    injury_tours = 0

    if random.random() < injury_chance:
        injured = True
        injury_tours = random.randint(1, 3)
        p["injury_tours"] = injury_tours
        p["is_injured"] = True
        total_gain -= 0.5

    p["train_done"] = True
    p["fatigue"] = min(100, p.get("fatigue", 0) + train_data["fatigue"])
    p["money"] -= cost
    p["train_streak"] = streak + 1
    p["train_count"] = p.get("train_count", 0) + 1
    p["trust"] = min(100, p.get("trust", 15) + 3)

    p[f"train_{train_type}_count"] = p.get(f"train_{train_type}_count", 0) + 1

    if inspiration:
        p["fatigue"] = max(0, p["fatigue"] - 5)

    p["rating"] = max(1.0, min(100.0, round(p["rating"] + total_gain, 1)))

    new_achievements, ach_reward = check_train_achievements(
        p, p.get("train_count", 0), p.get("train_streak", 0)
    )

    if new_achievements:
        p["rating"] += ach_reward
        train_achievements = p.get("train_achievements", [])
        for ach in new_achievements:
            for key, val in TRAIN_ACHIEVEMENTS.items():
                if val["name"] == ach["name"] and key not in train_achievements:
                    train_achievements.append(key)
                    break
        p["train_achievements"] = train_achievements

    p["reputation"] = min(100, p.get("reputation", 50) + 0.5)

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await callback.message.delete()

    msg_lines = ["💪 **ТРЕНИРОВКА ЗАВЕРШЕНА!**", "━━━━━━━━━━━━━━━━━━━━"]
    msg_lines.append(f"📋 Направление: **{train_data['name']}**")

    if failed:
        msg_lines.append("😞 **ПРОВАЛ!** Рейтинг -0.2")
    elif injured:
        msg_lines.append(f"🚑 **ТРАВМА!** Выбытие на {injury_tours} тур(а)")
        msg_lines.append("📉 Рейтинг: -0.5 (штраф за травму)")
    else:
        msg_lines.append(f"📈 Прирост: +{gain}")
        if streak_bonus > 0:
            msg_lines.append(f"🔥 Бонус серии ({streak}): +{streak_bonus}")
        if golden:
            msg_lines.append("🌟 **ЗОЛОТАЯ ТРЕНИРОВКА! x2**")
        if inspiration:
            msg_lines.append("💡 Вдохновение! Усталость -5%")

    msg_lines.append("━━━━━━━━━━━━━━━━━━━━")
    msg_lines.append(f"⚡ Рейтинг: **{p['rating']}**")
    msg_lines.append(f"❤️ Доверие: **{p['trust']}**")
    msg_lines.append(f"🔋 Усталость: **{p['fatigue']}%**")
    msg_lines.append(f"💰 Потрачено: **{cost}$**")
    msg_lines.append(f"💵 Баланс: **{p['money']}$**")
    msg_lines.append("━━━━━━━━━━━━━━━━━━━━")
    msg_lines.append(f"🔥 Серия: **{p['train_streak']}** тренировок подряд")

    if new_achievements:
        msg_lines.append("━━━━━━━━━━━━━━━━━━━━")
        msg_lines.append("🎉 **НОВЫЕ ДОСТИЖЕНИЯ!**")
        for ach in new_achievements:
            msg_lines.append(f"🏅 {ach['name']} (+{ach['reward']})")

    if injured:
        msg_lines.append("\n⏳ Ты пропустишь матчи до восстановления!")

    await callback.message.answer(
        text="\n".join(msg_lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]
        ])
    )


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer("🏠 Главное меню.",
                                      reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    else:
        try:
            await callback.message.edit_text("🏠 Главное меню.",
                                             reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
        except Exception:
            await callback.message.answer("🏠 Главное меню.",
                                          reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))


@dp.callback_query(F.data == "menu_table")
@with_user_lock
async def show_table_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    tables = await load_data(TABLES_FILE)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

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
        await callback.message.answer(text, parse_mode="Markdown",
                                      reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown",
                                             reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))
        except Exception:
            await callback.message.answer(text, parse_mode="Markdown",
                                          reply_markup=await main_menu_keyboard(callback.from_user.username, user_id))


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
            try:
                await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=retired_keyboard())
            except Exception:
                await callback.message.answer(text, parse_mode="Markdown", reply_markup=retired_keyboard())
        return

    val = calculate_player_value(p["rating"], p["division"])

    loan_status = f"\n⚠️ *В аренде из {p['parent_club']}* (Осталось: {p['loan_tours_left']} тур.)" if p.get("on_loan") else ""
    injury_status = f"\n🚑 *Травмирован!* (Лечиться еще: {p.get('injury_tours', 0)} тур.)" if p.get("injury_tours", 0) > 0 else ""

    if p["position"] == "GK":
        stats_text = f"🧤 Сейвы: {p['stats_season'].get('saves', 0)}"
    elif p["position"] == "CB":
        stats_text = f"🛡️ Отборы: {p['stats_season'].get('tackles', 0)} | ⚽ Голы: {p['stats_season'].get('goals', 0)}"
    else:
        stats_text = f"⚽ Голы: {p['stats_season'].get('goals', 0)} | 🅰️ Ассисты: {p['stats_season'].get('assists', 0)}"

    history_str = ""
    if p.get("career_history"):
        history_str = "\n\n📚 **Прошлые карьеры:**\n" + "\n\n".join(p["career_history"])

    season_display = min(p['season'], 13)
    tour_display = min(p['tour'], 30)

    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Удалить карьеру", callback_data="delete_career")])

    train_stats = (
        f"\n📊 **Тренировки:**\n"
        f"🔥 Серия: {p.get('train_streak', 0)}\n"
        f"📈 Всего: {p.get('train_count', 0)}\n"
        f"🎯 Техника: {p.get('train_tech_count', 0)} раз\n"
        f"🏃 Физика: {p.get('train_phys_count', 0)} раз\n"
        f"⭐ Специальная: {p.get('train_special_count', 0)} раз\n"
        f"🏅 Достижений: {len(p.get('train_achievements', []))}"
    )

    euro_stats = ""
    if p.get("euro_tournament") and p.get("euro_tournament") != "none":
        euro_stats = (
            f"\n🌍 **Еврокубки:** {get_euro_name(p['euro_tournament'])}\n"
            f"📈 Матчей: {p.get('euro_matches', 0)} | ⚽ Голов: {p.get('euro_goals', 0)} | 🅰️ Ассистов: {p.get('euro_assists', 0)}"
        )

    text = (
        f"👑 ПРОФИЛЬ ИГРОКА\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃‍♂️ {p['name']} | 🌍 {p.get('nation', 'Россия')} | 🎂 {p.get('age', 17)} лет\n"
        f"⚡️ Рейтинг: {p['rating']}/100\n"
        f"🏢 Клуб: {p['club']} ({p['position']}){loan_status}{injury_status}\n"
        f"💵 Баланс: {p.get('money', 0)}$ | 🏷️ Стоимость: {val:,}$\n"
        f"🤝 Зарплата: {p.get('contract_salary', 0)}$/матч\n"
        f"💎 Спонсор: {p.get('sponsor', 'Нет')}\n"
        f"📊 Статус: {get_status_by_trust(p['trust'])}\n"
        f"🔋 Усталость: {p.get('fatigue', 0)}%\n"
        f"💍 Девушка: {p.get('girlfriend', 'Нет')}\n"
        f"🏟️ Сезон: {season_display}/13 | Тур Лиги: {tour_display}/30\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **Текущая карьера (за сезон):**\n{stats_text}\n"
        f"📈 **Общая статистика (текущий игрок):**\nВсего игр: {p.get('stats_total', {}).get('games', 0)} | Голов: {p.get('stats_total', {}).get('goals', 0)} | Ассистов: {p.get('stats_total', {}).get('assists', 0)}"
        f"{euro_stats}{train_stats}{history_str}"
    )
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await callback.message.answer(text, reply_markup=kb)


# ============================================================
# ОСНОВНОЙ МАТЧ ЛИГИ
# ============================================================

@dp.callback_query(F.data.startswith("scandal_club:"))
@with_user_lock
async def scandal_club_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    new_club = callback.data.split(":")[1]

    p["club"] = new_club
    p["division"] = get_division(new_club)
    p["trust"] = 15

    base_salaries = {
        "ФНЛ 2": 1500, "Насьональ": 1500, "Первая лига Англии": 1800,
        "ФНЛ": 6000, "Лига 2": 6000, "Чемпионшип": 8000, "Сегунда": 8000, "Серия Б": 8000, "Вторая Бундеслига": 7500,
        "РПЛ": 30000, "Лига 1": 30000, "АПЛ": 50000, "Ла Лига": 50000, "Серия А": 45000, "Бундеслига": 48000,
        "Примейра": 35000, "Сегунда лига": 7500,
        "Бразильская Серия А": 30000,
        "Эрстедивизи": 7500, "Эредивизи": 35000,
        "Jupiler Pro League": 35000,
        "Беларусь Первая лига": 2000,
        "Беларусь Высшая лига": 5000,
        "Турция Первая лига": 3000,
        "Турция Суперлига": 25000,
        "Казахстан Премьер-лига": 25000
    }
    p["contract_salary"] = int(base_salaries.get(p["division"], 1500) * (p["rating"] / 45))
    p["played_league_rivals"] = []

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    if p.get("tour", 1) <= 1:
        await init_tables_for_user(user_id, p["division"], p["club"])
    else:
        await simulate_table_until_tour(user_id, p["division"], p["club"], p["tour"])

    euro_data = await load_data(EURO_FILE)
    if euro_data and euro_data.get("status") == "group":
        tournament = None
        for t in ["champions_league", "europa_league", "conference_league"]:
            if p["club"] in euro_data[t]["clubs"]:
                tournament = t
                break
        p["euro_tournament"] = tournament if tournament else "none"

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    await callback.message.delete()
    await callback.message.answer(
        text=f"✍️ Ты успешно перешел в **{new_club}**!\n"
             f"💵 Твоя новая зарплата: **{p['contract_salary']}$/матч**.\n"
             f"📊 Таблица для новой лиги создана!\n"
             f"Пора доказывать фанатам свою преданность!",
        parse_mode="Markdown",
        reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
    )


@dp.callback_query(F.data == "menu_match")
@with_user_lock
async def match_handler(callback: CallbackQuery, state: FSMContext):
    if not await check_sub(callback.from_user.id):
        return await callback.message.answer(
            "❗️ **Для игры необходимо подписаться на нашего спонсора!**\nСначала подпишитесь, а затем продолжите игру.",
            reply_markup=sub_keyboard(), parse_mode="Markdown"
        )

    user_id = await get_uid(callback)
    await heal_injury_if_needed(user_id)
    await track_activity(user_id)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    if not p.get("train_done", False):
        if p.get("train_streak", 0) > 0:
            p["train_streak"] = 0
            players[user_id] = p
            await save_data(PLAYERS_FILE, players)
            await send_auto_delete_message(
                callback.message,
                "⚠️ **СЕРИЯ ПРЕРВАНА!**\nТы сыграл матч, но не потренировался.\n🔥 Серия тренировок сброшена до 0!",
                delay=3
            )

    trust = p.get("trust", 15)
    status = get_status_by_trust(trust)

    if trust < 21:
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
        p["stats_season"]["games"] += 1

        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        await simulate_table_tour(user_id, p["division"], p["club"], rival, outcome)

        if callback.message.photo:
            await callback.message.delete()

        await send_auto_delete_message(
            callback.message,
            f"🪑 **ТЫ В РЕЗЕРВЕ!**\nТы не попал в состав на матч против **{rival}**.\n"
            f"📊 Статус: {status}\n💡 Подними доверие (trust) до 21, чтобы играть!\n"
            f"🔹 Итог матча: **{'Победа' if outcome == 'win' else 'Ничья' if outcome == 'draw' else 'Поражение'}**",
            delay=3
        )
        return

    if p.get("injury_tours", 0) > 0:
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
        p["stats_season"]["games"] += 1

        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        await simulate_table_tour(user_id, p["division"], p["club"], rival, outcome)

        if callback.message.photo:
            await callback.message.delete()

        msg = (f"🚑 **ТЫ ПРОПУСТИЛ ТУР ИЗ-ЗА ТРАВМЫ**\n"
               f"Команда сыграла против **{rival}**. Итог: "
               f"**{'Победа' if outcome == 'win' else 'Ничья' if outcome == 'draw' else 'Поражение'}**.\n")
        if p["injury_tours"] > 0:
            msg += f"⏳ Осталось лечиться: {p['injury_tours']} тур(а)."
        else:
            msg += "✅ **Ты полностью восстановился и готов к следующему матчу!**"

        await send_auto_delete_message(callback.message, msg, delay=3)
        return

    if p.get("fatigue", 0) >= 95:
        return await callback.answer("🚫 Ты смертельно устал! Сходи в ресторан.", show_alert=True)

    current_rating = p.get("rating", 40)

    if trust < 51:
        total_moments = random.randint(1, 2)
        await send_auto_delete_message(
            callback.message,
            f"🔄 **ТЫ НА ЗАМЕНЕ!**\nТы выйдешь на поле во втором тайме.\n"
            f"📊 Статус: {status}\n💡 Играй лучше, чтобы попасть в старт!",
            delay=3
        )
    else:
        total_moments = random.randint(2, 4)

    offer_made = False
    if not offer_made and p["division"] not in ["Бундеслига", "Вторая Бундеслига"] and random.random() < 0.10:
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

    if not offer_made and p["division"] not in ["Примейра", "Сегунда лига"] and random.random() < 0.10:
        if current_rating >= 74:
            pt_offers = random.sample(CLUBS["Примейра"], 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🇵🇹 {c}", callback_data=f"scandal_club:{c}")] for c in pt_offers
            ] + [[InlineKeyboardButton(text="❌ Отклонить предложение", callback_data="back_to_menu")]])
            await callback.message.delete()
            return await callback.message.answer(
                text=f"📈 **ТРАНСФЕРНОЕ ПРЕДЛОЖЕНИЕ!** Твой высокий рейтинг ({current_rating}) привлек внимание клубов из Португалии! Тебе предлагают контракт в **Примейре**:",
                reply_markup=kb, parse_mode="Markdown"
            )
        elif current_rating >= 55:
            pt_offers = random.sample(CLUBS["Сегунда лига"], 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🇵🇹 {c}", callback_data=f"scandal_club:{c}")] for c in pt_offers
            ] + [[InlineKeyboardButton(text="❌ Отклонить предложение", callback_data="back_to_menu")]])
            await callback.message.delete()
            return await callback.message.answer(
                text=f"📈 **ТРАНСФЕРНОЕ ПРЕДЛОЖЕНИЕ!** На основе твоего рейтинга ({current_rating}) команды из Португалии предлагают тебе контракт в **Сегунда лиге**:",
                reply_markup=kb, parse_mode="Markdown"
            )

    if p["tour"] > 30:
        return await season_results_handler(callback)

    if random.random() < 0.01:
        div_clubs = [c for c in CLUBS[p["division"]] if c != p["club"]]
        available_clubs = random.sample(div_clubs, min(len(div_clubs), 2))

        top_leagues = ["РПЛ", "Лига 1", "АПЛ", "Ла Лига", "Серия А", "Бундеслига", "Примейра",
                       "Бразильская Серия А", "Эредивизи", "Jupiler Pro League",
                       "Беларусь Высшая лига", "Турция Суперлига", "Казахстан Премьер-лига"]
        my_top_league = "РПЛ"
        if p["division"] in ["Насьональ", "Лига 2", "Лига 1"]: my_top_league = "Лига 1"
        elif p["division"] in ["Первая лига Англии", "Чемпионшип", "АПЛ"]: my_top_league = "АПЛ"
        elif p["division"] in ["Сегунда", "Ла Лига"]: my_top_league = "Ла Лига"
        elif p["division"] in ["Серия Б", "Серия А"]: my_top_league = "Серия А"
        elif p["division"] in ["Вторая Бундеслига", "Бундеслига"]: my_top_league = "Бундеслига"
        elif p["division"] in ["Сегунда лига", "Примейра"]: my_top_league = "Примейра"
        elif p["division"] in ["Бразильская Серия А"]: my_top_league = "Бразильская Серия А"
        elif p["division"] in ["Эрстедивизи", "Эредивизи"]: my_top_league = "Эредивизи"
        elif p["division"] in ["Jupiler Pro League"]: my_top_league = "Jupiler Pro League"
        elif p["division"] in ["Беларусь Первая лига", "Беларусь Высшая лига"]: my_top_league = "Беларусь Высшая лига"
        elif p["division"] in ["Турция Первая лига", "Турция Суперлига"]: my_top_league = "Турция Суперлига"
        elif p["division"] in ["Казахстан Премьер-лига"]: my_top_league = "Казахстан Премьер-лига"

        alt_leagues = [l for l in top_leagues if l != my_top_league]
        alt_league = random.choice(alt_leagues) if alt_leagues else "РПЛ"
        available_clubs.append(random.choice(CLUBS[alt_league]))
        random.shuffle(available_clubs)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🏢 {club}", callback_data=f"scandal_club:{club}")]
            for club in available_clubs
        ])
        await callback.message.delete()
        return await callback.message.answer(
            text=f"🤬 **СКАНДАЛ С РУКОВОДСТВОМ!** Твой контракт с {p['club']} разорван.\n"
                 f"Интерес к тебе проявили клубы. Выбери новую команду:",
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
        elif p["division"] in ["Сегунда лига", "Примейра"]: country_leagues = ["Сегунда лига", "Примейра"]
        elif p["division"] in ["Бразильская Серия А"]: country_leagues = ["Бразильская Серия А"]
        elif p["division"] in ["Эрстедивизи", "Эредивизи"]: country_leagues = ["Эрстедивизи", "Эредивизи"]
        elif p["division"] in ["Jupiler Pro League"]: country_leagues = ["Jupiler Pro League"]
        elif p["division"] in ["Беларусь Первая лига", "Беларусь Высшая лига"]: country_leagues = ["Беларусь Первая лига", "Беларусь Высшая лига"]
        elif p["division"] in ["Турция Первая лига", "Турция Суперлига"]: country_leagues = ["Турция Первая лига", "Турция Суперлига"]
        elif p["division"] in ["Казахстан Премьер-лига"]: country_leagues = ["Казахстан Премьер-лига"]

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
        "total_moments": total_moments,
        "current_moment": 1,
        "minute": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0, "yellow_cards": 0,
        "my_team_score": 0, "rival_team_score": 0,
        "is_cup": is_cup_match, "cup_stage": cup_stg if is_cup_match else None,
        "log": ""
    }
    await state.update_data(match=match_data)

    match_title = f"🏆 НАЦИОНАЛЬНЫЙ КУБОК ({cup_stg}) 🏆" if is_cup_match else f"🏟️ РЕГУЛЯРНЫЙ ЧЕМПИОНАТ ({p['division']})"

    if callback.message.photo:
        await callback.message.delete()
    msg = await callback.message.answer(
        f"⚽ **{match_title}**\n⚔️ **{p['club']}** vs **{match_data['rival']}**\nСудья дает свисток к началу игры!",
        parse_mode="Markdown"
    )
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
    if m["minute"] > 90:
        m["minute"] = 90

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
        is_knockout = m["is_cup"]
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
            [InlineKeyboardButton(text="🧤 Прыгнуть в левый угол", callback_data="gk_act:left"),
             InlineKeyboardButton(text="🧤 Прыгнуть в правый угол", callback_data="gk_act:right")],
            [InlineKeyboardButton(text="🏃 Сблизить дистанцию", callback_data="gk_act:rush")]
        ])
    elif p["position"] == "CB":
        if random.random() < 0.75:
            text += "🛡️ **Форвард соперника идет на дриблинге прямо в твою зону!**"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🧲 Жесткий подкат", callback_data="cb_act:tackle_hard"),
                 InlineKeyboardButton(text="🕴️ Встретить корпусом", callback_data="cb_act:tackle_smart")],
                [InlineKeyboardButton(text="📐 Отдать пас ближнему", callback_data="act:pass")]
            ])
        else:
            text += "🔥 **Ты подключился на угловой! Мяч летит к тебе!**"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Пробить головой", callback_data="act:shoot_menu"),
                 InlineKeyboardButton(text="📐 Сбросить под удар партнеру", callback_data="act:pass")]
            ])
    else:
        text += "🔥 **Ты контролируешь мяч на подступах к штрафной! Твое решение?**"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Пробить по воротам", callback_data="act:shoot_menu"),
             InlineKeyboardButton(text="📐 Отдать пас", callback_data="act:pass")]
        ])

    await state.update_data(match=m)
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
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
    if action == "rush":
        is_saved = random.random() < (save_chance + 0.1)
    else:
        is_saved = (action == opp_shoot_dir) or (random.random() < save_chance * 0.8)

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
@with_user_lock
async def act_shoot_menu_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "match" not in data:
        return await callback.answer("⏳ Матч уже завершен!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 Левый верхний (Девятка)", callback_data="shoot_dir:в левую девятку"),
         InlineKeyboardButton(text="📐 Правый верхний (Девятка)", callback_data="shoot_dir:в правую девятку")],
        [InlineKeyboardButton(text="👇 Левый нижний", callback_data="shoot_dir:низом в левый угол"),
         InlineKeyboardButton(text="👇 Правый нижний", callback_data="shoot_dir:низом в правый угол")]
    ])
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass


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
    score_chance = 0.60 + ((p["rating"] - rival_rating) * 0.015)
    gk_dive = random.choice(["в левую девятку", "в правую девятку", "низом в левый угол", "низом в правый угол"])

    if gk_dive == target_dir:
        score_chance -= 0.15
        gk_guessed = True
    else:
        score_chance += 0.10
        gk_guessed = False
    score_chance = max(0.05, min(0.95, score_chance))

    if random.random() < score_chance:
        m["goals"] += 1
        m["my_team_score"] += 1
        try:
            await callback.message.edit_text(
                f"⚽ **{m['minute']}'** | ГОЛ! Твой шикарный удар {target_dir} разрывает сетку ворот!",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await asyncio.sleep(2)
        m["log"] += f"⚽ **{m['minute']}'** | ГОЛ! Твой шикарный удар {target_dir}!\n"
    else:
        if gk_guessed:
            m["log"] += f"❌ **{m['minute']}'** | Ты пробил {target_dir}, но голкипер парировал удар!\n"
        else:
            m["log"] += f"❌ **{m['minute']}'** | Целился {target_dir}, но мяч пролетел мимо!\n"
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
    p = (await load_data(PLAYERS_FILE)).get(user_id)

    rival_rating = CLUB_RATINGS.get(m["rival"], 50)
    pass_chance = 0.60 + ((p["rating"] - rival_rating) * 0.015)
    pass_chance = max(0.05, min(0.95, pass_chance))

    if random.random() < pass_chance:
        m["assists"] += 1
        m["my_team_score"] += 1
        m["log"] += f"✅ **{m['minute']}'** | Шикарный точный пас на партнера, и он вколачивает мяч в сетку! ГОЛ!\n"
    else:
        m["log"] += f"❌ **{m['minute']}'** | Пас оказался неточным, перехват соперника.\n"
    m["current_moment"] += 1
    await state.update_data(match=m)
    await generate_moment(callback, state, user_id)


async def _clear_match_state(state: FSMContext):
    data = await state.get_data()
    data.pop("match", None)
    await state.set_data(data)


async def start_penalty_shootout(callback: CallbackQuery, state: FSMContext, user_id: str):
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

    p.setdefault("stats_season", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})
    p.setdefault("stats_total", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})
    for stat in ("goals", "assists", "saves", "tackles"):
        p["stats_season"][stat] = p["stats_season"].get(stat, 0) + m.get(stat, 0)
        p["stats_total"][stat] = p["stats_total"].get(stat, 0) + m.get(stat, 0)
    p["stats_total"]["games"] = p["stats_total"].get("games", 0) + 1

    goals = m.get("goals", 0)
    assists = m.get("assists", 0)
    saves = m.get("saves", 0)
    tackles = m.get("tackles", 0)
    conceded = m.get("rival_team_score", 0)

    raw = (goals * 0.35 + assists * 0.25 + saves * 0.25 + tackles * 0.15
           - conceded * 0.10
           + (0.20 if outcome == "win" else (-0.15 if outcome == "loss" else 0.0)))
    raw = max(-1.0, min(1.0, raw))
    rating_delta = round(raw * 0.06, 2)
    p["rating"] = round(max(1.0, min(100.0, p.get("rating", 40.0) + rating_delta)), 2)

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
                p["rating"] = max(1.0, min(100.0, round(p["rating"] + 0.5, 1)))
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

    age = p.get("age", 17)
    if age >= 36:
        p["rating"] = max(1.0, round(p["rating"] - 0.3, 1))
    elif age >= 33:
        p["rating"] = max(1.0, round(p["rating"] - 0.2, 1))
    elif age >= 30:
        p["rating"] = max(1.0, round(p["rating"] - 0.1, 1))

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await _clear_match_state(state)

    penalty_line = ""
    if penalty_result:
        my_pen, rival_pen, _ = penalty_result
        penalty_line = f"🥅 Пенальти: {my_pen} : {rival_pen}\n"

    sponsor_line = (f"💼 Доход от {p.get('sponsor')}: +{sponsor_income}$\n" if sponsor_income else "")

    rating_performance = 5.0
    rating_performance += goals * 1.0
    rating_performance += assists * 0.8
    rating_performance += saves * 0.5
    rating_performance += tackles * 0.5
    if outcome == "win":
        rating_performance += 1.0
    elif outcome == "draw":
        rating_performance += 0.5
    rating_performance -= conceded * 0.3
    rating_performance = max(5.0, min(10.0, rating_performance))
    rating_performance = round(rating_performance, 1)
    p["rating_performance"] = rating_performance

    text = (
        f"🏁 **МАТЧ ЗАВЕРШЕН!**\n"
        f"⚔️ **{p['club']} {m['my_team_score']} : {m['rival_team_score']} {m['rival']}**\n"
        f"{penalty_line}{outcome_text}\n\n"
        f"📊 **Оценка за матч: {rating_performance} / 10**\n"
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

    if rating_performance >= 9.0:
        await start_interview(callback, state, user_id, p)


def _pick_offers_by_rating(rating: float, current_club: str, current_division: str) -> list:
    low = max(0, int(rating) - 15)
    high = min(100, int(rating) + 20)
    candidates = []
    for div, clubs in CLUBS.items():
        for club in clubs:
            cr = CLUB_RATINGS.get(club, 50)
            if low <= cr <= high and club != current_club:
                candidates.append({"club": club, "division": div, "club_rating": cr})
    if len(candidates) < 4:
        candidates = [
            {"club": c, "division": d, "club_rating": CLUB_RATINGS.get(c, 50)}
            for d, clubs in CLUBS.items()
            for c in clubs
            if c != current_club
        ]
    random.shuffle(candidates)
    seen_divs = set()
    offers = []
    for cand in candidates:
        if cand["division"] not in seen_divs:
            seen_divs.add(cand["division"])
            salary = max(1500, int(cand["club_rating"] * 150 + rating * 50))
            cand["salary"] = salary
            offers.append(cand)
        if len(offers) == 4:
            break
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


async def start_interview(callback: CallbackQuery, state: FSMContext, user_id: str, p: dict):
    questions = [
        {
            "question": "Как ты оцениваешь свой вклад в сегодняшнюю победу?",
            "a": "Я был лидером и вёл команду за собой",
            "b": "Я просто выполнял свою работу на поле",
            "trust_a": 5, "trust_b": 2
        },
        {
            "question": "Что бы ты сказал болельщикам после такого матча?",
            "a": "Спасибо за вашу невероятную поддержку!",
            "b": "Мы ещё не всё показали, впереди много побед!",
            "trust_a": 3, "trust_b": 4
        },
        {
            "question": "Какой момент матча ты запомнил больше всего?",
            "a": "Мой забитый мяч / сейв / отбор",
            "b": "Командная работа и дух борьбы",
            "trust_a": 4, "trust_b": 3
        }
    ]
    await state.set_state(InterviewState.waiting_for_answer)
    await state.update_data(interview={"questions": questions, "trust_gain": 0})
    q0 = questions[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=q0["a"], callback_data="interview:0:a")],
        [InlineKeyboardButton(text=q0["b"], callback_data="interview:0:b")]
    ])
    await callback.message.answer(
        f"🎙️ **Поздравляем с выдающимся матчем! Твоя оценка {p.get('rating_performance', 9.0)}!**\n"
        f"Журналисты хотят задать тебе несколько вопросов.\n\n"
        f"**Вопрос 1/3:**\n_{q0['question']}_",
        parse_mode="Markdown", reply_markup=kb
    )


@dp.callback_query(F.data.startswith("interview:"))
@with_user_lock
async def interview_handler(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer()
    q_idx = int(parts[1])
    choice = parts[2]

    data = await state.get_data()
    iv = data.get("interview")
    if not iv:
        await callback.answer()
        user_id = await get_uid(callback)
        kb = await main_menu_keyboard(callback.from_user.username, user_id)
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass
        return

    questions = iv["questions"]
    trust_gain = iv.get("trust_gain", 0)
    rep_gain = iv.get("rep_gain", 0)

    if q_idx < len(questions):
        q = questions[q_idx]
        if choice == "a":
            trust_gain += q.get("trust_a", 0)
            rep_gain += q.get("rep_a", 0)
        elif choice == "b":
            trust_gain += q.get("trust_b", 0)
            rep_gain += q.get("rep_b", 0)
        else:
            trust_gain += q.get("trust_c", 0)
            rep_gain += q.get("rep_c", 0)

    user_id = await get_uid(callback)
    next_idx = q_idx + 1

    await callback.answer()

    if next_idx < len(questions):
        await state.update_data(interview={
            "questions": questions,
            "current": next_idx,
            "trust_gain": trust_gain,
            "rep_gain": rep_gain
        })

        nq = questions[next_idx]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"A) {nq['a']}", callback_data=f"interview:{next_idx}:a")],
            [InlineKeyboardButton(text=f"B) {nq['b']}", callback_data=f"interview:{next_idx}:b")]
        ])

        try:
            await callback.message.edit_text(
                f"🎙️ **Интервью — вопрос {next_idx + 1}/3:**\n_{nq['question']}_\n\nВыбери ответ:",
                parse_mode="Markdown", reply_markup=kb
            )
        except Exception as e:
            logging.warning(f"interview next_q error: {e}")
    else:
        await state.update_data(interview=None)
        players = await load_data(PLAYERS_FILE)
        p = players.get(user_id)
        if p:
            p["trust"] = min(100, p.get("trust", 0) + trust_gain)
            p["reputation"] = min(100, max(0, p.get("reputation", 50) + rep_gain))
            players[user_id] = p
            await save_data(PLAYERS_FILE, players)

        trust_now = p.get("trust", 0) if p else 0
        rep_now = p.get("reputation", 50) if p else 50
        text = (
            f"🎙️ **Интервью завершено!**\n"
            f"📣 Твои ответы произвели впечатление на публику!\n"
            f"❤️ +{trust_gain} к доверию болельщиков (итого: {trust_now})\n"
            f"⭐ {rep_gain:+} к репутации (итого: {rep_now})"
        )
        kb = await main_menu_keyboard(callback.from_user.username, user_id)
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logging.warning(f"interview finish error: {e}")
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


# ============================================================
# SEASON RESULTS
# ============================================================

async def season_results_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        table = tables.get(user_id, {}).get(p["division"], [])
    table_sorted = sorted(table, key=lambda x: x["points"], reverse=True)
    total_clubs = max(len(table_sorted), 1)
    position = next((i + 1 for i, row in enumerate(table_sorted) if row["club"] == p["club"]), total_clubs)

    season_num = p.get("season", 1)

    ladder = get_ladder(p["division"])
    idx_in_ladder = ladder.index(p["division"]) if p["division"] in ladder else 0

    promotion_div = None
    relegation_div = None

    if position == 1:
        result_text = f"🥇 **ЧЕМПИОНСТВО!** 1 место из {total_clubs} в **{p['division']}**!"
        p["trophies"] = p.get("trophies", []) + [f"🥇 Чемпион «{p['division']}» (Сезон {season_num})"]
        if idx_in_ladder < len(ladder) - 1:
            promotion_div = ladder[idx_in_ladder + 1]
            result_text += f"\n📈 Ваша команда получила путевку в **{promotion_div}**!"
    elif position <= 2 and idx_in_ladder < len(ladder) - 1:
        promotion_div = ladder[idx_in_ladder + 1]
        result_text = (f"🎉 **ВЫХОД В ВЫСШИЙ ДИВИЗИОН!** {position} место из {total_clubs}.\n"
                       f"Команда пробилась в **{promotion_div}**!")
        p["trophies"] = p.get("trophies", []) + [f"⬆️ Выход в «{promotion_div}» (Сезон {season_num})"]
    elif position >= total_clubs - 1 and total_clubs > 2 and idx_in_ladder > 0:
        relegation_div = ladder[idx_in_ladder - 1]
        result_text = (f"📉 **ВЫЛЕТ!** {position} место из {total_clubs}.\n"
                       f"Команда падает в **{relegation_div}**.")
    else:
        result_text = f"📊 {position} место из {total_clubs} в **{p['division']}**."

    stats = p.get("stats_season", {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0})
    pos_code = p.get("position", "ST")
    if pos_code == "GK":
        stats_text = f"🎮 {stats.get('games', 0)} матчей | 🧤 {stats.get('saves', 0)} сейвов"
    elif pos_code == "CB":
        stats_text = f"🎮 {stats.get('games', 0)} матчей | 🛡️ {stats.get('tackles', 0)} отборов | ⚽ {stats.get('goals', 0)} голов"
    else:
        stats_text = f"🎮 {stats.get('games', 0)} матчей | ⚽ {stats.get('goals', 0)} голов | 🅰️ {stats.get('assists', 0)} ассистов"

    p["age"] = p.get("age", 17) + 1
    retired_now = False

    if season_num > 13 or (p["age"] >= 36 and random.random() < 0.35):
        retired_now = True
        p["retired"] = True
        career_summary = (f"📌 {p['name']} | Рейтинг: {p['rating']} | "
                          f"Клуб: {p['club']} | Трофеев: {len(p.get('trophies', []))}")
        p["career_history"] = p.get("career_history", []) + [career_summary]
        await add_to_retired_leaderboard(p["name"], p["rating"], len(p.get("trophies", [])))

    if retired_now:
        awards = await calculate_player_awards(user_id, season_num)
        bonuses = await apply_awards_bonuses(user_id, awards, season_num)
        players = await load_data(PLAYERS_FILE)
        p = players.get(user_id)

        _apply_new_season_reset(p)
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)

        awards_text = ""
        if awards:
            awards_text = "\n\n🏆 **НОМИНАЦИИ СЕЗОНА:**\n"
            if awards.get("golden_ball"):
                gb = awards["golden_ball"]
                mark = "⭐ " if gb.get("is_player") else ""
                awards_text += f"🥇 ЗМ: {mark}{gb['name']}\n"
            if awards.get("golden_glove"):
                gg = awards["golden_glove"]
                mark = "⭐ " if gg.get("is_player") else ""
                awards_text += f"🧤 ЗП: {mark}{gg['name']}\n"
            if awards.get("best_defender"):
                bd = awards["best_defender"]
                mark = "⭐ " if bd.get("is_player") else ""
                awards_text += f"🛡️ ЛЗ: {mark}{bd['name']}\n"
            if awards.get("best_assistant"):
                ba = awards["best_assistant"]
                mark = "⭐ " if ba.get("is_player") else ""
                awards_text += f"🅰️ ЛА: {mark}{ba['name']}\n"

        if bonuses:
            awards_text += "\n🎁 **ТВОИ НАГРАДЫ:**\n" + "\n".join(bonuses)

        text = (
            f"🏁 **ИТОГИ СЕЗОНА {season_num}**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{result_text}\n\n"
            f"📊 {stats_text}\n"
            f"{awards_text}\n\n"
            f"🏁 **Карьера завершена! Ты провел великий путь и уходишь на заслуженную пенсию.**"
        )
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=retired_keyboard())
        except Exception:
            if callback.message.photo:
                await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=retired_keyboard())
        return

    rating = p.get("rating", 40.0)
    offers = _pick_offers_by_rating(rating, p["club"], p["division"])

    forced_div = promotion_div or relegation_div
    if forced_div:
        forced_club = random.choice([c for c in CLUBS.get(forced_div, []) if c != p["club"]] or CLUBS.get(forced_div, [p["club"]]))
        forced_salary = max(1500, int(CLUB_RATINGS.get(forced_club, 50) * 150 + rating * 50))
        forced_offer = {"club": forced_club, "division": forced_div,
                        "club_rating": CLUB_RATINGS.get(forced_club, 50), "salary": forced_salary}
        offers = [o for o in offers if o["division"] != forced_div][:3]
        offers.insert(0, forced_offer)

    p["_season_offers"] = offers
    p["_season_num"] = season_num
    p["_season_forced_div"] = forced_div
    p["_season_result_text"] = result_text
    p["_season_stats_text"] = stats_text
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    current_salary = p.get("contract_salary", 1500)
    renew_salary = max(current_salary, int(current_salary * 1.15))
    buttons = []
    for i, o in enumerate(offers):
        label = f"🏟 {o['club']} ({o['division']}) — {o['salary']}$/матч"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"season_choice:{i}")])
    buttons.append([InlineKeyboardButton(
        text=f"🔄 Продлить контракт с {p['club']} — {renew_salary}$/матч",
        callback_data="season_choice:renew"
    )])

    awards = await calculate_player_awards(user_id, season_num)
    bonuses = await apply_awards_bonuses(user_id, awards, season_num)

    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)

    awards_text = ""
    if awards:
        awards_text = "\n\n🏆 **НОМИНАЦИИ СЕЗОНА:**\n"
        if awards.get("golden_ball"):
            gb = awards["golden_ball"]
            mark = "⭐ " if gb.get("is_player") else ""
            awards_text += f"🥇 ЗМ: {mark}{gb['name']}\n"
        if awards.get("golden_glove"):
            gg = awards["golden_glove"]
            mark = "⭐ " if gg.get("is_player") else ""
            awards_text += f"🧤 ЗП: {mark}{gg['name']}\n"
        if awards.get("best_defender"):
            bd = awards["best_defender"]
            mark = "⭐ " if bd.get("is_player") else ""
            awards_text += f"🛡️ ЛЗ: {mark}{bd['name']}\n"
        if awards.get("best_assistant"):
            ba = awards["best_assistant"]
            mark = "⭐ " if ba.get("is_player") else ""
            awards_text += f"🅰️ ЛА: {mark}{ba['name']}\n"

    if bonuses:
        awards_text += "\n🎁 **ТВОИ НАГРАДЫ:**\n" + "\n".join(bonuses)

    buttons.append([InlineKeyboardButton(
        text="🏆 Подробнее о номинациях",
        callback_data="menu_awards"
    )])

    text = (
        f"🏁 **ИТОГИ СЕЗОНА {season_num}**\n━━━━━━━━━━━━━━━━━━━━\n"
        f"{result_text}\n\n"
        f"📊 {stats_text}\n"
        f"{awards_text}\n\n"
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
    p["season"] = p.get("_season_num", p.get("season", 1)) + 1
    p["tour"] = 1
    p["stats_season"] = {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0}
    p["played_league_rivals"] = []
    p["cup_out"] = False
    p["cup_stage"] = "1/16"
    p["cup_rivals"] = []
    p["train_done"] = False
    p["fatigue"] = max(0, p.get("fatigue", 0) - 30)
    for key in ("_season_offers", "_season_num", "_season_result_text", "_season_stats_text", "_season_forced_div"):
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
    forced_div = p.get("_season_forced_div")

    if choice == "renew":
        old_salary = p.get("contract_salary", 1500)
        p["contract_salary"] = max(old_salary, int(old_salary * 1.15))

        if forced_div:
            p["division"] = forced_div
            club_line = (f"🔄 Ты продлил контракт с **{p['club']}**!\n"
                         f"📈 Твоя команда переходит в **{forced_div}**!\n"
                         f"💰 Новая зарплата: **{p['contract_salary']}$/матч**")
        else:
            club_line = (f"🔄 Ты продлил контракт с **{p['club']}**!\n"
                         f"💰 Новая зарплата: **{p['contract_salary']}$/матч**")
    else:
        try:
            idx = int(choice)
        except ValueError:
            return await callback.answer("❌ Неверный выбор.", show_alert=True)
        if idx < 0 or idx >= len(offers):
            return await callback.answer("❌ Предложение недоступно.", show_alert=True)
        offer = offers[idx]
        p["club"] = offer["club"]
        p["division"] = offer["division"]
        p["contract_salary"] = offer["salary"]
        p["trust"] = 15
        club_line = (f"✍️ Контракт подписан!\n"
                     f"🏟 Клуб: **{p['club']}** ({p['division']})\n"
                     f"💰 Зарплата: **{p['contract_salary']}$/матч**")

    new_season = p.get("season", 1) + 1
    await generate_euro_data(new_season)
    euro_data = await load_data(EURO_FILE)

    if euro_data and euro_data.get("status") == "group":
        tournament = None
        for t in ["champions_league", "europa_league", "conference_league"]:
            if p["club"] in euro_data[t]["clubs"]:
                tournament = t
                break

        if tournament:
            p["euro_tournament"] = tournament
            p["euro_goals"] = 0
            p["euro_assists"] = 0
            p["euro_matches"] = 0
            p["euro_playoff_stage"] = None
            club_line += f"\n\n🌍 {get_euro_name(tournament)}!"
        else:
            p["euro_tournament"] = "none"
    else:
        p["euro_tournament"] = "none"

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
        if callback.message.photo:
            await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


# ============================================================
# ЗАПУСК
# ============================================================

async def ensure_files_exist():
    files_defaults = {
        PLAYERS_FILE: {},
        LEADERBOARD_FILE: {"top_careers": []},
        TABLES_FILE: {},
        SLOTS_FILE: {},
        EURO_FILE: {},
        AWARDS_FILE: {},
        NPC_FILE: {},
    }
    for filename, default_value in files_defaults.items():
        if not os.path.exists(filename):
            await save_data(filename, default_value)
            print(f"📁 Создан файл: {filename}")


async def main():
    print("🚀 Бот запущен и ожидает сообщений...")
    print("📌 Еврокубки: 36 клубов, 8 туров (round-robin)")
    print("📌 Плей-офф: стыки + 1/8, 1/4, 1/2, Финал")
    print("📌 Игрок играет матчи еврокубков при trust ≥ 21")
    print("📌 В плей-офф есть доп. время и пенальти")
    print("📌 Номинации сезона: Лучший клуб, ЗМ, ЗП, ЛЗ, ЛА")
    print("📌 NPC-игроки для всех клубов (7 на клуб)")
    print("📌 NPC-статы ограничены реалистичными рамками")
    print("📌 Лучший клуб: очки + дивизион + трофеи + еврокубки")
    print("📌 Статистика лиги: бомбардиры, ассистенты, вратари, защитники")

    await ensure_files_exist()

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
