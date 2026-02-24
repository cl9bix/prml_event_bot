import asyncio
import logging
import os
import time
from typing import Dict, Any, Optional

import requests
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

load_dotenv()

# ================== НАЛАШТУВАННЯ ===================

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
DJANGO_BASE_URL = os.getenv("DJANGO_BASE_URL", "http://localhost:8000")

API_CHECK_USER = f"{DJANGO_BASE_URL}/api/tg/check_user/"
API_CREATE_USER = f"{DJANGO_BASE_URL}/api/user/create/"
API_EVENTS_LIST = f"{DJANGO_BASE_URL}/api/events/"
API_EVENT_DETAILS = f"{DJANGO_BASE_URL}/api/events/get/"
API_CREATE_PAYMENT = f"{DJANGO_BASE_URL}/api/payments/create/"
API_CREATE_PAYMENT_LINK = f"{DJANGO_BASE_URL}/api/payments/create/payment/link"
API_CHECK_PAYMENT = f"{DJANGO_BASE_URL}/api/payments/check/"
API_CHECK_MONOBANK_PAYMENT = f"{DJANGO_BASE_URL}/api/payments/monobank/check"
API_GET_TICKET = f"{DJANGO_BASE_URL}/api/tickets/get/"
API_GET_PROMO_VALUE = f"{DJANGO_BASE_URL}/api/promocode/data/get/"
API_USER_TICKETS = f"{DJANGO_BASE_URL}/api/tickets/my/"
API_CONFIRM_MONO = f"{DJANGO_BASE_URL}/api/payments/confirm_monobank/"
API_PAYMENTS_CONFIG = f'{DJANGO_BASE_URL}/api/payments/config/'
API_PAYMENTS_HISTORY = f'{DJANGO_BASE_URL}/api/payments/history/'
API_EMAIL_CONFIRMATION = f'{DJANGO_BASE_URL}/api/email-confirmation/send/'
API_ADD_GOOGLE_SHEETS = f'{DJANGO_BASE_URL}/api/google-sheets/add/'

# Monobank
MONO_TOKEN = os.getenv("MONO_TOKEN", "")
MONO_CARD = os.getenv("MONOBANK_CARD", "0000 0000 0000 0000")
MONO_CLIENT_INFO_URL = "https://api.monobank.ua/personal/client-info"
MONO_STATEMENT_URL = "https://api.monobank.ua/personal/statement/{account}/{from_date}/{to_date}"
MONO_DAYS_LOOKBACK = int(os.getenv("MONOBANK_DAYS_LOOKBACK", "3"))

# Conversation states
CHOOSING_EVENT, REG_NAME, REG_AGE, REG_PHONE, REG_EMAIL, ASK_PROMO, ENTER_PROMO, WAITING_PAYMENT, WAITING_GROUP, EVENTS = range(
    10)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ================== HTTP HELPERS ===================

def api_get_json(method: str, url: str, **kwargs) -> Dict[str, Any]:
    try:
        resp = requests.request(method, url, timeout=10, **kwargs)

        # якщо бек повернув json навіть на 400 — віддай його в лог і в відповідь
        content_type = resp.headers.get("Content-Type", "")
        if resp.status_code >= 400:
            try:
                data = resp.json()
            except Exception:
                data = {"detail": resp.text[:2000]}
            logger.error("API %s %s -> %s | %s", method, url, resp.status_code, data)
            return {"ok": False, "status_code": resp.status_code, "error": data}

        return resp.json()

    except Exception as e:
        logger.exception("API error: %s", e)
        return {"ok": False, "error": str(e)}


def check_user(tg_user) -> Dict[str, Any]:
    payload = {
        "tg_id": tg_user.id,
        "username": tg_user.username,

    }
    return api_get_json("POST", API_CHECK_USER, json=payload)


def create_user(payload: dict) -> Dict[str, Any]:
    return api_get_json("POST", API_CREATE_USER, json=payload)


def get_events() -> Dict[str, Any]:
    return api_get_json("GET", API_EVENTS_LIST)


def get_event_details(event_id: int) -> Dict[str, Any]:
    return api_get_json("GET", API_EVENT_DETAILS, params={'event_id': event_id})


def create_payment(payload: Dict[str, Any]) -> Dict[str, Any]:
    return api_get_json("POST", API_CREATE_PAYMENT, json=payload)


def get_payment_config() -> Dict[str, Any]:
    return api_get_json("GET", API_PAYMENTS_CONFIG)


def get_transactions_history() -> Dict[str, Any]:
    return api_get_json("GET", API_PAYMENTS_HISTORY)


def check_payment_status(payment_id: int) -> Dict[str, Any]:
    return api_get_json(
        "GET",
        API_CHECK_PAYMENT,
        params={"payment_id": payment_id}
    )


def check_payment_monobank(payment_id: int) -> Dict[str, Any]:
    return api_get_json(
        "GET",
        API_CHECK_PAYMENT,
        params={"payment_id": payment_id, "refresh": 1}
    )


def send_email_confirmation(payment_id: int, ticket_url: str) -> Dict[str, Any]:
    return api_get_json(
        "POST",
        API_EMAIL_CONFIRMATION,
        json={"payment_id": payment_id, "ticket_url": ticket_url},
    )


async def CustomMessageSender(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb: list = None,
                              reply_text: bool = False, parse_mode: str = None):
    q = update.callback_query
    if reply_text:
        return await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=parse_mode)
    return await q.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=parse_mode)


def get_ticket(payment_id: int) -> Dict[str, Any]:
    return api_get_json("GET", API_GET_TICKET, params={"payment_id": payment_id})


def get_user_tickets(tg_id: int) -> Dict[str, Any]:
    return api_get_json("GET", API_USER_TICKETS, params={"tg_id": tg_id})


def confirm_monobank_payment(payment_id: int, mono_data: Dict[str, Any]) -> Dict[str, Any]:
    return api_get_json("POST", API_CONFIRM_MONO, json={"payment_id": payment_id, "mono": mono_data})


def get_promo(code: str, event_id: int) -> Dict[str, Any]:
    return api_get_json("GET", API_GET_PROMO_VALUE, params={'code': code, "event_id": event_id})


async def ask_promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Продовжити без промокоду", callback_data="promo_no")],
        [InlineKeyboardButton("Так є промокод 🎁", callback_data="promo_yes")],
    ])

    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text(
        "Перед оплатою — маленький бонус 🎉\n"
        "Можливо, у тебе є промокод на знижку?",
        reply_markup=kb
    )
    return ASK_PROMO


async def promo_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введи промокод (наприклад: <code>NY2026</code>)",
        parse_mode="HTML",
    )
    return ENTER_PROMO


async def promo_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["promo_code"] = None
    await query.edit_message_text("Окей 🙂 Йдемо до оплати…")
    return await start_payment_flow(update, context)


async def promo_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = (update.message.text or "").strip().upper()
    context.user_data["promo_code"] = code
    await update.message.reply_text(f"Прийняв промокод: <code>{code}</code> ✅\nПеревіряю…",
                                    parse_mode="HTML")
    return await start_payment_flow(update, context)


# ================== MONOBANK HELPERS ===================

def mono_get_accounts() -> Dict[str, Any]:
    if not MONO_TOKEN:
        raise RuntimeError("MONOBANK_TOKEN не заданий")
    headers = {"X-Token": MONO_TOKEN}
    resp = requests.get(MONO_CLIENT_INFO_URL, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ================== UX HELPERS ===================

async def typing(update: Update, seconds: float = 0.6):
    if update.effective_message:
        await update.effective_message.chat.send_action(ChatAction.TYPING)
    await asyncio.sleep(seconds)


def event_price_uah(event: dict) -> int:
    # з бекенда може прийти "199.00" як str — кастимо акуратно
    try:
        return int(float(event.get("price", 0)))
    except Exception:
        return 0


def nice_event_card(event: dict) -> str:
    logger.info("EVENT DATA=%s", event)
    start_at = event.get("start_at") or ""
    return (
        f"✨ <b>{event.get('title', 'Івент')}</b>\n"
        f"{event.get('welcome_text', '')}\n\n"
        f"{event.get('description', '')}\n\n"
        f"Вартість: <b>{event.get('price', '—')} грн</b>\n"
        f"{('🗓️ ' + start_at) if start_at else ''}"
    ).strip()


async def is_user_in_required_group(
        context: ContextTypes.DEFAULT_TYPE,
        group_id: int,
        user_id: int,
) -> bool:
    try:
        member = await context.bot.get_chat_member(group_id, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning("get_chat_member failed: group_id=%s user_id=%s err=%s", group_id, user_id, e)
        return False


def _extract_user_id(message_or_query, fallback_update: Update | None = None) -> int | None:
    if hasattr(message_or_query, "from_user") and message_or_query.from_user:
        return message_or_query.from_user.id
    if hasattr(message_or_query, "message") and message_or_query.message and message_or_query.message.from_user:
        return message_or_query.message.from_user.id
    if fallback_update and fallback_update.effective_user:
        return fallback_update.effective_user.id
    return None


# ================== BOT FLOW ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    context.user_data.clear()
    context.user_data['promo_checked'] = False

    await typing(update, 0.7)
    await update.message.reply_text("Привіт! Це ПРМЛ бот, який допоможе тобі стати учасником наших подій⚡️")

    await typing(update, 0.5)
    resp = check_user(user)
    if not resp.get("ok"):
        await update.message.reply_text("Упс, сервер відповів дивно 😅 Спробуй ще раз пізніше.")
        return ConversationHandler.END

    exists = bool(resp.get("exists", False))
    backend_user = resp.get("user") if exists else None

    context.user_data["backend_user"] = backend_user
    context.user_data["is_registered"] = exists

    if exists:
        await update.message.reply_text(f"Радий бачити знову, {backend_user.get('full_name', user.first_name)}! 🔥")
    else:
        await update.message.reply_text(
            "То що, давай реєструватися?"
        )

    return await show_events(update, context)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎉 Івенти", callback_data="menu_events")],
        [
            InlineKeyboardButton("👤 Мій профіль", callback_data="menu_profile"),
        ],
        [
            InlineKeyboardButton("ℹ️ Про нас", callback_data="menu_about"),
            InlineKeyboardButton("💎 Наші цінності", callback_data="menu_values"),
        ],
    ])

    text = "<b>Головне меню 👇</b>"

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        return

    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def menu_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tg_id = query.from_user.id
    user = update.effective_user
    user_q = check_user(user)
    logger.info('Getting user from db [menu_profile].\nUser_data=%s', user_q)
    if user_q['exists'] is not True:
        return await query.message.reply_text(
            "Ви не зареєструвались!"
        )
    kb = [
        [InlineKeyboardButton('Назад', callback_data='menu')]
    ]
    userName = user_q['user']['full_name']
    userAge = user_q['user']['age']
    userPhone = user_q['user']['phone']
    userEmail = user_q['user']['email']
    userUsername = user_q['user']['username']
    userTgId = user_q['user']['tg_id']
    text = f"""
Повне ім`я: [<b>{userName}</b>]
Вік: [<b>{userAge}</b>]
Номер телефону: [<b>{userPhone}</b>]
Email: [<b>{userEmail}</b>]
Username: [<b>{userUsername}</b>]
Telegram Id: [<b>{userTgId}</b>]"""

    return await CustomMessageSender(update, context, text, kb, parse_mode="HTML")


async def menu_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("Назад", callback_data='menu')]
    ]

    text = f"""
<b>Привіт!</b> 👋

Ми <b>ПРМЛ</b> - місце, де навчання формує, спільнота збудовує, а знання - практично застосовуються.

    <b>Підписуйся на нас:</b>

    🔸 <a href="https://www.instagram.com/prml.ua?igsh=MWJ0NTF3bDNzd3ExNw==">Instagram PRML</a>  
    🔸 <a href="https://youtube.com/@prml_ua?si=A9aSmPTFxEeEeM5s">YouTube PRML</a>  
    🔸 <a href="https://ubts.org.ua/programy/programa-rozvytu-molodyh-lideriv/">Сайт платформи (УБТС)</a>
    """
    await CustomMessageSender(update, context, text, kb, parse_mode="HTML")


async def menu_values(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("Назад", callback_data="menu")]
    ]
    text = f"""
Ми хочемо, щоб відбулася трансформація суспільства, але розуміємо, що це безпосередньо залежить від якості того, хто буде звершувати трасформацію.

Саме тому - це місце твого розвитку! 
Місце, де навчання збудовує.
Місце, де події несуть сенси.
Місце, де люди підтримують один одного.
Місце, де побувши раз - відчуваєш себе частинкою спільноти назавжди.

"""
    await query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(kb))


async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await typing(update, 0.4)
    resp = get_events()
    logger.info("Gettings get_events=%s", resp)
    if not resp.get("ok"):
        await update.effective_message.reply_text("Не можу отримати список подій 😢")
        return ConversationHandler.END

    events = resp.get("events", [])
    logger.info("Gettings all events=%s", resp.get("events"))

    if not events:
        await update.effective_message.reply_text("Зараз немає активних подій.")
        return ConversationHandler.END

    context.user_data["events"] = {e["id"]: e for e in events}

    keyboard = [[InlineKeyboardButton(f"{e['title']}", callback_data=f"event_{e['id']}")] for e in events]
    await update.effective_message.reply_text(
        "Обери подію 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSING_EVENT


async def event_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    _, event_id_str = query.data.split("_", 1)
    event_id = int(event_id_str)

    event = context.user_data.get("events", {}).get(event_id)
    if not event:
        await query.edit_message_text("Не знайшов таку подію 😕")
        return ConversationHandler.END

    context.user_data["chosen_event"] = event

    await query.edit_message_text(nice_event_card(event), parse_mode="HTML")

    await typing(update, 0.4)
    await query.message.reply_text("✅ Крок 1/3: Івент обрано.\n")
    await typing(update, 0.4)
    user = update.effective_user
    is_exsists = check_user(user)
    if is_exsists['exists'] is not True:
        # if not context.user_data.get("is_registered", False):
        context.user_data["reg_data"] = {}
        context.user_data['reg_data']['username'] = user.username
        context.user_data['reg_data']['tg_id'] = user.id
        await query.message.reply_text("Тепер — міні-реєстрація ")
        await typing(update, 0.5)
        await query.message.reply_text("Вкажи свої персональні дані:\nІм'я та призвіще")

        return REG_NAME
    await query.message.reply_text("Перейдемо одразу до оплати!")
    return await start_payment_flow(update, context)


# ===== Registration (in memory only) =====

async def reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_user_full_name: str = update.message.text.strip()
    if len(get_user_full_name.split(' ')) != 2:
        await update.message.reply_text("Введи будь-ласка своє повне ім'я! (приклад: Тарас Шевченко)")
        return REG_NAME

    context.user_data["reg_data"]["full_name"] = get_user_full_name
    await update.message.reply_text("Твій вік? (числом)")
    return REG_AGE


async def reg_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    if not txt.isdigit():
        await update.message.reply_text("Окей, але треба цифрами 🙂")
        return REG_AGE
    context.user_data["reg_data"]["age"] = int(txt)
    await update.message.reply_text("Номер телефону?")
    return REG_PHONE


async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_phone = update.message.text.strip()
    import re
    is_valid = lambda s: bool(re.fullmatch(r'(?:\+?38)?0\d{9}', re.sub(r'\D', '', s)))
    if not is_valid(get_phone):
        await update.message.reply_text("Введи будь ласка коректний номер телефону: (+380501234567)")
        return REG_PHONE

    context.user_data["reg_data"]["phone"] = get_phone
    await update.message.reply_text("Email?")
    return REG_EMAIL


async def reg_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    get_email = update.message.text.strip()
    import re
    is_email = lambda s: bool(re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', s))

    if not is_email(get_email):
        await update.message.reply_text("Введи будь ласка коректний email: (test@test.com)")
        return REG_EMAIL

    context.user_data["reg_data"]["email"] = get_email
    logger.info('Creating user [%s]. with tg_id=%s', context.user_data["reg_data"]["full_name"],
                update.effective_user.id

                )
    try:
        payload = context.user_data["reg_data"]
        logger.info("Payload data for user==%s", payload)
        is_created = create_user(payload)
        await update.message.reply_text("✅ Крок 1/3 готово. Далі — оплата 💳")
        return await start_payment_flow(update, context)
    except Exception as e:
        logger.exception('Error by creating user: %s', e)
        await update.message.reply_text("Помилка на сервері,натисніть /start")


# ===== Payment =====


async def start_payment_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event = context.user_data.get("chosen_event")
    tg_user = update.effective_user

    if not event:
        await update.effective_message.reply_text("Івент загубився 😅 Почни /start")
        return ConversationHandler.END

    if not context.user_data.get("promo_checked"):
        return await ask_promo(update, context)

    payload: Dict[str, Any] = {"event_id": event["id"]}
    price = event_price_uah(event)

    reg_data = context.user_data.get("reg_data") or {}

    # ✅ backend_resp треба отримати ДО використання
    backend_resp = check_user(tg_user)

    # ✅ user_id тільки якщо юзер реально існує в бекенді
    if backend_resp.get("ok") and backend_resp.get("exists") and backend_resp.get("user"):
        payload["user_id"] = backend_resp["user"]["id"]

    # базові дані (можеш лишити, бек їх кладе в extra якщо user_id нема)
    payload.update({
        "tg_id": tg_user.id,
        "username": tg_user.username,
        "full_name": tg_user.full_name,
        "reg_data": reg_data,
    })

    promo_code = context.user_data.get("promo_code")  # рядок або None
    promo_check = None
    final_amount = None

    # 1) promo check
    if promo_code:
        promo_check = get_promo(code=promo_code, event_id=payload["event_id"])
        if not promo_check.get("ok"):
            await update.effective_message.reply_text(
                "Не можу знайти промокод :(\n\nПродовжую без промокоду"
            )
            context.user_data.pop("promo_code", None)
            promo_code = None
        else:
            final_amount = promo_check.get("final_amount")
            payload["promo_code"] = promo_code
            payload["final_amount"] = final_amount
    context.user_data["promo_checked"] = True

    await typing(update, 0.5)

    resp = create_payment(payload)

    if not resp.get("ok"):
        await update.effective_message.reply_text("Не вдалось створити платіж 😢 Спробуй пізніше.")
        context.user_data.pop("promo_code", None)
        return ConversationHandler.END

    payment = resp.get("payment", {})
    if payment:
        context.user_data["payment"] = payment

    # ✅ FREE CASE
    if resp.get("is_free") is True or payment.get("provider") == "promo":
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text(
            "🎉 Промокод покрив 100% вартості!\n"
            "Оплата не потрібна ✅\n"
            "Перевіряю доступ до групи й видаю квиток… 🎫"
        )
        return await gate_group_then_ticket(msg, context)

    # NORMAL PAYMENT FLOW (далі твій код без змін)
    invoice = resp.get("invoice") or {}
    invoice_data = invoice.get("invoiceData") or {}
    payment_link = invoice_data.get("pageUrl")

    text = "<b>Крок 2 з 3: оплата.</b>\n\n"

    if promo_code and promo_check:
        text += (
            f"Промокод: <code>{promo_code}</code> 🎁\n"
            f"Вартість конференції: <s>{price} грн</s>  <b>{final_amount} гривень</b>\n"
        )
    else:
        new_price_value: str = event["new_price_value"]
        text += (
            f"Вартість конференції:\n"
            f"<b>{price} гривень - {event['original_price_until']}</b>\n"
            f"<b>{new_price_value.removesuffix('.00')} гривень - {event['new_price_from']}</b>"
        )

    text += (
        "\n\n"
        "Оплату можна здійснити комфортним способом онлайн, натиснувши кнопку нижче\n"
        "Після оплати натисни «✅ Я оплатив(ла)» і твій індивідуальний квиток з’явиться нижче."
        "\n\n"
        "<b>З важливого:</b>\n\n"
        "<i>  -  Відповідно до законодавства України та умов продажу квитків, вартість квитків не повертається...</i>"
    )

    kb_rows = []
    if payment_link:
        kb_rows.append([InlineKeyboardButton("Посилання на оплату 🔗", url=payment_link)])
    kb_rows.append([InlineKeyboardButton("✅ Я оплатив(ла)", callback_data="check_payment")])

    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(kb_rows), parse_mode="HTML")
    return WAITING_PAYMENT



async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    payment = context.user_data.get("payment")
    if not payment:
        await query.message.reply_text("Платіж не знайдено 😕 Почни /start")
        return ConversationHandler.END

    provider = payment.get("provider", "unknown")
    payment_id = int(payment.get("id"))

    if provider == "promo":
        context.user_data["promo_checked"] = True
        await query.answer("Оплата не потрібна ✅ Видаю квиток… 🎫")
        return await gate_group_then_ticket(query, context)

    await query.answer("Перевіряю оплату… ⏳")
    await asyncio.sleep(1)

    # ================= MONOBANK =================
    if provider == "monobank":
        resp = check_payment_monobank(payment_id=payment_id)

        if not resp.get("ok"):
            await query.answer(
                "Не можу перевірити оплату зараз 😅 Спробуй ще раз трохи пізніше.",
                show_alert=True,
            )
            return WAITING_PAYMENT

        payment_data = resp.get("payment") or {}
        status = payment_data.get("status")

        if status == "success":
            context.user_data["payment"] = payment_data

            backend_user = resp.get("user")
            if backend_user:
                context.user_data["backend_user"] = backend_user
                context.user_data["is_registered"] = True

            return await gate_group_then_ticket(query, context)

        if status == "pending":
            await query.message.reply_text("Поки не бачу підтвердження 🙏 Спробуй ще раз через хвильку.")
            return WAITING_PAYMENT

        await query.message.reply_text("Схоже, оплата не пройшла 😕")
        return ConversationHandler.END

    # ================= ІНШІ ПЛАТІЖКИ =================
    resp = check_payment_status(payment_id)

    if not resp.get("ok"):
        await query.message.reply_text("Не можу перевірити оплату зараз 😅 Спробуй ще раз трохи пізніше.")
        return WAITING_PAYMENT

    payment_data = resp.get("payment", {})
    status = payment_data.get("status")

    if status == "success":
        context.user_data["payment"] = payment_data

        backend_user = resp.get("user")
        if backend_user:
            context.user_data["backend_user"] = backend_user
            context.user_data["is_registered"] = True

        return await gate_group_then_ticket(query, context)

    if status == "pending":
        await query.message.reply_text("Поки що не бачу підтвердження 🙏 Спробуй ще раз через хвильку.")
        return WAITING_PAYMENT

    await query.message.reply_text("Схоже, оплата не пройшла 😕")
    context.user_data.pop("promo_code", None)
    return ConversationHandler.END


async def check_payment_backend(query, context: ContextTypes.DEFAULT_TYPE) -> Optional[bool]:
    """
    True  -> платіж підтверджено (payment.status = success)
    False -> знайдено, але проблема (сума / сервер)
    None  -> ще не знайдено (дозволяємо retry)
    """
    user = query.from_user
    payment = context.user_data.get("payment")
    event = context.user_data.get("chosen_event")

    if not payment or not event:
        await query.edit_message_text("Дані платежу загубились 😕")
        return False

    amount_uah = event_price_uah(event)

    try:
        acc = get_payment_config()
        tx = get(
            acc,
            user_id=user.id,
            course_amount=amount_uah
        )
    except Exception as e:
        logger.exception("Monobank error: %s", e)
        await query.edit_message_text("Помилка перевірки Monobank 😕")
        return False

    if tx is None:
        await query.edit_message_text(
            "Поки не бачу оплату 😅\n\n"
            "Коментар має бути:\n"
            f"<code>Оплата курсу id:{user.id}</code>",
            parse_mode="HTML"
        )
        return None

    mono_data = {
        "time": tx["date"],
        "amount": tx["amount"],
        "user_tg_id": user.id,
    }

    resp = confirm_monobank_payment(payment["id"], mono_data)
    if not resp.get("ok"):
        await query.edit_message_text("Оплату бачу, але сервер не підтвердив 😕")
        return False

    context.user_data["payment"] = resp["payment"]
    context.user_data["backend_user"] = resp.get("user")
    context.user_data["is_registered"] = True

    await query.edit_message_text("Оплата підтверджена ✅")
    return True


# ===== Group gate -> Ticket =====

async def gate_group_then_ticket(message_or_query, context: ContextTypes.DEFAULT_TYPE) -> int:
    event = context.user_data.get("chosen_event")
    if not event:
        if hasattr(message_or_query, "edit_message_text"):
            await message_or_query.edit_message_text("Івент загубився 😕 Почни з /start")
        else:
            await message_or_query.reply_text("Івент загубився 😕 Почни з /start")
        return ConversationHandler.END

    required_group_id = event.get("required_group_id")
    invite_link = event.get("required_group_invite_link")

    logger.info(
        "[gate_group_then_ticket] required_group_id=%s invite_link=%s",
        required_group_id,
        invite_link,
    )

    if not required_group_id:
        return await send_ticket(message_or_query, context)

    user_id = _extract_user_id(message_or_query)
    if not user_id:
        if hasattr(message_or_query, "edit_message_text"):
            await message_or_query.edit_message_text("Не зміг визначити твій user_id 😕 Спробуй /start")
        else:
            await message_or_query.reply_text("Не зміг визначити твій user_id 😕 Спробуй /start")
        return ConversationHandler.END

    in_group = await is_user_in_required_group(context, int(required_group_id), int(user_id))
    if in_group:
        msg = "✅ Крок 3/3: Доступ підтверджено. Видаю квиток… 🎫"
        if hasattr(message_or_query, "edit_message_text"):
            await asyncio.sleep(0.5)
            await message_or_query.edit_message_text(msg)
        else:
            await message_or_query.reply_text(msg)

        await asyncio.sleep(0.4)
        return await send_ticket(message_or_query, context)

    if not invite_link:
        text = (
            "✅ Оплата є!\n\n"
            "🔒 Для видачі квитка треба бути в групі події, але лінк зараз не налаштований.\n"
            "Напиши адміну 🙏"
        )
        if hasattr(message_or_query, "edit_message_text"):
            await message_or_query.edit_message_text(text)
        else:
            await message_or_query.reply_text(text)
        return WAITING_GROUP

    text = (
        "✅ Оплата є!\n\n"
        "🔒 Щоб отримати квиток, потрібно бути в групі події.\n"
        f"Ось лінк: {invite_link}\n\n"
        "Після вступу натисни кнопку 👇"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Я вже в групі", callback_data="check_group")]
    ])

    if hasattr(message_or_query, "edit_message_text"):
        await message_or_query.edit_message_text(text, reply_markup=kb)
    else:
        await message_or_query.reply_text(text, reply_markup=kb)

    return WAITING_GROUP


async def check_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    event = context.user_data.get("chosen_event")
    if not event:
        await query.edit_message_text("Івент не знайдено 😕 Почни /start")
        return ConversationHandler.END

    required_group_id = event.get("required_group_id")
    if not required_group_id:
        return await send_ticket(query, context)

    ok = await is_user_in_required_group(context, int(required_group_id), int(query.from_user.id))
    if not ok:
        await query.message.reply_text(
            "Ще не бачу тебе в групі 😅\n"
            "Зайди за лінком і спробуй ще раз."
        )
        return WAITING_GROUP

    await query.edit_message_text("Тепер бачу ✅ Видаю квиток… 🎫")
    await asyncio.sleep(0.4)
    return await send_ticket(query, context)



async def send_ticket(message_or_query, context: ContextTypes.DEFAULT_TYPE) -> int:
    payment = context.user_data.get("payment")

    if not payment or not payment.get("id"):
        if hasattr(message_or_query, "edit_message_text"):
            await message_or_query.edit_message_text("Платіж не знайдено 😕")
        else:
            await message_or_query.reply_text("Платіж не знайдено 😕")
        return ConversationHandler.END

    resp = get_ticket(int(payment["id"]))
    if not resp.get("ok"):
        if hasattr(message_or_query, "edit_message_text"):
            await message_or_query.edit_message_text(
                "Не можу отримати квиток зараз 😔 Спробуй трохи пізніше."
            )
        else:
            await message_or_query.reply_text(
                "Не можу отримати квиток зараз 😔 Спробуй трохи пізніше."
            )
        return ConversationHandler.END

    ticket = resp.get("ticket", {})
    image_url = ticket.get("image_url")

    if not image_url:
        logger.warning("send_ticket: image_url missing | payment_id=%s", payment["id"])
        return ConversationHandler.END

    caption = (
        "🎫 Ось твій квиток!\n"
        "Збережи його — і побачимось на події 🔥"
    )

    try:
        # ==========================
        # 1️⃣ Надсилаємо квиток у Telegram
        # ==========================
        r = requests.get(image_url, timeout=10)
        r.raise_for_status()
        img_bytes = r.content

        if hasattr(message_or_query, "edit_message_text"):
            await message_or_query.edit_message_text("Готово! Надсилаю квиток 👇")
            await message_or_query.message.reply_photo(photo=img_bytes, caption=caption)
        else:
            await message_or_query.reply_photo(photo=img_bytes, caption=caption)

        # ==========================
        # 2️⃣ Тепер шлемо email (Варіант A — передаємо ticket_url)
        # ==========================
        payment_id = payment.get("id")
        if payment_id:
            try:
                API_BASE_URL = os.getenv("API_BASE_URL")
                url = f"{API_BASE_URL}/api/send-email-confirmation/"

                resp = requests.post(
                    url,
                    json={
                        "payment_id": payment_id,
                        "ticket_url": image_url  #
                    },
                    timeout=15
                )

                logger.info(
                    "Email API response | status=%s | text=%s",
                    resp.status_code,
                    resp.text[:300]
                )

                data = {}
                if resp.headers.get("Content-Type", "").startswith("application/json"):
                    data = resp.json()

                if resp.status_code == 200 and data.get("ok"):
                    logger.info("Email confirmation sent | payment_id=%s", payment_id)
                else:
                    logger.warning(
                        "Email confirmation failed | payment_id=%s | status=%s | data=%s",
                        payment_id,
                        resp.status_code,
                        data
                    )

            except Exception as e:
                logger.exception(
                    "Email confirmation request error | payment_id=%s | %s",
                    payment_id,
                    e
                )

    except Exception as e:
        logger.exception("Ticket download/send error: %s", e)
        if hasattr(message_or_query, "edit_message_text"):
            await message_or_query.edit_message_text(
                "Квиток згенеровано, але картинку не можу завантажити 😔"
            )
        else:
            await message_or_query.reply_text(
                "Квиток згенеровано, але картинку не можу завантажити 😔"
            )

    return ConversationHandler.END



# ===== Extra =====

async def my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    resp = get_user_tickets(update.effective_user.id)
    if not resp.get("ok"):
        await update.message.reply_text("Не можу отримати твої квитки 😔")
        return

    tickets = resp.get("tickets", [])
    if not tickets:
        await update.message.reply_text("Поки що в тебе немає квитків.")
        return

    await update.message.reply_text("Ось твої останні квитки 🎫")
    for t in tickets[:5]:
        txt = f"🎟️ <b>{t.get('event_title', 'Івент')}</b>\nДата: {t.get('event_date', '—')}"
        image_url = t.get("image_url")
        if image_url:
            try:
                r = requests.get(image_url, timeout=10)
                r.raise_for_status()
                await update.message.reply_photo(photo=r.content, caption=txt, parse_mode="HTML")
            except Exception:
                await update.message.reply_text(txt, parse_mode="HTML")
        else:
            await update.message.reply_text(txt, parse_mode="HTML")


async def back_to_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Окей, повертаю список подій 👇")
    return await show_events(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Окей 🙂 Якщо що — пиши /start")
    return ConversationHandler.END


async def debug_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("CHAT ID:", update.effective_chat.id)


# ================== MAIN ===================

def main() -> None:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN не заданий в env")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_EVENT: [
                CallbackQueryHandler(event_chosen, pattern=r"^event_\d+$"),
            ],
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_age)],
            REG_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_phone)],
            REG_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_email)],
            ASK_PROMO: [
                CallbackQueryHandler(promo_yes, pattern=r"^promo_yes$"),
                CallbackQueryHandler(promo_no, pattern=r"^promo_no$"),
            ],
            ENTER_PROMO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, promo_entered),
            ],
            WAITING_PAYMENT: [
                CallbackQueryHandler(check_payment, pattern=r"^check_payment$"),
                # CallbackQueryHandler(back_to_events, pattern=r"^back_to_events$"),
            ],

            EVENTS: [
                CallbackQueryHandler(show_events, pattern=r"^show_events$")
            ],

            WAITING_GROUP: [
                CallbackQueryHandler(check_group, pattern=r"^check_group$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("mytickets", my_tickets))
    # application.add_handler(MessageHandler(filters.ALL, debug_group))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    application.add_handler(CallbackQueryHandler(menu_profile, pattern="^menu_profile$"))
    application.add_handler(CallbackQueryHandler(menu_about, pattern="^menu_about$"))
    application.add_handler(CallbackQueryHandler(menu_values, pattern="^menu_values$"))
    application.add_handler(CallbackQueryHandler(show_events, pattern="^menu_events$"))
    application.add_handler(CallbackQueryHandler(event_chosen, pattern=r"^event_\d+$"))
    application.add_handler(CallbackQueryHandler(promo_yes, pattern=r"^promo_yes$"))
    application.add_handler(CallbackQueryHandler(promo_no, pattern=r"^promo_no$"))
    application.add_handler(CallbackQueryHandler(check_payment, pattern=r"^check_payment$"))

    logger.info("BOT SUCCESSFULLY STARTED - %s", time.strftime("%y/%m/%d (%H:%M:%S)"))
    application.run_polling()


if __name__ == "__main__":
    main()
