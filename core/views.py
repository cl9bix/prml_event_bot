# core/views.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import TgUser, Event, Payment, Ticket, EventMessageTemplate, TgOutboxMessage
from .serializers import (
    TgUserSerializer,
    TgUserCreateSerializer,
    TgUserCheckSerializer,
    EventForBotSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    TicketSerializer,
)
from .google_sheet import send_registration_to_google_sheets
from .monobank import mono_create_invoice
from .ticket import generate_ticket


@dataclass(frozen=True)
class MonoWebhookStatus:
    SUCCESS: tuple[str, ...] = ("success", "hold")
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

    changed = False
    for field in ("username", "first_name", "last_name"):
        new_val = data.get(field)
        if getattr(user, field) != new_val:
            setattr(user, field, new_val)
            changed = True

    if changed:
        user.save(update_fields=["username", "first_name", "last_name"])

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
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "full_name": data["full_name"],
            "age": data.get("age"),
            "phone": data["phone"],
            "email": data["email"],
        },
    )

    if not created:
        for f in ("username", "first_name", "last_name", "full_name", "age", "phone", "email"):
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


@api_view(["POST"])
def payment_create(request):
    s = PaymentCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data

    event = get_object_or_404(Event, id=data["event_id"])
    user = None
    extra: dict[str, Any] = {}



    if data.get("user_id"):
        user = get_object_or_404(TgUser, id=data["user_id"])
    else:
        extra = {
            "tg_id": data.get("tg_id"),
            "username": data.get("username"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "reg_data": data.get("reg_data", {}),
            "final_amount": data.get("final_amount")
        }
    print("FINAL_AMOUNT:",data.get('final_amount'))
    amount = data.get("final_amount",event.price)

    payment = Payment.objects.create(
        user=user,
        event=event,
        amount=amount,
        status="pending",
        provider="monobank",
        extra=extra,
    )

    tg_id = user.tg_id if user else extra.get("tg_id")
    reference = f"Оплата в Telegram | telegramId:{tg_id}; pay:{payment.id}"
    webhook_url = request.build_absolute_uri(reverse("mono_webhook"))

    invoice = mono_create_invoice(
        amount_uah=float(payment.amount),
        reference=reference,
        webhook_url=webhook_url,
        redirect_url=None,
    )

    payment.provider_payment_id = invoice['invoiceData']['invoiceId']
    payment.extra = {
        **(payment.extra or {}),
        "mono_invoice": invoice,
        "mono_reference": reference,
    }
    payment.save(update_fields=["provider_payment_id", "extra", "updated_at"])

    return Response(
        {
            "ok": True,
            "payment": PaymentSerializer(payment, context={"request": request}).data,
            "invoice": invoice,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def payment_check(request):
    payment_id = request.query_params.get("payment_id")
    if not payment_id:
        return Response({"ok": False, "error": "payment_id is required"}, status=400)

    payment = get_object_or_404(Payment, id=payment_id)
    return Response({"ok": True, "payment": PaymentSerializer(payment, context={"request": request}).data})


@api_view(["GET"])
def ticket_get(request):
    payment_id = request.query_params.get("payment_id")
    if not payment_id:
        return Response({"ok": False, "error": "payment_id required"}, status=400)

    payment = get_object_or_404(Payment.objects.select_related("event", "user"), id=payment_id)
    if payment.status != "success":
        return Response({"ok": False, "error": "Payment is not successful"}, status=400)

    ticket = Ticket.objects.filter(payment=payment).first()
    if ticket and ticket.image:
        return Response({"ok": True, "ticket": TicketSerializer(ticket, context={"request": request}).data})

    try:
        ticket = generate_ticket(payment.event, payment.user, payment)
    except Exception as e:
        return Response(
            {"ok": False, "error": f"ticket_generate_failed: {type(e).__name__}: {str(e)}"},
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
    data = request.data if isinstance(request.data, dict) else json.loads((request.body or b"{}").decode("utf-8"))

    invoice_id = data.get("invoiceId") or data.get("invoice_id")
    status_mono = data.get("status")

    if not invoice_id:
        return Response({"ok": False, "error": "invoiceId missing"}, status=400)

    payment = Payment.objects.filter(provider="monobank", provider_payment_id=invoice_id).first()
    if not payment:
        return Response({"ok": True})

    extra = payment.extra or {}
    extra["mono_webhook"] = data

    if status_mono in MonoWebhookStatus.SUCCESS:
        payment.status = "success"
        if payment.promo_code_id:
            PromoCode.objects.filter(id=payment.promo_code_id).update(uses_count=F("uses_count") + 1)
    elif status_mono in MonoWebhookStatus.FAILED:
        payment.status = "failed"

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


from rest_framework.decorators import api_view
from rest_framework.response import Response
from decimal import Decimal, ROUND_HALF_UP
from core.models import Event, PromoCode
from core.serializers import PromoValidateSerializer

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
    discount = (price * Decimal(promo.percentage) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    final_price = (price - discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if final_price < Decimal("0.00"):
        final_price = Decimal("0.00")

    return Response({
        "ok": True,
        "promo": {"code": promo.code, "percentage": promo.percentage},
        "original_amount": str(price),
        "final_amount": str(final_price),
        "discount_amount": str(discount),
    })


