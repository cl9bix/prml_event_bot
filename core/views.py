from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from typing import Any

from .google_sheet import send_registration_to_google_sheets
from .models import TgUser, Event, Payment, Ticket, EventMessageTemplate, TgOutboxMessage, PromoCode
from .monobank import mono_create_invoice, verify_mono_webhook_signature
from .serializers import (
    TgUserSerializer,
    TgUserCreateSerializer,
    TgUserCheckSerializer,
    EventForBotSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    TicketSerializer,
)
from .services.payment_handlers import refresh_payment_from_mono
from .ticket import generate_ticket

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonoWebhookStatus:
    SUCCESS: tuple[str, ...] = ("success",)
    PENDING: tuple[str, ...] = ("hold", "created", "processing")
    FAILED: tuple[str, ...] = ("failure", "expired", "reversed")


def _safe_send_to_sheets(payload: dict[str, Any]) -> None:
    try:
        send_registration_to_google_sheets(payload)
    except Exception:
        return


@api_view(["POST"])
def tg_check_user(request):
    s = TgUserCheckSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    tg_id = data["tg_id"]
    user = TgUser.objects.filter(tg_id=tg_id).first()

    if not user:
        return Response({"ok": True, "exists": False, "user": None})
    return Response({"ok": True, "exists": True, "user": TgUserSerializer(user).data})


@api_view(["POST"])
def tg_create_user(request):
    s = TgUserCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    user, created = TgUser.objects.get_or_create(
        tg_id=data["tg_id"],
        defaults={
            "username": data.get("username"),
            "full_name": data["full_name"],
            "age": data.get("age"),
            "phone": data["phone"],
            "email": data["email"],
        },
    )

    if not created:
        for f in ("username", "full_name", "age", "phone", "email"):
            setattr(user, f, data.get(f, getattr(user, f)))
        user.save()

    _safe_send_to_sheets(
        {
            "tg_id": user.tg_id,
            "username": user.username,
            "full_name": user.full_name,
            "age": user.age,
            "phone": user.phone,
            "email": user.email,
        }
    )

    return Response({"ok": True, "user": TgUserSerializer(user).data}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def events_list(request):
    qs = Event.objects.filter(is_active=True).order_by("start_at")
    return Response({"ok": True, "events": EventForBotSerializer(qs, many=True).data})


@api_view(["GET"])
def event_get_details(request):
    event = get_object_or_404(Event, id=request.query_params.get('event_id') or None)
    if event is None:
        return Response({"ok": False, 'Message': 'Api returned a None value'})
    serializer = EventForBotSerializer(event)
    return Response({'ok': True, "event": serializer.data})


@api_view(["GET"])
def promo_check(request):
    code = (request.query_params.get("code") or "").strip()
    event_id = request.query_params.get("event_id")

    if not code or not event_id:
        return Response(
            {"ok": False, "error": "code and event_id are required"},
            status=400
        )

    promo = PromoCode.objects.filter(
        code__iexact=code,
        is_available=True,
        valid_until__gte=timezone.now()
    ).first()

    if not promo:
        return Response(
            {"ok": False, "error": "Promo code is invalid or expired"},
            status=404
        )

    event = Event.objects.filter(id=event_id, is_active=True).first()
    if not event:
        return Response(
            {"ok": False, "error": "Event not found"},
            status=404
        )

    price = Decimal(str(event.price))

    if promo.percentage >= 100:
        return Response({
            "ok": True,
            "promo": {
                "code": promo.code,
                "percentage": promo.percentage,
            },
            "original_amount": str(price),
            "discount_amount": str(price),
            "final_amount": "0.00",
            "is_free": True,
        })

    discount = (price * Decimal(promo.percentage) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    final_price = (price - discount).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if final_price < Decimal("0.00"):
        final_price = Decimal("0.00")

    return Response({
        "ok": True,
        "promo": {
            "code": promo.code,
            "percentage": promo.percentage,
        },
        "original_amount": str(price),
        "discount_amount": str(discount),
        "final_amount": str(final_price),
        "is_free": final_price == Decimal("0.00"),
    })


from django.db import transaction


@api_view(["POST"])
def payment_create(request):
    s = PaymentCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    event = get_object_or_404(Event, id=data["event_id"], is_active=True)

    # -----------------------------
    # 1) Завжди отримуємо/створюємо user
    # -----------------------------
    user = None
    extra: dict[str, Any] = {}

    if data.get("user_id"):
        user = get_object_or_404(TgUser, id=data["user_id"])
    else:
        # fallback: якщо бот не передав user_id — спробуємо зібрати дані з reg_data
        reg_data = data.get("reg_data") or {}
        tg_id = data.get("tg_id") or reg_data.get("tg_id")
        if not tg_id:
            return Response({"ok": False, "error": "user_id або tg_id required"}, status=400)

        extra = {
            "tg_id": tg_id,
            "username": data.get("username") or reg_data.get("username"),
            "full_name": data.get("full_name") or reg_data.get("full_name"),
            "reg_data": reg_data,
        }

        # створимо/оновимо TgUser, щоб потім можна було створити Ticket (в Ticket.user не null)
        full_name = (reg_data.get("full_name") or data.get("full_name") or "").strip()
        phone = (reg_data.get("phone") or "").strip()
        email = (reg_data.get("email") or "").strip()

        if not full_name or not phone or not email:
            return Response(
                {"ok": False, "error": "reg_data must contain full_name/phone/email when user_id is missing"},
                status=400,
            )

        user, _ = TgUser.objects.get_or_create(
            tg_id=tg_id,
            defaults={
                "username": extra.get("username"),
                "full_name": full_name,
                "age": reg_data.get("age"),
                "phone": phone,
                "email": email,
            },
        )

    # -----------------------------
    # 2) Promo / amount / is_free
    # -----------------------------
    promo_code_raw = (data.get("promo_code") or "").strip()
    promo = None
    discount_percent = 0

    original_amount = Decimal(str(event.price))
    # якщо final_amount не передали — беремо event.price
    final_amount = Decimal(str(data.get("final_amount") or event.price))

    if promo_code_raw:
        promo = PromoCode.objects.filter(
            code__iexact=promo_code_raw,
            is_available=True,
            valid_until__gte=timezone.now(),
        ).first()
        if not promo:
            return Response({"ok": False, "error": "Promo invalid"}, status=404)

        discount_percent = int(promo.percentage or 0)

        if discount_percent >= 100:
            final_amount = Decimal("0.00")
        else:
            if final_amount < Decimal("0.00"):
                final_amount = Decimal("0.00")

    is_free = (final_amount == Decimal("0.00"))

    # -----------------------------
    # 3) Створюємо Payment + FREE flow
    # -----------------------------
    with transaction.atomic():
        payment = Payment.objects.create(
            user=user,
            event=event,
            amount=final_amount,
            status="success" if is_free else "pending",
            provider="promo" if is_free else "monobank",
            provider_payment_id=None,
            promo_code=promo,
            discount_percent=discount_percent,
            original_amount=original_amount,
            extra={
                **(extra or {}),
                "final_amount": str(final_amount),
                "is_free": is_free,
                "promo_code": promo.code if promo else None,
            },
        )

        if is_free:
            # промо використовуємо атомарно
            if promo:
                PromoCode.objects.filter(id=promo.id).update(uses_count=F("uses_count") + 1)

            # юзеру позначка (якщо треба)
            TgUser.objects.filter(id=user.id).update(has_paid_once=True)

            # ✅ генеруємо квиток і зберігаємо в Ticket.image
            date_text = event.start_at.strftime("%d.%m / %H:%M") if event.start_at else ""
            filename = generate_ticket(full_name=user.full_name, date_text=date_text)

            ticket, _ = Ticket.objects.get_or_create(
                payment=payment,
                defaults={
                    "user": user,
                    "event": event,
                    "token": payment.extra.get("token") or "",  # якщо токен генеруєш окремо — підстав
                },
            )
            # якщо token обов'язковий — краще генерувати тут нормально (uuid/sha)
            if not ticket.token:
                import uuid
                ticket.token = uuid.uuid4().hex

            ticket.image = f"tickets/{filename}"
            ticket.save(update_fields=["token", "image"])

            return Response(
                {
                    "ok": True,
                    "is_free": True,
                    "payment": PaymentSerializer(payment, context={"request": request}).data,
                    "invoice": None,
                },
                status=status.HTTP_201_CREATED,
            )

    # -----------------------------
    # 4) Звичайний кейс: інвойс Monobank
    # -----------------------------
    tg_id = user.tg_id
    reference = f"Оплата в Telegram | telegramId:{tg_id}; pay:{payment.id}"
    webhook_url = request.build_absolute_uri(reverse("mono_webhook"))

    invoice = mono_create_invoice(
        amount_uah=float(payment.amount),
        reference=reference,
        webhook_url=webhook_url,
        redirect_url="https://t.me/prml_event_bot",
    )

    payment.provider_payment_id = invoice["invoiceData"]["invoiceId"]
    payment.extra = {
        **(payment.extra or {}),
        "mono_invoice": invoice,
        "mono_reference": reference,
        "mono_modifiedDate": None,
        "mono_status": None,
    }
    payment.save(update_fields=["provider_payment_id", "extra", "updated_at"])

    return Response(
        {
            "ok": True,
            "is_free": False,
            "payment": PaymentSerializer(payment, context={"request": request}).data,
            "invoice": invoice,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["GET"])
def payment_check(request):
    payment_id = request.query_params.get("payment_id")
    refresh = True

    logger.info("🔎 payment_check called | payment_id=%s | refresh=%s", payment_id, refresh)

    if not payment_id:
        logger.warning("❌ payment_check without payment_id")
        return Response({"ok": False, "error": "payment_id is required"}, status=400)

    payment = get_object_or_404(Payment, id=payment_id)

    logger.info(
        "📦 Current payment state | id=%s | status=%s | provider=%s | provider_payment_id=%s",
        payment.id,
        payment.status,
        payment.provider,
        payment.provider_payment_id,
    )

    if refresh and payment.status == "pending" and payment.provider == "monobank" and payment.provider_payment_id:
        last = getattr(payment, "last_provider_sync_at", None)

        logger.info("⏳ Attempting refresh from Monobank...")

        if not last or (timezone.now() - last).total_seconds() > 8:
            try:
                old_status = payment.status

                changed = refresh_payment_from_mono(payment)
                payment.refresh_from_db()

                logger.info(
                    "✅ Monobank refresh done | changed=%s | old_status=%s | new_status=%s",
                    changed,
                    old_status,
                    payment.status,
                )

                if payment.extra:
                    logger.info(
                        "📡 Mono payload status=%s",
                        payment.extra.get("mono_status")
                    )

            except Exception as e:
                logger.exception("💥 Monobank refresh failed: %s", str(e))
        else:
            logger.info("🚫 Refresh skipped due to throttle")

    else:
        logger.info("ℹ️ Refresh conditions not met")

    return Response({
        "ok": True,
        "payment": PaymentSerializer(payment, context={"request": request}).data
    })







@api_view(["GET"])
def ticket_get(request):
    payment_id = request.query_params.get("payment_id")
    if not payment_id:
        return Response({"ok": False, "error": "payment_id required"}, status=400)

    payment = get_object_or_404(
        Payment.objects.select_related("event", "user"),
        id=payment_id
    )

    if payment.status != "success":
        return Response({"ok": False, "error": "Payment is not successful"}, status=400)

    # 1) Якщо квиток уже є і зображення існує — віддаємо одразу (ідемпотентність)
    ticket = Ticket.objects.filter(payment=payment).first()
    if ticket and ticket.image:
        return Response({"ok": True, "ticket": TicketSerializer(ticket, context={"request": request}).data})

    # 2) Створюємо/оновлюємо Ticket атомарно + гарантуємо token
    try:
        date_text = payment.event.start_at.strftime("%d.%m / %H:%M") if payment.event.start_at else ""

        # Спробуємо кілька разів на випадок колізії токена (дуже малоймовірно, але safe)
        for _ in range(3):
            try:
                with transaction.atomic():
                    ticket = Ticket.objects.select_for_update().filter(payment=payment).first()

                    if not ticket:
                        # ✅ Створюємо квиток строго під цей payment (бо OneToOne)
                        ticket = Ticket.objects.create(
                            user=payment.user,
                            event=payment.event,
                            payment=payment,
                            token=uuid.uuid4().hex,
                        )
                    else:
                        # ✅ Якщо квиток існує, але token порожній — виправляємо
                        if not ticket.token:
                            ticket.token = uuid.uuid4().hex
                            ticket.save(update_fields=["token"])

                break
            except IntegrityError:
                # якщо раптом згенерився токен, який вже існує
                continue
        else:
            return Response(
                {"ok": False, "error": "ticket_generate_failed: IntegrityError: token collision"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 3) Генерація зображення + збереження
        filename = generate_ticket(full_name=payment.user.full_name, date_text=date_text)
        ticket.image = f"tickets/{filename}"
        ticket.save(update_fields=["image"])

    except Exception as e:
        logger.exception("ticket_get failed | payment_id=%s | %s", payment_id, e)
        return Response(
            {"ok": False, "error": f"ticket_generate_failed: {type(e).__name__}: {e}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({"ok": True, "ticket": TicketSerializer(ticket, context={"request": request}).data})

@api_view(["GET"])
def tickets_my(request):
    tg_id = request.query_params.get("tg_id")
    if not tg_id:
        return Response({"ok": False, "error": "tg_id required"}, status=400)

    user = get_object_or_404(TgUser, tg_id=tg_id)
    qs = Ticket.objects.filter(user=user).select_related("event").order_by("-created_at")

    items = []
    for t in qs:
        d = TicketSerializer(t, context={"request": request}).data
        d["event_date"] = t.event.start_at
        items.append(d)

    return Response({"ok": True, "tickets": items})


@api_view(["POST"])
@csrf_exempt
def mono_webhook(request):
    x_sign = request.headers.get("X-Sign", "")

    if not x_sign or not verify_mono_webhook_signature(body_bytes=request.body, x_sign_b64=x_sign):
        return Response({"ok": False, "error": "bad signature"}, status=400)

    data = request.data if isinstance(request.data, dict) else json.loads((request.body or b"{}").decode("utf-8"))

    invoice_id = data.get("invoiceId") or data.get("invoice_id")
    status_mono = (data.get("status") or "").lower()
    modified_date = data.get("modifiedDate")

    if not invoice_id:
        return Response({"ok": False, "error": "invoiceId missing"}, status=400)

    payment = Payment.objects.filter(provider="monobank", provider_payment_id=invoice_id).first()
    if not payment:
        return Response({"ok": True})

    extra = payment.extra or {}

    # out-of-order protection
    prev_modified = extra.get("mono_modifiedDate")
    if prev_modified and modified_date and modified_date <= prev_modified:
        extra["mono_webhook_last_payload"] = data
        payment.extra = extra
        payment.updated_at = timezone.now()
        payment.save(update_fields=["extra", "updated_at"])
        return Response({"ok": True})

    extra["mono_webhook_last_payload"] = data
    extra["mono_status"] = status_mono
    extra["mono_modifiedDate"] = modified_date

    if status_mono in MonoWebhookStatus.SUCCESS:
        payment.status = "success"
        if getattr(payment, "promo_code_id", None):
            PromoCode.objects.filter(id=payment.promo_code_id).update(uses_count=F("uses_count") + 1)

    elif status_mono in MonoWebhookStatus.FAILED:
        payment.status = "failed"

    else:
        payment.status = "pending"

    payment.extra = extra
    payment.updated_at = timezone.now()
    payment.save(update_fields=["status", "extra", "updated_at"])

    return Response({"ok": True})


@api_view(["POST"])
def trigger_event_messages(request):
    event_id = request.data.get("event_id")
    tg_id = request.data.get("tg_id")
    trigger = request.data.get("trigger")

    event = Event.objects.filter(id=event_id).first()
    if not event:
        return Response({"ok": False, "error": "Event not found"}, status=404)

    templates = EventMessageTemplate.objects.filter(event=event, trigger=trigger, is_enabled=True)
    now = timezone.now()

    TgOutboxMessage.objects.bulk_create(
        [
            TgOutboxMessage(
                tg_id=tg_id,
                event=event,
                trigger=trigger,
                text=tpl.text,
                run_at=now + timezone.timedelta(seconds=tpl.delay_seconds),
            )
            for tpl in templates
        ]
    )

    return Response({"ok": True})


import os
import tempfile
import logging
import requests
from core.service_email import send_ticket_email


@api_view(["POST"])
def send_email_confirmation(request):
    payment_id = request.data.get("payment_id")
    ticket_url = (request.data.get("ticket_url") or "").strip()

    if not payment_id:
        return Response(
            {"ok": False, "error": "payment_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payment = Payment.objects.select_related("user", "event").filter(id=payment_id).first()
    if not payment:
        return Response(
            {"ok": False, "error": "payment not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # ========================
    # EMAIL DATA
    # ========================
    if payment.user:
        to_email = payment.user.email
        user_name = payment.user.full_name
    else:
        extra = payment.extra or {}
        reg_data = extra.get("reg_data", {})
        to_email = reg_data.get("email") or extra.get("email")
        user_name = reg_data.get("full_name") or extra.get("full_name")

    if not to_email:
        return Response(
            {"ok": False, "error": "recipient email not found"},
            status=400,
        )

    event_name = payment.event.title
    event_dt = (
        payment.event.start_at.strftime("%d.%m / %H:%M")
        if payment.event.start_at
        else ""
    )

    # ========================
    # 🔥 ВАРІАНТ A: беремо ticket_url з POST
    # ========================
    if not ticket_url:
        return Response(
            {"ok": False, "error": "ticket_url not provided"},
            status=400,
        )

    logger.info(
        "send_email_confirmation | payment_id=%s | ticket_url=%s",
        payment_id,
        ticket_url,
    )

    try:
        resp = requests.get(ticket_url, timeout=20)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        ext = ".pdf" if "pdf" in content_type else ".jpg"

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        ok = send_ticket_email(
            to_email=to_email,
            user_name=user_name or "друже",
            event_name=event_name,
            date=event_dt,
            ticket_path=tmp_path,
        )

        try:
            os.remove(tmp_path)
        except Exception:
            logger.warning("Temp file not removed: %s", tmp_path)

        if not ok:
            return Response(
                {"ok": False, "error": "email sending failed"},
                status=500,
            )

        return Response({"ok": True})

    except Exception as e:
        logger.exception("send_email_confirmation error | %s", e)
        return Response({"ok": False, "error": "server error"}, status=500)


