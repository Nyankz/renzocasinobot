import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# === НАСТРОЙКИ ===
BOT_TOKEN = "7606518006:AAGSgmiBquOUZoGAaOSrnp5fFOfgJ5S3R3s"
CHANNEL_ID = -1002835648324  # Твой канал ID
ADMINS = [764515145]         # Твои Telegram ID

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# === БАЗА ДАННЫХ ===
conn = sqlite3.connect("votes.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS battles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name1 TEXT,
    name2 TEXT,
    message_id INTEGER,
    chat_id INTEGER,
    end_time TEXT,
    votes1 INTEGER DEFAULT 0,
    votes2 INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS votes (
    user_id INTEGER,
    battle_id INTEGER,
    choice INTEGER
)
""")
conn.commit()

# === FSM ===
class BattleState(StatesGroup):
    name1 = State()
    name2 = State()
    duration = State()

# === /start ===
@router.message(F.text == "/start")
async def start(message: Message):
    await message.answer("Бұл бот голос батл жасауға арналған. Админ болсаңыз — /admin.")

# === /admin ===
@router.message(F.text == "/admin")
async def admin_panel(message: Message):
    if message.from_user.id not in ADMINS:
        return await message.answer("Сізге рұқсат жоқ.")
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Батл жасау", callback_data="create_battle")
    kb.button(text="⛔ Батл тоқтату", callback_data="stop_battle")
    await message.answer("Админ панель:", reply_markup=kb.as_markup())

# === FSM: Battle жасау ===
@router.callback_query(F.data == "create_battle")
async def ask_name1(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("1-қатысушының атын жазыңыз:")
    await state.set_state(BattleState.name1)

@router.message(BattleState.name1)
async def ask_name2(message: Message, state: FSMContext):
    await state.update_data(name1=message.text)
    await message.answer("2-қатысушының атын жазыңыз:")
    await state.set_state(BattleState.name2)

@router.message(BattleState.name2)
async def ask_duration(message: Message, state: FSMContext):
    await state.update_data(name2=message.text)
    await message.answer("Батл ұзақтығын жазыңыз (минутпен):")
    await state.set_state(BattleState.duration)

@router.message(BattleState.duration)
async def create_battle(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        minutes = int(message.text)
    except:
        return await message.answer("Санмен жазыңыз (мыс: 60)")

    name1, name2 = data['name1'], data['name2']
    end_time = datetime.utcnow() + timedelta(minutes=minutes)
    text = f"<b>🥊 Батл: {name1} | {name2}</b>\nДауыс беру астында!\n\n{name1} — 0 голос\n{name2} — 0 голос"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗳 Голосовать", callback_data=f"vote:{name1}:{name2}")]
    ])
    sent = await bot.send_message(CHANNEL_ID, text, reply_markup=kb)

    c.execute("INSERT INTO battles (name1, name2, message_id, chat_id, end_time) VALUES (?, ?, ?, ?, ?)",
              (name1, name2, sent.message_id, sent.chat.id, end_time.isoformat()))
    conn.commit()
    await message.answer("✅ Батл жарияланды!")
    await state.clear()
    asyncio.create_task(timer_check())

# === Дауыс беру ===
@router.callback_query(F.data.startswith("vote:"))
async def handle_vote(callback: CallbackQuery):
    user_id = callback.from_user.id
    _, name1, name2 = callback.data.split(":")
    c.execute("SELECT * FROM battles WHERE name1=? AND name2=? AND is_active=1 ORDER BY id DESC LIMIT 1", (name1, name2))
    battle = c.fetchone()
    if not battle:
        return await callback.answer("⛔ Бұл батл аяқталған!", show_alert=True)

    battle_id = battle[0]
    c.execute("SELECT * FROM votes WHERE user_id=? AND battle_id=?", (user_id, battle_id))
    if c.fetchone():
        return await callback.answer("Сіз дауыс беріп қойғансыз.", show_alert=True)

    kb = InlineKeyboardBuilder()
    kb.button(text=name1, callback_data=f"choose:{battle_id}:1")
    kb.button(text=name2, callback_data=f"choose:{battle_id}:2")
    await callback.message.answer("Кімге дауыс бересіз?", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("choose:"))
async def process_choice(callback: CallbackQuery):
    _, battle_id, choice = callback.data.split(":")
    battle_id, choice = int(battle_id), int(choice)
    user_id = callback.from_user.id

    c.execute("SELECT * FROM battles WHERE id=?", (battle_id,))
    battle = c.fetchone()
    if not battle or battle[8] == 0:
        return await callback.answer("Батл аяқталған.", show_alert=True)

    c.execute("INSERT INTO votes (user_id, battle_id, choice) VALUES (?, ?, ?)", (user_id, battle_id, choice))
    if choice == 1:
        c.execute("UPDATE battles SET votes1 = votes1 + 1 WHERE id = ?", (battle_id,))
    else:
        c.execute("UPDATE battles SET votes2 = votes2 + 1 WHERE id = ?", (battle_id,))
    conn.commit()

    name1, name2 = battle[1], battle[2]
    votes1 = battle[6] + (1 if choice == 1 else 0)
    votes2 = battle[7] + (1 if choice == 2 else 0)
    new_text = f"<b>🥊 Батл: {name1} | {name2}</b>\nДауыс беру астында!\n\n{name1} — {votes1} голос\n{name2} — {votes2} голос"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗳 Голосовать", callback_data=f"vote:{name1}:{name2}")]
    ])
    await bot.edit_message_text(new_text, battle[4], battle[3], reply_markup=kb)
    await callback.answer("✅ Дауыс қабылданды")

# === Таймер тексеру ===
async def timer_check():
    while True:
        now = datetime.utcnow()
        c.execute("SELECT * FROM battles WHERE is_active=1")
        for b in c.fetchall():
            end = datetime.fromisoformat(b[5])
            if now >= end:
                await stop_battle_by_id(b[0])
        await asyncio.sleep(5)

# === Батл тоқтату (авто және /stop үшін)
async def stop_battle_by_id(battle_id):
    c.execute("SELECT * FROM battles WHERE id=? AND is_active=1", (battle_id,))
    b = c.fetchone()
    if not b:
        return
    c.execute("UPDATE battles SET is_active=0 WHERE id=?", (battle_id,))
    conn.commit()
    name1, name2 = b[1], b[2]
    votes1, votes2 = b[6], b[7]
    winner = name1 if votes1 > votes2 else name2 if votes2 > votes1 else "Екеуі тең"
    text = f"<b>⛔ Батл аяқталды!</b>\n\n{name1} — {votes1} голос\n{name2} — {votes2} голос\n\n🥇 Жеңімпаз: {winner} 🎉"
    await bot.edit_message_text(text, b[4], b[3])

# === /stop → тізімнен таңдату
@router.message(F.text == "/stop")
async def stop_battle_menu(message: Message):
    if message.from_user.id not in ADMINS:
        return await message.answer("Сізге рұқсат жоқ.")
    c.execute("SELECT id, name1, name2 FROM battles WHERE is_active=1")
    active = c.fetchall()
    if not active:
        return await message.answer("Қазір белсенді батл жоқ.")
    kb = InlineKeyboardBuilder()
    for b in active:
        kb.button(text=f"{b[1]} | {b[2]}", callback_data=f"force_stop:{b[0]}")
    await message.answer("Қай батлды тоқтатқыңыз келеді?", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("force_stop:"))
async def stop_selected_battle(callback: CallbackQuery):
    battle_id = int(callback.data.split(":")[1])
    await stop_battle_by_id(battle_id)
    await callback.answer("Батл тоқтатылды.")
