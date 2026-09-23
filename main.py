import asyncio
import random
import time
import os
from aiohttp import web

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

BOT_TOKEN = "8962785716:AAH9h4b5A65hPGS3Qbsd0TXOU90rLIj4kzE"
ADMIN_ID = 7939255638

REQUIRED_CHANNELS = ["@craxkspot", "@noksyaa"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
active_games = {}

async def handle_ping(request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def check_subscription(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

async def send_sub_request(message: Message):
    await message.reply(
        "❌ <b>Чтобы пользоваться ботом, необходимо подписаться на наши каналы!</b>\n\n"
        "👉 t.me/craxkspot\n"
        "👉 t.me/noksyaa\n\n"
        "После подписки ты сможешь делать ставки и использовать все команды.",
        parse_mode="HTML"
    )

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

def get_commands_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📜 Команды", callback_data="show_commands")]
        ]
    )

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type in ["group", "supergroup"]:
        return
        
    await get_user(message.from_user.id)
    await message.answer(
        "🎰 <b>Добро пожаловать в казино Нокси</b>",
        reply_markup=get_commands_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "show_commands")
async def process_show_commands(callback: CallbackQuery):
    commands_text = (
        "📌 <b>Команды бота (нужна подписка на @craxkspot и @noksyaa):</b>\n"
        "• <code>баланс</code> или <code>б</code> — узнать свой баланс\n"
        "• <code>бонус</code> — забрать ежедневный бонус (5000 ноксябаксов)\n"
        "• <code>п &lt;сумма&gt;</code> или <code>передать &lt;сумма&gt;</code> (ответом на сообщение) — перевести деньги\n"
        "• <code>го</code> — запустить рулетку после ставок (доступно через 10 сек)\n\n"
        "🎰 <b>Варианты ставок в рулетке:</b>\n"
        "• На цвет: <code>к</code> (красное), <code>ч</code> (черное)\n"
        "• На четность: <code>чет</code>, <code>нечет</code>\n"
        "• На дюжину: <code>1д</code>, <code>2д</code>, <code>3д</code>\n"
        "• На число: от <code>0</code> до <code>36</code> (умножение x36)\n"
        "• На <b>любой диапазон</b>: <code>1-12</code>, <code>1-15</code>, <code>5-20</code> и т.д. (коэффициент высчитывается автоматически)"
    )
    await callback.message.answer(commands_text, parse_mode="HTML")
    await callback.answer()

@dp.message(F.text.lower().in_({"баланс", "б", "/balance"}))
async def cmd_balance(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    balance, _ = await get_user(message.from_user.id)
    name = message.from_user.first_name.replace("<", "&lt;").replace(">", "&gt;")
    mention = f'<a href="tg://user?id={message.from_user.id}">{name}</a>'

    await message.reply(f"👤 {mention}, твой баланс: <b>{balance}</b> ноксябаксов.", parse_mode="HTML")

@dp.message(F.text.lower().in_({"бонус", "/bonus"}))
async def cmd_bonus(message: Message):
    user_id = message.from_user.id

    if not await check_subscription(user_id):
        await send_sub_request(message)
        return

    balance, last_bonus = await get_user(user_id)
    current_time = int(time.time())
    
    cooldown = 86400
    passed_time = current_time - last_bonus

    if passed_time < cooldown:
        remaining = cooldown - passed_time
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        await message.reply(f"⏳ Бонус можно получить через <b>{hours}ч {minutes}мин</b>.", parse_mode="HTML")
    else:
        new_balance = balance + 5000
        await update_balance(user_id, new_balance)
        await update_bonus_time(user_id, current_time)
        await message.reply("🎁 Ты получил ежедневный бонус: <b>+5000</b> ноксябаксов!", parse_mode="HTML")

@dp.message(F.text.lower().startswith("читы "))
async def cmd_admin_cheat(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    text = message.text.strip().split()
    if len(text) == 2 and text[1].isdigit():
        amount = int(text[1])
        user_id = message.from_user.id
        balance, _ = await get_user(user_id)
        new_balance = balance + amount
        await update_balance(user_id, new_balance)
        await message.reply(f"👑 <b>Админ-выдача:</b> Выдано <b>+{amount}</b> ноксябаксов!", parse_mode="HTML")

@dp.message(F.text.lower().startswith(("п ", "передать ")))
async def process_transfer(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    if not message.reply_to_message or message.reply_to_message.from_user.is_bot:
        await message.reply("Ответь этой командой на сообщение человека, которому хочешь перевести деньги!", parse_mode="HTML")
        return

    text = message.text.strip().split()
    if len(text) != 2 or not text[1].isdigit():
        await message.reply("Укажи сумму перевода числом! Пример: <code>п 500</code>", parse_mode="HTML")
        return

    amount = int(text[1])
    sender_id = message.from_user.id
    recipient_id = message.reply_to_message.from_user.id

    if sender_id == recipient_id:
        await message.reply("Нельзя переводить деньги самому себе!", parse_mode="HTML")
        return

    if amount <= 0:
        await message.reply("Сумма перевода должна быть больше 0!", parse_mode="HTML")
        return

    sender_balance, _ = await get_user(sender_id)

    if amount > sender_balance:
        await message.reply("У тебя недостаточно ноксябаксов для перевода!", parse_mode="HTML")
        return

    recipient_balance, _ = await get_user(recipient_id)

    await update_balance(sender_id, sender_balance - amount)
    await update_balance(recipient_id, recipient_balance + amount)

    rec_name = message.reply_to_message.from_user.first_name.replace("<", "&lt;").replace(">", "&gt;")
    rec_mention = f'<a href="tg://user?id={recipient_id}">{rec_name}</a>'

    await message.reply(f"💸 Ты успешно перевел <b>{amount}</b> ноксябаксов пользователю {rec_mention}!", parse_mode="HTML")

@dp.message(F.text.lower() == "го")
async def cmd_spin_go(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    chat_id = message.chat.id

    if chat_id not in active_games or not active_games[chat_id]["bets"]:
        await message.reply("На столе пока нет ставок! Сделайте ставку (например: <code>1000 к</code> или <code>1000 1-12</code>).", parse_mode="HTML")
        return

    game = active_games[chat_id]
    passed_time = time.time() - game["start_time"]

    if passed_time < 10:
        remaining = int(10 - passed_time)
        await message.reply(f"⏳ Подождите еще <b>{remaining}</b> сек., прежде чем крутить!", parse_mode="HTML")
        return

    bets = game["bets"]
    del active_games[chat_id]

    gif_url = "https://media.giphy.com/media/26uf2YTgF5upXUTm0/giphy.gif"
    msg = await message.answer_animation(animation=gif_url, caption="🎰 Колесо крутится...")

    await asyncio.sleep(3)

    try:
        await msg.delete()
    except Exception:
        pass

    number = random.randint(0, 36)
    if number == 0:
        color_str = "зеленое (ЗЕРО)"
    elif number in RED_NUMBERS:
        color_str = "красное"
    else:
        color_str = "черное"

    results_text = f"🎯 Выпало: <b>{number}</b> ({color_str})\n\n"

    for b in bets:
        user_id = b["user_id"]
        user_name = b["user_name"]
        
        # Кликабельная ссылка-тег с ИМЕНЕМ пользователя
        user_mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'
        
        bet = b["bet"]
        target = b["target"]

        multiplier = 0
        is_number_bet = target.isdigit() and 0 <= int(target) <= 36

        if is_number_bet and int(target) == number:
            multiplier = 36
        elif "-" in target:
            try:
                start_str, end_str = target.split("-")
                start, end = int(start_str), int(end_str)
                if start <= number <= end:
                    total_numbers = (end - start) + 1
                    multiplier = 36 / total_numbers
            except ValueError:
                pass
        elif number != 0:
            if target == "к" and number in RED_NUMBERS:
                multiplier = 2
            elif target == "ч" and number not in RED_NUMBERS:
                multiplier = 2
            elif target == "чет" and number % 2 == 0:
                multiplier = 2
            elif target == "нечет" and number % 2 != 0:
                multiplier = 2
            elif target == "1д" and 1 <= number <= 12:
                multiplier = 3
            elif target == "2д" and 13 <= number <= 24:
                multiplier = 3
            elif target == "3д" and 25 <= number <= 36:
                multiplier = 3

        balance, _ = await get_user(user_id)

        if multiplier > 0:
            win_amount = int(bet * multiplier)
            profit = win_amount - bet
            new_balance = balance + profit
            results_text += f"🎉 {user_mention}: Выигрыш <b>+{profit}</b> ноксябаксов! (x{round(multiplier, 2)})\n"
        else:
            new_balance = balance - bet
            results_text += f"❌ {user_mention}: Потеряно <b>-{bet}</b> ноксябаксов.\n"

        await update_balance(user_id, new_balance)

    await message.answer(results_text, parse_mode="HTML")

@dp.message()
async def process_roulette_bet(message: Message):
    text = message.text.strip().lower().split()
    
    if len(text) != 2 or not text[0].isdigit():
        return

    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    bet = int(text[0])
    target = text[1]
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Отображаем именно Name пользователя
    user_name = message.from_user.first_name.replace("<", "&lt;").replace(">", "&gt;")
    user_mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    balance, _ = await get_user(user_id)

    if bet <= 0:
        await message.reply("Ставка должна быть больше 0!", parse_mode="HTML")
        return

    if bet > balance:
        await message.reply("У тебя недостаточно ноксябаксов!", parse_mode="HTML")
        return

    valid_targets = {"к", "ч", "чет", "нечет", "1д", "2д", "3д"}
    is_number_bet = target.isdigit() and 0 <= int(target) <= 36

    is_range_bet = False
    if "-" in target:
        parts = target.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            start, end = int(parts[0]), int(parts[1])
            if 0 <= start < end <= 36:
                is_range_bet = True

    if not is_number_bet and not is_range_bet and target not in valid_targets:
        return

    current_time = time.time()
    if chat_id not in active_games:
        active_games[chat_id] = {
            "start_time": current_time,
            "bets": []
        }

    active_games[chat_id]["bets"].append({
        "user_id": user_id,
        "user_name": user_name,
        "bet": bet,
        "target": target
    })

    passed = current_time - active_games[chat_id]["start_time"]
    remaining = max(0, int(10 - passed))

    timer_info = f" Запустить колесо можно через <b>{remaining}</b> сек (команда <code>го</code>)." if remaining > 0 else " Напишите <code>го</code> для запуска!"

    await message.reply(
        f"✅ {user_mention}, ставка принята: <b>{bet}</b> ноксябаксов на <b>{target}</b>.\n"
        f"{timer_info}",
        parse_mode="HTML"
    )

async def main():
    await init_db()
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
