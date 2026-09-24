import asyncio
import random
import time
import os
from aiohttp import web

import asyncpg
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
active_bj_games = {}
db_pool: asyncpg.Pool = None

DATABASE_URL = os.environ.get("DATABASE_URL", "")

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
    global db_pool
    if not DATABASE_URL:
        print("CRITICAL: DATABASE_URL не найдена в окружении!")
        return

    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    db_pool = await asyncpg.create_pool(dsn=db_url)

    async with db_pool.acquire() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance BIGINT DEFAULT 2000,
                last_bonus BIGINT DEFAULT 0
            )
        """)

async def get_user(user_id: int, username: str = None):
    async with db_pool.acquire() as db:
        row = await db.fetchrow("SELECT balance, last_bonus FROM users WHERE user_id = $1", user_id)
        if row is None:
            uname = username.lower() if username else "unknown"
            await db.execute(
                "INSERT INTO users (user_id, username, balance, last_bonus) VALUES ($1, $2, 2000, 0) ON CONFLICT (user_id) DO NOTHING", 
                user_id, uname
            )
            return 2000, 0
        
        if username:
            await db.execute("UPDATE users SET username = $1 WHERE user_id = $2", username.lower(), user_id)
            
        balance = row["balance"] if row["balance"] is not None else 2000
        last_bonus = row["last_bonus"] if row["last_bonus"] is not None else 0
        return balance, last_bonus

async def get_user_by_username(username: str):
    username_clean = username.lstrip("@").lower()
    async with db_pool.acquire() as db:
        row = await db.fetchrow("SELECT user_id, balance FROM users WHERE LOWER(username) = $1", username_clean)
        if row:
            return row["user_id"], row["balance"]
        return None, None

async def update_balance(user_id: int, new_balance: int):
    async with db_pool.acquire() as db:
        await db.execute("UPDATE users SET balance = $1 WHERE user_id = $2", new_balance, user_id)

async def update_bonus_time(user_id: int, current_time: int):
    async with db_pool.acquire() as db:
        await db.execute("UPDATE users SET last_bonus = $1 WHERE user_id = $2", current_time, user_id)

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
        
    await get_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "🎰 <b>Добро пожаловать в казино Нокси</b>",
        reply_markup=get_commands_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "show_commands")
async def process_show_commands(callback: CallbackQuery):
    commands_text = (
        "📌 <b>Команды бота:</b>\n"
        "• <code>баланс</code> или <code>б</code> — узнать свой баланс\n"
        "• <code>бонус</code> — забрать ежедневный бонус\n"
        "• <code>п @username &lt;сумма&gt;</code> — перевести деньги\n"
        "• <code>отмена</code> — отменить свои несыгравшие ставки\n"
        "• <code>го</code> — запустить рулетку\n"
        "• <code>бж &lt;сумма&gt;</code> (или <code>блекджек</code>) — сыграть в блекджек\n\n"
        "🎰 <b>Варианты ставок в рулетке:</b>\n"
        "• На цвет: <code>к</code> (красное), <code>ч</code> (черное)\n"
        "• На четность: <code>чет</code>, <code>нечет</code>\n"
        "• На дюжину: <code>1д</code>, <code>2д</code>, <code>3д</code>\n"
        "• На число: от <code>0</code> до <code>36</code>\n"
        "• На диапазон: <code>1-12</code>, <code>5-20</code>\n"
        "• Ставка всем балансом: <code>вабанк к</code> (или <code>ва-банк</code>)"
    )
    await callback.message.edit_text(commands_text, parse_mode="HTML")
    await callback.answer()

@dp.message(F.text.lower().in_({"баланс", "б", "/balance"}))
async def cmd_balance(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    balance, _ = await get_user(message.from_user.id, message.from_user.username)
    name = message.from_user.first_name.replace("<", "&lt;").replace(">", "&gt;")
    mention = f'<a href="tg://user?id={message.from_user.id}">{name}</a>'

    await message.reply(f"👤 {mention}, твой баланс: <b>{balance}</b> ноксябаксов.", parse_mode="HTML")

@dp.message(F.text.lower().in_({"бонус", "/bonus"}))
async def cmd_bonus(message: Message):
    user_id = message.from_user.id

    if not await check_subscription(user_id):
        await send_sub_request(message)
        return

    balance, last_bonus = await get_user(user_id, message.from_user.username)
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
        balance, _ = await get_user(user_id, message.from_user.username)
        new_balance = balance + amount
        await update_balance(user_id, new_balance)
        await message.reply(f"👑 <b>Админ-выдача:</b> Выдано <b>+{amount}</b> ноксябаксов!", parse_mode="HTML")

@dp.message(F.text.lower().startswith(("забрать ", "списать ")))
async def cmd_admin_take(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.strip().split()
    target_user_id = None
    amount = 0
    target_name = "Пользователь"

    if message.reply_to_message and not message.reply_to_message.from_user.is_bot:
        if len(parts) == 2 and parts[1].isdigit():
            target_user_id = message.reply_to_message.from_user.id
            amount = int(parts[1])
            target_name = message.reply_to_message.from_user.first_name
    elif len(parts) == 3 and parts[2].isdigit():
        target_username = parts[1]
        amount = int(parts[2])
        target_user_id, _ = await get_user_by_username(target_username)
        if not target_user_id:
            await message.reply("❌ Пользователь не найден!", parse_mode="HTML")
            return
        target_name = target_username

    if not target_user_id or amount <= 0:
        await message.reply("❌ Ошибка формата списания.", parse_mode="HTML")
        return

    balance, _ = await get_user(target_user_id)
    new_balance = max(0, balance - amount)
    await update_balance(target_user_id, new_balance)
    
    clean_name = target_name.replace("<", "&lt;").replace(">", "&gt;")
    target_mention = f'<a href="tg://user?id={target_user_id}">{clean_name}</a>'
    await message.reply(f"👑 <b>Админ-списание:</b> У {target_mention} списано <b>{amount}</b> ноксябаксов.", parse_mode="HTML")

@dp.message(F.text.lower().startswith(("п ", "передать ")))
async def process_transfer(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    parts = message.text.strip().split()
    sender_id = message.from_user.id
    recipient_id = None
    recipient_name = None
    amount = 0

    if message.reply_to_message and not message.reply_to_message.from_user.is_bot:
        if len(parts) == 2 and parts[1].isdigit():
            recipient_id = message.reply_to_message.from_user.id
            recipient_name = message.reply_to_message.from_user.first_name
            amount = int(parts[1])
    elif len(parts) == 3 and parts[2].isdigit():
        recipient_username_input = parts[1]
        amount = int(parts[2])
        recipient_id, _ = await get_user_by_username(recipient_username_input)

        if not recipient_id:
            await message.reply("❌ Пользователь не найден!", parse_mode="HTML")
            return
        
        async with db_pool.acquire() as db:
            row = await db.fetchrow("SELECT username FROM users WHERE user_id = $1", recipient_id)
            recipient_name = row["username"] if row and row["username"] else recipient_username_input

    if not recipient_id or amount <= 0:
        await message.reply("❌ Неверный формат перевода!", parse_mode="HTML")
        return

    if sender_id == recipient_id:
        await message.reply("Нельзя переводить деньги самому себе!", parse_mode="HTML")
        return

    sender_balance, _ = await get_user(sender_id, message.from_user.username)

    if amount > sender_balance:
        await message.reply("У тебя недостаточно ноксябаксов!", parse_mode="HTML")
        return

    recipient_balance, _ = await get_user(recipient_id)

    await update_balance(sender_id, sender_balance - amount)
    await update_balance(recipient_id, recipient_balance + amount)

    clean_rec_name = str(recipient_name or "Пользователь").replace("<", "&lt;").replace(">", "&gt;")
    rec_mention = f'<a href="tg://user?id={recipient_id}">{clean_rec_name}</a>'
    
    await message.reply(f"💸 Ты успешно перевел <b>{amount}</b> ноксябаксов {rec_mention}!", parse_mode="HTML")

# ================= БЛЕКДЖЕК =================

def get_deck():
    suits = ['♠', '♥', '♦', '♣']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    deck = [(r, s) for s in suits for r in ranks]
    random.shuffle(deck)
    return deck

def calc_hand(hand):
    value = 0
    aces = 0
    for rank, _ in hand:
        if rank in ['J', 'Q', 'K']:
            value += 10
        elif rank == 'A':
            aces += 1
            value += 11
        else:
            value += int(rank)
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def hand_str(hand):
    return " ".join([f"{r}{s}" for r, s in hand])

@dp.message(F.text.lower().startswith(("бж ", "блекджек ")))
async def cmd_blackjack(message: Message):
    user_id = message.from_user.id

    if not await check_subscription(user_id):
        await send_sub_request(message)
        return

    if user_id in active_bj_games:
        await message.reply("У тебя уже есть активная игра в блекджек! Закончи её.", parse_mode="HTML")
        return

    text = message.text.lower().replace("ва банк", "вабанк").replace("ва-банк", "вабанк").split()
    if len(text) != 2:
        return

    balance, _ = await get_user(user_id, message.from_user.username)
    
    if text[1] == "вабанк":
        bet = balance
    elif text[1].isdigit():
        bet = int(text[1])
    else:
        return

    if bet <= 0:
        return
    if bet > balance:
        await message.reply(f"❌ Недостаточно средств! Баланс: <b>{balance}</b>.", parse_mode="HTML")
        return

    await update_balance(user_id, balance - bet)

    deck = get_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    player_val = calc_hand(player_hand)
    
    if player_val == 21:
        dealer_val = calc_hand(dealer_hand)
        if dealer_val == 21:
            await update_balance(user_id, balance) # Ничья, возврат
            result_txt = (
                f"🃏 <b>Блекджек</b> | Ставка: {bet}\n\n"
                f"Твои карты: {hand_str(player_hand)} (21)\n"
                f"Карты дилера: {hand_str(dealer_hand)} (21)\n\n"
                f"🤝 <b>Ничья!</b> У обоих Блекджек. Возврат ставки."
            )
        else:
            win_amount = int(bet * 2.5) # Блекджек платит 3:2
            await update_balance(user_id, (balance - bet) + win_amount)
            result_txt = (
                f"🃏 <b>Блекджек</b> | Ставка: {bet}\n\n"
                f"Твои карты: {hand_str(player_hand)} (21)\n"
                f"Карты дилера: {hand_str(dealer_hand)} ({dealer_val})\n\n"
                f"🎉 <b>БЛЕКДЖЕК!</b> Выигрыш: <b>+{win_amount - bet}</b>"
            )
        await message.reply(result_txt, parse_mode="HTML")
        return

    active_bj_games[user_id] = {
        "bet": bet,
        "deck": deck,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Ещё", callback_data="bj_hit"),
         InlineKeyboardButton(text="🛑 Хватит", callback_data="bj_stand")]
    ])

    await message.reply(
        f"🃏 <b>Блекджек</b> | Ставка: {bet}\n\n"
        f"Твои карты: {hand_str(player_hand)} ({player_val})\n"
        f"Карты дилера: {dealer_hand[0][0]}{dealer_hand[0][1]} 🎴 (?)\n\n"
        f"Твой ход:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "bj_hit")
async def process_bj_hit(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_bj_games:
        await callback.answer("Игра не найдена или уже завершена.", show_alert=True)
        return

    game = active_bj_games[user_id]
    game["player_hand"].append(game["deck"].pop())
    
    player_val = calc_hand(game["player_hand"])
    
    if player_val > 21:
        del active_bj_games[user_id]
        await callback.message.edit_text(
            f"🃏 <b>Блекджек</b> | Ставка: {game['bet']}\n\n"
            f"Твои карты: {hand_str(game['player_hand'])} ({player_val})\n"
            f"Карты дилера: {game['dealer_hand'][0][0]}{game['dealer_hand'][0][1]} 🎴\n\n"
            f"💥 <b>Перебор!</b> Ты проиграл <b>{game['bet']}</b> ноксябаксов.",
            parse_mode="HTML"
        )
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🃏 Ещё", callback_data="bj_hit"),
             InlineKeyboardButton(text="🛑 Хватит", callback_data="bj_stand")]
        ])
        await callback.message.edit_text(
            f"🃏 <b>Блекджек</b> | Ставка: {game['bet']}\n\n"
            f"Твои карты: {hand_str(game['player_hand'])} ({player_val})\n"
            f"Карты дилера: {game['dealer_hand'][0][0]}{game['dealer_hand'][0][1]} 🎴 (?)\n\n"
            f"Твой ход:",
            reply_markup=kb,
            parse_mode="HTML"
        )
    await callback.answer()

@dp.callback_query(F.data == "bj_stand")
async def process_bj_stand(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in active_bj_games:
        await callback.answer("Игра не найдена или уже завершена.", show_alert=True)
        return

    game = active_bj_games[user_id]
    del active_bj_games[user_id]

    player_val = calc_hand(game["player_hand"])
    dealer_hand = game["dealer_hand"]
    deck = game["deck"]
    bet = game["bet"]

    dealer_val = calc_hand(dealer_hand)
    while dealer_val < 17:
        dealer_hand.append(deck.pop())
        dealer_val = calc_hand(dealer_hand)

    balance, _ = await get_user(user_id)
    
    if dealer_val > 21:
        win_amount = bet * 2
        await update_balance(user_id, balance + win_amount)
        result_msg = f"🎉 <b>Дилер перебрал!</b> Ты выиграл <b>+{bet}</b>."
    elif dealer_val > player_val:
        result_msg = f"💸 <b>Дилер выиграл.</b> Ты проиграл <b>{bet}</b>."
    elif player_val > dealer_val:
        win_amount = bet * 2
        await update_balance(user_id, balance + win_amount)
        result_msg = f"🎉 <b>Ты выиграл!</b> Плюс <b>+{bet}</b>."
    else:
        await update_balance(user_id, balance + bet)
        result_msg = f"🤝 <b>Ничья.</b> Ставка <b>{bet}</b> возвращена."

    await callback.message.edit_text(
        f"🃏 <b>Блекджек</b> | Ставка: {bet}\n\n"
        f"Твои карты: {hand_str(game['player_hand'])} ({player_val})\n"
        f"Карты дилера: {hand_str(dealer_hand)} ({dealer_val})\n\n"
        f"{result_msg}",
        parse_mode="HTML"
    )
    await callback.answer()

# ================= РУЛЕТКА =================

@dp.message(F.text.lower().in_({"отмена", "отменить"}))
async def cmd_cancel_bets(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_id not in active_games or not active_games[chat_id]["bets"]:
        await message.reply("На столе сейчас нет ставок для отмены!", parse_mode="HTML")
        return

    game = active_games[chat_id]
    user_bets = [b for b in game["bets"] if b["user_id"] == user_id]

    if not user_bets:
        await message.reply("У тебя нет активных ставок в этом раунде!", parse_mode="HTML")
        return

    refund_amount = sum(b["bet"] for b in user_bets)
    game["bets"] = [b for b in game["bets"] if b["user_id"] != user_id]

    balance, _ = await get_user(user_id, message.from_user.username)
    await update_balance(user_id, balance + refund_amount)

    name = message.from_user.first_name.replace("<", "&lt;").replace(">", "&gt;")
    mention = f'<a href="tg://user?id={user_id}">{name}</a>'

    await message.reply(f"🚫 {mention}, твои ставки отменены! На баланс возвращено <b>+{refund_amount}</b> ноксябаксов.", parse_mode="HTML")

@dp.message(F.text.lower() == "го")
async def cmd_spin_go(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    chat_id = message.chat.id

    if chat_id not in active_games or not active_games[chat_id]["bets"]:
        await message.reply("На столе пока нет ставок!", parse_mode="HTML")
        return

    game = active_games[chat_id]
    passed_time = time.time() - game["start_time"]

    if passed_time < 10:
        remaining = int(10 - passed_time)
        await message.reply(f"⏳ Подождите еще <b>{remaining}</b> сек. перед запуском!", parse_mode="HTML")
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

    user_bets_map = {}
    for b in bets:
        uid = b["user_id"]
        if uid not in user_bets_map:
            user_bets_map[uid] = {
                "name": b["user_name"],
                "bets": []
            }
        user_bets_map[uid]["bets"].append(b)

    for user_id, u_data in user_bets_map.items():
        user_name = u_data["name"]
        user_mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'
        
        results_text += f"👤 <b>{user_mention}</b>:\n"

        total_payout_to_add = 0

        for b in u_data["bets"]:
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
                except Exception:
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

            if multiplier > 0:
                payout = int(bet * multiplier)
                profit = payout - bet
                total_payout_to_add += payout
                results_text += f"  ▫️ Ставка <code>{bet}</code> на <code>{target}</code> — ✅ Выигрыш <b>+{profit}</b> (x{round(multiplier, 2)})\n"
            else:
                results_text += f"  ▫️ Ставка <code>{bet}</code> на <code>{target}</code> — ❌ Проигрыш <b>-{bet}</b>\n"

        total_user_bets = sum(b["bet"] for b in u_data["bets"])
        net_round_change = total_payout_to_add - total_user_bets

        balance, _ = await get_user(user_id)
        final_user_balance = max(0, balance + total_payout_to_add)
        await update_balance(user_id, final_user_balance)
        
        sign_str = "+" if net_round_change > 0 else ""
        results_text += f"  💰 Итог раунда: <b>{sign_str}{net_round_change}</b> ноксябаксов\n\n"

    await message.bot.send_message(chat_id=chat_id, text=results_text, parse_mode="HTML")

@dp.message()
async def process_roulette_bet(message: Message):
    if not message.text:
        return

    text_to_parse = message.text.lower().replace("ва банк", "вабанк").replace("ва-банк", "вабанк")
    text_lines = text_to_parse.strip().split("\n")
    
    user_id = message.from_user.id
    chat_id = message.chat.id

    balance, _ = await get_user(user_id, message.from_user.username)
    available_balance = balance

    parsed_bets = []
    total_bet_sum = 0

    valid_targets = {"к", "ч", "чет", "нечет", "1д", "2д", "3д"}

    for line in text_lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        parts = line_clean.split()
        if len(parts) != 2:
            continue
            
        target = parts[1].lower()

        if parts[0] == "вабанк":
            bet = available_balance
        elif parts[0].isdigit():
            bet = int(parts[0])
        else:
            continue

        if bet <= 0:
            continue

        is_number_bet = target.isdigit() and 0 <= int(target) <= 36
        is_range_bet = False
        if "-" in target:
            range_parts = target.split("-")
            if len(range_parts) == 2 and range_parts[0].isdigit() and range_parts[1].isdigit():
                start, end = int(range_parts[0]), int(range_parts[1])
                if 0 <= start < end <= 36:
                    is_range_bet = True

        if is_number_bet or is_range_bet or target in valid_targets:
            parsed_bets.append({"bet": bet, "target": target})
            total_bet_sum += bet
            available_balance -= bet 

    if not parsed_bets:
        return

    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    user_name = message.from_user.first_name.replace("<", "&lt;").replace(">", "&gt;")
    user_mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    if total_bet_sum > balance:
        await message.reply(f"❌ Недостаточно средств! Сумма ставок: <b>{total_bet_sum}</b>, баланс: <b>{balance}</b>.", parse_mode="HTML")
        return

    await update_balance(user_id, balance - total_bet_sum)

    current_time = time.time()
    if chat_id not in active_games:
        active_games[chat_id] = {
            "start_time": current_time,
            "bets": []
        }

    for b in parsed_bets:
        active_games[chat_id]["bets"].append({
            "user_id": user_id,
            "user_name": user_name,
            "bet": b["bet"],
            "target": b["target"]
        })

    passed = current_time - active_games[chat_id]["start_time"]
    remaining = max(0, int(10 - passed))

    timer_info = f" Запустить колесо через <b>{remaining}</b> сек (команда <code>го</code>)." if remaining > 0 else " Напишите <code>го</code>!"

    bets_list_str = "\n".join([f"• <b>{b['bet']}</b> на <code>{b['target']}</code>" for b in parsed_bets])

    await message.reply(
        f"✅ {user_mention}, принято ставок: <b>{len(parsed_bets)}</b> (сумма: <b>{total_bet_sum}</b>):\n"
        f"{bets_list_str}\n"
        f"{timer_info}",
        parse_mode="HTML"
    )

async def main():
    await init_db()
    await start_web_server()
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
