from django.core.management.base import BaseCommand
from core.tasks import outbox_tick


class Command(BaseCommand):
    help = "Send pending TgOutboxMessage now"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options):
        limit = options["limit"]
        res = outbox_tick(limit=limit)  # синхронно
        self.stdout.write(self.style.SUCCESS(
            f"Done | total={res['total']} sent={res['sent']} failed={res['failed']}"
        ))
