import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djangoProject.settings")

app = Celery("djangoProject")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "sync-paid-users-to-sheets-every-minute": {
        "task": "core.tasks.sync_paid_users_to_sheets",
        "schedule": crontab(),  # кожну хвилину
    },
}