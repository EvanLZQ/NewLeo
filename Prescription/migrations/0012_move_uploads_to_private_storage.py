from django.conf import settings
from django.db import migrations


def forwards(apps, schema_editor):
    from Prescription.private_move import move_public_uploads_to_private
    move_public_uploads_to_private(settings.MEDIA_ROOT, settings.PRIVATE_MEDIA_ROOT)


class Migration(migrations.Migration):
    """Files only; FileField names are unchanged. Not reversed on purpose:
    never move prescriptions back into public /media."""

    dependencies = [
        ('Prescription', '0011_owner_and_private_storage'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
