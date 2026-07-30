# Fourth-pass adjustment: a color's price doesn't vary by index tier (see
# 0005/0006), but its *availability* does — e.g. SVD's Polarized Green/Brown
# are offered at 1.56/1.61 but drop off at 1.67. This field records which
# index values a color is actually offered at, so the Color step can be
# filtered to the prescription's allowed index bracket, and the Index step
# that follows can be narrowed to whichever index values the chosen color
# still supports. Backfilled by import_lens_reference_guide, not hand-edited
# data worth preserving here.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0006_lenscoloroption_function_path_schema'),
    ]

    operations = [
        migrations.AddField(
            model_name='lenscoloroption',
            name='available_index_values',
            field=models.JSONField(
                default=list,
                help_text='Index values this color is offered at, e.g. ["1.56", "1.61"]. '
                          "Populated from the Color Compatibility sheet's per-row Index column.",
            ),
        ),
    ]
