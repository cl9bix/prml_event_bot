import logging
import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from core.google_sheet import send_registration_to_google_sheets

from telegram import Bot
from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError, TimedOut

from core.models import TgOutboxMessage

logger = logging.getLogger(__name__)


@shared_task
def save_to_sheets_task(data):
    send_registration_to_google_sheets(data)

def send_telegram_message(token: str, chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(str(data))

@shared_task(bind=True, name="core.tasks.outbox_tick", max_retries=5, default_retry_delay=10)
def outbox_tick(self, limit: int = 200):
    token = settings.TELEGRAM_BOT_TOKEN
    bot = Bot(token=token)

    now = timezone.now()
    msgs = list(
        TgOutboxMessage.objects
        .filter(status=TgOutboxMessage.Status.PENDING, run_at__lte=now)
        .order_by("run_at")[:limit]
    )

    logger.info("outbox_tick started | pending=%s", len(msgs))

    sent = failed = 0
    for m in msgs:
        try:
            token = settings.TELEGRAM_BOT_TOKEN
            send_telegram_message(token=token,chat_id=m.tg_id, text=m.text)

            m.status = TgOutboxMessage.Status.SENT
            m.sent_at = timezone.now()
            m.error = ""
            m.save(update_fields=["status", "sent_at", "error"])
            sent += 1

        except RetryAfter as e:
            wait_for = int(getattr(e, "retry_after", 1))
            raise self.retry(countdown=wait_for)

        except (Forbidden, BadRequest) as e:
            failed += 1
            m.status = TgOutboxMessage.Status.FAILED
            m.error = str(e)
            m.save(update_fields=["status", "error"])
            logger.warning("Cannot send | outbox_id=%s | %s", m.id, e)

        except (NetworkError, TimedOut) as e:
            failed += 1
            m.status = TgOutboxMessage.Status.FAILED
            m.error = str(e)
            m.save(update_fields=["status", "error"])
            logger.warning("Network issue | outbox_id=%s | %s", m.id, e)

        except Exception as e:
            failed += 1
            m.status = TgOutboxMessage.Status.FAILED
            m.error = str(e)
            m.save(update_fields=["status", "error"])
            logger.exception("Unexpected error | outbox_id=%s", m.id)

    logger.info("outbox_tick finished | sent=%s failed=%s", sent, failed)
    return {"total": len(msgs), "sent": sent, "failed": failed}

save_to_sheets_task.delay({
    "tg_id": '123213',
    "username": 'cl9bix',
    "full_name": "Yuriy Scheffer",
    "age": 21,
    "phone": "+380956103761",
    "email": "cl9bix.dev@gmail.com",
})