import asyncio
import copy
import functools
import logging
import random
import json
import os
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8494602735:AAFq9H3eZ8O4m9b1HfE9wPG82zbpfKgeT2A"

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
EURO_DIR = "euro_data"
AWARDS_FILE = "awards.json"
NPC_FILE = "npc_players.json"
MOMENT_IMAGES_FILE = "moment_images.json"
PROFILE_IMAGES_FILE = "profile_images.json"


MOMENT_KEYS = {
    "st_one_on_one", "st_counter", "st_penalty_area", "st_header",
    "st_free_kick", "st_wing", "st_press", "st_penalty",
    "cm_midfield", "cm_through_ball", "cm_counter", "cm_press",
    "cm_tackle", "cm_free_kick", "cm_corner", "cm_wing",
    "cb_dribbler", "cb_last_defender", "cb_cross", "cb_corner_def",
    "cb_aerial", "cb_counter", "cb_corner_attack", "cb_press",
    "gk_one_on_one", "gk_long_shot", "gk_close_shot", "gk_cross",
    "gk_corner", "gk_pass", "gk_penalty", "gk_rebound",
    "goal_celebration", "save_moment", "card_moment",
}

MOMENT_KEYS_DESC = {
    "st_one_on_one": "Форвард один на один с вратарём",
    "st_counter": "Форвард бежит в контратаку",
    "st_penalty_area": "Форвард в штрафной под давлением",
    "st_header": "Форвард бьёт головой",
    "st_free_kick": "Игрок готовится к штрафному",
    "st_wing": "Форвард на фланге против защитника",
    "st_press": "Форвард прессингует защитника",
    "st_penalty": "Игрок у точки пенальти",
    "cm_midfield": "Борьба в центре поля",
    "cm_through_ball": "Полузащитник отдаёт пас",
    "cm_counter": "Полузащитник ведёт контратаку",
    "cm_press": "Полузащитник прессингует",
    "cm_tackle": "Отбор в центре поля",
    "cm_free_kick": "Штрафной удар",
    "cm_corner": "Подача углового",
    "cm_wing": "Полузащитник на фланге",
    "cb_dribbler": "Защитник против дриблингующего форварда",
    "cb_last_defender": "Защитник догоняет форварда",
    "cb_cross": "Защитник выбивает навес",
    "cb_corner_def": "Защитник на угловом у своих ворот",
    "cb_aerial": "Верховое единоборство",
    "cb_counter": "Защитник один против контратаки",
    "cb_corner_attack": "Защитник на угловом у чужих ворот",
    "cb_press": "Защитник прессингует у штрафной",
    "gk_one_on_one": "Вратарь против выходящего форварда",
    "gk_long_shot": "Вратарь в прыжке за дальним ударом",
    "gk_close_shot": "Вратарь отражает удар в упор",
    "gk_cross": "Вратарь на выходе на навес",
    "gk_corner": "Вратарь на угловом",
    "gk_pass": "Вратарь с мячом начинает атаку",
    "gk_penalty": "Вратарь на линии перед пенальти",
    "gk_rebound": "Вратарь бросается на добивание",
    "goal_celebration": "Празднование гола",
    "save_moment": "Красивый сейв",
    "card_moment": "Судья показывает карточку",
}


MOMENT_SCENARIOS = {
    "st_one_on_one": {
        "text": "🔥 **Выход один на один!** Вратарь выбежал навстречу, у тебя доля секунды на решение.",
        "actions": [
            ("🎯 Ближний угол", "m_shoot:near"),
            ("📐 Дальний угол", "m_shoot:far"),
            ("🌀 Обвести вратаря", "m_dribble:keeper"),
            ("📐 Пас на пустые", "m_pass:open"),
        ],
    },
    "st_counter": {
        "text": "⚡ **Стремительная контратака!** Ты на мяче, партнёры разбегаются по флангам.",
        "actions": [
            ("🏃 Сольный проход", "m_run:solo"),
            ("📐 Проникающий пас", "m_pass:through"),
            ("🎯 Удар с дистанции", "m_shoot:long"),
            ("🌀 Финт и ускорение", "m_dribble:burst"),
        ],
    },
    "st_penalty_area": {
        "text": "🎯 **Ты получил мяч в штрафной!** Защитник наседает со спины.",
        "actions": [
            ("🎯 Развернуться и пробить", "m_shoot:near"),
            ("🌀 Убрать под опорную", "m_dribble:body"),
            ("📐 Откатить под удар", "m_pass:knockdown"),
            ("🏃 Продавить защитника", "m_run:power"),
        ],
    },
    "st_header": {
        "text": "📐 **Навес с фланга!** Мяч летит тебе на голову.",
        "actions": [
            ("🎯 Пробить головой в угол", "m_shoot:header"),
            ("📐 Скинуть партнёру", "m_pass:knockdown"),
            ("🏃 Перепрыгнуть и продавить", "m_run:power"),
        ],
    },
    "st_free_kick": {
        "text": "🎯 **Штрафной у самой штрафной!** Ты берёшь мяч.",
        "actions": [
            ("🎯 Обводящий в девятку", "m_shoot:topcorner"),
            ("👇 Силовой под перекладину", "m_shoot:power"),
            ("📐 Навес на партнёра", "m_pass:cross"),
        ],
    },
    "st_wing": {
        "text": "🏃 **Ты получил мяч на фланге.** Защитник закрывает прострел.",
        "actions": [
            ("🌀 Обыграть 1 в 1", "m_dribble:wing"),
            ("📐 Прострел в штрафную", "m_pass:cross"),
            ("🎯 Сместиться и пробить", "m_shoot:cut_inside"),
            ("🏃 Пробежать по флангу", "m_run:wing"),
        ],
    },
    "st_press": {
        "text": "⚡ **Защитник соперника медлит с мячом.** Прессингуешь?",
        "actions": [
            ("⚡ Налететь и отобрать", "m_press:high"),
            ("🏃 Перекрыть линию паса", "m_press:cut"),
            ("🕴️ Остаться в позиции", "m_idle:stay"),
        ],
    },
    "st_penalty": {
        "text": "🥅 **ПЕНАЛЬТИ!** Ты подошёл к точке.",
        "actions": [
            ("🎯 Пробить в угол", "m_penalty:corner"),
            ("🎩 Паненка", "m_penalty:panenka"),
            ("👇 Силовой в центр", "m_penalty:power"),
        ],
    },
    "cm_midfield": {
        "text": "⚔️ **Борьба в центре поля.** Соперник идёт на тебя.",
        "actions": [
            ("🌀 Финт корпусом", "m_dribble:body"),
            ("📐 Пас вперёд", "m_pass:forward"),
            ("🏃 Развернуть атаку", "m_run:turn"),
            ("⚡ Прессинговать", "m_press:high"),
        ],
    },
    "cm_through_ball": {
        "text": "🎯 **Ты видишь открывание партнёра!** Нужен точный пас.",
        "actions": [
            ("📐 Проникающий пас", "m_pass:through"),
            ("📐 Пас вразрез", "m_pass:open"),
            ("🏃 Подключиться в атаку", "m_run:solo"),
            ("🎯 Удар с дистанции", "m_shoot:long"),
        ],
    },
    "cm_counter": {
        "text": "⚡ **Контратака!** Ты с мячом, впереди свободные зоны.",
        "actions": [
            ("🏃 Сольный проход", "m_run:solo"),
            ("📐 Проникающий пас", "m_pass:through"),
            ("🎯 Удар с дистанции", "m_shoot:long"),
            ("🌀 Финт и ускорение", "m_dribble:burst"),
        ],
    },
    "cm_press": {
        "text": "⚡ **Соперник начал атаку.** Ты идёшь в прессинг?",
        "actions": [
            ("⚡ Налететь и отобрать", "m_press:high"),
            ("🧲 Подкат", "m_tackle:hard"),
            ("🕴️ Задержать корпусом", "m_tackle:body"),
            ("🏃 Вернуться в оборону", "m_idle:stay"),
        ],
    },
    "cm_tackle": {
        "text": "🛡️ **Соперник идёт на тебя в центре.** Нужно отобрать.",
        "actions": [
            ("🧲 Жёсткий подкат", "m_tackle:hard"),
            ("🕴️ Встретить корпусом", "m_tackle:body"),
            ("⚡ Выбить мяч", "m_clear:head"),
        ],
    },
    "cm_free_kick": {
        "text": "🎯 **Штрафной!** До ворот метров 25.",
        "actions": [
            ("🎯 Обводящий в девятку", "m_shoot:topcorner"),
            ("📐 Навес на партнёра", "m_pass:cross"),
            ("📐 Разыграть коротко", "m_pass:safe"),
        ],
    },
    "cm_corner": {
        "text": "📐 **Угловой!** Ты подаёшь.",
        "actions": [
            ("📐 Навес на ближнюю", "m_pass:cross"),
            ("📐 Навес на дальнюю", "m_pass:knockdown"),
            ("📐 Разыграть коротко", "m_pass:safe"),
        ],
    },
    "cm_wing": {
        "text": "🏃 **Ты сместился на фланг.** Есть пространство.",
        "actions": [
            ("🌀 Обыграть 1 в 1", "m_dribble:wing"),
            ("📐 Прострел в штрафную", "m_pass:cross"),
            ("🏃 Пробежать по флангу", "m_run:wing"),
        ],
    },
    "cb_dribbler": {
        "text": "🛡️ **Форвард соперника идёт на дриблинге прямо в твою зону!**",
        "actions": [
            ("🧲 Жёсткий подкат", "m_tackle:hard"),
            ("🕴️ Встретить корпусом", "m_tackle:body"),
            ("📐 Пас ближнему (страховка)", "m_pass:safe"),
            ("⚡ Прессинговать", "m_press:high"),
        ],
    },
    "cb_last_defender": {
        "text": "🚨 **Ты последний защитник!** Нападающий убегает один на один.",
        "actions": [
            ("🧲 Догнать и подкатить", "m_tackle:hard"),
            ("🕴️ Задержать корпусом", "m_tackle:body"),
            ("⚡ Фолить (риск карточки)", "m_tackle:foul"),
            ("🏃 Бежать за ним", "m_run:chase"),
        ],
    },
    "cb_cross": {
        "text": "📐 **Опасный навес в штрафную!** Ты должен выбить мяч.",
        "actions": [
            ("🦶 Выбить головой", "m_clear:head"),
            ("🧲 Подкат в штрафной", "m_tackle:hard"),
            ("📐 Остановить и отдать пас", "m_pass:safe"),
        ],
    },
    "cb_corner_def": {
        "text": "🛡️ **Угловой у твоих ворот.** Ты держишь самого рослого игрока.",
        "actions": [
            ("🦶 Выбить мяч головой", "m_clear:head"),
            ("🧲 Отобрать мяч", "m_tackle:body"),
            ("📐 Забрать и начать атаку", "m_pass:safe"),
            ("🛡️ Помешать вратарю", "m_shield:screen"),
        ],
    },
    "cb_aerial": {
        "text": "📐 **Верховой мяч в твою зону!** Форвард идёт на мяч.",
        "actions": [
            ("🦶 Выбить головой", "m_clear:head"),
            ("🕴️ Продавить корпусом", "m_tackle:body"),
            ("🏃 Опередить на прыжке", "m_run:power"),
        ],
    },
    "cb_counter": {
        "text": "⚡ **Быстрая контратака соперника!** Ты остался один в обороне.",
        "actions": [
            ("🧲 Подкат", "m_tackle:hard"),
            ("🕴️ Задержать корпусом", "m_tackle:body"),
            ("⚡ Фолить (риск)", "m_tackle:foul"),
        ],
    },
    "cb_corner_attack": {
        "text": "🔥 **Ты подключился на угловой!** Мяч летит к тебе.",
        "actions": [
            ("🎯 Пробить головой", "m_shoot:header"),
            ("📐 Скинуть под удар", "m_pass:knockdown"),
            ("🛡️ Помешать вратарю", "m_shield:screen"),
        ],
    },
    "cb_press": {
        "text": "⚡ **Соперник разыгрывает мяч у штрафной.** Прессингуешь?",
        "actions": [
            ("⚡ Налететь и отобрать", "m_press:high"),
            ("🧲 Подкат", "m_tackle:hard"),
            ("🕴️ Держать позицию", "m_idle:stay"),
        ],
    },
    "gk_one_on_one": {
        "text": "🚨 **Нападающий выходит один на один!** Твои действия?",
        "actions": [
            ("🧤 Прыгнуть в левый угол", "m_gk:left"),
            ("🧤 Прыгнуть в правый угол", "m_gk:right"),
            ("🏃 Сблизить дистанцию", "m_gk:rush"),
        ],
    },
    "gk_long_shot": {
        "text": "🎯 **Дальний удар по твоим воротам!** Мяч летит с подкруткой.",
        "actions": [
            ("🧤 Прыгнуть в левый угол", "m_gk:left"),
            ("🧤 Прыгнуть в правый угол", "m_gk:right"),
            ("🦶 Выбить кулаком", "m_gk:punch"),
        ],
    },
    "gk_close_shot": {
        "text": "🔥 **Удар в упор!** Нападающий бьёт с 5 метров.",
        "actions": [
            ("🧤 Реакция в угол", "m_gk:reflex"),
            ("🏃 Сократить угол", "m_gk:rush"),
            ("🦶 Выставить ногу", "m_gk:foot"),
        ],
    },
    "gk_cross": {
        "text": "📐 **Навес в твою штрафную!** Игроки идут на мяч.",
        "actions": [
            ("🧤 Выйти и забрать", "m_gk:catch"),
            ("🦶 Выбить кулаком", "m_gk:punch"),
            ("🏃 Остаться на линии", "m_gk:stay"),
        ],
    },
    "gk_corner": {
        "text": "📐 **Угловой у твоих ворот!** Толпа в штрафной.",
        "actions": [
            ("🧤 Выйти на мяч", "m_gk:catch"),
            ("🦶 Выбить кулаком", "m_gk:punch"),
            ("🏃 Остаться на линии", "m_gk:stay"),
        ],
    },
    "gk_pass": {
        "text": "🦶 **Мяч откатился к тебе.** Ты начинаешь атаку.",
        "actions": [
            ("📐 Короткий пас защитнику", "m_pass:safe"),
            ("🏃 Длинный заброс вперёд", "m_pass:long"),
            ("🦶 Выбить в аут", "m_clear:safe"),
        ],
    },
    "gk_penalty": {
        "text": "🥅 **Пенальти в твои ворота!** Ты на линии.",
        "actions": [
            ("🧤 Прыгнуть влево", "m_gk:left"),
            ("🧤 Прыгнуть вправо", "m_gk:right"),
            ("🕴️ Остаться в центре", "m_gk:center"),
        ],
    },
    "gk_rebound": {
        "text": "💥 **Мяч отскочил от штанги!** Игроки бросаются на добивание.",
        "actions": [
            ("🧤 Броситься на мяч", "m_gk:rush"),
            ("🦶 Выбить кулаком", "m_gk:punch"),
            ("🏃 Остаться на линии", "m_gk:stay"),
        ],
    },
}


def _get_scenarios_for_position(position: str) -> list:
    if position == "ST":
        keys = ["st_one_on_one", "st_counter", "st_penalty_area", "st_header",
                "st_free_kick", "st_wing", "st_press", "st_penalty"]
    elif position == "CM":
        keys = ["cm_midfield", "cm_through_ball", "cm_counter", "cm_press",
                "cm_tackle", "cm_free_kick", "cm_corner", "cm_wing"]
    elif position == "CB":
        keys = ["cb_dribbler", "cb_last_defender", "cb_cross", "cb_corner_def",
                "cb_aerial", "cb_counter", "cb_corner_attack", "cb_press"]
    elif position == "GK":
        keys = ["gk_one_on_one", "gk_long_shot", "gk_close_shot", "gk_cross",
                "gk_corner", "gk_pass", "gk_penalty", "gk_rebound"]
    else:
        keys = ["st_penalty_area"]
    return keys


def _pick_scenario_for_position(position: str) -> str:
    return random.choice(_get_scenarios_for_position(position))


def _moment_count(trust: int, rating: float) -> int:
    base = random.randint(3, 5)
    if trust >= 76:
        base += 1
    if rating >= 80:
        base += 1
    return max(3, min(7, base))


def _load_data_sync(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            backup_name = f"{filename}.corrupted_{int(time.time())}"
            os.replace(filename, backup_name)
            logging.error(f"Файл {filename} повреждён ({e}) → {backup_name}")
            return {}
    return {}


def _save_data_sync(filename, data):
    tmp_path = f"{filename}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_path, filename)


class _TrackedDict(dict):
    _snapshot = None


def _snapshot_of(data):
    return {k: json.dumps(v, ensure_ascii=False) for k, v in data.items()}


def _load_tracked_sync(filename):
    data = _load_data_sync(filename)
    if isinstance(data, dict):
        tracked = _TrackedDict(data)
        tracked._snapshot = _snapshot_of(tracked)
        return tracked
    return data


def _merge_save_sync(filename, data):
    snapshot = data._snapshot or {}
    current = _load_data_sync(filename)
    if not isinstance(current, dict) or not current:
        merged = dict(data)
    else:
        merged = current
        for key, value in data.items():
            if snapshot.get(key) != json.dumps(value, ensure_ascii=False):
                merged[key] = value
        for key in snapshot:
            if key not in data:
                merged.pop(key, None)
    _save_data_sync(filename, merged)
    data._snapshot = _snapshot_of(data)


_cache_locks = {}


def get_cache_lock(filename):
    if filename not in _cache_locks:
        _cache_locks[filename] = asyncio.Lock()
    return _cache_locks[filename]


async def load_data(filename):
    return await asyncio.to_thread(_load_tracked_sync, filename)


async def save_data(filename, data):
    lock = get_cache_lock(filename)
    async with lock:
        if isinstance(data, _TrackedDict) and data._snapshot is not None:
            await asyncio.to_thread(_merge_save_sync, filename, data)
        else:
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
        logging.error(f"Ошибка подписки: {e}")
        return False


def sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на Спонсора", url=SPONSOR_CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub_callback")]
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
        await callback.message.answer("⚠️ Профиль не найден. Нажми /start.", parse_mode="Markdown")
        return True
    if p.get("retired"):
        try:
            await callback.message.edit_text(
                "🏁 **Карьера завершена!** Нажми кнопку ниже.",
                parse_mode="Markdown", reply_markup=retired_keyboard()
            )
        except Exception:
            await callback.message.answer("🏁 **Карьера завершена!**", reply_markup=retired_keyboard())
        return True
    return False


async def deny_if_retired_msg(message: Message, p) -> bool:
    if not p:
        await message.answer("⚠️ Профиль не найден. Нажми /start.", parse_mode="Markdown")
        return True
    if p.get("retired"):
        await message.answer(
            "🏁 **Карьера завершена!** Нажми кнопку ниже.",
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


def _table_sort_key(row):
    return (row.get("points", 0), row.get("wins", 0))


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
    leaderboard["top_careers"].append({"name": name, "rating": rating, "trophies": trophies_count})
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
    tables[user_id][division] = sorted(table, key=_table_sort_key, reverse=True)
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
        tables[user_id][division] = sorted(table, key=_table_sort_key, reverse=True)
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
        tables[user_id][division] = sorted(table, key=_table_sort_key, reverse=True)
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

    return {"games": games, "goals": goals, "assists": assists, "saves": saves, "tackles": tackles}


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
        score = (c["rating"] * 7 + s.get("goals", 0) * 5 + s.get("assists", 0) * 3 + c["trophies"] * 18)
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
        if "лига чемпионов" in t: return 500
        if "лига европы" in t: return 350
        if "лига конференций" in t: return 200
        if "🥇 чемпион" in t: return 150
        if "🏆 кубок" in t: return 120
        if "⬆️ выход" in t: return 80
        if "🥇 золотой мяч" in t or "🧤 золотая перчатка" in t: return 0
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
        if pdata.get("euro_tournament") in EURO_TOURNAMENTS:
            euro_bonus += 100
            stage = pdata.get("euro_playoff_stage")
            if stage and stage != "eliminated":
                euro_bonus += 150
            if stage == "round_16": euro_bonus += 100
            elif stage == "quarter": euro_bonus += 200
            elif stage == "semi": euro_bonus += 350
            elif stage == "final": euro_bonus += 500
        score = points * 2 + wins * 3 + div_weight * 2 + trophy_score + euro_bonus
        if club not in club_scores or score > club_scores[club]["score"]:
            club_scores[club] = {
                "club": club, "points": points, "wins": wins,
                "division": division, "trophies": len(club_trophies),
                "euro_bonus": euro_bonus, "score": score
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
            "club": club, "points": 0, "wins": 0, "division": division,
            "trophies": 0, "euro_bonus": 0, "score": score
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


EURO_CUPS = ("champions_league", "europa_league", "conference_league")
EURO_PLAYOFF_FLAGS = ("playoff_round_played", "round_16_played", "quarter_played", "semi_played", "final_played")


def _euro_path(user_id):
    return os.path.join(EURO_DIR, f"{user_id}.json")


async def load_euro(user_id):
    data = await asyncio.to_thread(_load_data_sync, _euro_path(user_id))
    return data if isinstance(data, dict) and data else None


async def save_euro(user_id, euro_data):
    def _write():
        os.makedirs(EURO_DIR, exist_ok=True)
        _save_data_sync(_euro_path(user_id), dict(euro_data))
    async with get_cache_lock(_euro_path(user_id)):
        await asyncio.to_thread(_write)


async def delete_euro(user_id):
    def _remove():
        try:
            os.remove(_euro_path(user_id))
        except FileNotFoundError:
            pass
    async with get_cache_lock(_euro_path(user_id)):
        await asyncio.to_thread(_remove)


async def migrate_euro_file():
    if not os.path.exists(EURO_FILE):
        return
    legacy = await asyncio.to_thread(_load_data_sync, EURO_FILE)
    if isinstance(legacy, dict) and ("status" in legacy or "champions_league" in legacy):
        players = await load_data(PLAYERS_FILE)
        for uid, p in players.items():
            t = p.get("euro_tournament")
            if p.get("retired") or not t or t == "none" or t not in legacy:
                continue
            await save_euro(uid, copy.deepcopy(dict(legacy)))
    try:
        await asyncio.to_thread(os.replace, EURO_FILE, EURO_FILE + ".migrated")
    except OSError:
        pass


def _rating_rank_in_division(club, division):
    ordered = sorted(CLUBS.get(division, []), key=lambda c: -CLUB_RATINGS.get(c, 50))
    return ordered.index(club) + 1 if club in ordered else None


async def determine_euro_participants(user_id, club, division, old_club=None, old_division=None):
    tables = await load_data(TABLES_FILE)
    buckets = {t: [] for t in EURO_CUPS}

    src_div = old_division or division
    ranked = sorted(tables.get(user_id, {}).get(src_div, []), key=_table_sort_key, reverse=True)
    for pos, row in enumerate(ranked, 1):
        t = get_euro_tournament_by_position(src_div, pos)
        if t and row["club"] not in buckets[t]:
            buckets[t].append(row["club"])

    if not any(club in lst for lst in buckets.values()) and old_club and club != old_club and division != src_div:
        rank = _rating_rank_in_division(club, division)
        t = get_euro_tournament_by_position(division, rank) if rank else None
        if t:
            buckets[t].append(club)

    for t in EURO_CUPS:
        if club in buckets[t]:
            buckets[t].remove(club)
            buckets[t].insert(0, club)

    all_top_clubs = []
    for league in ["РПЛ", "АПЛ", "Ла Лига", "Серия А", "Бундеслига", "Лига 1", "Примейра", "Эредивизи"]:
        all_top_clubs.extend(CLUBS.get(league, []))
    all_top_clubs = list(set(all_top_clubs))

    used_clubs = {c for lst in buckets.values() for c in lst}
    used_clubs.add(club)
    available = [c for c in all_top_clubs if c not in used_clubs]
    random.shuffle(available)

    for t in EURO_CUPS:
        while len(buckets[t]) < 36 and available:
            buckets[t].append(available.pop())

    return {t: buckets[t][:36] for t in EURO_CUPS}


async def generate_euro_data(user_id, season, club, division, old_club=None, old_division=None):
    participants = await determine_euro_participants(user_id, club, division, old_club, old_division)
    tournament = next((t for t in EURO_CUPS if club in participants[t]), None)
    if not tournament:
        await delete_euro(user_id)
        return None, None

    def _empty_playoff():
        return {"round_16": [], "quarter": [], "semi": [], "final": None, "current_stage": "round_16",
                "top8": [], "playoff_round": [], "playoff_winners": []}

    euro_data = {
        "season": season,
        "champions_league": {"clubs": [], "table": {}, "fixtures": {}, "played": 0, "current_tour": 1},
        "europa_league": {"clubs": [], "table": {}, "fixtures": {}, "played": 0, "current_tour": 1},
        "conference_league": {"clubs": [], "table": {}, "fixtures": {}, "played": 0, "current_tour": 1},
        "playoffs": {t: _empty_playoff() for t in EURO_CUPS},
        "status": "group",
        "tour_played": {i: False for i in range(1, EURO_TOTAL_TOURS + 1)}
    }

    clubs = participants[tournament]
    euro_data[tournament]["clubs"] = clubs
    for c in clubs:
        euro_data[tournament]["table"][c] = {
            "points": 0, "goals_for": 0, "goals_against": 0,
            "played": 0, "wins": 0, "draws": 0, "losses": 0
        }
    if len(clubs) >= 8:
        euro_data[tournament]["fixtures"] = generate_swiss_fixtures(clubs)

    await save_euro(user_id, euro_data)
    return euro_data, tournament


async def assign_euro_for_new_season(user_id, p, season, old_club, old_division):
    _, tournament = await generate_euro_data(
        user_id, season, p["club"], p["division"], old_club, old_division
    )
    p["euro_tournament"] = tournament or "none"
    p["euro_playoff_stage"] = None
    p["euro_goals"] = 0
    p["euro_assists"] = 0
    p["euro_matches"] = 0
    return tournament


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
            fixtures[a].append({"opponent": b, "home": home_a, "tour": tour_num,
                                "played": False, "goals_for": 0, "goals_against": 0, "result": None})
            fixtures[b].append({"opponent": a, "home": not home_a, "tour": tour_num,
                                "played": False, "goals_for": 0, "goals_against": 0, "result": None})
        rotating = [rotating[-1]] + rotating[:-1]
    for club in fixtures:
        fixtures[club].sort(key=lambda m: m["tour"])
    return fixtures


async def get_euro_fixture(user_id):
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        return None
    euro_data = await load_euro(user_id)
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
    euro_data = await load_euro(user_id)
    if not euro_data:
        return None
    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        return None
    table = euro_data[tournament]["table"]
    sorted_table = sorted(table.items(),
                          key=lambda x: (x[1]["points"], x[1]["goals_for"] - x[1]["goals_against"]),
                          reverse=True)
    for i, (club, _) in enumerate(sorted_table, 1):
        if club == p["club"]:
            return i
    return None


def get_euro_name(tournament):
    return {
        "champions_league": "🏆 Лига Чемпионов",
        "europa_league": "🥈 Лига Европы",
        "conference_league": "🥉 Лига Конференций"
    }.get(tournament, "❌ Нет")


def get_euro_stage_name(stage):
    return {
        "playoff_round": "Стыковые матчи", "round_16": "1/8 финала",
        "quarter": "1/4 финала", "semi": "Полуфинал", "final": "Финал"
    }.get(stage, stage)


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
            tour_matches.append({"club1": club, "club2": match["opponent"], "home1": match["home"]})

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
        return (goals, goals, club1) if random.random() < 0.5 else (goals, goals, club2)
    else:
        goals2 = random.randint(1, 3)
        goals1 = random.randint(0, goals2 - 1)
        return goals1, goals2, club2


async def generate_euro_playoffs(euro_data, tournament):
    table = euro_data[tournament]["table"]
    sorted_table = sorted(table.items(),
                          key=lambda x: (x[1]["points"], x[1]["goals_for"] - x[1]["goals_against"]),
                          reverse=True)
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
    return euro_data


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


async def get_moment_image(scenario_key: str):
    if not scenario_key:
        return None
    images = await load_data(MOMENT_IMAGES_FILE)
    lst = images.get(scenario_key) or []
    return random.choice(lst) if lst else None


async def get_profile_image(user_id: str):
    """Возвращает фото профиля: сначала личное, потом глобальное (случайное)."""
    images = await load_data(PROFILE_IMAGES_FILE)
    personal = images.get(user_id)
    if personal:
        return personal
    glob = images.get("__global__") or []
    if glob:
        return random.choice(glob)
    return None


async def send_or_edit_moment(callback: CallbackQuery, text: str, kb, scenario_key: str):
    photo = await get_moment_image(scenario_key)
    if photo:
        try:
            if callback.message.photo:
                await callback.message.edit_media(
                    media=InputMediaPhoto(media=photo, caption=text, parse_mode="Markdown"),
                    reply_markup=kb
                )
            else:
                await callback.message.delete()
                await callback.message.answer_photo(
                    photo=photo, caption=text, parse_mode="Markdown", reply_markup=kb
                )
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                return
            logging.warning(f"send_or_edit_moment photo: {e}")
        except Exception as e:
            logging.warning(f"send_or_edit_moment: {e}")

    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


@dp.message(F.photo)
async def save_photo_handler(message: Message):
    username = (message.from_user.username or "").replace("@", "")
    if username not in ADMINS:
        return
    key = (message.caption or "").strip()
    if not key and message.reply_to_message and message.reply_to_message.text:
        parts = message.reply_to_message.text.split()
        if len(parts) == 2 and parts[0].startswith("/set"):
            key = parts[1].strip()
    if not key:
        return await message.answer(
            "❌ Не вижу ключ.\n"
            "• Глобальное фото профиля: подпись `profile`\n"
            "• Личное фото профиля: `profile_<user_id>`\n"
            "• Фото момента: `st_one_on_one` и т.п.\nСписок: /moment_keys",
            parse_mode="Markdown"
        )

    # ---- ГЛОБАЛЬНОЕ ФОТО ПРОФИЛЯ ----
    if key.lower() == "profile":
        file_id = message.photo[-1].file_id
        images = await load_data(PROFILE_IMAGES_FILE)
        images.setdefault("__global__", [])
        if file_id in images["__global__"]:
            return await message.answer("⚠️ Это фото уже добавлено в глобальные.", parse_mode="Markdown")
        images["__global__"].append(file_id)
        if len(images["__global__"]) > 5:
            images["__global__"] = images["__global__"][-5:]
        await save_data(PROFILE_IMAGES_FILE, images)
        return await message.answer(
            f"✅ Глобальное фото профиля сохранено ({len(images['__global__'])}/5).\n"
            f"Будет показываться всем игрокам без личного фото.",
            parse_mode="Markdown"
        )

    # ---- ЛИЧНОЕ ФОТО ПРОФИЛЯ ----
    if key.startswith("profile_"):
        target_uid = key[len("profile_"):].strip()
        players = await load_data(PLAYERS_FILE)
        if target_uid not in players:
            return await message.answer(
                f"❌ Профиль `{target_uid}` не найден в players.json.",
                parse_mode="Markdown"
            )
        file_id = message.photo[-1].file_id
        images = await load_data(PROFILE_IMAGES_FILE)
        images[target_uid] = file_id
        await save_data(PROFILE_IMAGES_FILE, images)
        return await message.answer(
            f"✅ Личное фото профиля для `{target_uid}` сохранено.",
            parse_mode="Markdown"
        )

    # ---- ФОТО МОМЕНТОВ ----
    key_lower = key.lower()
    if key_lower not in MOMENT_KEYS:
        return await message.answer(
            f"❌ Неизвестный ключ: `{key_lower}`\nСписок: /moment_keys",
            parse_mode="Markdown"
        )
    file_id = message.photo[-1].file_id
    images = await load_data(MOMENT_IMAGES_FILE)
    images.setdefault(key_lower, [])
    if file_id in images[key_lower]:
        return await message.answer(f"⚠️ Уже привязано к `{key_lower}`.", parse_mode="Markdown")
    images[key_lower].append(file_id)
    if len(images[key_lower]) > 3:
        images[key_lower] = images[key_lower][-3:]
    await save_data(MOMENT_IMAGES_FILE, images)
    await message.answer(
        f"✅ `{key_lower}` → сохранено ({len(images[key_lower])}/3)\n_{MOMENT_KEYS_DESC.get(key_lower, '')}_",
        parse_mode="Markdown"
    )


@dp.message(Command("set"))
async def set_cmd(message: Message):
    username = (message.from_user.username or "").replace("@", "")
    if username not in ADMINS:
        return
    await message.answer(
        "📸 Кинь фото боту с подписью-ключом.\n"
        "• Глобальное фото профиля (для всех): `profile`\n"
        "• Личное фото профиля: `profile_<user_id>` (например `profile_123456789_1`)\n"
        "• Для моментов: `st_one_on_one`, `gk_penalty` и т.д.\n\n"
        "Список моментов: /moment_keys\nСтатистика: /moment_stats",
        parse_mode="Markdown"
    )


@dp.message(Command("moment_keys"))
async def moment_keys_cmd(message: Message):
    username = (message.from_user.username or "").replace("@", "")
    if username not in ADMINS:
        return
    images = await load_data(MOMENT_IMAGES_FILE)
    groups = {
        "⚽ ST": [k for k in MOMENT_KEYS if k.startswith("st_")],
        "🪄 CM": [k for k in MOMENT_KEYS if k.startswith("cm_")],
        "🛡️ CB": [k for k in MOMENT_KEYS if k.startswith("cb_")],
        "🧤 GK": [k for k in MOMENT_KEYS if k.startswith("gk_")],
        "🎬 Общие": [k for k in MOMENT_KEYS if k in ("goal_celebration", "save_moment", "card_moment")],
    }
    text = "📋 **КЛЮЧИ МОМЕНТОВ**\n"
    for gname, keys in groups.items():
        text += f"\n**{gname}**\n"
        for k in sorted(keys):
            cnt = len(images.get(k, []))
            check = "✅" if cnt > 0 else "⬜"
            text += f"{check} `{k}` — {MOMENT_KEYS_DESC.get(k, '')} ({cnt}/3)\n"
    text += (
        "\n🖼 **Фото профиля:**\n"
        "• Глобальное (для всех): `profile`\n"
        "• Личное (для одного): `profile_<user_id>` (напр. `profile_123456789_1`)"
    )
    if len(text) > 4000:
        text = text[:4000] + "\n…обрезано"
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("moment_stats"))
async def moment_stats_cmd(message: Message):
    username = (message.from_user.username or "").replace("@", "")
    if username not in ADMINS:
        return
    images = await load_data(MOMENT_IMAGES_FILE)
    total = len(MOMENT_KEYS)
    filled = sum(1 for k in MOMENT_KEYS if images.get(k))
    photos = sum(len(images.get(k, [])) for k in MOMENT_KEYS)
    missing = [k for k in MOMENT_KEYS if not images.get(k)]
    profiles = await load_data(PROFILE_IMAGES_FILE)
    global_count = len(profiles.get("__global__", []))
    personal_count = len([k for k in profiles.keys() if k != "__global__"])
    text = (f"📊 **СТАТИСТИКА КАРТИНОК**\n🔑 {filled}/{total}\n🖼 {photos}/{total * 3}\n"
            f"👤 Фото профилей: 🌍 глобальных {global_count}/5, личных {personal_count}")
    if missing:
        text += f"\n\n❌ Пусто ({len(missing)}):\n" + ", ".join(f"`{k}`" for k in missing[:20])
    await message.answer(text, parse_mode="Markdown")
# ============================================================
# НОВАЯ МЕХАНИКА МОМЕНТОВ (ПОНИЖЕННЫЕ ШАНСЫ ГОЛА/АССИСТА)
# ============================================================

GOAL_CHANCE_MULTIPLIER = 0.45


async def _show_moment(callback: CallbackQuery, state: FSMContext, user_id: str, m: dict,
                       scenario_key: str, match_ctx: str = "match"):
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        return

    scenario = MOMENT_SCENARIOS.get(scenario_key)
    if not scenario:
        scenario_key = _pick_scenario_for_position(p.get("position", "ST"))
        scenario = MOMENT_SCENARIOS[scenario_key]

    if match_ctx == "match":
        home_club = p["club"]
        rival = m["rival"]
        my_score = m["my_team_score"]
        rival_score = m["rival_team_score"]
        minute = m["minute"]
        cur = m["current_moment"]
        total = m["total_moments"]
    else:
        home_club = p["club"]
        rival = m["opponent"]
        my_score = m["my_score"]
        rival_score = m["opponent_score"]
        minute = m["minute"]
        cur = m["moment"]
        total = m["total_moments"]

    text = (
        f"⏱ **{minute}' МИНУТА** | Момент {cur}/{total}\n"
        f"⚔️ **{home_club}** vs **{rival}**\n"
        f"Счет: **{my_score} : {rival_score}**\n\n"
        f"📝 **События матча:**\n{m['log'] or 'Идет плотная позиционная борьба...'}\n\n"
        f"{scenario['text']}"
    )

    m["log"] = ""
    m["scenario"] = scenario_key
    key = "match" if match_ctx == "match" else "euro_match"
    await state.update_data(**{key: m})

    buttons = []
    row = []
    for label, cb in scenario["actions"]:
        row.append(InlineKeyboardButton(text=label, callback_data=cb))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await send_or_edit_moment(callback, text, kb, scenario_key)


def _action_chance(base: float, p: dict, rival_rating: int, bonus: float = 0.0) -> float:
    chance = base + ((p.get("rating", 40) - rival_rating) * 0.010) + bonus
    chance *= GOAL_CHANCE_MULTIPLIER
    return max(0.02, min(0.85, chance))


async def _handle_moment_action(callback: CallbackQuery, state: FSMContext, user_id: str,
                                action: str, match_ctx: str = "match"):
    data = await state.get_data()
    key = "match" if match_ctx == "match" else "euro_match"
    m = data.get(key)
    if not m:
        return await callback.answer("⏳ Матч уже завершен!", show_alert=True)

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        return

    rival = m["rival"] if match_ctx == "match" else m["opponent"]
    rival_rating = CLUB_RATINGS.get(rival, 50)

    kind, _, param = action.partition(":")
    minute = m["minute"]

    def _add_goal():
        if match_ctx == "match":
            m["my_team_score"] += 1
        else:
            m["my_score"] += 1

    def _add_rival_goal():
        if match_ctx == "match":
            m["rival_team_score"] += 1
        else:
            m["opponent_score"] += 1

    if kind == "m_shoot":
        shot_cfg = {
            "near": (0.28, "в ближний угол"),
            "far": (0.24, "в дальний угол"),
            "long": (0.12, "с дистанции"),
            "header": (0.22, "головой"),
            "topcorner": (0.18, "в девятку"),
            "power": (0.22, "силовым"),
            "cut_inside": (0.26, "сместившись в центр"),
        }
        base, desc = shot_cfg.get(param, (0.25, "по воротам"))
        if random.random() < _action_chance(base, p, rival_rating):
            m["goals"] += 1
            _add_goal()
            m["log"] += f"⚽ **{minute}'** | ГОЛ! Твой удар {desc} разрывает сетку!\n"
        else:
            m["log"] += f"❌ **{minute}'** | Удар {desc} — мимо или вратарь парирует.\n"

    elif kind == "m_pass":
        pass_cfg = {
            "open": (0.40, "на пустые ворота"),
            "through": (0.24, "проникающий"),
            "knockdown": (0.28, "скидка"),
            "cross": (0.22, "прострел"),
            "forward": (0.35, "вперёд"),
            "safe": (0.90, "поперёк"),
            "long": (0.25, "длинный заброс"),
        }
        base, desc = pass_cfg.get(param, (0.30, "пас"))
        if random.random() < _action_chance(base, p, rival_rating):
            if param in ("open", "through", "knockdown", "cross", "long"):
                m["assists"] += 1
                _add_goal()
                m["log"] += f"✅ **{minute}'** | {desc.capitalize()} пас — партнёр забивает! ГОЛ!\n"
            else:
                m["log"] += f"✅ **{minute}'** | {desc.capitalize()} пас дошёл.\n"
        else:
            m["log"] += f"❌ **{minute}'** | {desc.capitalize()} пас перехвачен.\n"

    elif kind == "m_dribble":
        dribble_cfg = {
            "keeper": (0.20, "Ты обвёл вратаря и закатил в пустые!"),
            "burst": (0.30, "Ты финтом ушёл от защитника!"),
            "body": (0.35, "Ты корпусом закрыл мяч."),
            "wing": (0.28, "Ты обыграл защитника на фланге!"),
        }
        base, success_text = dribble_cfg.get(param, (0.28, "Финт удался!"))
        if random.random() < _action_chance(base, p, rival_rating, bonus=0.02):
            roll = random.random()
            if roll < 0.25:
                m["goals"] += 1
                _add_goal()
                m["log"] += f"🌀 **{minute}'** | {success_text} ГОЛ!\n"
            elif roll < 0.45:
                m["assists"] += 1
                _add_goal()
                m["log"] += f"🌀 **{minute}'** | {success_text} Партнёр замыкает — ГОЛ!\n"
            else:
                m["log"] += f"🌀 **{minute}'** | {success_text} Момент не реализован.\n"
        else:
            m["log"] += f"❌ **{minute}'** | Соперник разгадал финт.\n"

    elif kind == "m_run":
        run_cfg = {
            "solo": (0.14, "Ты прошёл троих и вышел на ворота!"),
            "turn": (0.60, "Ты развернул атаку."),
            "wing": (0.55, "Ты промчался по флангу!"),
            "power": (0.20, "Ты продавил защитника корпусом!"),
            "chase": (0.30, "Ты догнал форварда и выбил мяч!"),
        }
        base, success_text = run_cfg.get(param, (0.25, "Проход удался!"))
        if random.random() < _action_chance(base, p, rival_rating):
            if param == "chase":
                m["tackles"] += 1
                m["log"] += f"🏃 **{minute}'** | {success_text}\n"
            else:
                m["goals"] += 1
                _add_goal()
                m["log"] += f"🏃 **{minute}'** | {success_text} ГОЛ!\n"
        else:
            m["log"] += f"❌ **{minute}'** | Проход не удался.\n"

    elif kind == "m_press":
        base = 0.40 if param == "high" else 0.55
        if random.random() < _action_chance(base, p, rival_rating):
            m["tackles"] += 1
            m["log"] += f"⚡ **{minute}'** | Ты отобрал мяч высоким прессингом!\n"
        else:
            m["log"] += f"❌ **{minute}'** | Прессинг не удался.\n"

    elif kind == "m_tackle":
        tackle_cfg = {
            "hard": (0.40, 0.15, "Мощнейший чистый подкат!"),
            "body": (0.50, 0.05, "Ты встретил корпусом и отобрал мяч."),
            "foul": (0.30, 0.45, "Ты сфолил."),
        }
        base, foul_risk, success_text = tackle_cfg.get(param, (0.45, 0.1, "Отбор!"))
        if random.random() < foul_risk:
            if random.random() < 0.4:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Фол в штрафной — пенальти! Соперник забивает.\n"
            else:
                m["yellow_cards"] = m.get("yellow_cards", 0) + 1
                m["log"] += f"🟨 **{minute}'** | Жёлтая карточка.\n"
                if m["yellow_cards"] >= 2:
                    m["log"] += f"🟥 **{minute}'** | ВТОРАЯ ЖЁЛТАЯ — удаление!\n"
                    m["minute"] = 90
        elif random.random() < _action_chance(base, p, rival_rating):
            m["tackles"] += 1
            m["log"] += f"🛡️ **{minute}'** | {success_text}\n"
        else:
            _add_rival_goal()
            m["log"] += f"⚡ **{minute}'** | Тебя обыграли. Гол.\n"

    elif kind == "m_clear":
        clear_cfg = {"head": (0.60, "Ты выбил мяч головой!"), "safe": (0.90, "Выбил в аут.")}
        base, text_ok = clear_cfg.get(param, (0.6, "Мяч выбит."))
        if random.random() < _action_chance(base, p, rival_rating):
            m["tackles"] += 1
            m["log"] += f"🦶 **{minute}'** | {text_ok}\n"
        else:
            m["log"] += f"❌ **{minute}'** | Вынос не удался.\n"

    elif kind == "m_shield":
        if random.random() < _action_chance(0.50, p, rival_rating):
            m["log"] += f"🛡️ **{minute}'** | Ты помешал вратарю.\n"
        else:
            m["log"] += f"⚠️ **{minute}'** | Ты нарушил правила — штрафной.\n"

    elif kind == "m_gk":
        if param in ("left", "right"):
            save_chance = _action_chance(0.35, p, rival_rating, bonus=p.get("rating", 40) * 0.004)
            opp_dir = random.choice(["left", "right"])
            saved = (param == opp_dir) or (random.random() < save_chance * 0.8)
            if saved:
                m["saves"] += 1
                m["log"] += f"🧤 **{minute}'** | БЕЗУМНЫЙ СЕЙВ!\n"
            else:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Гол...\n"
        elif param == "rush":
            if random.random() < _action_chance(0.45, p, rival_rating, bonus=p.get("rating", 40) * 0.004):
                m["saves"] += 1
                m["log"] += f"🧤 **{minute}'** | Сократил угол и забрал мяч!\n"
            else:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Перекинули тебя. Гол.\n"
        elif param == "punch":
            if random.random() < 0.70:
                m["saves"] += 1
                m["log"] += f"🦶 **{minute}'** | Кулаком выбил мяч!\n"
            else:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Промахнулся — гол.\n"
        elif param == "catch":
            if random.random() < 0.65:
                m["saves"] += 1
                m["log"] += f"🧤 **{minute}'** | Забрал навес в руки!\n"
            else:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Мяч выскользнул — гол.\n"
        elif param == "stay":
            if random.random() < 0.50:
                m["log"] += f"🧤 **{minute}'** | Мяч пролетел мимо ворот.\n"
            else:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Навес замкнули — гол.\n"
        elif param == "reflex":
            if random.random() < _action_chance(0.38, p, rival_rating, bonus=p.get("rating", 40) * 0.005):
                m["saves"] += 1
                m["log"] += f"🧤 **{minute}'** | НЕВЕРОЯТНАЯ РЕАКЦИЯ!\n"
            else:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Гол.\n"
        elif param == "foot":
            if random.random() < 0.50:
                m["saves"] += 1
                m["log"] += f"🦶 **{minute}'** | Выставил ногу и спас!\n"
            else:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Прошёл под ногой — гол.\n"
        elif param == "center":
            if random.random() < 0.30:
                m["saves"] += 1
                m["log"] += f"🧤 **{minute}'** | Отбил удар в центре!\n"
            else:
                _add_rival_goal()
                m["log"] += f"⚡ **{minute}'** | Мяч в углу. Гол.\n"

    elif kind == "m_penalty":
        if param == "corner":
            chance = _action_chance(0.65, p, rival_rating)
        elif param == "panenka":
            chance = _action_chance(0.45, p, rival_rating)
        else:
            chance = _action_chance(0.55, p, rival_rating)
        if random.random() < chance:
            m["goals"] += 1
            _add_goal()
            m["log"] += f"⚽ **{minute}'** | ГОЛ С ПЕНАЛЬТИ!\n"
        else:
            m["log"] += f"❌ **{minute}'** | Вратарь отбил пенальти!\n"

    elif kind == "m_idle":
        m["log"] += f"⏱ **{minute}'** | Ты остался в позиции.\n"

    if match_ctx == "match":
        m["current_moment"] += 1
        await state.update_data(match=m)
    else:
        m["moment"] += 1
        await state.update_data(euro_match=m)

    await _continue_match(callback, state, user_id, match_ctx)


@dp.callback_query(F.data.startswith("m_"))
@with_user_lock
async def universal_moment_action_handler(callback: CallbackQuery, state: FSMContext):
    user_id = await get_uid(callback)
    data = await state.get_data()
    if "match" in data:
        await _handle_moment_action(callback, state, user_id, callback.data, "match")
    elif "euro_match" in data:
        await _handle_moment_action(callback, state, user_id, callback.data, "euro")


async def _continue_match(callback: CallbackQuery, state: FSMContext, user_id: str, match_ctx: str):
    data = await state.get_data()
    key = "match" if match_ctx == "match" else "euro_match"
    m = data.get(key)
    if not m:
        return

    p = (await load_data(PLAYERS_FILE)).get(user_id)
    rival = m["rival"] if match_ctx == "match" else m["opponent"]
    my_rating = CLUB_RATINGS.get(p["club"], 50)
    rival_rating = CLUB_RATINGS.get(rival, 50)
    rating_diff = my_rating - rival_rating

    m["minute"] = min(90, m.get("minute", 0) + random.randint(12, 22))

    def _add_my_goal():
        if match_ctx == "match":
            m["my_team_score"] += 1
        else:
            m["my_score"] += 1

    def _add_rival_goal():
        if match_ctx == "match":
            m["rival_team_score"] += 1
        else:
            m["opponent_score"] += 1

    if random.random() < 0.35:
        if random.random() < 0.5:
            if random.random() < max(0.03, min(0.75, 0.28 - rating_diff * 0.02)):
                _add_rival_goal()
                m["log"] += f"⚡ **{m['minute']}'** | ГОЛ! Соперник забивает!\n"
        else:
            if random.random() < max(0.03, min(0.75, 0.28 + rating_diff * 0.02)):
                _add_my_goal()
                m["log"] += f"⚽ **{m['minute']}'** | ГОЛ! Твоя команда забивает!\n"

    if random.random() < 0.35:
        flavor = random.choice([
            "🔥 Красивый финт в центре поля обостряет игру.",
            "📐 Подача углового, но защита выносит мяч.",
            "🟨 Судья показывает желтую карточку игроку соперника.",
            "⚔️ Жесткий стык, но судья не дает свисток.",
            "👐 Вратарь уверенно забирает мяч после навеса.",
        ])
        m["log"] += f"⏱ **{m['minute']}'** | {flavor}\n"

    if random.random() < 0.06:
        if random.random() < 0.15:
            m["log"] += f"🟥 **{m['minute']}'** | ПРЯМАЯ КРАСНАЯ! Ты удален!\n"
            m["minute"] = 90
        else:
            m["log"] += f"🟨 **{m['minute']}'** | Желтая карточка тебе.\n"
            m["yellow_cards"] = m.get("yellow_cards", 0) + 1
            if m["yellow_cards"] >= 2:
                m["log"] += f"🟥 **{m['minute']}'** | ВТОРАЯ ЖЕЛТАЯ — УДАЛЕНИЕ!\n"
                m["minute"] = 90

    if match_ctx == "match":
        finished = (m["current_moment"] > m["total_moments"]) or (m["minute"] >= 90)
        if finished:
            is_knockout = m.get("is_cup", False)
            if is_knockout and m["my_team_score"] == m["rival_team_score"]:
                await start_penalty_shootout(callback, state, user_id)
            else:
                await finish_match(callback, state, user_id)
            return
    else:
        finished = (m["moment"] > m["total_moments"]) or (m["minute"] >= 90)
        if finished:
            if m.get("is_playoff"):
                await finish_euro_playoff_match(callback, state, user_id)
            else:
                await finish_euro_match(callback, state, user_id)
            return

    new_key = _pick_scenario_for_position(p.get("position", "ST"))
    await _show_moment(callback, state, user_id, m, new_key, match_ctx)


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
            "🏆 **НОМИНАЦИИ СЕЗОНА**\n\nНоминации за этот сезон ещё не подведены.\n"
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
            text += f"   Еврокубки: +{bc['euro_bonus']}\n"
        text += "\n"

    if awards.get("golden_ball"):
        gb = awards["golden_ball"]
        mark = "⭐ " if gb.get("is_player") else ""
        text += f"🥇 **Золотой мяч:** {mark}{gb['name']} ({gb['club']})\n"
        text += f"   Рейтинг: {gb['rating']} | Голы: {gb['stats'].get('goals', 0)}\n\n"

    if awards.get("golden_glove"):
        gg = awards["golden_glove"]
        mark = "⭐ " if gg.get("is_player") else ""
        text += f"🧤 **Золотая перчатка:** {mark}{gg['name']} ({gg['club']})\n"
        text += f"   Сейвы: {gg['stats'].get('saves', 0)}\n\n"

    if awards.get("best_defender"):
        bd = awards["best_defender"]
        mark = "⭐ " if bd.get("is_player") else ""
        text += f"🛡️ **Лучший защитник:** {mark}{bd['name']} ({bd['club']})\n"
        text += f"   Отборы: {bd['stats'].get('tackles', 0)}\n\n"

    if awards.get("best_assistant"):
        ba = awards["best_assistant"]
        mark = "⭐ " if ba.get("is_player") else ""
        text += f"🅰️ **Лучший ассистент:** {mark}{ba['name']} ({ba['club']})\n"
        text += f"   Ассисты: {ba['stats'].get('assists', 0)}\n"

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
        for key, label in [("golden_ball", "🥇 ЗМ"), ("golden_glove", "🧤 ЗП"),
                            ("best_defender", "🛡️ ЛЗ"), ("best_assistant", "🅰️ ЛА")]:
            a = awards.get(key)
            if a:
                mark = "⭐ " if a.get("is_player") else ""
                text += f"{label}: {mark}{a['name']}\n"
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
        f"📊 **СТАТИСТИКА ЛИГИ: {division}**\n━━━━━━━━━━━━━━━━━━━━\n"
        "Выбери категорию:"
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
        stat_label, stat_key, stat_emoji = "СЕЙВЫ", "saves", "🧤"
    elif stat_type == "tackles":
        candidates = [x for x in all_players if x["position"] == "CB"]
        stat_label, stat_key, stat_emoji = "ОТБОРЫ", "tackles", "🛡️"
    elif stat_type == "assists":
        candidates, stat_label, stat_key, stat_emoji = all_players, "АССИСТЫ", "assists", "🅰️"
    else:
        candidates, stat_label, stat_key, stat_emoji = all_players, "ГОЛЫ", "goals", "⚽"

    candidates = sorted(candidates, key=lambda x: x["stats"].get(stat_key, 0), reverse=True)

    player_position = None
    for i, c in enumerate(candidates, 1):
        if c.get("is_player") and c.get("user_id") == user_id:
            player_position = i
            break

    text = f"{stat_emoji} **ТОП-15 {stat_label}**\n📊 Лига: **{division}**\n━━━━━━━━━━━━━━━━━━━━\n\n"

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 12
    for i, c in enumerate(candidates[:15], 1):
        value = c["stats"].get(stat_key, 0)
        is_me = c.get("is_player") and c.get("user_id") == user_id
        marker = "👉 " if is_me else ""
        name_display = f"**{c['name']}**" if is_me else c['name']
        text += f"{medals[i-1]} {marker}{name_display} ({c.get('club', '—')}) — **{value}**\n"

    if player_position and player_position > 15:
        pd = next((c for c in candidates if c.get("is_player") and c.get("user_id") == user_id), None)
        if pd:
            text += f"\n━━━━━━━━━━━━━━━━━━━━\n👉 **Ты:** {player_position} место — {pd['stats'].get(stat_key, 0)}\n"

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

    euro_data = await load_euro(user_id)
    if not euro_data or not euro_data.get("status"):
        try:
            await callback.message.edit_text(
                "🌍 Еврокубки еще не начались.",
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
                gf, ga = f.get("goals_for", 0), f.get("goals_against", 0)
                result = "✅ Победа" if gf > ga else ("🤝 Ничья" if gf == ga else "❌ Поражение")
            text += f"{status} Тур {i}: {home} {f['opponent']} {result}\n"

    buttons = []
    next_match = next((f for f in fixtures if not f.get("played", False)), None)

    if next_match and euro_data.get("status") == "group":
        if p.get("trust", 15) >= 21:
            buttons.append([InlineKeyboardButton(text="▶️ Следующий матч", callback_data="euro_play_match")])
        else:
            buttons.append([InlineKeyboardButton(text="▶️ Смотреть матч", callback_data="euro_simulate_match")])

    if euro_data.get("status") == "group" and played >= total and total > 0:
        buttons.append([InlineKeyboardButton(text="📊 Итоги группы", callback_data="euro_group_results")])

    if euro_data.get("status") == "playoff":
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
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    euro_data = await load_euro(user_id)
    if not euro_data or euro_data.get("status") != "group":
        await callback.answer("Групповой этап завершён")
        return
    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь")
        return
    fixture = await get_euro_fixture(user_id)
    if not fixture:
        await callback.answer("Все матчи сыграны!")
        return

    tour = fixture["tour"]
    euro_data = await simulate_euro_tour(euro_data, tournament, tour)
    await save_euro(user_id, euro_data)

    gf = ga = 0
    result_text = "📊 Матч сыгран"
    for match in euro_data[tournament]["fixtures"].get(p["club"], []):
        if match["tour"] == tour:
            gf, ga = match.get("goals_for", 0), match.get("goals_against", 0)
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
        await save_euro(user_id, euro_data)
        position = await get_euro_position(user_id)
        if position and position <= 8:
            p["euro_playoff_stage"] = "round_16"
            p["playoff_round_played"] = True
            extra = "\n\n🎉 Ты прошёл в 1/8!"
        elif position and position <= 24:
            p["euro_playoff_stage"] = "playoff_round"
            extra = "\n\n⚔️ Ты в стыках!"
        else:
            p["euro_tournament"] = "none"
            p["euro_playoff_stage"] = "eliminated"
            extra = "\n\n😔 Вылет."
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)

    try:
        await callback.message.edit_text(
            f"📊 **МАТЧ СИМУЛИРОВАН!**\n⚔️ **{p['club']}** vs **{fixture['opponent']}**\n"
            f"Счет: **{gf} : {ga}**\n{result_text}{extra}",
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
    euro_data = await load_euro(user_id)
    if not euro_data:
        await callback.answer("Еврокубки не начались")
        return
    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь")
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
    euro_data = await load_euro(user_id)
    tournament = p.get("euro_tournament")
    if not euro_data or not tournament or tournament not in euro_data:
        await callback.answer("Ошибка")
        return
    await _render_euro_table(callback, user_id, p, euro_data, tournament, page)


async def _render_euro_table(callback, user_id, p, euro_data, tournament, page):
    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    table = euro_data[tournament]["table"]
    sorted_table = sorted(table.items(),
                          key=lambda x: (x[1]["points"], x[1]["goals_for"] - x[1]["goals_against"]),
                          reverse=True)
    per_page = 15
    total_pages = max(1, (len(sorted_table) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    text = f"📊 **ТАБЛИЦА {euro_info.get('name', '')}**\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    start = (page - 1) * per_page
    end = min(start + per_page, len(sorted_table))
    for i, (club, stats) in enumerate(sorted_table[start:end], start + 1):
        is_p = "👉 " if club == p["club"] else "• "
        text += (f"{i}. {is_p}**{club}** — {stats['points']} очков "
                 f"({stats['played']} игр)\n")
    text += f"\n📄 Страница {page}/{total_pages}"

    buttons = []
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"euro_table_page:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"euro_table_page:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

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
        await callback.answer("❌ Ты в резерве!", show_alert=True)
        return

    euro_data = await load_euro(user_id)
    if not euro_data or euro_data.get("status") != "group":
        await callback.answer("Групповой этап завершён")
        return
    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь")
        return
    fixture = await get_euro_fixture(user_id)
    if not fixture:
        await callback.answer("Все матчи сыграны!")
        return

    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    match_data = {
        "tournament": tournament, "opponent": fixture["opponent"], "home": fixture["home"],
        "tour": fixture["tour"], "goals": 0, "assists": 0, "saves": 0, "tackles": 0,
        "yellow_cards": 0, "my_score": 0, "opponent_score": 0, "log": "",
        "moment": 1, "total_moments": _moment_count(p.get("trust", 15), p.get("rating", 40)),
        "minute": 0, "is_playoff": False, "stage": None, "stage_name": None,
    }
    await state.update_data(euro_match=match_data)

    home_text = "🏠 Дома" if fixture["home"] else "✈️ В гостях"
    text = (
        f"{euro_info.get('emoji', '🌍')} **{euro_info.get('name', 'Еврокубки')}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⚔️ **{p['club']}** vs **{fixture['opponent']}**\n"
        f"📍 {home_text}\n📅 Тур {fixture['tour']}/{EURO_TOTAL_TOURS}\n\n"
        "🏟️ **Матч начался!**"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="euro_moment_next")]
    ])
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "euro_moment_next")
@with_user_lock
async def euro_moment_next_handler(callback: CallbackQuery, state: FSMContext):
    user_id = await get_uid(callback)
    data = await state.get_data()
    m = data.get("euro_match")
    if not m:
        await callback.answer("Матч не найден")
        return
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    key = _pick_scenario_for_position(p.get("position", "ST"))
    await _show_moment(callback, state, user_id, m, key, "euro")


@dp.callback_query(F.data == "euro_group_results")
@with_user_lock
async def euro_group_results_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    euro_data = await load_euro(user_id)
    if not euro_data:
        await callback.answer("Еврокубки не начались")
        return
    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь")
        return
    if euro_data.get("status") != "group":
        await callback.answer("Групповой этап уже завершён", show_alert=True)
        return
    _my_fixtures = euro_data[tournament]["fixtures"].get(p["club"], [])
    if not _my_fixtures or not all(f.get("played", False) for f in _my_fixtures):
        await callback.answer("Групповой этап ещё не завершён", show_alert=True)
        return

    position = await get_euro_position(user_id)
    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    text = f"📊 **ИТОГИ ГРУППЫ**\n{euro_info.get('name', '')}\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📈 Место: {position if position else '?'} из {len(euro_data[tournament]['table'])}\n\n"

    progressed = False
    if position and position <= 8:
        text += "🎉 **Ты напрямую прошёл в 1/8!**"
        p["euro_playoff_stage"] = "round_16"
        p["playoff_round_played"] = True
        progressed = True
    elif position and position <= 24:
        text += "⚔️ **Ты в стыках!**"
        p["euro_playoff_stage"] = "playoff_round"
        progressed = True
    else:
        text += "😔 **Вылет.**"
        p["euro_tournament"] = "none"
        p["euro_playoff_stage"] = "eliminated"

    players = await load_data(PLAYERS_FILE)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    buttons = []
    if progressed:
        buttons.append([InlineKeyboardButton(text="🏆 К плей-офф", callback_data="euro_playoff_menu")])
    buttons.append([InlineKeyboardButton(text="📊 Таблица", callback_data="euro_table_full")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
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
    euro_data = await load_euro(user_id)
    if not euro_data or euro_data.get("status") != "playoff":
        await callback.answer("Плей-офф еще не начался")
        return
    tournament = p.get("euro_tournament")
    if not tournament or tournament not in euro_data:
        await callback.answer("Ты не участвуешь")
        return

    playoffs = euro_data["playoffs"][tournament]
    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    current_stage = playoffs.get("current_stage", "playoff_round")
    top8 = playoffs.get("top8", []) or []

    if p.get("euro_tournament") == "none" or p.get("euro_playoff_stage") == "eliminated":
        try:
            await callback.message.edit_text(
                f"🏆 **ПЛЕЙ-ОФФ {euro_info.get('name', '')}**\n━━━━━━━━━━━━━━━━━━━━\n"
                "😔 Ты вылетел.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")]
                ])
            )
        except TelegramBadRequest:
            pass
        return

    player_in_stage = False
    opponent = None
    pairs_to_show = playoffs.get(current_stage, []) or []
    for pair in pairs_to_show:
        if p["club"] in pair:
            player_in_stage = True
            opponent = pair[0] if pair[1] == p["club"] else pair[1]
            break

    stage_names = {"playoff_round": "Стыки", "round_16": "1/8",
                   "quarter": "1/4", "semi": "Полуфинал", "final": "Финал"}
    text = f"🏆 **ПЛЕЙ-ОФФ {euro_info.get('name', '')}**\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📅 Стадия: **{stage_names.get(current_stage, current_stage)}**\n\n"
    if player_in_stage and opponent:
        text += f"⚔️ Соперник: **{opponent}**\n\n"

    buttons = []

    if current_stage == "playoff_round":
        if p["club"] in top8:
            text += "\n🎉 Ты в топ-8 и **пропускаешь стыки**!"
            buttons.append([InlineKeyboardButton(text="⏭ Пропустить стыки",
                                                 callback_data="euro_skip_playoff_round")])
        elif player_in_stage:
            if p.get("trust", 15) >= 21:
                buttons.append([InlineKeyboardButton(text="▶️ Сыграть стык",
                                                     callback_data="euro_play_playoff_round")])
            else:
                buttons.append([InlineKeyboardButton(text="▶️ Смотреть стык",
                                                     callback_data="euro_sim_playoff_round")])
        else:
            text += "\n😔 Ты вылетел."
    else:
        if player_in_stage:
            if p.get("trust", 15) >= 21:
                cb_map = {
                    "round_16": ("▶️ Сыграть 1/8", "euro_play_round16"),
                    "quarter": ("▶️ Сыграть 1/4", "euro_play_quarter"),
                    "semi": ("▶️ Сыграть полуфинал", "euro_play_semi"),
                    "final": ("🏆 Сыграть финал!", "euro_play_final"),
                }
                label, cb = cb_map.get(current_stage, ("▶️ Сыграть", "noop"))
                buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])
            else:
                cb_map = {
                    "round_16": ("▶️ Смотреть 1/8", "euro_simulate_round16"),
                    "quarter": ("▶️ Смотреть 1/4", "euro_simulate_quarter"),
                    "semi": ("▶️ Смотреть полуфинал", "euro_simulate_semi"),
                    "final": ("🏆 Смотреть финал", "euro_simulate_final"),
                }
                label, cb = cb_map.get(current_stage, ("▶️ Смотреть", "noop"))
                buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="menu_euro")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "euro_skip_playoff_round")
@with_user_lock
async def euro_skip_playoff_round_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    euro_data = await load_euro(user_id)
    tournament = p.get("euro_tournament")
    if not euro_data or not tournament or tournament not in euro_data:
        await callback.answer("Ошибка")
        return
    playoffs = euro_data["playoffs"][tournament]
    if playoffs.get("current_stage") != "playoff_round":
        await callback.answer("Уже сыграно")
        return
    if p["club"] not in playoffs.get("top8", []):
        await callback.answer("Ты не в топ-8")
        return
    await simulate_playoff_round_without_player(euro_data, tournament)
    await save_euro(user_id, euro_data)
    try:
        await callback.message.edit_text(
            "⏭ Стыки симулированы! Ты в 1/8.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏆 К 1/8", callback_data="euro_playoff_menu")],
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
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    euro_data = await load_euro(user_id)
    tournament = p.get("euro_tournament")
    if not euro_data or not tournament or tournament not in euro_data:
        await callback.answer("Ошибка")
        return
    pairs = euro_data["playoffs"][tournament].get(stage, [])
    opponent = None
    for pair in pairs:
        if p["club"] in pair:
            opponent = pair[0] if pair[1] == p["club"] else pair[1]
            break
    if not opponent:
        await callback.answer("Ты не участвуешь")
        return
    goals1, goals2, winner = await simulate_euro_playoff_match(p["club"], opponent)
    p[f"{stage}_played"] = True

    if winner == p["club"]:
        result_text = "🏆 **ПОБЕДА! ПРОШЁЛ!**"
        prize = EURO_TOURNAMENTS[tournament]["prize_win"] * 2
        so = ["round_16", "quarter", "semi", "final"]
        ci = so.index(stage) if stage in so else -1
        if ci < len(so) - 1:
            p["euro_playoff_stage"] = so[ci + 1]
        else:
            p["trophies"] = p.get("trophies", []) + [f"🏆 {EURO_TOURNAMENTS[tournament]['name']}"]
            p["money"] = p.get("money", 0) + EURO_TOURNAMENTS[tournament]["prize_winner"]
            p["rating"] = min(100.0, p["rating"] + EURO_TOURNAMENTS[tournament]["rating_bonus_winner"])
            p["euro_tournament"] = "none"
            p["euro_playoff_stage"] = None
    else:
        result_text = "❌ **ПОРАЖЕНИЕ.**"
        prize = 0
        p["euro_tournament"] = "none"
        p["euro_playoff_stage"] = "eliminated"

    p["rating"] = max(1.0, min(100.0, round(p["rating"] + (0.1 if winner == p["club"] else -0.1), 1)))
    p["money"] = p.get("money", 0) + prize
    p["euro_matches"] = p.get("euro_matches", 0) + 1

    players = await load_data(PLAYERS_FILE)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    if stage in ["round_16", "quarter", "semi"]:
        await advance_playoff_round(euro_data, tournament, stage,
                                    player_club=p["club"], player_won=(winner == p["club"]))
    await save_euro(user_id, euro_data)

    try:
        await callback.message.edit_text(
            f"🏁 **МАТЧ СИМУЛИРОВАН!**\n⚔️ **{p['club']} {goals1} : {goals2} {opponent}**\n"
            f"{result_text}\n\n💰 +{prize}$\n📈 {p['rating']}",
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
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    euro_data = await load_euro(user_id)
    tournament = p.get("euro_tournament")
    if not euro_data or not tournament or tournament not in euro_data:
        await callback.answer("Ошибка")
        return
    pairs = euro_data["playoffs"][tournament].get("playoff_round", [])
    opponent = None
    for pair in pairs:
        if p["club"] in pair:
            opponent = pair[0] if pair[1] == p["club"] else pair[1]
            break
    if not opponent:
        await callback.answer("Ты не участвуешь")
        return
    goals1, goals2, winner = await simulate_euro_playoff_match(p["club"], opponent)
    won = winner == p["club"]
    p["playoff_round_played"] = True

    if won:
        result_text = "🏆 **ПОБЕДА! ТЫ В 1/8!**"
        prize = EURO_TOURNAMENTS[tournament]["prize_win"] * 2
        p["euro_playoff_stage"] = "round_16"
    else:
        result_text = "❌ **ПОРАЖЕНИЕ.**"
        prize = 0
        p["euro_tournament"] = "none"
        p["euro_playoff_stage"] = "eliminated"

    p["rating"] = max(1.0, min(100.0, round(p["rating"] + (0.1 if won else -0.1), 1)))
    p["money"] = p.get("money", 0) + prize
    p["euro_matches"] = p.get("euro_matches", 0) + 1

    players = await load_data(PLAYERS_FILE)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    await simulate_playoff_round(euro_data, tournament, player_club=p["club"], player_won=won)
    await save_euro(user_id, euro_data)

    try:
        await callback.message.edit_text(
            f"🏁 **СТЫК СИМУЛИРОВАН!**\n⚔️ **{p['club']} {goals1} : {goals2} {opponent}**\n"
            f"{result_text}\n\n💰 +{prize}$",
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
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    if p.get("trust", 15) < 21:
        await callback.answer("❌ Ты в резерве!", show_alert=True)
        return
    euro_data = await load_euro(user_id)
    tournament = p.get("euro_tournament")
    if not euro_data or not tournament or tournament not in euro_data:
        await callback.answer("Ошибка")
        return
    pairs = euro_data["playoffs"][tournament].get(stage, []) if stage != "playoff_round" \
        else euro_data["playoffs"][tournament].get("playoff_round", [])
    opponent = None
    for pair in pairs:
        if p["club"] in pair:
            opponent = pair[0] if pair[1] == p["club"] else pair[1]
            break
    if not opponent:
        await callback.answer("Ты не участвуешь")
        return

    match_data = {
        "tournament": tournament, "opponent": opponent, "home": random.choice([True, False]),
        "tour": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0, "yellow_cards": 0,
        "my_score": 0, "opponent_score": 0, "log": "", "moment": 1,
        "total_moments": _moment_count(p.get("trust", 15), p.get("rating", 40)),
        "minute": 0, "is_playoff": True, "stage": stage, "stage_name": stage_name,
    }
    await state.update_data(euro_match=match_data)
    euro_info = EURO_TOURNAMENTS.get(tournament, {})
    home_text = "🏠 Дома" if match_data["home"] else "✈️ В гостях"
    text = (
        f"{euro_info.get('emoji', '🌍')} **{euro_info.get('name', 'Еврокубки')}**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **{stage_name}**\n⚔️ **{p['club']}** vs **{opponent}**\n📍 {home_text}\n\n"
        "🏟️ **Матч начался!**"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="euro_moment_next")]
    ])
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest:
        pass


async def start_penalty_shootout(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    m = data.get("match")
    if not m:
        return
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        return

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
    m["log"] += f"\n🥅 **СЕРИЯ ПЕНАЛЬТИ:** {my_score} : {rival_score} — {'ПРОШЁЛ!' if won_shootout else 'вылет...'}\n"
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
            "⚠️ Данные матча потеряны.",
            reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
        )

    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        data.pop("match", None)
        await state.set_data(data)
        return

    if m["my_team_score"] > m["rival_team_score"]:
        outcome = "win"; outcome_text = "🏆 **ПОБЕДА!**"
        p["trust"] = min(100, p.get("trust", 0) + 5)
    elif m["my_team_score"] == m["rival_team_score"]:
        outcome = "draw"; outcome_text = "🤝 **НИЧЬЯ**"
        p["trust"] = min(100, p.get("trust", 0) + 1)
    else:
        outcome = "loss"; outcome_text = "❌ **ПОРАЖЕНИЕ**"
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
                cup_summary = "\n\n🏆 **ТЫ ВЫИГРАЛ КУБОК!!!** 🎉"
            else:
                p["cup_stage"] = stages[idx + 1]
                cup_summary = f"\n\n➡️ Прошёл в **{p['cup_stage']}** Кубка!"
        else:
            p["cup_out"] = True
            cup_summary = "\n\n🚫 Вылет из Кубка."
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
    rating_performance = max(5.0, min(10.0, round(rating_performance, 1)))
    p["rating_performance"] = rating_performance

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    data.pop("match", None)
    await state.set_data(data)

    penalty_line = ""
    if penalty_result:
        my_pen, rival_pen, _ = penalty_result
        penalty_line = f"🥅 Пенальти: {my_pen} : {rival_pen}\n"
    sponsor_line = (f"💼 Доход от {p.get('sponsor')}: +{sponsor_income}$\n" if sponsor_income else "")

    text = (
        f"🏁 **МАТЧ ЗАВЕРШЕН!**\n"
        f"⚔️ **{p['club']} {m['my_team_score']} : {m['rival_team_score']} {m['rival']}**\n"
        f"{penalty_line}{outcome_text}\n\n"
        f"📊 **Оценка: {rating_performance} / 10**\n"
        f"⚽ Голы: {m.get('goals', 0)} | 🅰️ Ассисты: {m.get('assists', 0)} | "
        f"🧤 Сейвы: {m.get('saves', 0)} | 🛡️ Отборы: {m.get('tackles', 0)}\n"
        f"💰 Зарплата: +{p.get('contract_salary', 1500)}$\n"
        f"{sponsor_line}"
        f"📈 Рейтинг: {p['rating']} ({'+' if rating_delta >= 0 else ''}{rating_delta})"
        f"{cup_summary}"
    )

    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    final_photo = await get_moment_image("goal_celebration")
    if final_photo:
        try:
            if callback.message.photo:
                await callback.message.edit_media(
                    media=InputMediaPhoto(media=final_photo, caption=text, parse_mode="Markdown"),
                    reply_markup=kb
                )
            else:
                await callback.message.delete()
                await callback.message.answer_photo(
                    photo=final_photo, caption=text, parse_mode="Markdown", reply_markup=kb
                )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                if callback.message.photo:
                    await callback.message.delete()
                await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            if callback.message.photo:
                await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            if callback.message.photo:
                await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)

    if rating_performance >= 9.0:
        await start_interview(callback, state, user_id, p)


async def finish_euro_match(callback: CallbackQuery, state: FSMContext, user_id: str):
    data = await state.get_data()
    match = data.get("euro_match")
    if not match:
        return

    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    euro_data = await load_euro(user_id)

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
        if result == "win": table[my_club]["wins"] += 1
        elif result == "draw": table[my_club]["draws"] += 1
        else: table[my_club]["losses"] += 1

    for f in euro_data[tournament]["fixtures"].get(my_club, []):
        if f["tour"] == my_tour and f["opponent"] == opponent:
            f["played"] = True
            f["goals_for"] = match["my_score"]
            f["goals_against"] = match["opponent_score"]
            f["result"] = result
            break

    for mm in euro_data[tournament]["fixtures"].get(opponent, []):
        if mm["tour"] == my_tour and mm["opponent"] == my_club:
            mm["played"] = True
            mm["goals_for"] = match["opponent_score"]
            mm["goals_against"] = match["my_score"]
            mm["result"] = "win" if result == "loss" else ("draw" if result == "draw" else "loss")
            break

    if opponent in table:
        table[opponent]["points"] += (3 if result == "loss" else (1 if result == "draw" else 0))
        table[opponent]["goals_for"] += match["opponent_score"]
        table[opponent]["goals_against"] += match["my_score"]
        table[opponent]["played"] += 1
        if result == "loss": table[opponent]["wins"] += 1
        elif result == "draw": table[opponent]["draws"] += 1
        else: table[opponent]["losses"] += 1

    euro_data = await simulate_euro_tour(euro_data, tournament, my_tour)
    await save_euro(user_id, euro_data)

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

    rating_bonus = (match.get("goals", 0) * 0.1 + match.get("assists", 0) * 0.05
                    + match.get("saves", 0) * 0.05 + match.get("tackles", 0) * 0.03)
    if result == "win": rating_bonus += 0.1
    elif result == "loss": rating_bonus -= 0.05
    p["rating"] = max(1.0, min(100.0, round(p["rating"] + rating_bonus, 1)))

    fixtures = euro_data[tournament]["fixtures"].get(my_club, [])
    all_played = all(f.get("played", False) for f in fixtures) and len(fixtures) >= EURO_TOTAL_TOURS
    playoff_text = ""
    if all_played:
        euro_data["status"] = "playoff"
        await generate_euro_playoffs(euro_data, tournament)
        await save_euro(user_id, euro_data)
        position = await get_euro_position(user_id)
        if position and position <= 8:
            p["euro_playoff_stage"] = "round_16"
            p["playoff_round_played"] = True
            playoff_text = "\n\n🎉 Прошёл в 1/8!"
        elif position and position <= 24:
            p["euro_playoff_stage"] = "playoff_round"
            playoff_text = "\n\n⚔️ Стыки!"
        else:
            p["euro_tournament"] = "none"
            p["euro_playoff_stage"] = "eliminated"
            playoff_text = "\n\n😔 Вылет."

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    text = (
        f"🏁 **МАТЧ ЗАВЕРШЕН!**\n"
        f"⚔️ **{p['club']} {match['my_score']} : {match['opponent_score']} {match['opponent']}**\n"
        f"{result_text}\n\n⚽ {match.get('goals', 0)} | 🅰️ {match.get('assists', 0)} | "
        f"🧤 {match.get('saves', 0)} | 🛡️ {match.get('tackles', 0)}\n"
        f"💰 +{prize}$ | 📈 {p['rating']}{playoff_text}"
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

    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    euro_data = await load_euro(user_id)

    stage = match.get("stage")
    tournament = match["tournament"]

    if match["my_score"] == match["opponent_score"]:
        match["log"] += "\n⏱ ДОПОЛНИТЕЛЬНОЕ ВРЕМЯ!\n"
        await state.update_data(euro_match=match)
        await asyncio.sleep(1)
        for period in range(2):
            if random.random() < 0.3:
                if random.random() < 0.5:
                    match["my_score"] += 1
                else:
                    match["opponent_score"] += 1
            await state.update_data(euro_match=match)
            await asyncio.sleep(1)

        if match["my_score"] == match["opponent_score"]:
            my_pen, opp_pen = 0, 0
            for _ in range(5):
                if random.random() < 0.75: my_pen += 1
                if random.random() < 0.75: opp_pen += 1
            while my_pen == opp_pen:
                if random.random() < 0.75: my_pen += 1
                else: opp_pen += 1
            if my_pen > opp_pen:
                match["my_score"] += 1
            else:
                match["opponent_score"] += 1
            await state.update_data(euro_match=match)

    won = match["my_score"] > match["opponent_score"]

    if won:
        result_text = "🏆 **ПОБЕДА! ПРОШЁЛ ДАЛЬШЕ!**"
        prize = EURO_TOURNAMENTS[tournament]["prize_win"] * 2
        if stage == "playoff_round":
            p["euro_playoff_stage"] = "round_16"
            p["playoff_round_played"] = True
            await simulate_playoff_round(euro_data, tournament, player_club=p["club"], player_won=True)
        else:
            so = ["round_16", "quarter", "semi", "final"]
            ci = so.index(stage) if stage in so else -1
            if ci < len(so) - 1:
                p["euro_playoff_stage"] = so[ci + 1]
            else:
                p["trophies"] = p.get("trophies", []) + [f"🏆 {EURO_TOURNAMENTS[tournament]['name']}"]
                p["money"] = p.get("money", 0) + EURO_TOURNAMENTS[tournament]["prize_winner"]
                p["rating"] = min(100.0, p["rating"] + EURO_TOURNAMENTS[tournament]["rating_bonus_winner"])
                p["euro_tournament"] = "none"
                p["euro_playoff_stage"] = None
    else:
        result_text = "❌ **ПОРАЖЕНИЕ. ВЫЛЕТ.**"
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

    rating_bonus = (match.get("goals", 0) * 0.1 + match.get("assists", 0) * 0.05
                    + match.get("saves", 0) * 0.05 + match.get("tackles", 0) * 0.03)
    rating_bonus += 0.3 if won else -0.1
    p["rating"] = max(1.0, min(100.0, round(p["rating"] + rating_bonus, 1)))
    p["money"] = p.get("money", 0) + prize

    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    if stage in ["round_16", "quarter", "semi"]:
        await advance_playoff_round(euro_data, tournament, stage, player_club=p["club"], player_won=won)
    await save_euro(user_id, euro_data)

    text = (
        f"🏁 **МАТЧ ЗАВЕРШЕН!**\n"
        f"⚔️ **{p['club']} {match['my_score']} : {match['opponent_score']} {match['opponent']}**\n"
        f"{result_text}\n\n⚽ {match.get('goals', 0)} | 🅰️ {match.get('assists', 0)}\n"
        f"💰 +{prize}$ | 📈 {p['rating']}"
    )
    await state.clear()
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        if callback.message.photo:
            await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


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
    await state.update_data(interview={"questions": questions, "trust_gain": 0, "rep_gain": 0})
    q0 = questions[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=q0["a"], callback_data="interview:0:a")],
        [InlineKeyboardButton(text=q0["b"], callback_data="interview:0:b")]
    ])
    await callback.message.answer(
        f"🎙️ **Поздравляем с выдающимся матчем! Оценка {p.get('rating_performance', 9.0)}!**\n"
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
            "questions": questions, "current": next_idx,
            "trust_gain": trust_gain, "rep_gain": rep_gain
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
            f"❤️ +{trust_gain} к доверию (итого: {trust_now})\n"
            f"⭐ {rep_gain:+} к репутации (итого: {rep_now})"
        )
        kb = await main_menu_keyboard(callback.from_user.username, user_id)
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logging.warning(f"interview finish error: {e}")
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


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
        "ФНЛ": 6000, "Лига 2": 6000, "Чемпионшип": 8000, "Сегунда": 8000,
        "Серия Б": 8000, "Вторая Бундеслига": 7500,
        "РПЛ": 30000, "Лига 1": 30000, "АПЛ": 50000, "Ла Лига": 50000,
        "Серия А": 45000, "Бундеслига": 48000,
        "Примейра": 35000, "Сегунда лига": 7500,
        "Бразильская Серия А": 30000, "Эрстедивизи": 7500,
        "Эредивизи": 35000, "Jupiler Pro League": 35000,
        "Беларусь Первая лига": 2000, "Беларусь Высшая лига": 5000,
        "Турция Первая лига": 3000, "Турция Суперлига": 25000,
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

    euro_data = await load_euro(user_id)
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
        text=f"✍️ Ты перешёл в **{new_club}**!\n💵 Зарплата: **{p['contract_salary']}$/матч**.",
        parse_mode="Markdown",
        reply_markup=await main_menu_keyboard(callback.from_user.username, user_id)
    )
@dp.callback_query(F.data == "menu_match")
@with_user_lock
async def match_handler(callback: CallbackQuery, state: FSMContext):
    if not await check_sub(callback.from_user.id):
        return await callback.message.answer(
            "❗️ **Подпишись на спонсора!**",
            reply_markup=sub_keyboard(), parse_mode="Markdown"
        )

    user_id = await get_uid(callback)
    await heal_injury_if_needed(user_id)
    await track_activity(user_id)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    if p.get("tour", 1) > 30:
        return await season_results_handler(callback)

    if not p.get("train_done", False):
        if p.get("train_streak", 0) > 0:
            p["train_streak"] = 0
            players[user_id] = p
            await save_data(PLAYERS_FILE, players)
            await send_auto_delete_message(
                callback.message,
                "⚠️ **СЕРИЯ ПРЕРВАНА!**",
                delay=3
            )

    trust = p.get("trust", 15)

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
            f"🪑 **ТЫ В РЕЗЕРВЕ!** Матч против **{rival}**.",
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
        await send_auto_delete_message(
            callback.message,
            f"🚑 **ПРОПУСК ИЗ-ЗА ТРАВМЫ.** Матч против **{rival}**.",
            delay=3
        )
        return

    if p.get("fatigue", 0) >= 95:
        return await callback.answer("🚫 Ты смертельно устал!", show_alert=True)

    current_rating = p.get("rating", 40)

    if p["division"] not in ["Бундеслига", "Вторая Бундеслига"] and random.random() < 0.10:
        if current_rating >= 74:
            ger_offers = random.sample(CLUBS["Бундеслига"], 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🇩🇪 {c}", callback_data=f"scandal_club:{c}")] for c in ger_offers
            ] + [[InlineKeyboardButton(text="❌ Отклонить", callback_data="back_to_menu")]])
            await callback.message.delete()
            return await callback.message.answer(
                text=f"📈 **ТРАНСФЕР!** Клубы Бундеслиги предлагают тебе контракт:",
                reply_markup=kb, parse_mode="Markdown"
            )
        elif current_rating >= 55:
            ger_offers = random.sample(CLUBS["Вторая Бундеслига"], 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🇩🇪 {c}", callback_data=f"scandal_club:{c}")] for c in ger_offers
            ] + [[InlineKeyboardButton(text="❌ Отклонить", callback_data="back_to_menu")]])
            await callback.message.delete()
            return await callback.message.answer(
                text=f"📈 **ТРАНСФЕР!** Клубы из Второй Бундеслиги:",
                reply_markup=kb, parse_mode="Markdown"
            )

    if p["division"] not in ["Примейра", "Сегунда лига"] and random.random() < 0.10:
        if current_rating >= 74:
            pt_offers = random.sample(CLUBS["Примейра"], 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🇵🇹 {c}", callback_data=f"scandal_club:{c}")] for c in pt_offers
            ] + [[InlineKeyboardButton(text="❌ Отклонить", callback_data="back_to_menu")]])
            await callback.message.delete()
            return await callback.message.answer(
                text=f"📈 **ТРАНСФЕР!** Клубы из Примейры:",
                reply_markup=kb, parse_mode="Markdown"
            )
        elif current_rating >= 55:
            pt_offers = random.sample(CLUBS["Сегунда лига"], 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🇵🇹 {c}", callback_data=f"scandal_club:{c}")] for c in pt_offers
            ] + [[InlineKeyboardButton(text="❌ Отклонить", callback_data="back_to_menu")]])
            await callback.message.delete()
            return await callback.message.answer(
                text=f"📈 **ТРАНСФЕР!** Клубы из Сегунда лиги:",
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
        "total_moments": _moment_count(p.get("trust", 15), p.get("rating", 40)),
        "current_moment": 1,
        "minute": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0, "yellow_cards": 0,
        "my_team_score": 0, "rival_team_score": 0,
        "is_cup": is_cup_match, "cup_stage": cup_stg if is_cup_match else None,
        "log": "", "scenario": None,
    }
    await state.update_data(match=match_data)

    match_title = f"🏆 НАЦИОНАЛЬНЫЙ КУБОК ({cup_stg}) 🏆" if is_cup_match else f"🏟️ РЕГУЛЯРНЫЙ ЧЕМПИОНАТ ({p['division']})"

    if callback.message.photo:
        await callback.message.delete()
    msg = await callback.message.answer(
        f"⚽ **{match_title}**\n⚔️ **{p['club']}** vs **{match_data['rival']}**\nСудья дает свисток!",
        parse_mode="Markdown"
    )
    await asyncio.sleep(2)
    await msg.delete()

    key = _pick_scenario_for_position(p.get("position", "ST"))
    await _show_moment(callback, state, user_id, match_data, key, "match")


@dp.callback_query(F.data == "menu_online")
async def online_handler(callback: CallbackQuery):
    players = await load_data(PLAYERS_FILE)
    total = len(players)
    online = max(1, int(total * 0.15) + random.randint(1, 4))
    top_active = sorted(players.values(), key=lambda x: x.get("activity_minutes", 0), reverse=True)[:5]
    top_text = "\n\n🔥 **Топ по активности:**\n"
    for i, pl in enumerate(top_active, 1):
        mins = pl.get('activity_minutes', 0)
        top_text += f"{i}. {pl['name']} — {mins // 60}ч {mins % 60}м\n"
    await callback.answer(f"🟢 Онлайн: {online}\n👥 Всего: {total}", show_alert=True)
    user_id = await get_uid(callback)
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
            text = "🏆 **ЗАЛ СЛАВЫ**\n\nСтань первым легендой!"
        else:
            lines = ["🏆 **ЗАЛ СЛАВЫ**\n━━━━━━━━━━━━━━━━━━━━"]
            for i, c in enumerate(careers[:10]):
                lines.append(f"{medals[i]} {c['name']} | ⭐ {c['rating']} | 🏆 {c['trophies']}")
            text = "\n".join(lines)
    except Exception:
        text = "⚠️ Ошибка загрузки."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest:
        pass


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
        if name == current_sponsor:
            status = "✅"
        elif locked:
            status = f"🔒 {info['min_rating']}"
        else:
            status = ""
        lines.append(f"{info['emoji']} **{name}** {status} — {info['income_per_match']}$")
        cb = "noop" if (locked or name == current_sponsor) else f"sponsor:{name}"
        row.append(InlineKeyboardButton(text=f"{info['emoji']} {name} {status}", callback_data=cb))
        if len(row) == 2:
            buttons.append(row); row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    text = (f"💰 **СПОНСОРЫ**\n📊 Рейтинг: **{rating}** | ⭐ Репутация: {reputation}\n"
            f"Текущий: **{current_sponsor or 'Нет'}**\n\n" + "\n".join(lines))
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        else:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
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
        return await callback.answer("❌")
    if p.get("rating", 40) < info["min_rating"]:
        return await callback.answer(f"❌ Нужен рейтинг {info['min_rating']}!", show_alert=True)
    p["sponsor"] = sp
    sign_bonus = info["sign_bonus"]
    p["money"] = p.get("money", 0) + sign_bonus
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(f"🤝 Контракт с {sp}!\n+{sign_bonus}$", reply_markup=kb, parse_mode="Markdown")
        else:
            await callback.message.edit_text(f"🤝 Контракт с {sp}!\n+{sign_bonus}$", reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(f"🤝 +{sign_bonus}$", reply_markup=kb)


@dp.callback_query(F.data == "menu_quests")
@with_user_lock
async def quests_menu_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    completed = p.get("completed_quests", [])
    has_claimable = False
    text = "🎯 **КВЕСТЫ**\n\n"
    for q_id, q in QUESTS_DATA.items():
        if q_id in completed:
            text += f"✅ ~~{q['name']}~~ (+{q['reward']})\n"
        else:
            prog = get_quest_progress(p, q['type'])
            if prog >= q['target']:
                text += f"🎁 **{q['name']}** — ГОТОВО!\n"
                has_claimable = True
            else:
                text += f"⏳ **{q['name']}**: {prog}/{q['target']}\n"
    kb = []
    if has_claimable:
        kb.append([InlineKeyboardButton(text="🎁 Забрать", callback_data="claim_quests")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
        else:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "claim_quests")
@with_user_lock
async def claim_quests_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    completed = p.get("completed_quests", [])
    total = 0.0
    for q_id, q in QUESTS_DATA.items():
        if q_id not in completed and get_quest_progress(p, q['type']) >= q['target']:
            total += q['reward']
            completed.append(q_id)
    if total > 0:
        p["completed_quests"] = completed
        p["rating"] = min(100.0, round(p.get("rating", 40.0) + total, 1))
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)
        await callback.answer(f"🎉 +{round(total, 1)} рейтинга!", show_alert=True)
        kb = await main_menu_keyboard(callback.from_user.username, user_id)
        await callback.message.edit_text("🏠 Меню", reply_markup=kb)
    else:
        await callback.answer("Нет наград.", show_alert=True)


@dp.callback_query(F.data == "menu_personal_life")
@with_user_lock
async def personal_life_menu(callback: CallbackQuery):
    user_id = await get_uid(callback)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 Ресторан (-500$)", callback_data="personal:rest")],
        [InlineKeyboardButton(text="💃 Девушка (-2000$)" if p.get("girlfriend", "Нет") == "Нет" else "🎁 Подарок (-1000$)", callback_data="personal:girl")],
        [InlineKeyboardButton(text="🧘 Йога (-300$)", callback_data="personal:yoga")],
        [InlineKeyboardButton(text="🪂 Парашют (-1500$)", callback_data="personal:parachute")],
        [InlineKeyboardButton(text="🎁 Благотворительность (-1000$)", callback_data="personal:charity")],
        [InlineKeyboardButton(text="🎉 Вечеринка (-800$)", callback_data="personal:party")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    text = (f"🍷 **ЛИЧНАЯ ЖИЗНЬ**\n💵 {p.get('money', 0)}$\n🔋 Усталость: {p.get('fatigue', 0)}%\n"
            f"❤️ Доверие: {p.get('trust', 0)}%")
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
    cost = 0; msg = ""; fr = 0; tb = 0
    if action == "rest": cost = 500; fr = 15; msg = "🍽 -15% усталости"
    elif action == "girl":
        if p.get("girlfriend", "Нет") == "Нет":
            cost = 2000
            if p.get("money", 0) >= cost:
                p["girlfriend"] = "Есть"; msg = "💃 Есть девушка!"
            else:
                msg = "❌ Нет денег"
        else:
            cost = 1000; fr = 20; msg = "🎁 -20%"
    elif action == "yoga": cost = 300; fr = 20; tb = 1; msg = "🧘 -20%"
    elif action == "parachute": cost = 1500; fr = 25; tb = 5; msg = "🪂 -25%"
    elif action == "charity": cost = 1000; tb = 10; msg = "🎁 +10 доверия"
    elif action == "party": cost = 800; fr = 15; tb = -2; msg = "🎉 -15%"

    if "❌" not in msg:
        if p.get("money", 0) >= cost:
            p["money"] -= cost
            p["fatigue"] = max(0, p.get("fatigue", 0) - fr)
            p["trust"] = min(100, max(0, p.get("trust", 15) + tb))
        else:
            msg = "❌ Нет денег"
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await callback.answer(msg, show_alert=True)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 Ресторан (-500$)", callback_data="personal:rest")],
        [InlineKeyboardButton(text="💃 Девушка (-2000$)" if p.get("girlfriend", "Нет") == "Нет" else "🎁 Подарок (-1000$)", callback_data="personal:girl")],
        [InlineKeyboardButton(text="🧘 Йога (-300$)", callback_data="personal:yoga")],
        [InlineKeyboardButton(text="🪂 Парашют (-1500$)", callback_data="personal:parachute")],
        [InlineKeyboardButton(text="🎁 Благотворительность (-1000$)", callback_data="personal:charity")],
        [InlineKeyboardButton(text="🎉 Вечеринка (-800$)", callback_data="personal:party")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    try:
        await callback.message.edit_text(
            f"🍷 **ЛИЧНАЯ ЖИЗНЬ**\n💵 {p.get('money', 0)}$\n🔋 {p.get('fatigue', 0)}%\n❤️ {p.get('trust', 0)}%",
            reply_markup=kb, parse_mode="Markdown"
        )
    except Exception:
        pass


@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery, state: FSMContext):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("Нет доступа.", show_alert=True)
    text = (
        "👑 Отправь ID пользователя (например `123456_1`):\n\n"
        "📸 **Глобальное фото профиля** (для всех игроков): пришли фото с подписью `profile`\n"
        "📸 **Личное фото профиля**: пришли фото с подписью `profile_<user_id>`"
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
                "❌ Не найден. Попробуй полный ID (например `123456789_1`).",
                parse_mode="Markdown"
            )
        if len(found) > 1:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"Слот {uid.split('_')[1]}: {players[uid]['name']}",
                    callback_data=f"admin_select:{uid}"
                )] for uid in found
            ])
            await message.answer("Найдено несколько. Выбери:", reply_markup=kb)
            return
        target_id = found[0]
    await show_admin_user_profile(message, target_id)
    await state.clear()


@dp.callback_query(F.data.startswith("admin_select:"))
async def admin_select_handler(callback: CallbackQuery, state: FSMContext):
    target_id = callback.data.split(":")[1]
    await show_admin_user_profile(callback, target_id)
    await state.clear()


async def show_admin_user_profile(msg_or_call, target_id):
    players = await load_data(PLAYERS_FILE)
    p = players.get(target_id)
    if not p:
        return
    val = calculate_player_value(p["rating"], p["division"])
    parts = target_id.split("_")
    tg_id = parts[0]
    slot = parts[1] if len(parts) > 1 else "?"

    if p["position"] == "GK":
        stats_text = f"🧤 Сейвы: {p['stats_season'].get('saves', 0)}"
    elif p["position"] == "CB":
        stats_text = f"🛡️ Отборы: {p['stats_season'].get('tackles', 0)}"
    else:
        stats_text = f"⚽ Голы: {p['stats_season'].get('goals', 0)} | 🅰️ {p['stats_season'].get('assists', 0)}"

    images = await load_data(PROFILE_IMAGES_FILE)
    has_personal = target_id in images
    has_global = bool(images.get("__global__"))
    if has_personal:
        photo_line = "📸 Фото профиля: ✅ личное\n"
    elif has_global:
        photo_line = "📸 Фото профиля: 🌍 глобальное\n"
    else:
        photo_line = "📸 Фото профиля: ❌ нет\n"

    text = (
        f"👑 ПРОФИЛЬ\n📱 TG ID: `{tg_id}`\n💾 Полный ID: `{target_id}`\n📁 Слот: {slot}\n"
        f"{photo_line}"
        f"🏃 {p['name']} | 🌍 {p.get('nation', 'Россия')} | 🎂 {p.get('age', 17)}\n"
        f"⚡ Рейтинг: {p['rating']}/100\n🏢 {p['club']} ({p['position']})\n"
        f"💵 {p.get('money', 0)}$ | 🏷 {val:,}$\n"
        f"🏟 Сезон: {p['season']} | Тур: {p['tour']}/30\n"
        f"🌍 Еврокубки: {get_euro_name(p.get('euro_tournament', 'none'))}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n{stats_text}\n\n"
        f"📸 Фото: `profile` (глоб.) или `profile_{target_id}` (личное)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Тур (+1)", callback_data=f"adm_tour:{target_id}"),
         InlineKeyboardButton(text="⏭ Сезон (+1)", callback_data=f"adm_season:{target_id}")],
        [InlineKeyboardButton(text="💰 Деньги", callback_data=f"adm_money:{target_id}"),
         InlineKeyboardButton(text="⚡ Рейтинг", callback_data=f"adm_rating:{target_id}")],
        [InlineKeyboardButton(text="🖼 Удалить личное фото", callback_data=f"adm_delphoto:{target_id}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])

    if isinstance(msg_or_call, Message):
        await msg_or_call.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        try:
            await msg_or_call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data.startswith("adm_delphoto:"))
async def adm_del_photo(callback: CallbackQuery):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("Ошибка доступа.", show_alert=True)
    target_id = callback.data.split(":")[1]
    images = await load_data(PROFILE_IMAGES_FILE)
    if target_id in images:
        del images[target_id]
        await save_data(PROFILE_IMAGES_FILE, images)
        await callback.answer("🖼 Личное фото профиля удалено.", show_alert=True)
    else:
        await callback.answer("У игрока нет личного фото (используется глобальное).", show_alert=True)
    await show_admin_user_profile(callback, target_id)


@dp.callback_query(F.data.startswith("adm_tour:"))
async def adm_skip_tour(callback: CallbackQuery):
    if not callback.from_user.username or callback.from_user.username.replace("@", "") not in ADMINS:
        return await callback.answer("Ошибка доступа.", show_alert=True)
    target_id = callback.data.split(":")[1]
    async with get_user_lock(target_id):
        players = await load_data(PLAYERS_FILE)
        if target_id in players:
            p = players[target_id]
            if p.get("tour", 1) > 30:
                return await callback.answer("Сезон закончен.", show_alert=True)
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
            old_club, old_div = p["club"], p["division"]
            _apply_new_season_reset(p)
            await assign_euro_for_new_season(target_id, p, p["season"], old_club, old_div)
            players[target_id] = p
            await save_data(PLAYERS_FILE, players)
            await init_tables_for_user(target_id, p["division"], p["club"])
            await show_admin_user_profile(callback, target_id)


@dp.callback_query(F.data.startswith("adm_money:"))
async def adm_money_btn(callback: CallbackQuery, state: FSMContext):
    target_id = callback.data.split(":")[1]
    await state.update_data(adm_target_id=target_id)
    await callback.message.edit_text("💰 Сумма:", parse_mode="Markdown")
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
    await callback.message.edit_text("⚡ Рейтинг (1-100):", parse_mode="Markdown")
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


@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    if not await check_sub(message.from_user.id):
        return await message.answer(
            "❗️ **Подпишись на спонсора!**",
            reply_markup=sub_keyboard(), parse_mode="Markdown"
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"),
         InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])
    await message.answer("⚽ **Добро пожаловать!** Выбери слот:",
                         reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data == "check_sub_callback")
async def check_sub_handler(callback: CallbackQuery, state: FSMContext):
    if not await check_sub(callback.from_user.id):
        return await callback.answer("❌ Не подписан!", show_alert=True)
    await callback.message.delete()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"),
         InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])
    await callback.message.answer("✅ Подписка!\n⚽ Выбери слот:",
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
            f"👋 **{players[user_id]['name']}!** ID: `{user_id}`",
            reply_markup=await main_menu_keyboard(callback.from_user.username, user_id),
            parse_mode="Markdown"
        )
    else:
        if user_id in players and players[user_id].get("retired", False):
            await state.update_data(career_history=players[user_id].get("career_history", []))
            await callback.message.edit_text(
                f"⚽ Слот {slot}. Прошлая карьера окончена. Введи Имя и Фамилию:",
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                f"⚽ Слот {slot}. Введи Имя и Фамилию:",
                parse_mode="Markdown"
            )
        await state.set_state(PlayerCreation.waiting_for_name)


@dp.message(PlayerCreation.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=NATIONS[i], callback_data=f"nat:{NATIONS[i]}"),
         InlineKeyboardButton(text=NATIONS[i + 1] if i + 1 < len(NATIONS) else NATIONS[i],
                              callback_data=f"nat:{NATIONS[i + 1] if i + 1 < len(NATIONS) else NATIONS[i]}")]
        for i in range(0, min(len(NATIONS), 12), 2)
    ])
    await message.answer("🌍 Национальность:", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_nation)


@dp.callback_query(PlayerCreation.waiting_for_nation, F.data.startswith("nat:"))
async def process_nation(callback: CallbackQuery, state: FSMContext):
    await state.update_data(nation=callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=pos, callback_data=f"pos:{POSITIONS[pos]}")]
        for pos in POSITIONS.keys()
    ])
    await callback.message.edit_text("📋 Амплуа:", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_position)


@dp.callback_query(PlayerCreation.waiting_for_position, F.data.startswith("pos:"))
async def process_position(callback: CallbackQuery, state: FSMContext):
    await state.update_data(position=callback.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Россия", callback_data="league:Россия"),
         InlineKeyboardButton(text="🇫🇷 Франция", callback_data="league:Франция")],
        [InlineKeyboardButton(text="🏴 Англия", callback_data="league:Англия"),
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
    await callback.message.edit_text("🌍 Страна:", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_country_league)


@dp.callback_query(PlayerCreation.waiting_for_country_league, F.data.startswith("league:"))
async def process_country_league(callback: CallbackQuery, state: FSMContext):
    lc = callback.data.split(":")[1]
    mapping = {
        "Россия": "ФНЛ 2", "Франция": "Насьональ", "Англия": "Первая лига Англии",
        "Испания": "Сегунда", "Германия": "Вторая Бундеслига", "Италия": "Серия Б",
        "Португалия": "Сегунда лига", "Нидерланды": "Эрстедивизи",
        "Бельгия": "Jupiler Pro League", "Беларусь": "Беларусь Первая лига",
        "Турция": "Турция Первая лига", "Казахстан": "Казахстан Премьер-лига"
    }
    await state.update_data(start_division=mapping.get(lc, "ФНЛ 2"))
    await callback.message.edit_text("🔢 Номер (1-99):", parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_number)


@dp.message(PlayerCreation.waiting_for_number)
async def process_number(message: Message, state: FSMContext):
    if not message.text.isdigit() or not (1 <= int(message.text) <= 99):
        return await message.answer("🚫 1-99")
    await state.update_data(number=int(message.text))
    ud = await state.get_data()
    clubs = random.sample(CLUBS[ud["start_division"]], 3)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏢 {c}", callback_data=f"club:{c}")] for c in clubs
    ])
    await message.answer(f"📉 Лига: **{ud['start_division']}**. Выбери клуб:",
                         reply_markup=kb, parse_mode="Markdown")
    await state.set_state(PlayerCreation.waiting_for_club)


@dp.callback_query(PlayerCreation.waiting_for_club, F.data.startswith("club:"))
@with_user_lock
async def process_club(callback: CallbackQuery, state: FSMContext):
    ud = await state.get_data()
    user_id = await get_uid(callback)
    chosen = callback.data.split(":")[1]

    profile = {
        "name": ud["name"], "nation": ud.get("nation", "Россия"),
        "position": ud["position"], "number": ud["number"],
        "club": chosen, "division": get_division(chosen),
        "rating": 40.0, "trust": 15, "fatigue": 0, "girlfriend": "Нет",
        "age": 17, "season": 1, "tour": 1, "money": 5000, "contract_salary": 1500,
        "sponsor": None, "on_loan": False, "parent_club": None, "loan_tours_left": 0,
        "cup_out": False, "cup_stage": "1/16", "cup_rivals": [], "played_league_rivals": [],
        "trophies": [],
        "stats_season": {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0},
        "stats_total": {"games": 0, "goals": 0, "assists": 0, "saves": 0, "tackles": 0},
        "completed_quests": [], "train_done": False, "train_streak": 0, "train_count": 0,
        "train_tech_count": 0, "train_phys_count": 0, "train_special_count": 0,
        "train_achievements": [], "is_injured": False, "injury_tours": 0,
        "username_tg": callback.from_user.username, "career_history": ud.get("career_history", []),
        "retired": False, "activity_minutes": 0, "activity_week": datetime.now().isocalendar()[1],
        "reputation": 50, "motivation": 50, "married": False, "children": 0,
        "wife_loyalty": 0, "business": None, "business_crisis": False,
        "business_crisis_timer": 0, "car": None, "has_yoga_bonus": False,
        "last_interview_tour": 0, "rating_performance": 0, "age_penalty_applied": False,
        "euro_tournament": None, "euro_goals": 0, "euro_assists": 0, "euro_matches": 0,
        "euro_playoff_stage": None
    }
    players = await load_data(PLAYERS_FILE)
    players[user_id] = profile
    await save_data(PLAYERS_FILE, players)
    await init_tables_for_user(user_id, profile["division"], profile["club"])
    await delete_euro(user_id)
    await state.clear()
    await callback.message.edit_text(
        f"✍️ Контракт с {chosen}!\n💰 {profile['contract_salary']}$/матч.",
        reply_markup=await main_menu_keyboard(callback.from_user.username, user_id),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data == "start_new_career")
@with_user_lock
async def start_new_career_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"),
         InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer("⚽ Выбери слот:", reply_markup=kb, parse_mode="Markdown")
        else:
            await callback.message.edit_text("⚽ Выбери слот:", reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await callback.message.answer("⚽ Выбери слот:", reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data == "delete_career")
@with_user_lock
async def delete_career_confirm(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="delete_career_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="back_to_menu")]
    ])
    text = "🗑 Удалить карьеру?\nЭто действие необратимо!"
    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data == "delete_career_yes")
@with_user_lock
async def delete_career_final(callback: CallbackQuery, state: FSMContext):
    players = await load_data(PLAYERS_FILE)
    user_id = await get_uid(callback)
    if user_id in players:
        del players[user_id]
        await save_data(PLAYERS_FILE, players)
    images = await load_data(PROFILE_IMAGES_FILE)
    if user_id in images:
        del images[user_id]
        await save_data(PROFILE_IMAGES_FILE, images)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Слот 1", callback_data="select_slot:1"),
         InlineKeyboardButton(text="📁 Слот 2", callback_data="select_slot:2")]
    ])
    await callback.message.edit_text("🗑 Удалено. Выбери слот:", reply_markup=kb, parse_mode="Markdown")


@dp.callback_query(F.data == "menu_train_choice")
@with_user_lock
async def train_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if await deny_if_retired_cb(callback, p):
        return
    if p.get("injury_tours", 0) > 0:
        return await callback.answer(f"🚑 Травма: {p['injury_tours']} туров", show_alert=True)
    if p.get("train_done", False):
        return await callback.answer("🚫 Сыграй матч!", show_alert=True)
    fatigue = p.get("fatigue", 0)
    if fatigue >= 70:
        return await callback.answer(f"🚫 Устал: {fatigue}%", show_alert=True)
    cost = get_train_cost(p.get("rating", 40))
    if p.get("money", 0) < cost:
        return await callback.answer(f"❌ Нужно {cost}$", show_alert=True)

    config = TRAINING_CONFIG.get(p.get("position", "ST"), TRAINING_CONFIG["ST"])
    text = (f"🏋️ **ТРЕНИРОВКА**\nРейтинг: {p['rating']}\nУсталость: {fatigue}%\n"
            f"Серия: {p.get('train_streak', 0)}\nСтоимость: {cost}$")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎯 {config['tech']['name']}", callback_data="train:tech")],
        [InlineKeyboardButton(text=f"🏃 {config['phys']['name']}", callback_data="train:phys")],
        [InlineKeyboardButton(text=f"⭐ {config['special']['name']}", callback_data="train:special")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        else:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")


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
        return await callback.answer("🚑 Травма!", show_alert=True)
    if p.get("train_done", False):
        return await callback.answer("🚫 Сыграй матч!", show_alert=True)
    fatigue = p.get("fatigue", 0)
    if fatigue >= 70:
        return await callback.answer(f"🚫 {fatigue}% усталости", show_alert=True)
    cost = get_train_cost(p.get("rating", 40))
    if p.get("money", 0) < cost:
        return await callback.answer(f"❌ {cost}$", show_alert=True)

    config = TRAINING_CONFIG.get(p.get("position", "ST"), TRAINING_CONFIG["ST"])
    td = config.get(train_type, config["tech"])
    gain = td["base_gain"]
    streak = p.get("train_streak", 0)
    total_gain = gain + get_streak_bonus(streak)
    golden = random.random() < 0.05
    if golden:
        total_gain *= 2
    failed = random.random() < 0.03
    if failed:
        total_gain = -0.2
    inspiration = random.random() < 0.08

    injured = False
    if random.random() < 0.02 + (fatigue / 100) * 0.05:
        injured = True
        p["injury_tours"] = random.randint(1, 3)
        total_gain -= 0.5

    p["train_done"] = True
    p["fatigue"] = min(100, p.get("fatigue", 0) + td["fatigue"])
    p["money"] -= cost
    p["train_streak"] = streak + 1
    p["train_count"] = p.get("train_count", 0) + 1
    p["trust"] = min(100, p.get("trust", 15) + 3)
    p[f"train_{train_type}_count"] = p.get(f"train_{train_type}_count", 0) + 1
    if inspiration:
        p["fatigue"] = max(0, p["fatigue"] - 5)
    p["rating"] = max(1.0, min(100.0, round(p["rating"] + total_gain, 1)))

    new_ach, ach_rew = check_train_achievements(p, p.get("train_count", 0), p.get("train_streak", 0))
    if new_ach:
        p["rating"] += ach_rew
        train_ach = p.get("train_achievements", [])
        for ach in new_ach:
            for key, val in TRAIN_ACHIEVEMENTS.items():
                if val["name"] == ach["name"] and key not in train_ach:
                    train_ach.append(key)
                    break
        p["train_achievements"] = train_ach

    p["reputation"] = min(100, p.get("reputation", 50) + 0.5)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)
    await callback.message.delete()

    msg = ["💪 **ТРЕНИРОВКА**", f"📋 {td['name']}"]
    if failed:
        msg.append("😞 Провал")
    elif injured:
        msg.append(f"🚑 Травма: {p['injury_tours']} туров")
    else:
        msg.append(f"📈 +{gain}")
        if streak > 0: msg.append(f"🔥 Бонус серии: +{get_streak_bonus(streak)}")
        if golden: msg.append("🌟 Золотая x2")
        if inspiration: msg.append("💡 Вдохновение -5% усталости")
    msg.append(f"⚡ {p['rating']} | ❤️ {p['trust']} | 🔋 {p['fatigue']}%")
    if new_ach:
        msg.append("🎉 Достижения:")
        for ach in new_ach:
            msg.append(f"🏅 {ach['name']} (+{ach['reward']})")

    await callback.message.answer("\n".join(msg), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                      [InlineKeyboardButton(text="🏠 Меню", callback_data="back_to_menu")]
                                  ]))


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer("🏠 Меню.", reply_markup=kb)
        else:
            await callback.message.edit_text("🏠 Меню.", reply_markup=kb)
    except Exception:
        await callback.message.answer("🏠 Меню.", reply_markup=kb)


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
    table = tables[user_id][p["division"]]
    text = f"📊 **ТАБЛИЦА: {p['division']}**\n"
    for i, r in enumerate(table, 1):
        is_p = "👉 " if r["club"] == p["club"] else "• "
        text += f"{i}. {is_p}**{r['club']}** — {r['points']} очков ({r['wins']}В/{r['draws']}Н/{r['losses']}П)\n"
    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "menu_profile")
@with_user_lock
async def profile_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    await track_activity(user_id)
    p = (await load_data(PLAYERS_FILE)).get(user_id)
    if not p:
        return await callback.message.answer("⚠️ Нажми /start")
    if p.get("retired"):
        history = "\n\n".join(p.get("career_history", [])) or "—"
        text = (
            f"🏁 **КАРЬЕРА ЗАВЕРШЕНА**\n🏃 {p['name']} | 🌍 {p.get('nation', 'Россия')}\n\n"
            f"📚 **История:**\n{history}"
        )
        kb = retired_keyboard()
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        else:
            try:
                await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            except Exception:
                await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        return

    val = calculate_player_value(p["rating"], p["division"])
    loan_status = f"\n⚠️ Аренда из {p['parent_club']}" if p.get("on_loan") else ""
    injury_status = f"\n🚑 Травма: {p.get('injury_tours', 0)} тур." if p.get("injury_tours", 0) > 0 else ""

    if p["position"] == "GK":
        stats_text = f"🧤 Сейвы: {p['stats_season'].get('saves', 0)}"
    elif p["position"] == "CB":
        stats_text = f"🛡️ Отборы: {p['stats_season'].get('tackles', 0)} | ⚽ {p['stats_season'].get('goals', 0)}"
    else:
        stats_text = f"⚽ {p['stats_season'].get('goals', 0)} | 🅰️ {p['stats_season'].get('assists', 0)}"

    history_str = ""
    if p.get("career_history"):
        history_str = "\n\n📚 **Прошлые карьеры:**\n" + "\n\n".join(p["career_history"])

    season_display = min(p['season'], 13)
    tour_display = min(p['tour'], 30)

    train_stats = (
        f"\n📊 **Тренировки:**\n🔥 Серия: {p.get('train_streak', 0)}\n"
        f"📈 Всего: {p.get('train_count', 0)}\n"
        f"🏅 Достижений: {len(p.get('train_achievements', []))}"
    )

    euro_stats = ""
    if p.get("euro_tournament") and p.get("euro_tournament") != "none":
        euro_stats = (
            f"\n🌍 **Еврокубки:** {get_euro_name(p['euro_tournament'])}\n"
            f"Матчей: {p.get('euro_matches', 0)} | Голов: {p.get('euro_goals', 0)} | "
            f"Ассистов: {p.get('euro_assists', 0)}"
        )

    text = (
        f"👑 ПРОФИЛЬ\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃 {p['name']} | 🌍 {p.get('nation', 'Россия')} | 🎂 {p.get('age', 17)}\n"
        f"⚡ Рейтинг: {p['rating']}/100\n"
        f"🏢 {p['club']} ({p['position']}){loan_status}{injury_status}\n"
        f"💵 Баланс: {p.get('money', 0)}$ | 🏷 Стоимость: {val:,}$\n"
        f"🤝 Зарплата: {p.get('contract_salary', 0)}$/матч\n"
        f"💎 Спонсор: {p.get('sponsor', 'Нет')}\n"
        f"📊 Статус: {get_status_by_trust(p['trust'])}\n"
        f"🔋 Усталость: {p.get('fatigue', 0)}%\n"
        f"💍 Девушка: {p.get('girlfriend', 'Нет')}\n"
        f"🏟 Сезон: {season_display}/13 | Тур: {tour_display}/30\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 **За сезон:** {stats_text}\n"
        f"📈 **Всего:** Игр: {p.get('stats_total', {}).get('games', 0)} | "
        f"Голов: {p.get('stats_total', {}).get('goals', 0)} | "
        f"Ассистов: {p.get('stats_total', {}).get('assists', 0)}"
        f"{euro_stats}{train_stats}{history_str}"
    )

    kb = await main_menu_keyboard(callback.from_user.username, user_id)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Удалить карьеру", callback_data="delete_career")])

    profile_photo = await get_profile_image(user_id)

    if profile_photo:
        try:
            if callback.message.photo:
                await callback.message.edit_media(
                    media=InputMediaPhoto(media=profile_photo, caption=text, parse_mode="Markdown"),
                    reply_markup=kb
                )
            else:
                await callback.message.delete()
                await callback.message.answer_photo(
                    photo=profile_photo, caption=text, parse_mode="Markdown", reply_markup=kb
                )
        except TelegramBadRequest:
            if callback.message.photo:
                await callback.message.delete()
            await callback.message.answer_photo(
                photo=profile_photo, caption=text, parse_mode="Markdown", reply_markup=kb
            )
    else:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=kb)
        else:
            try:
                await callback.message.edit_text(text, reply_markup=kb)
            except Exception:
                await callback.message.answer(text, reply_markup=kb)


def _season_choice_pending(p: dict) -> bool:
    return bool(p.get("_season_pending") or p.get("_season_offers"))


def _format_awards_text(awards, bonuses) -> str:
    awards_text = ""
    if awards:
        awards_text = "\n\n🏆 **НОМИНАЦИИ СЕЗОНА:**\n"
        for key, label in [("golden_ball", "🥇 ЗМ"), ("golden_glove", "🧤 ЗП"),
                            ("best_defender", "🛡️ ЛЗ"), ("best_assistant", "🅰️ ЛА")]:
            a = awards.get(key)
            if a:
                mark = "⭐ " if a.get("is_player") else ""
                awards_text += f"{label}: {mark}{a['name']}\n"
    if bonuses:
        awards_text += "\n🎁 **ТВОИ НАГРАДЫ:**\n" + "\n".join(bonuses)
    return awards_text


async def _send_season_results(callback: CallbackQuery, p: dict):
    offers = p.get("_season_offers", [])
    season_num = p.get("_season_num", p.get("season", 1))
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
    buttons.append([InlineKeyboardButton(text="🏆 Подробнее о номинациях", callback_data="menu_awards")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = (
        f"🏁 **ИТОГИ СЕЗОНА {season_num}**\n━━━━━━━━━━━━━━━━━━━━\n"
        f"{p.get('_season_result_text', '')}\n\n"
        f"📊 {p.get('_season_stats_text', '')}\n"
        f"{p.get('_season_awards_text', '')}\n\n"
        f"📋 **Выбери, где продолжить карьеру:**"
    )

    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "message is not modified" in str(e):
            return
        logging.warning(f"season_results send error: {e}")
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def season_results_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if await deny_if_retired_cb(callback, p):
        return

    if _season_choice_pending(p):
        return await _send_season_results(callback, p)

    async with get_table_lock():
        tables = await load_data(TABLES_FILE)
        table = tables.get(user_id, {}).get(p["division"], [])
    table_sorted = sorted(table, key=_table_sort_key, reverse=True)
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
        stats_text = f"🎮 {stats.get('games', 0)} матчей | 🛡️ {stats.get('tackles', 0)} отборов"
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
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)

        awards = await calculate_player_awards(user_id, season_num)
        bonuses = await apply_awards_bonuses(user_id, awards, season_num)

        players = await load_data(PLAYERS_FILE)
        p = players.get(user_id)
        _apply_new_season_reset(p)
        players[user_id] = p
        await save_data(PLAYERS_FILE, players)

        awards_text = _format_awards_text(awards, bonuses)

        text = (
            f"🏁 **ИТОГИ СЕЗОНА {season_num}**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{result_text}\n\n"
            f"📊 {stats_text}\n"
            f"{awards_text}\n\n"
            f"🏁 **Карьера завершена! Ты уходишь на заслуженную пенсию.**"
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
        forced_club = random.choice(
            [c for c in CLUBS.get(forced_div, []) if c != p["club"]] or CLUBS.get(forced_div, [p["club"]])
        )
        forced_salary = max(1500, int(CLUB_RATINGS.get(forced_club, 50) * 150 + rating * 50))
        forced_offer = {"club": forced_club, "division": forced_div,
                        "club_rating": CLUB_RATINGS.get(forced_club, 50), "salary": forced_salary}
        offers = [o for o in offers if o["division"] != forced_div][:3]
        offers.insert(0, forced_offer)

    p["_season_pending"] = True
    p["_season_offers"] = offers
    p["_season_num"] = season_num
    p["_season_forced_div"] = forced_div
    p["_season_result_text"] = result_text
    p["_season_stats_text"] = stats_text
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    awards = await calculate_player_awards(user_id, season_num)
    bonuses = await apply_awards_bonuses(user_id, awards, season_num)

    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    p["_season_awards_text"] = _format_awards_text(awards, bonuses)
    players[user_id] = p
    await save_data(PLAYERS_FILE, players)

    await _send_season_results(callback, p)


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
    for key in EURO_PLAYOFF_FLAGS:
        p.pop(key, None)
    p["euro_playoff_stage"] = None
    p["euro_goals"] = 0
    p["euro_assists"] = 0
    p["euro_matches"] = 0
    for key in ("_season_offers", "_season_num", "_season_result_text", "_season_stats_text",
                "_season_forced_div", "_season_pending", "_season_awards_text"):
        p.pop(key, None)


@dp.callback_query(F.data.startswith("season_choice:"))
@with_user_lock
async def season_choice_handler(callback: CallbackQuery):
    user_id = await get_uid(callback)
    players = await load_data(PLAYERS_FILE)
    p = players.get(user_id)
    if not p:
        return await callback.answer("⚠️ Профиль не найден. Нажми /start.", show_alert=True)

    if not _season_choice_pending(p):
        return await callback.answer(
            "⚠️ Этот выбор уже неактуален: клуб на новый сезон уже выбран.",
            show_alert=True
        )

    old_club, old_division = p["club"], p["division"]
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

    _apply_new_season_reset(p)

    euro_tournament = await assign_euro_for_new_season(user_id, p, p["season"], old_club, old_division)
    if euro_tournament:
        club_line += f"\n\n🌍 {get_euro_name(euro_tournament)}!"

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
        logging.warning(f"season_choice edit error: {e}")
        if callback.message.photo:
            await callback.message.delete()
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def ensure_files_exist():
    files_defaults = {
        PLAYERS_FILE: {},
        LEADERBOARD_FILE: {"top_careers": []},
        TABLES_FILE: {},
        SLOTS_FILE: {},
        AWARDS_FILE: {},
        NPC_FILE: {},
        MOMENT_IMAGES_FILE: {},
        PROFILE_IMAGES_FILE: {},
    }
    for filename, default_value in files_defaults.items():
        if not os.path.exists(filename):
            await save_data(filename, default_value)
            print(f"📁 Создан файл: {filename}")


async def main():
    print("🚀 Бот запущен и ожидает сообщений...")
    print("📌 Пониженные шансы голов/ассистов (множитель 0.45)")
    print("📌 Глобальное фото профиля: админ кидает фото с подписью `profile`")
    print("📌 Личное фото профиля: фото с подписью `profile_<user_id>`")
    print("📌 Моменты: /set, /moment_keys, /moment_stats")

    await ensure_files_exist()
    os.makedirs(EURO_DIR, exist_ok=True)
    await migrate_euro_file()

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
