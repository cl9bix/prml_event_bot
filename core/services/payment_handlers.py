from __future__ import annotations

from django.utils import timezone

from core.monobank import mono_invoice_status


def map_mono_to_local(status_mono: str) -> str:
    st = (status_mono or "").lower().strip()

    # success
    if st in {"success", "paid"}:
        return "success"

    # definitely failed / terminal
    if st in {"failure", "reversed", "expired"}:
        return "failed"

    # everything else -> pending
    # created / processing / hold / ...
    return "pending"


def refresh_payment_from_mono(payment) -> bool:
    """
    Ідемпотентно синкає payment.status з Monobank merchant invoice/status.
    Повертає True якщо статус/дані реально змінилися.
    """
    if not payment.provider_payment_id:
        return False

    data = mono_invoice_status(payment.provider_payment_id)
    mono_status = (data.get("status") or "").lower()
    mono_modified = data.get("modifiedDate")  # ISO string

    extra = payment.extra or {}
    prev_modified = extra.get("mono_modifiedDate")

    # out-of-order protection
    if prev_modified and mono_modified and mono_modified <= prev_modified:
        payment.last_provider_sync_at = timezone.now()
        payment.save(update_fields=["last_provider_sync_at", "updated_at"])
        return False

    extra["mono_last_status_payload"] = data
    extra["mono_status"] = mono_status
    extra["mono_modifiedDate"] = mono_modified

    new_status = map_mono_to_local(mono_status)
    changed = (payment.status != new_status)

    payment.status = new_status
    payment.extra = extra
    payment.last_provider_sync_at = timezone.now()
    payment.save(update_fields=["status", "extra", "last_provider_sync_at", "updated_at"])
    return changed
