from django.db import migrations, models


class Migration(migrations.Migration):
    """The price file now has separate Color, Depth and Coating columns (it used
    to have Coating Main / Coating Add-on, which held colors, tint depths and
    coatings mixed together). The table is replaced wholesale by each upload,
    so existing rows are simply carried over under the new names."""

    dependencies = [
        ("lens_workflow", "0012_lens_price_table"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="lenspriceblock",
            name="uniq_lens_price_block",
        ),
        migrations.RenameField(
            model_name="lenspriceblock",
            old_name="coating_main",
            new_name="color",
        ),
        migrations.RenameField(
            model_name="lenspriceblock",
            old_name="coating_add_on",
            new_name="depth",
        ),
        migrations.AlterField(
            model_name="lenspriceblock",
            name="depth",
            field=models.CharField(default="N", max_length=50),
        ),
        migrations.AddField(
            model_name="lenspriceblock",
            name="coating",
            field=models.CharField(default="N", max_length=100),
        ),
        migrations.AddConstraint(
            model_name="lenspriceblock",
            constraint=models.UniqueConstraint(
                fields=("tier", "prescription_type", "lens_type", "color", "depth", "coating", "lens_index"),
                name="uniq_lens_price_block",
            ),
        ),
    ]
