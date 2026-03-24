import asyncio
import os
from datetime import datetime, timedelta, timezone

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CopyTextButton,
)
from dotenv import load_dotenv

# ================= LOAD ENV =================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
VPN_KEY = os.getenv("VPN_KEY")

PAYMENT_CARD = os.getenv("PAYMENT_CARD", "")
PAYMENT_PHONE = os.getenv("PAYMENT_PHONE", "")
PAYMENT_BANK = os.getenv("PAYMENT_BANK", "Т-Банк")

SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/supp_vpntock1a")
REVIEWS_URL = os.getenv("REVIEWS_URL", "https://t.me/black_vpn_chat")
INSTRUCTION_URL = os.getenv("INSTRUCTION_URL", "https://t.me/blackvpn_connect")

KEY_LIFETIME_SECONDS = int(os.getenv("KEY_LIFETIME_SECONDS", "45"))
KEY_COOLDOWN_SECONDS = int(os.getenv("KEY_COOLDOWN_SECONDS", "60"))

BRAND_NAME = os.getenv("BRAND_NAME", "Black VPN")
SUBSCRIPTION_PRICE = os.getenv("SUBSCRIPTION_PRICE", "699")
SUBSCRIPTION_PERIOD = os.getenv("SUBSCRIPTION_PERIOD", "12 месяцев")

# ================= CHECK ENV =================

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")
if not ADMIN_ID:
    raise ValueError("ADMIN_ID не найден в .env")
if not VPN_KEY:
    raise ValueError("VPN_KEY не найден в .env")
if not PAYMENT_CARD:
    raise ValueError("PAYMENT_CARD не найден в .env")
if not PAYMENT_PHONE:
    raise ValueError("PAYMENT_PHONE не найден в .env")

# ================= INIT =================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================= TEXTS =================

def start_text(first_name: str | None) -> str:
    return (
        f"⚫️ <b>{BRAND_NAME}</b>\n\n"
        "Добро пожаловать.\n\n"
        "Премиальный VPN-доступ для тех, кто ценит:\n"
        "• стабильное соединение\n"
        "• высокую скорость\n"
        "• приватность без лишнего шума\n\n"
        "Выберите нужный раздел ниже 👇"
    )

BUY_TEXT = (
    "💎 <b>Премиум-доступ</b>\n\n"
    f"Стоимость: <b>{SUBSCRIPTION_PRICE} ₽</b>\n"
    f"Срок доступа: <b>{SUBSCRIPTION_PERIOD}</b>\n\n"
    "Выберите удобный способ оплаты:\n\n"
    "💳 <b>По номеру карты:</b>\n"
    "<code>{payment_card}</code>\n\n"
    "📱 <b>По СБП:</b>\n"
    "<code>{payment_phone}</code>\n"
    "Банк: <b>{payment_bank}</b>\n\n"
    "Нажмите кнопку ниже, чтобы скопировать нужные реквизиты.\n"
    "После перевода нажмите <b>«Я оплатил»</b> и отправьте чек."
)

WAITING_CHECK_TEXT = (
    "📸 <b>Отправьте чек одним сообщением</b>\n"
    "Как только чек поступит, мы передадим его на проверку."
)

CHECK_ACCEPTED_TEXT = (
    "✅ <b>Чек принят</b>\n"
    "Проверка оплаты уже запущена. Ожидайте подтверждения."
)

PAYMENT_REJECTED_TEXT = (
    "❌ <b>Оплата отклонена</b>\n"
    "Если это ошибка, свяжитесь с поддержкой и отправьте чек повторно."
)

HOME_TEXT = (
    "🏠 <b>Главное меню</b>\n\n"
    "Управление доступом доступно ниже 👇"
)

NO_SUB_TEXT = (
    "❌ <b>Доступ не активирован</b>\n\n"
    "Чтобы получить VPN-ключ, сначала купите подписку."
)

EXPIRED_SUB_TEXT = (
    "❌ <b>Срок доступа истёк</b>\n\n"
    "Продлите подписку, чтобы снова получить VPN-ключ."
)

# ================= DATABASE =================

async def init_db():
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            subscription_until TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS payment_waiting (
            user_id INTEGER PRIMARY KEY,
            created_at TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS key_access (
            user_id INTEGER PRIMARY KEY,
            last_sent_at TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS temp_messages (
            user_id INTEGER PRIMARY KEY,
            message_id INTEGER
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            user_id INTEGER PRIMARY KEY,
            photo_file_id TEXT,
            username TEXT,
            created_at TEXT
        )
        """)

        await db.commit()


async def ensure_user_exists(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute("""
        INSERT OR IGNORE INTO users (user_id, subscription_until)
        VALUES (?, NULL)
        """, (user_id,))
        await db.commit()


def now() -> datetime:
    return datetime.now(timezone.utc)

# ================= SUBSCRIPTIONS =================

async def set_subscription(user_id: int, days: int = 365):
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute(
            "SELECT subscription_until FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        base_date = now()

        if row and row[0]:
            try:
                current_until = datetime.fromisoformat(row[0])
                if current_until > base_date:
                    base_date = current_until
            except ValueError:
                pass

        new_expire = base_date + timedelta(days=days)

        await db.execute("""
        INSERT INTO users (user_id, subscription_until)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET subscription_until = excluded.subscription_until
        """, (user_id, new_expire.isoformat()))
        await db.commit()


async def get_subscription(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute(
            "SELECT subscription_until FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

# ================= PAYMENT WAITING =================

async def set_waiting(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute("""
        INSERT INTO payment_waiting (user_id, created_at)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET created_at = excluded.created_at
        """, (user_id, now().isoformat()))
        await db.commit()


async def is_waiting(user_id: int) -> bool:
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute(
            "SELECT 1 FROM payment_waiting WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def clear_waiting(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute(
            "DELETE FROM payment_waiting WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()

# ================= TEMP MESSAGE =================

async def save_temp_message(user_id: int, message_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute("""
        INSERT INTO temp_messages (user_id, message_id)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET message_id = excluded.message_id
        """, (user_id, message_id))
        await db.commit()


async def get_temp_message(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute(
            "SELECT message_id FROM temp_messages WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def clear_temp_message(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute(
            "DELETE FROM temp_messages WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()

# ================= RECEIPTS =================

async def save_receipt(user_id: int, photo_file_id: str, username: str):
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute("""
        INSERT INTO receipts (user_id, photo_file_id, username, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            photo_file_id = excluded.photo_file_id,
            username = excluded.username,
            created_at = excluded.created_at
        """, (user_id, photo_file_id, username, now().isoformat()))
        await db.commit()


async def get_receipt(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute("""
            SELECT photo_file_id, username, created_at
            FROM receipts
            WHERE user_id = ?
        """, (user_id,)) as cursor:
            return await cursor.fetchone()


async def clear_receipt(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute("DELETE FROM receipts WHERE user_id = ?", (user_id,))
        await db.commit()

# ================= KEY COOLDOWN =================

async def get_remaining_cooldown(user_id: int) -> int:
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute(
            "SELECT last_sent_at FROM key_access WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row or not row[0]:
        return 0

    try:
        last_sent_at = datetime.fromisoformat(row[0])
    except ValueError:
        return 0

    seconds_passed = int((now() - last_sent_at).total_seconds())
    remaining = KEY_COOLDOWN_SECONDS - seconds_passed
    return max(0, remaining)


async def update_key_sent_time(user_id: int):
    async with aiosqlite.connect("vpn.db") as db:
        await db.execute("""
        INSERT INTO key_access (user_id, last_sent_at)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_sent_at = excluded.last_sent_at
        """, (user_id, now().isoformat()))
        await db.commit()

# ================= STATISTICS =================

async def get_stats_text() -> str:
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]

        async with db.execute("""
            SELECT COUNT(*) FROM users
            WHERE subscription_until IS NOT NULL
            AND subscription_until > ?
        """, (now().isoformat(),)) as cursor:
            active_subs = (await cursor.fetchone())[0]

        async with db.execute("""
            SELECT COUNT(*) FROM users
            WHERE subscription_until IS NOT NULL
            AND subscription_until <= ?
        """, (now().isoformat(),)) as cursor:
            expired_subs = (await cursor.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM payment_waiting") as cursor:
            waiting_payments = (await cursor.fetchone())[0]

    return (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"✅ Активных подписок: <b>{active_subs}</b>\n"
        f"❌ Истёкших подписок: <b>{expired_subs}</b>\n"
        f"⏳ Ожидают проверку оплаты: <b>{waiting_payments}</b>"
    )


async def get_waiting_users():
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute("""
            SELECT user_id, created_at
            FROM payment_waiting
            ORDER BY created_at DESC
        """) as cursor:
            return await cursor.fetchall()


async def get_paid_users_text() -> str:
    async with aiosqlite.connect("vpn.db") as db:
        async with db.execute("""
            SELECT user_id, subscription_until
            FROM users
            WHERE subscription_until IS NOT NULL
            ORDER BY subscription_until DESC
        """) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return "✅ <b>Оплативших пользователей пока нет</b>"

    lines = ["✅ <b>Пользователи с подпиской</b>\n"]
    current_time = now()

    for user_id, subscription_until in rows:
        try:
            expire = datetime.fromisoformat(subscription_until)
            status = "активна" if expire > current_time else "истекла"
            expire_str = expire.strftime("%d.%m.%Y %H:%M")
        except ValueError:
            status = "ошибка даты"
            expire_str = subscription_until

        lines.append(
            f"🆔 <code>{user_id}</code>\n"
            f"📅 До: <b>{expire_str}</b>\n"
            f"📌 Статус: <b>{status}</b>\n"
        )

    return "\n".join(lines)

# ================= KEYBOARDS =================

def main_menu(user_id: int | None = None):
    keyboard = [
        [InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="🔑 Получить ключ", callback_data="key")],
        [InlineKeyboardButton(text="📅 Моя подписка", callback_data="sub")],
        [InlineKeyboardButton(text="📖 Как подключиться", url=INSTRUCTION_URL)],
        [InlineKeyboardButton(text="⭐️ Отзывы клиентов", url=REVIEWS_URL)],
        [InlineKeyboardButton(text="💬 Поддержка", url=SUPPORT_URL)],
    ]

    if user_id == ADMIN_ID:
        keyboard.insert(0, [InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin_panel")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⏳ Ожидают проверку", callback_data="waiting_list")],
        [InlineKeyboardButton(text="✅ Уже оплатили", callback_data="paid_list")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
    ])


def pay_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📋 Скопировать номер карты",
                copy_text=CopyTextButton(text=PAYMENT_CARD)
            )
        ],
        [
            InlineKeyboardButton(
                text="📱 Скопировать номер для СБП",
                copy_text=CopyTextButton(text=PAYMENT_PHONE)
            )
        ],
        [InlineKeyboardButton(text="💸 Я оплатил", callback_data="paid")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
    ])


def confirm_kb(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтвердить оплату",
                callback_data=f"confirm_{user_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отказать оплату",
                callback_data=f"reject_{user_id}"
            ),
        ]
    ])


def waiting_list_kb(rows):
    keyboard = []

    for user_id, created_at in rows:
        short_time = created_at[:16].replace("T", " ")
        keyboard.append([
            InlineKeyboardButton(
                text=f"🧾 {user_id} | {short_time}",
                callback_data=f"open_waiting_{user_id}"
            )
        ])

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================= HELPERS =================

async def send_temporary_key(chat_id: int, user_id: int):
    await update_key_sent_time(user_id)

    msg = await bot.send_message(
        chat_id,
        "✅ <b>Доступ активирован</b>\n\n"
        "🔑 <b>Ваш VPN-ключ:</b>\n"
        f"<code>{VPN_KEY}</code>\n\n"
        f"👤 Доступ выдан для ID: <code>{user_id}</code>\n"
        f"🕒 Сообщение будет удалено через <b>{KEY_LIFETIME_SECONDS}</b> сек.\n\n"
        "⚠️ Не передавайте ключ третьим лицам."
    )

    await asyncio.sleep(KEY_LIFETIME_SECONDS)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except Exception:
        pass


async def safe_delete_message(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


def format_subscription_text(expire: datetime) -> str:
    days_left = (expire - now()).days
    if days_left < 0:
        days_left = 0

    return (
        "📅 <b>Моя подписка</b>\n\n"
        f"Статус: <b>активна</b>\n"
        f"Действует до: <b>{expire.strftime('%d.%m.%Y')}</b>\n"
        f"Осталось дней: <b>{days_left}</b>"
    )

# ================= START =================

@dp.message(CommandStart())
async def start(message: Message):
    await ensure_user_exists(message.from_user.id)
    await message.answer(
        start_text(message.from_user.first_name),
        reply_markup=main_menu(message.from_user.id)
    )

# ================= BUY =================

@dp.callback_query(F.data == "buy")
async def buy(callback: CallbackQuery):
    formatted_card = " ".join(
        [PAYMENT_CARD[i:i + 4] for i in range(0, len(PAYMENT_CARD), 4)]
    )

    await callback.message.edit_text(
        BUY_TEXT.format(
            payment_card=formatted_card,
            payment_phone=PAYMENT_PHONE,
            payment_bank=PAYMENT_BANK
        ),
        reply_markup=pay_menu()
    )
    await callback.answer()


@dp.callback_query(F.data == "paid")
async def paid(callback: CallbackQuery):
    user_id = callback.from_user.id
    await ensure_user_exists(user_id)
    await set_waiting(user_id)

    old_temp_msg_id = await get_temp_message(user_id)
    if old_temp_msg_id:
        await safe_delete_message(user_id, old_temp_msg_id)
        await clear_temp_message(user_id)

    msg = await callback.message.answer(WAITING_CHECK_TEXT)
    await save_temp_message(user_id, msg.message_id)

    await callback.answer()

# ================= RECEIPT =================

@dp.message(F.photo)
async def receipt(message: Message):
    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        return

    if not await is_waiting(user_id):
        await message.answer("❌ <b>Сначала нажмите кнопку «Я оплатил»</b>")
        return

    temp_msg_id = await get_temp_message(user_id)
    if temp_msg_id:
        await safe_delete_message(user_id, temp_msg_id)
        await clear_temp_message(user_id)

    try:
        await message.delete()
    except Exception:
        pass

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "без username"
    )

    await save_receipt(user_id, message.photo[-1].file_id, username)

    try:
        await bot.send_photo(
            ADMIN_ID,
            photo=message.photo[-1].file_id,
            caption=(
                "💸 <b>Новый чек на подтверждение</b>\n\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"👤 Username: {username}"
            ),
            reply_markup=confirm_kb(user_id)
        )

        await message.answer(CHECK_ACCEPTED_TEXT)

    except TelegramBadRequest:
        await message.answer(
            "❌ <b>Не удалось передать чек администратору</b>\n"
            "Проверьте <code>ADMIN_ID</code> и убедитесь, что администратор написал боту <code>/start</code>."
        )

# ================= ADMIN PANEL =================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.message.edit_text(
        "🛠 <b>Админ-панель</b>\n\nВыберите раздел:",
        reply_markup=admin_panel_kb()
    )
    await callback.answer()

# ================= CONFIRM / REJECT =================

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split("_")[1])

    await set_subscription(user_id, days=365)
    await clear_waiting(user_id)
    await clear_receipt(user_id)

    asyncio.create_task(send_temporary_key(user_id, user_id))

    try:
        old_caption = callback.message.caption or ""
        if "✅ <b>Оплата подтверждена</b>" not in old_caption:
            new_caption = old_caption + "\n\n✅ <b>Оплата подтверждена</b>"
        else:
            new_caption = old_caption

        await callback.message.edit_caption(
            caption=new_caption,
            reply_markup=None
        )
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=None)

    await callback.answer("Готово")


@dp.callback_query(F.data.startswith("reject_"))
async def reject(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split("_")[1])

    await clear_waiting(user_id)
    await clear_receipt(user_id)

    try:
        await bot.send_message(user_id, PAYMENT_REJECTED_TEXT, reply_markup=main_menu(user_id))
    except Exception:
        pass

    try:
        old_caption = callback.message.caption or ""
        if "❌ <b>Оплата отклонена</b>" not in old_caption:
            new_caption = old_caption + "\n\n❌ <b>Оплата отклонена</b>"
        else:
            new_caption = old_caption

        await callback.message.edit_caption(
            caption=new_caption,
            reply_markup=None
        )
    except TelegramBadRequest:
        await callback.message.edit_reply_markup(reply_markup=None)

    await callback.answer("Оплата отклонена")

# ================= KEY =================

@dp.callback_query(F.data == "key")
async def key(callback: CallbackQuery):
    user_id = callback.from_user.id

    sub_value = await get_subscription(user_id)
    if not sub_value:
        await callback.answer("Нет подписки", show_alert=True)
        await callback.message.answer(NO_SUB_TEXT, reply_markup=main_menu(callback.from_user.id))
        return

    try:
        expire = datetime.fromisoformat(sub_value)
    except ValueError:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    if expire <= now():
        await callback.answer("Подписка истекла", show_alert=True)
        await callback.message.answer(EXPIRED_SUB_TEXT, reply_markup=main_menu(callback.from_user.id))
        return

    remaining = await get_remaining_cooldown(user_id)
    if remaining > 0:
        await callback.answer(
            f"⏳ Повторная выдача через {remaining} сек.",
            show_alert=True
        )
        return

    await callback.answer("Ключ отправлен")
    asyncio.create_task(send_temporary_key(user_id, user_id))

# ================= SUB =================

@dp.callback_query(F.data == "sub")
async def sub(callback: CallbackQuery):
    sub_value = await get_subscription(callback.from_user.id)

    if not sub_value:
        text = NO_SUB_TEXT
    else:
        try:
            expire = datetime.fromisoformat(sub_value)
            if expire > now():
                text = format_subscription_text(expire)
            else:
                text = EXPIRED_SUB_TEXT
        except ValueError:
            text = "❌ <b>Не удалось прочитать данные подписки</b>"

    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

# ================= STATS =================

@dp.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    text = await get_stats_text()
    await callback.message.edit_text(
        text,
        reply_markup=admin_panel_kb()
    )
    await callback.answer()


@dp.callback_query(F.data == "waiting_list")
async def waiting_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    rows = await get_waiting_users()

    if not rows:
        await callback.message.edit_text(
            "⏳ <b>Ожидающих проверку нет</b>",
            reply_markup=admin_panel_kb()
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "⏳ <b>Ожидают проверку оплаты</b>\n\nНажмите на пользователя, чтобы открыть чек:",
        reply_markup=waiting_list_kb(rows)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("open_waiting_"))
async def open_waiting(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split("_")[2])
    receipt = await get_receipt(user_id)

    if not receipt:
        await callback.answer("Чек не найден", show_alert=True)
        return

    photo_file_id, username, created_at = receipt

    await bot.send_photo(
        callback.from_user.id,
        photo=photo_file_id,
        caption=(
            "💸 <b>Чек на проверку</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Username: {username}\n"
            f"🕒 Создано: <b>{created_at[:16].replace('T', ' ')}</b>"
        ),
        reply_markup=confirm_kb(user_id)
    )

    await callback.answer("Чек открыт")


@dp.callback_query(F.data == "paid_list")
async def paid_list(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    text = await get_paid_users_text()
    await callback.message.edit_text(
        text,
        reply_markup=admin_panel_kb()
    )
    await callback.answer()

# ================= HOME =================

@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery):
    await callback.message.edit_text(
        HOME_TEXT,
        reply_markup=main_menu(callback.from_user.id)
    )
    await callback.answer()

# ================= RUN =================

async def main():
    await init_db()
    print("✅ Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
