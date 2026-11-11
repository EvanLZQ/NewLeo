from django.conf import settings
from django.core.management.base import BaseCommand

from Prescription.private_move import move_public_uploads_to_private


class Command(BaseCommand):
    help = ("Move prescription uploads from public MEDIA_ROOT/prescription_uploads "
            "to PRIVATE_MEDIA_ROOT (idempotent).")

    def handle(self, *args, **options):
        moved, dupes = move_public_uploads_to_private(
            settings.MEDIA_ROOT, settings.PRIVATE_MEDIA_ROOT,
            log=lambda m: self.stdout.write(m))
        self.stdout.write(self.style.SUCCESS(
            f"Moved {moved} file(s); removed {dupes} public duplicate(s)."))
