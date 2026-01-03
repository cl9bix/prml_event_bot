from django.db import models
from django.utils import timezone


# ================= USERS =================

class TgUser(models.Model):
    tg_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)

    full_name = models.CharField(max_length=255)
    age = models.PositiveIntegerField(null=True, blank=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField()

    has_paid_once = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


# ================= EVENTS =================

class Event(models.Model):
    title = models.CharField(max_length=255)
    welcome_text = models.TextField()
    description = models.TextField(blank=True)
    banner_image = models.ImageField(upload_to="event_banners/")
    ticket_template = models.ImageField(upload_to="ticket_templates/")
    price = models.DecimalField(max_digits=10, decimal_places=2)

    is_active = models.BooleanField(default=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    required_group_id = models.BigIntegerField()
    required_group_invite_link = models.CharField(max_length=512)

    # 👉 куди шлемо авто-повідомлення
    announce_chat_id = models.BigIntegerField(null=True, blank=True)

    def __str__(self):
        return self.title


# ================= EVENT MESSAGE TEMPLATES =================
# ⬅️ ОЦЕ і є "1.1 EventMessageTemplate — те, що адмін редагує"

class EventMessageTemplate(models.Model):
    class Trigger(models.TextChoices):
        AFTER_PRESS_PAY = "after_press_pay", "Після натиснув оплатити"
        AFTER_PAYMENT_SUCCESS = "after_payment_success", "Після успішної оплати"
        AFTER_JOIN_GROUP = "after_join_group", "Після вступу в групу"
        AFTER_TICKET_SENT = "after_ticket_sent", "Після видачі квитка"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="message_templates")

    trigger = models.CharField(max_length=64, choices=Trigger.choices)
    title = models.CharField(max_length=200, default="Message")
    text = models.TextField()

    delay_seconds = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.event_id} | {self.trigger} | +{self.delay_seconds}s"


# ================= OUTBOX (ЧЕРГА) =================

class TgOutboxMessage(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    tg_id = models.BigIntegerField(db_index=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    trigger = models.CharField(max_length=64)
    text = models.TextField()

    run_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tg_id} | {self.trigger} | {self.status}"


# ================= PAYMENTS =================

class Payment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        TgUser, on_delete=models.CASCADE,
        null=True, blank=True, related_name="payments"
    )
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="payments")

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    provider = models.CharField(max_length=50, default="monobank")
    provider_payment_id = models.CharField(max_length=255, blank=True, null=True)
    extra = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    promo_code = models.ForeignKey("PromoCode", null=True, blank=True, on_delete=models.SET_NULL)
    discount_percent = models.PositiveIntegerField(default=0)
    original_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"Payment #{self.id} ({self.status})"


# ================= TICKETS =================

class Ticket(models.Model):
    user = models.ForeignKey(TgUser, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE)

    token = models.CharField(max_length=64, unique=True)
    image = models.ImageField(upload_to="tickets/")
    created_at = models.DateTimeField(auto_now_add=True)

from django.db import models
from django.utils import timezone



class PromoCode(models.Model):
    code = models.CharField(max_length=16, unique=True)
    percentage = models.PositiveIntegerField(default=5)
    is_available = models.BooleanField(default=True)
    valid_until = models.DateTimeField()

    max_uses = models.PositiveIntegerField(default=0)
    uses_count = models.PositiveIntegerField(default=0)

    def is_valid_now(self) -> bool:
        if not self.is_available:
            return False
        if self.valid_until and self.valid_until < timezone.now():
            return False
        if self.max_uses and self.uses_count >= self.max_uses:
            return False
        return True

    def __str__(self):
        return f"{self.code} (-{self.percentage}%)"
