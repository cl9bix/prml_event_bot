import logging
from django.db import transaction
from django.utils import timezone

from core.models import TgUser, TgOutboxMessage, TgBroadcast

logger = logging.getLogger(__name__)


def enqueue_broadcast(broadcast: TgBroadcast, *, trigger: str = "admin_broadcast") -> int:
    qs = TgUser.objects.all()
    if broadcast.segment == TgBroadcast.Segment.PAID:
        qs = qs.filter(has_paid_once=True)
    tg_ids = list(qs.values_list("tg_id", flat=True))
    if not tg_ids:
        logger.info("enqueue_broadcast: no recipients | broadcast_id=%s", broadcast.id)
        broadcast.enqueued_count = 0
        broadcast.enqueued_at = timezone.now()
        broadcast.save(update_fields=["enqueued_count", "enqueued_at"])
        return 0

    now = timezone.now()

    messages = [
        TgOutboxMessage(
            tg_id=tg_id,
            event=broadcast.event,
            trigger=trigger,
            status=TgOutboxMessage.Status.PENDING,
            run_at=now,
            text=broadcast.text,
        )
        for tg_id in tg_ids
    ]

    logger.info(
        "enqueue_broadcast: preparing | broadcast_id=%s | segment=%s | recipients=%s",
        broadcast.id, broadcast.segment, len(messages)
    )

    with transaction.atomic():
        # ❗️ВАЖЛИВО:  тільки int, тільки keyword
        TgOutboxMessage.objects.bulk_create(messages, batch_size=1000)

        broadcast.enqueued_count = len(messages)
        broadcast.enqueued_at = now
        broadcast.save(update_fields=["enqueued_count", "enqueued_at"])

    logger.info(
        "enqueue_broadcast: done | broadcast_id=%s | enqueued=%s",
        broadcast.id, len(messages)
    )

    return len(messages)
