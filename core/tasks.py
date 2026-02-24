import logging
from typing import Any, Dict, List

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError, TimedOut

from core.google_sheet import send_registration_to_google_sheets
from core.models import TgOutboxMessage, Payment, TgUser

logger = logging.getLogger(__name__)

SHEETS_FLAG_KEY = "synced_to_sheets_at"


def send_telegram_message(token: str, chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(str(data))


@shared_task
def save_to_sheets_task(data: Dict[str, Any]) -> None:
    """
    Якщо хочеш ручний пуш 1 юзера в Sheets.
    """
    send_registration_to_google_sheets(data)


@shared_task(bind=True, name="core.tasks.outbox_tick", max_retries=5, default_retry_delay=10)
def outbox_tick(self, limit: int = 200) -> Dict[str, int]:
    now = timezone.now()
    msgs = list(
        TgOutboxMessage.objects
        .filter(status=TgOutboxMessage.Status.PENDING, run_at__lte=now)
        .order_by("run_at")[:limit]
    )

    logger.info("outbox_tick started | pending=%s", len(msgs))

    sent = 0
    failed = 0

    for m in msgs:
        try:
            send_telegram_message(
                token=settings.TELEGRAM_BOT_TOKEN,
                chat_id=m.tg_id,
                text=m.text
            )

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
            logger.exception("Unexpected error | outbox_id=%s | %s", m.id, e)

    logger.info("outbox_tick finished | sent=%s failed=%s", sent, failed)
    return {"total": len(msgs), "sent": sent, "failed": failed}


from typing import Any, Dict, List
from celery import shared_task
from django.utils import timezone
from django.db import transaction
import logging

from core.models import Payment, TgUser
from core.google_sheet import send_registration_to_google_sheets

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="core.tasks.sync_paid_users_to_sheets",
    max_retries=3,
    default_retry_delay=20
)
def sync_paid_users_to_sheets(self, limit: int = 200) -> Dict[str, Any]:
    """
    Раз на хвилину:
    - бере Payment зі status=success
    - user != null
    - exported_to_sheets=False
    - ТІЛЬКИ реальна оплата (monobank + amount > 0)  ✅
    - додає юзера в Google Sheets
    - ставить exported_to_sheets=True
    """

    # Якщо ти хочеш тільки "реальні" платежі:
    base_qs = (
        Payment.objects
        .select_related("user", "event")
        .filter(
            status="success",
            user__isnull=False,
            exported_to_sheets=False,

            provider="monobank",   # ✅ прибирає promo / тестові провайдери
            amount__gt=0,          # ✅ прибирає 100% промо з amount=0
        )
        # .filter(event__is_active=True)  # ✅ якщо треба тільки активні івенти
        .order_by("id")
    )

    # Якщо Postgres — краще так (без дубля при паралельних воркерах):
    try:
        with transaction.atomic():
            payments: List[Payment] = list(
                base_qs.select_for_update(skip_locked=True)[:limit]
            )
    except Exception:
        # fallback для SQLite/MySQL без skip_locked
        payments = list(base_qs[:limit])

    total = len(payments)
    if total == 0:
        logger.info("sync_paid_users_to_sheets: nothing to sync")
        return {"ok": True, "total": 0, "synced": 0, "failed": 0}

    synced = 0
    failed = 0

    for p in payments:
        u: TgUser = p.user

        payload = {
            "tg_id": u.tg_id,
            "username": u.username or "",
            "full_name": u.full_name,
            "age": u.age or "",
            "phone": u.phone,
            "email": u.email,
            "event": getattr(p.event, "title", ""),
            "payment_id": p.id,
            "paid_at": (p.updated_at or timezone.now()).strftime("%Y-%m-%d %H:%M:%S"),
        }

        try:
            send_registration_to_google_sheets(payload)

            p.exported_to_sheets = True
            p.save(update_fields=["exported_to_sheets"])

            synced += 1
            logger.info(
                "sync_paid_users_to_sheets: synced | payment_id=%s tg_id=%s",
                p.id, u.tg_id
            )

        except Exception as e:
            failed += 1
            logger.exception(
                "sync_paid_users_to_sheets: failed | payment_id=%s | %s",
                p.id, e
            )

    logger.info(
        "sync_paid_users_to_sheets: done | total=%s synced=%s failed=%s",
        total, synced, failed
    )

    return {"ok": True, "total": total, "synced": synced, "failed": failed}
