import asyncio
import random
import time
import os

# Автоматическая установка библиотек
os.system("pip install aiogram aiosqlite")

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

BOT_TOKEN = "8962785716:AAH9h4b5A65hPGS3Qbsd0TXOU90rLIj4kzE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

async def init_db():
    async with aiosqlite.connect("casino.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 2000,
                last_bonus INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect("casino.db") as db:
        cursor = await db.execute("SELECT balance, last_bonus FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            await db.execute("INSERT INTO users (user_id, balance, last_bonus) VALUES (?, 2000, 0)", (user_id,))
            await db.commit()
            return 2000, 0
        return row[0], row[1]

async def update_balance(user_id: int, new_balance: int):
    async with aiosqlite.connect("casino.db") as db:
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        await db.commit()

async def update_bonus_time(user_id: int, current_time: int):
    async with aiosqlite.connect("casino.db") as db:
        await db.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (current_time, user_id))
        await db.commit()

# Клавиатура с кнопкой "Команды"
def get_commands_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Команды", callback_data="show_commands")]
        ]
    )

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type in ["group", "supergroup"]:
        return  # В группах не спамит при добавлении
        
    await get_user(message.from_user.id)
    await message.answer(
        "🎰 **Добро пожаловать в казино Нокси**",
        reply_markup=get_commands_keyboard(),
        parse_mode="Markdown"
    )

# Обработка нажатия на кнопку "Команды"
@dp.callback_query(F.data == "show_commands")
async def process_show_commands(callback: CallbackQuery):
    commands_text = (
        "📌 **Команды бота:**\n"
        "• `баланс` или `б` — узнать свой баланс\n"
        "• `бонус` — забрать ежедневный бонус (5000 ноксябаксов)"
    )
    await callback.message.answer(commands_text, parse_mode="Markdown")
    await callback.answer()

# Просмотр баланса
@dp.message(F.text.lower().in_({"баланс", "б", "/balance"}))
async def cmd_balance(message: Message):
    balance, _ = await get_user(message.from_user.id)
    user_name = message.from_user.first_name
    await message.reply(f"👤 **{user_name}**, твой баланс: **{balance}** ноксябаксов.")

# Получение ежедневного бонуса
@dp.message(F.text.lower().in_({"бонус", "/bonus"}))
async def cmd_bonus(message: Message):
    user_id = message.from_user.id
    balance, last_bonus = await get_user(user_id)
    current_time = int(time.time())
    
    cooldown = 86400  # 24 часа
    passed_time = current_time - last_bonus

    if passed_time < cooldown:
        remaining = cooldown - passed_time
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await message.reply(f"⏳ Бонус можно получить через **{hours}ч {minutes}мин**.")
    else:
        new_balance = balance + 5000
        await update_balance(user_id, new_balance)
        await update_bonus_time(user_id, current_time)
        await message.reply("🎁 Ты получил ежедневный бонус: **+5000** ноксябаксов!")

# Рулетка
@dp.message()
async def process_roulette_bet(message: Message):
    text = message.text.strip().lower().split()
    
    if len(text) != 2 or not text[0].isdigit():
        return

    bet = int(text[0])
    target = text[1]
    user_id = message.from_user.id

    balance, _ = await get_user(user_id)

    if bet <= 0:
        await message.reply("Ставка должна быть больше 0!")
        return

    if bet > balance:
        await message.reply("У тебя недостаточно ноксябаксов!")
        return

    valid_targets = {"к", "ч", "чет", "нечет", "1-18", "19-36", "1д", "2д", "3д"}
    is_number_bet = target.isdigit() and 0 <= int(target) <= 36

    if not is_number_bet and target not in valid_targets:
        return

    gif_url = "https://media.giphy.com/media/26uf2YTgF5upXUTm0/giphy.gif"
    msg = await message.answer_animation(animation=gif_url, caption="🎰 Колесо крутится...")

    await asyncio.sleep(3)

    number = random.randint(0, 36)
    
    if number == 0:
        color_str = "зеленое (ЗЕРО)"
    elif number in RED_NUMBERS:
        color_str = "красное"
    else:
        color_str = "черное"

    multiplier = 0

    if is_number_bet and int(target) == number:
        multiplier = 36
    elif number != 0:
        if target == "к" and number in RED_NUMBERS:
            multiplier = 2
        elif target == "ч" and number not in RED_NUMBERS:
            multiplier = 2
        elif target == "чет" and number % 2 == 0:
            multiplier = 2
        elif target == "нечет" and number % 2 != 0:
            multiplier = 2
        elif target == "1-18" and 1 <= number <= 18:
            multiplier = 2
        elif target == "19-36" and 19 <= number <= 36:
            multiplier = 2
        elif target == "1д" and 1 <= number <= 12:
            multiplier = 3
        elif target == "2д" and 13 <= number <= 24:
            multiplier = 3
        elif target == "3д" and 25 <= number <= 36:
            multiplier = 3

    if multiplier > 0:
        profit = (bet * multiplier) - bet
        new_balance = balance + profit
        res_text = f"🎉 **ПОБЕДА!** Выигрыш: **+{profit}** ноксябаксов!"
    else:
        new_balance = balance - bet
        res_text = f"❌ **ПРОИГРЫШ!** Потеряно: **-{bet}** ноксябаксов."

    await update_balance(user_id, new_balance)

    await msg.reply(
        f"🎯 Выпало: **{number}** ({color_str})\n"
        f"{res_text}"
    )

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
