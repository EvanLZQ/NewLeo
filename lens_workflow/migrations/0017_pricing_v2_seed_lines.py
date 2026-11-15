"""Seed the two product lines of price_v2.xlsx and the settings row.

Additive only: get_or_create, nothing existing is changed or deleted.
Reverse is a no-op (rows are left in place; dropping the tables is
0016's reverse)."""
from django.db import migrations

LINES = [
    ("economic", "Economic", "Economic Lens", 10,
     "Great-value lenses with hard multi-coating."),
    ("premium", "Premium (Conant®)", "Premium Lens", 20,
     "Conant® branded lenses: premium hard multi-coating, strict quality checks, "
     "Mitsui MR™ materials at 1.60 / 1.67 / 1.74."),
]


def seed(apps, schema_editor):
    LensLine = apps.get_model("lens_workflow", "LensLine")
    Settings = apps.get_model("lens_workflow", "LensPricingSettings")
    for code, name, sheet, sort, desc in LINES:
        LensLine.objects.get_or_create(
            code=code, defaults=dict(display_name=name, sheet_name=sheet,
                                     sort_order=sort, description=desc))
    Settings.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("lens_workflow", "0016_pricing_v2_models")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
