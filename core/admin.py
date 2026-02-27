# admin.py
from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import Coalesce

from core.models import (
    Event, EventMessageTemplate, TgOutboxMessage,
    TgUser, Ticket, Payment, PromoCode, TgBroadcast
)
from core.services.broadcast import enqueue_broadcast


PAID_STATUS = "paid"
PENDING_STATUS = "pending"
REFUNDED_STATUS = "refunded"


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "percentage", "is_available", "valid_until", "max_uses", "uses_count")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "start_at", "price", "is_active", "announce_chat_id",
        "paid_users_count", "paid_payments_count", "revenue_total",
        "pending_payments_count", "refunded_payments_count",
        "tickets_count", "conversion_percent",
    )
    list_filter = ("is_active", "start_at")
    search_fields = ("title", "description")

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Якщо Payment має FK event — це працює напряму.
        # Якщо related_name інший — заміни "payment_set" на свій.
        return (
            qs.annotate(
                paid_payments_count_a=Count(
                    "payment",
                    filter=Q(payment__status=PAID_STATUS),
                    distinct=True,
                ),
                paid_users_count_a=Count(
                    "payment__user",
                    filter=Q(payment__status=PAID_STATUS),
                    distinct=True,
                ),
                pending_payments_count_a=Count(
                    "payment",
                    filter=Q(payment__status=PENDING_STATUS),
                    distinct=True,
                ),
                refunded_payments_count_a=Count(
                    "payment",
                    filter=Q(payment__status=REFUNDED_STATUS),
                    distinct=True,
                ),
                revenue_total_a=Coalesce(
                    Sum("payment__amount", filter=Q(payment__status=PAID_STATUS)),
                    Decimal("0.00"),
                ),
                tickets_count_a=Count("ticket", distinct=True),
            )
        )

    @admin.display(description="Paid users", ordering="paid_users_count_a")
    def paid_users_count(self, obj):
        return obj.paid_users_count_a

    @admin.display(description="Paid payments", ordering="paid_payments_count_a")
    def paid_payments_count(self, obj):
        return obj.paid_payments_count_a

    @admin.display(description="Revenue", ordering="revenue_total_a")
    def revenue_total(self, obj):
        # можна форматнути під валюту
        return obj.revenue_total_a

    @admin.display(description="Pending", ordering="pending_payments_count_a")
    def pending_payments_count(self, obj):
        return obj.pending_payments_count_a

    @admin.display(description="Refunded", ordering="refunded_payments_count_a")
    def refunded_payments_count(self, obj):
        return obj.refunded_payments_count_a

    @admin.display(description="Tickets", ordering="tickets_count_a")
    def tickets_count(self, obj):
        return obj.tickets_count_a

    @admin.display(description="Conversion", ordering="paid_users_count_a")
    def conversion_percent(self, obj):
        # конверсія: paid_users / tickets (або інший знаменник — як хочеш)
        denom = obj.tickets_count_a or 0
        if denom == 0:
            return "—"
        return f"{(obj.paid_users_count_a * 100) / denom:.1f}%"