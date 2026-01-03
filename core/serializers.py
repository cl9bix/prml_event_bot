from rest_framework import serializers
from .models import TgUser, Event, Payment, Ticket


class TgUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TgUser
        fields = ("id", "full_name", "has_paid_once")


class TgUserCreateSerializer(serializers.Serializer):
    tg_id = serializers.IntegerField()
    username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    full_name = serializers.CharField()
    age = serializers.IntegerField(required=False, allow_null=True)
    phone = serializers.CharField()
    email = serializers.EmailField()


class TgUserCheckSerializer(serializers.Serializer):
    tg_id = serializers.IntegerField()
    username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class EventForBotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = (
            "id",
            "title",
            "welcome_text",
            "price",
            "required_group_id",
            "required_group_invite_link",
        )


# serializers.py
from rest_framework import serializers

class PaymentCreateSerializer(serializers.Serializer):
    event_id = serializers.IntegerField()

    user_id = serializers.IntegerField(required=False)

    tg_id = serializers.IntegerField(required=False)
    username = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    first_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    last_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)

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
        fields = ("id", "status", "amount", "provider", "provider_payment_url")

    def get_provider_payment_url(self, obj):
        if obj.provider == "monobank":
            return None

        return (obj.extra or {}).get("provider_payment_url")
class TicketSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    event_title = serializers.CharField(source="event.title")
    user_name = serializers.CharField(source="user.full_name")

    class Meta:
        model = Ticket
        fields = ("id", "image_url", "event_title", "user_name")

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        url = obj.image.url
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
