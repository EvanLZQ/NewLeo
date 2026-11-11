"""Shopper copy for index notes, and 1.74 on progressive and bifocal.

The premium price sheet has 1.74 cells for Progressive and Bifocal. The
catalog add-on matches the existing 1.74 row (or 79.95 when that row is
absent). It is not a new sheet price.

Notes are rewritten to shopper language. Material and Abbe stay on their
own fields.
"""
from decimal import Decimal

from django.db import migrations


SHOPPER_NOTES = {
    "1.50": (
        "Our clearest lens. A good choice for mild prescriptions, where a "
        "thinner lens would not change how the glasses look."
    ),
    "1.56": "A little thinner than our clearest lens, for a small step up in price.",
    "1.61": "Thinner and light, with clear vision for everyday wear.",
    "1.67": "A thinner, lighter lens for stronger prescriptions.",
    "1.74": "Our thinnest lens, for strong prescriptions. It looks best in a full frame.",
}


def rewrite_index_notes(apps, schema_editor):
    Option = apps.get_model("lens_workflow", "LensIndexOption")
    for index_value, note in SHOPPER_NOTES.items():
        Option.objects.filter(index_value=Decimal(index_value)).update(notes=note)


def add_progressive_and_bifocal_174(apps, schema_editor):
    LensType = apps.get_model("lens_workflow", "LensType")
    Option = apps.get_model("lens_workflow", "LensIndexOption")
    for code in ("PROGRESSIVE", "BIFOCAL"):
        lens_type = LensType.objects.filter(code=code).first()
        if lens_type is None:
            continue
        row = Option.objects.filter(
            lens_type=lens_type, index_value=Decimal("1.74"), tier="Premium").first()
        if row is not None:
            row.is_active = True
            row.notes = SHOPPER_NOTES["1.74"]
            row.save(update_fields=["is_active", "notes"])
            continue
        price = Decimal("79.95")
        label = "Premium - 1.74 Index"
        svd = LensType.objects.filter(code="SVD").first()
        if svd is not None:
            source = Option.objects.filter(
                lens_type=svd, index_value=Decimal("1.74"), tier="Premium").first()
            if source is not None:
                price = source.price
                label = source.option_label
        Option.objects.create(
            lens_type=lens_type,
            tier="Premium",
            option_label=label,
            index_value=Decimal("1.74"),
            price=price,
            notes=SHOPPER_NOTES["1.74"],
            sort_order=50,
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("lens_workflow", "0014_retire_offsheet_indexes"),
    ]

    operations = [
        migrations.RunPython(rewrite_index_notes, migrations.RunPython.noop),
        migrations.RunPython(add_progressive_and_bifocal_174, migrations.RunPython.noop),
    ]
