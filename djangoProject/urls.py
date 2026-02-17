from django.contrib import admin
from django.urls import path,include
from core import views
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView



urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    path("api/tg/check_user/", views.tg_check_user, name="tg_check_user"),
    path("api/user/create/", views.tg_create_user, name="create_user"),

    path("api/events/", views.events_list, name="events_list"),
    path(r"api/events/get/", views.event_get_details, name="event_get_details_by_id"),
    path("api/payments/create/", views.payment_create, name="payment_create"),
    path("api/payments/check/", views.payment_check, name="payment_check"),

    path("api/mono/webhook/", views.mono_webhook, name="mono_webhook"),

    path("api/promocode/data/get/", views.promo_check, name="promocode-data"),

    path("api/tickets/get/", views.ticket_get, name="ticket_get"),
    path("api/tickets/my/", views.tickets_my, name="tickets_my"),

    path("messages/trigger/", views.trigger_event_messages, name="trigger_event_messages"),

    path("api/send-email-confirmation/",views.send_email_confirmation,name="email_confirmation"),
]


urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)