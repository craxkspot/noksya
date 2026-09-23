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
user_active_buffs = {}  # Персональное хранилище активных баффов: {user_id: tier}
db_pool: asyncpg.Pool = None

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Каталог компаньонок
PROSTITUTES_CATALOG = [
    {"id": 1, "name": "Мила (Улица)", "price": 3000, "tier": 1},
    {"id": 2, "name": "Кристина (Клуб)", "price": 15000, "tier": 2},
    {"id": 3, "name": "Элитная модель Сабина", "price": 75000, "tier": 3},
    {"id": 4, "name": "Премиум-дива Изабелла", "price": 250000, "tier": 4},
    {"id": 5, "name": "VIP-легенда казино (Абсолют)", "price": 500000, "tier": 5},
    {"id": 6, "name": "Ультра-фембой Артур / Артурия", "price": 1000000, "tier": 6},
]

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
            uname = username.lower() if username else None
            await db.execute(
                "INSERT INTO users (user_id, username, balance, last_bonus) VALUES ($1, $2, 2000, 0)", 
                user_id, uname
            )
            return 2000, 0
        
        if username:
            await db.execute("UPDATE users SET username = $1 WHERE user_id = $2", username.lower(), user_id)
            
        return row["balance"], row["last_bonus"]

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
            [InlineKeyboardButton(text="📜 Команды", callback_data="show_commands")],
            [InlineKeyboardButton(text="💃 Каталог шлюх", callback_data="show_prostitutes")]
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
        "📌 <b>Команды бота (нужна подписка на @craxkspot и @noksyaa):</b>\n"
        "• <code>баланс</code> или <code>б</code> — узнать свой баланс\n"
        "• <code>бонус</code> — забрать ежедневный бонус (5000 ноксябаксов)\n"
        "• <code>п @username &lt;сумма&gt;</code> или ответом — перевести деньги\n"
        "• <code>отмена</code> — отменить свои несыгравшие ставки\n"
        "• <code>го</code> — запустить рулетку после ставок (доступно через 10 сек)\n"
        "• <code>шлюхи</code> — открыть каталог шлюх и компаньонок\n\n"
        "🎰 <b>Варианты ставок в рулетке:</b>\n"
        "• На цвет: <code>к</code> (красное), <code>ч</code> (черное)\n"
        "• На четность: <code>чет</code>, <code>нечет</code>\n"
        "• На дюжину: <code>1д</code>, <code>2д</code>, <code>3д</code>\n"
        "• На число: от <code>0</code> до <code>36</code> (умножение x36)\n"
        "• На <b>диапазон</b>: <code>1-12</code>, <code>5-20</code> и т.д."
    )
    await callback.message.answer(commands_text, parse_mode="HTML")
    await callback.answer()

@dp.message(F.text.lower().in_({"шлюхи", "шлюха", "эскорт", "каталог"}))
async def cmd_prostitutes_catalog(message: Message):
    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    keyboard_buttons = []
    for p in PROSTITUTES_CATALOG:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{p['name']} — {p['price']} 💰", 
                callback_data=f"buy_prostitute_{p['id']}"
            )
        ])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.reply(
        "🔞 <b>Каталог ночных девок и компаньонок:</b>\n"
        "Выбери шлюху на вечер. Каждая покупка персонально активирует мощный бафф к шансам следующей рулетки!",
        reply_markup=markup,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("show_prostitutes"))
async def process_show_prostitutes_callback(callback: CallbackQuery):
    keyboard_buttons = []
    for p in PROSTITUTES_CATALOG:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{p['name']} — {p['price']} 💰", 
                callback_data=f"buy_prostitute_{p['id']}"
            )
        ])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_text(
        "🔞 <b>Каталог ночных девок и компаньонок:</b>\n"
        "Выбери шлюху на вечер. Каждая покупка персонально активирует мощный бафф к шансам следующей рулетки!",
        reply_markup=markup,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_prostitute_"))
async def process_buy_prostitute(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not await check_subscription(user_id):
        await callback.answer("Нужна подписка на каналы!", show_alert=True)
        return

    try:
        p_id = int(callback.data.split("_")[-1])
    except ValueError:
        return

    prostitute = next((p for p in PROSTITUTES_CATALOG if p["id"] == p_id), None)
    if not prostitute:
        await callback.answer("Персонаж не найден!", show_alert=True)
        return

    balance, _ = await get_user(user_id, callback.from_user.username)
    price = prostitute["price"]

    if balance < price:
        await callback.answer(f"❌ Недостаточно средств! Нужно {price} ноксябаксов.", show_alert=True)
        return

    new_balance = balance - price
    await update_balance(user_id, new_balance)

    tier = prostitute["tier"]
    name = prostitute["name"]

    user_active_buffs[user_id] = tier

    # Жесткие, смешные треш-сцены для дешевых, и красочный лютый разврат для дорогих
    if tier == 1:
        action_text = (
            f"💀 Ты подбираешь на трассе дешевую шлюху <b>{name}</b> за <b>{price}</b> ноксябаксов.\n\n"
            f"Закинул её в багажник «девятки», привёз на пустырь. Во время яростного соития на капоте она неожиданно так поперхнулась твоей спермой, закашлялась, пустила пузыри носом и откинула концы прямо посреди процесса! "
            f"Пришлось прикапывать труп под кустом, но карма зарядила тебя удачей. "
            f"<i>(🎲 Персональный бафф: Шанс выпадения твоих ставок в следующем спине повышен!)</i>"
        )
    elif tier == 2:
        action_text = (
            f"🚽 Ты снимаешь развратную шлюху <b>{name}</b> из придорожного клушника за <b>{price}</b> ноксябаксов.\n\n"
            f"Она так усердно отрабатывала в тесной кабинке сортира, что захлебнулась слюной, с размаху впечаталась лбом в бачок унитаза и потеряла сознание. Ты вытащил её за волосы в коридор клуба, перешагнул через тело и пошёл крутить рулетку. "
            f"<i>(🎲 Персональный бафф: Умеренный прирост удачи и вероятности выигрыша!)</i>"
        )
    elif tier == 3:
        action_text = (
            f"🔥 Элитная модель и дорогая содержанка <b>{name}</b> выкуплена за <b>{price}</b> ноксябаксов.\n\n"
            f"Шикарные апартаменты в центре города, запах дорогого парфюма, тусклый свет и страстный, глубокий минет под элитное шампанское плавно перетекающий в жаркие, сочные позы на огромной двуспальной кровати под её громкие стоны. "
            f"<i>(🎲 Персональный бафф: Серьезное увеличение шанса выпадения нужных секторов!)</i>"
        )
    elif tier == 4:
        action_text = (
            f"👑 Премиум-дива <b>{name}</b> заказана за <b>{price}</b> ноксябаксов.\n\n"
            f"Элитный эскорт экстра-класса: идеальные изгибы тела, горячая кожа и безумный, страстный секс в президентском люксе. Каждый толчок отдается эхом эйфории, а кульминацией становится обильное извержение на её роскошное лицо. "
            f"<i>(🎲 Персональный бафф: Мощный множитель на выпадение крупных коэффициентов!)</i>"
        )
    elif tier == 5:
        action_text = (
            f"💎 Легендарная VIP-легенда казино <b>{name}</b> твоя за <b>{price}</b> ноксябаксов.\n\n"
            f"Невероятная богиня страсти устраивает тебе дикую, первобытную оргию на столах с фишками. Безумный темп, влажные шлепки, горячие стоны на всё казино и абсолютное подчинение в каждом движении. "
            f"<i>(🎲 Персональный бафф: Огромный бонус к шансу выпадения точных чисел и зеро!)</i>"
        )
    else:
        action_text = (
            f"⚡️ МЕГА-ЛЕГЕНДАРНЫЙ ВЫБОР! Ультра-фембой <b>{name}</b> куплен за <b>1 000 000</b> ноксябаксов!\n\n"
            f"Изумительный сочный femboy в черном латексе, упругих чулках и с утонченным макияжем полностью отдается тебе. Ты жестко и страстно штурмуешь его со всеми прелестями бдсм-фантазий под сладкие вздохи и безумный драйв. "
            f"<b>(🔥 АКТИВИРОВАН МАКСИМАЛЬНЫЙ БАФФ: Шанс выпадения числа 0 и твоих ставок вырос до 95%!)</b>"
        )

    user_mention = f'<a href="tg://user?id={user_id}">{callback.from_user.first_name}</a>'
    
    await callback.message.edit_text(
        f"✅ {user_mention}, сделка оформлена!\n\n"
        f"{action_text}\n\n"
        f"💰 Остаток на балансе: <b>{new_balance}</b> ноксябаксов.",
        parse_mode="HTML"
    )
    await callback.answer("Успешно!")

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

    spinning_user_id = message.from_user.id
    active_tier = user_active_buffs.get(spinning_user_id, 0)

    if spinning_user_id in user_active_buffs:
        del user_active_buffs[spinning_user_id]

    gif_url = "https://media.giphy.com/media/26uf2YTgF5upXUTm0/giphy.gif"
    msg = await message.answer_animation(animation=gif_url, caption="🎰 Колесо крутится...")

    await asyncio.sleep(3)

    try:
        await msg.delete()
    except Exception:
        pass

    user_targeted_numbers = set()
    user_bets_for_spinning_user = [b for b in bets if b["user_id"] == spinning_user_id]

    for b in user_bets_for_spinning_user:
        t = b["target"]
        if t.isdigit() and 0 <= int(t) <= 36:
            user_targeted_numbers.add(int(t))
        elif "-" in t:
            try:
                s, e = map(int, t.split("-"))
                for i in range(s, e + 1):
                    user_targeted_numbers.add(i)
            except:
                pass
        elif t == "к":
            user_targeted_numbers.update(RED_NUMBERS)
        elif t == "ч":
            user_targeted_numbers.update(set(range(1, 37)) - RED_NUMBERS)
        elif t == "чет":
            user_targeted_numbers.update({i for i in range(1, 37) if i % 2 == 0})
        elif t == "нечет":
            user_targeted_numbers.update({i for i in range(1, 37) if i % 2 != 0})
        elif t == "1д":
            user_targeted_numbers.update(range(1, 13))
        elif t == "2д":
            user_targeted_numbers.update(range(13, 25))
        elif t == "3д":
            user_targeted_numbers.update(range(25, 37))

    forced_number = None
    if active_tier > 0 and user_bets_for_spinning_user and user_targeted_numbers:
        force_chances = {1: 0.20, 2: 0.35, 3: 0.50, 4: 0.65, 5: 0.80, 6: 0.95}
        chance = force_chances.get(active_tier, 0.40)

        if random.random() < chance:
            forced_number = random.choice(list(user_targeted_numbers))

    if forced_number is not None:
        number = forced_number
    else:
        numbers_pool = list(range(0, 37))
        weights = [1.0] * 37
        
        if active_tier > 0 and user_targeted_numbers:
            multiplier_boost = 1.0 + (active_tier * 0.5)
            weights[0] *= (2.0 if active_tier == 6 else 1.3)
            for num in user_targeted_numbers:
                weights[num] *= multiplier_boost

        number = random.choices(numbers_pool, weights=weights, k=1)[0]

    if number == 0:
        color_str = "зеленое (ЗЕРО)"
    elif number in RED_NUMBERS:
        color_str = "красное"
    else:
        color_str = "черное"

    buff_notification = ""
    if active_tier > 0:
        buff_names = {
            1: "Трассовый треш", 
            2: "Клубный отруб", 
            3: "Элитная страсть", 
            4: "Премиум-эскорт", 
            5: "VIP-оргия", 
            6: "Ультра-фембой бафф (95% победы!)"
        }
        buff_notification = f"🔞 <i>Сработал ваш персональный бафф компаньонки ({buff_names.get(active_tier, 'Бонус')})! Исход скорректирован в вашу пользу.</i>\n\n"

    results_text = f"{buff_notification}🎯 Выпало: <b>{number}</b> ({color_str})\n\n"

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

    await message.answer(results_text, parse_mode="HTML")

@dp.message()
async def process_roulette_bet(message: Message):
    if not message.text:
        return

    text_lines = message.text.strip().split("\n")
    parsed_bets = []
    total_bet_sum = 0

    valid_targets = {"к", "ч", "чет", "нечет", "1д", "2д", "3д"}

    for line in text_lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        parts = line_clean.split()
        if len(parts) != 2 or not parts[0].isdigit():
            continue

        bet = int(parts[0])
        target = parts[1].lower()

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

    if not parsed_bets:
        return

    if not await check_subscription(message.from_user.id):
        await send_sub_request(message)
        return

    user_id = message.from_user.id
    chat_id = message.chat.id

    user_name = message.from_user.first_name.replace("<", "&lt;").replace(">", "&gt;")
    user_mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    balance, _ = await get_user(user_id, message.from_user.username)

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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
