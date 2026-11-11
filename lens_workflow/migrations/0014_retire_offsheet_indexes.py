"""Retire catalog indexes the current price sheet does not sell.

Driving 1.61, Safety 1.59 (polycarbonate), and Elite 1.71 are matched by
name and index, not by primary key, and set inactive. The rows stay so an
old order can still point at them.

The stored recommendation rules are rewritten to the steep-meridian table
so the admin does not keep showing spherical-equivalent brackets. The
shopping flow reads the code table in lens_workflow.views, not these rows
and not the price sheet's Recommended SE column.
"""
from decimal import Decimal

from django.db import migrations, models


RETIRED = (
    (Decimal("1.61"), ("driving",)),
    (Decimal("1.59"), ("safety", "polycarbonate")),
    (Decimal("1.71"), ("elite",)),
)

# (max power, neighbor index strings, recommended catalog index)
BRACKETS = (
    ("2.00", ["1.50", "1.56", "1.60", "1.61"], "1.50"),
    ("4.00", ["1.56", "1.60", "1.61", "1.67"], "1.61"),
    ("6.00", ["1.60", "1.61", "1.67", "1.74"], "1.67"),
    (None, ["1.67", "1.74"], "1.74"),
)


def deactivate_retired_index_options(apps, schema_editor):
    IndexOption = apps.get_model("lens_workflow", "LensIndexOption")
    for index_value, needles in RETIRED:
        for row in IndexOption.objects.filter(index_value=index_value):
            blob = f"{row.tier} {row.option_label}".lower()
            if any(needle in blob for needle in needles) and row.is_active:
                row.is_active = False
                row.save(update_fields=["is_active"])


def rewrite_recommendation_rules(apps, schema_editor):
    Rule = apps.get_model("lens_workflow", "LensIndexRecommendationRule")
    Rule.objects.all().delete()
    for category in ("SINGLE_VISION", "BIFOCAL_PROGRESSIVE"):
        for position, (limit, available, recommended) in enumerate(BRACKETS, start=1):
            Rule.objects.create(
                category=category,
                direction="",
                max_combined_power=limit,
                available_index_values=available,
                recommended_index_value=recommended,
                sort_order=position * 10,
                notes="Absolute steep meridian. Recommended SE is not used.",
            )


class Migration(migrations.Migration):

    dependencies = [
        ("lens_workflow", "0013_price_table_color_depth_coating"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lensindexrecommendationrule",
            name="max_combined_power",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    "Upper bound in diopters for the absolute steep meridian "
                    "(larger of |S| and |S+C| on the stronger eye). "
                    "Null means no upper bound (the last/highest bracket)."
                ),
                max_digits=5,
                null=True,
            ),
        ),
        migrations.RunPython(deactivate_retired_index_options, migrations.RunPython.noop),
        migrations.RunPython(rewrite_recommendation_rules, migrations.RunPython.noop),
    ]
