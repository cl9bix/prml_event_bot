from rest_framework import serializers
from .models import TgUser, Event, Payment, Ticket


class TgUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TgUser
        fields = ("id",'tg_id', "full_name", "has_paid_once",'username','age','phone','email')


class TgUserCreateSerializer(serializers.Serializer):
    tg_id = serializers.IntegerField()
    username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    full_name = serializers.CharField()
    age = serializers.IntegerField(required=False, allow_null=True)
    phone = serializers.CharField()
    email = serializers.EmailField()


class TgUserCheckSerializer(serializers.Serializer):
    tg_id = serializers.IntegerField()
    username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    age = serializers.IntegerField(required=False,allow_null=True)
    email = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)


class EventForBotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "welcome_text",
            "description",
            "price",
            "original_price_until",
            "new_price_from",
            "new_price_value",
            "required_group_id",
            "required_group_invite_link",
        )


# serializers.py


class PaymentCreateSerializer(serializers.Serializer):
    event_id = serializers.IntegerField()

    user_id = serializers.IntegerField(required=False)

    tg_id = serializers.IntegerField(required=False)
    username = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    full_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    reg_data = serializers.DictField(required=False)
    promo_code = serializers.CharField(required=False, allow_blank=True)
    final_amount = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get("user_id") and not attrs.get("tg_id"):
            raise serializers.ValidationError("Provide user_id OR tg_id")
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    provider_payment_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ("id", "status", "amount", "provider", "provider_payment_url", 'extra')

    def get_provider_payment_url(self, obj):
        if obj.provider == "monobank":
            return None

        return (obj.extra or {}).get("provider_payment_url")


class TicketSerializer(serializers.ModelSerializer):
    event_title = serializers.CharField(source="event.title")
    user_name = serializers.CharField(source="user.full_name")
    date_text = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = ("id", "event_title", "user_name", "date_text", "image_url")

    def get_date_text(self, obj):
        return obj.event.start_at.strftime('%d.%m / %H:%M')

    def get_image_url(self, obj):
        request = self.context.get("request")
        if not obj.image:
            return None
        url = obj.image.url  # типу /media/tickets/xxx.png
        return request.build_absolute_uri(url) if request else url



from rest_framework import serializers
from core.models import TgUser, Event, Payment, Ticket


class ConfirmMonobankSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField()
    mono = serializers.DictField()


from rest_framework import serializers
from core.models import PromoCode


class PromoValidateSerializer(serializers.Serializer):
    code = serializers.CharField()

    def validate_code(self, value):
        code = value.strip().upper()
        promo = PromoCode.objects.filter(code=code).first()
        if not promo or not promo.is_valid_now():
            raise serializers.ValidationError("Промокод недійсний або прострочений")
        return code
