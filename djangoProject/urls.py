from django.contrib import admin
from django.urls import path,include
from core import views
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView



urlpatterns = [
    # ===== ADMIN =====
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    # swagger ui
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # ===== TELEGRAM USERS =====
    path("api/tg/check_user/", views.tg_check_user, name="tg_check_user"),
    path("api/tg/create_user/", views.tg_create_user, name="tg_create_user"),

    # ===== EVENTS =====
    path("api/events/", views.events_list, name="events_list"),

    # ===== PAYMENTS =====
    # path('api/payments/config', views.payment_config, name='payment_config'),
    path("api/payments/create/", views.payment_create, name="payment_create"),
    path("api/mono/webhook/", views.mono_webhook, name="mono_webhook"),
    path("api/payments/check/", views.payment_check, name="payment_check"),
    path("api/payments/check/monobank", views.payment_check, name="payment_check"),
    # path("api/payments/confirm_monobank/", views.confirm_monobank, name="confirm_monobank"),
    path("api/promocode/data/get/",views.promo_check,name='promocode-data'),
    # ===== TICKETS =====
    path("api/tickets/get/", views.ticket_get, name="ticket_get"),
    path("api/tickets/my/", views.tickets_my, name="tickets_my"),

    # ===== SYSTEM / CRON / TRIGGERS =====
    path("messages/trigger/", views.trigger_event_messages, name="trigger_event_messages"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)