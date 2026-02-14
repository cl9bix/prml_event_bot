from django.contrib import admin, messages

from core.models import (
    Event, EventMessageTemplate, TgOutboxMessage,
    TgUser, Ticket, Payment, PromoCode, TgBroadcast
)
from core.services.broadcast import enqueue_broadcast


# class EventMessageTemplateInline(admin.TabularInline):
#     model = EventMessageTemplate
#     extra = 1
#     fields = ("trigger", "title", "delay_seconds", "text", "is_enabled")


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "percentage", "is_available", "valid_until", "max_uses", "uses_count")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "start_at", "price", "is_active", "announce_chat_id")
    list_filter = ("is_active", "start_at")
    search_fields = ("title", "description")
    # inlines = [EventMessageTemplateInline]


@admin.register(TgUser)
class TgUserAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "tg_id", "phone", "email", "has_paid_once")
    search_fields = ("full_name", "tg_id", "username", "phone", "email")
    list_filter = ("has_paid_once",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event", "amount", "status", "provider", "created_at")
    list_filter = ("status", "provider")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "event", "payment", "token", "created_at")
    readonly_fields = ("token", "created_at")


@admin.register(TgOutboxMessage)
class TgOutboxMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "tg_id", "event", "trigger", "status", "run_at", "sent_at")
    list_filter = ("status", "trigger")
    readonly_fields = ("sent_at", "error", "created_at")
    search_fields = ("tg_id", "trigger", "text")


@admin.register(TgBroadcast)
class TgBroadcastAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "segment", "event", "enqueued_count", "enqueued_at", "created_at")
    list_filter = ("segment", "enqueued_at", "created_at")
    search_fields = ("title", "text")
    readonly_fields = ("enqueued_count", "enqueued_at", "created_at")

    actions = ["enqueue_selected"]

    @admin.action(description="Enqueue selected broadcasts to outbox")
    def enqueue_selected(self, request, queryset):
        total = 0
        for b in queryset:
            try:
                total += enqueue_broadcast(b)
            except Exception as e:
                messages.error(request, f"Broadcast #{b.id}: error: {e}")
        messages.success(request, f"Enqueued {total} messages to TgOutboxMessage.")
