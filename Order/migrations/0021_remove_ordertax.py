# The business does not charge tax — OrderTax was dead weight anyway: no
# serializer, view, or frontend code ever wrote to it or read from it (tax
# display/calculation was always client-side-only, disconnected from this
# table entirely). Dropping the table outright rather than leaving unused
# dead code around.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Order', '0020_completeset_tint_type'),
    ]

    operations = [
        migrations.DeleteModel(
            name='OrderTax',
        ),
    ]
