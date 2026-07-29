# Step 3 of 3: drop the retired generic LensStep/LensOption graph now that
# Order.CompleteSet no longer references LensOption (see
# Order/migrations/0017_completeset_new_lens_reference_fields.py).
#
# DeleteModel alone drops each table (and its own fields/constraints/indexes)
# in one go — no need to strip fields first, just delete in dependency order:
# LensStepRule (FKs to LensStep + LensOption) and LensOptionAvailability
# (FKs to LensOption twice) before the two models they depend on.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0002_new_lens_reference_models'),
        ('Order', '0017_completeset_new_lens_reference_fields'),
    ]

    operations = [
        migrations.DeleteModel(
            name='LensStepRule',
        ),
        migrations.DeleteModel(
            name='LensOptionAvailability',
        ),
        migrations.DeleteModel(
            name='LensOption',
        ),
        migrations.DeleteModel(
            name='LensStep',
        ),
    ]
