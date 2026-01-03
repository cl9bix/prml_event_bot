import requests
from celery import shared_task
from django.utils import timezone

from core.models import EventMessage

BOT_TOKEN = "8299398757:AAHvOZBKNbsVogB7X3jILQqXGUur89rT4rI"

from core.models import TgOutboxMessage

def tg_send_message(tg_id: int, text: str):
    token = BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": tg_id, "text": text}, timeout=10)
    r.raise_for_status()

@shared_task
def outbox_tick():
    now = timezone.now()
    qs = TgOutboxMessage.objects.filter(
        status=TgOutboxMessage.Status.PENDING,
        run_at__lte=now,
    ).order_by("run_at")[:200]

    for msg in qs:
        try:
            tg_send_message(msg.tg_id, msg.text)
            msg.status = TgOutboxMessage.Status.SENT
            msg.sent_at = now
            msg.save(update_fields=["status", "sent_at"])
        except Exception as e:
            msg.status = TgOutboxMessage.Status.FAILED
            msg.error = str(e)[:2000]
            msg.save(update_fields=["status", "error"])
