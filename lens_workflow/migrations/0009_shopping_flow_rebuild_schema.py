# Shopping-flow rebuild (Phase 1, part 2 of 2): the actual schema changes.
#
# - LensIndexOption rescoped from LensFunctionPath to LensType directly —
#   the same Index/Material list and prices apply no matter which Function
#   was picked within a Lens Type, confirmed against the pricing data.
# - LensCoating: dropped the No-AR/Standard-AR/Premium-AR tiered model
#   entirely, replaced with Anti-scratch/Anti-glare/UV-protection (always
#   included) + Blue-light-filtering/Oleophobic/Hydrophobic (optional
#   add-ons, with is_included/exclusive_group driving the new multi-select
#   Coating step).
# - LensFunctionPath.function_code: added PHOTOCHROMIC and
#   BLUE_LIGHT_FILTERING, dropped LIGHT_ADJUSTING (renamed — same product).
# - LensFunctionPath.sun_type (conceptually "tint type"): now
#   SOLID/GRADIENT/MIRRORED/POLARIZED — dropped the old combined
#   POLARIZED_MIRRORED value now that Mirrored and Polarized are separately
#   priced tiers.
# - LensType.is_reader: new structural routing flag for the readymade-
#   readers Lens Type.
# - New model: LensReaderStrength.
#
# See 0008 for why the schema change is split into its own migration.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0008_wipe_stale_reference_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='LensReaderStrength',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('strength_value', models.DecimalField(decimal_places=2, help_text='e.g. 1.25 for "+1.25"', max_digits=4, unique=True)),
                ('label', models.CharField(help_text='Display label, e.g. "+1.25"', max_length=20)),
                ('price', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Lens Reader Strength',
                'verbose_name_plural': 'Lens Reader Strengths',
                'db_table': 'LensReaderStrength',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AlterModelOptions(
            name='lensindexoption',
            options={'ordering': ['lens_type__sort_order', 'sort_order', 'id'], 'verbose_name': 'Lens Index Option', 'verbose_name_plural': 'Lens Index Options'},
        ),
        migrations.RemoveIndex(
            model_name='lensindexoption',
            name='LensIndexOp_functio_f3ce9b_idx',
        ),
        migrations.RemoveField(
            model_name='lensindexoption',
            name='function_path',
        ),
        migrations.AddField(
            model_name='lenscoating',
            name='exclusive_group',
            field=models.CharField(blank=True, default='', help_text='Coatings sharing a non-empty group are mutually exclusive — at most one from the group can be selected together.', max_length=50),
        ),
        migrations.AddField(
            model_name='lenscoating',
            name='is_included',
            field=models.BooleanField(default=False, help_text='Always bundled free with every lens — shown as included, not offered as a choice.'),
        ),
        migrations.AddField(
            model_name='lensindexoption',
            name='lens_type',
            field=models.ForeignKey(default=None, on_delete=django.db.models.deletion.CASCADE, related_name='index_options', to='lens_workflow.lenstype'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='lenstype',
            name='is_reader',
            field=models.BooleanField(default=False, help_text="True only for the readymade-readers Lens Type. Routes to a dedicated Reader Strength step instead of Prescription, and skips Function/Tint/Color/Material/Coating entirely — straight to the review/complete step. This is a structural routing flag, not a price/tier — unlike everything else in this app it's meant to stay a fixed code branch, not admin data."),
        ),
        migrations.AlterField(
            model_name='lenscoating',
            name='code',
            field=models.CharField(choices=[('ANTI_SCRATCH', 'Anti-scratch'), ('ANTI_GLARE', 'Anti-glare'), ('UV_PROTECTION', 'UV Protection'), ('BLUE_LIGHT_FILTERING', 'Blue Light Filtering'), ('OLEOPHOBIC', 'Oleophobic'), ('HYDROPHOBIC', 'Hydrophobic')], max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name='lensfunctionpath',
            name='function_code',
            field=models.CharField(choices=[('CLEAR', 'Clear'), ('BLUE_LIGHT_FILTERING', 'Blue Light Filtering'), ('PHOTOCHROMIC', 'Light-responsive / Photochromic'), ('SUN', 'Sun')], max_length=50),
        ),
        migrations.AlterField(
            model_name='lensfunctionpath',
            name='sun_type',
            field=models.CharField(blank=True, choices=[('SOLID', 'Solid'), ('GRADIENT', 'Gradient'), ('MIRRORED', 'Mirrored'), ('POLARIZED', 'Polarized')], default='', help_text="Tint type — only set when function_code == SUN. Field name kept as sun_type for continuity with existing code; conceptually this is the workflow's 'Tint Type' step.", max_length=30),
        ),
        migrations.AlterField(
            model_name='lenstype',
            name='is_prescription_required',
            field=models.BooleanField(default=True, help_text='False for NON-PRESCRIPTION and READER — frontend uses this to skip the Prescription step.'),
        ),
        migrations.AddIndex(
            model_name='lensindexoption',
            index=models.Index(fields=['lens_type', 'is_active', 'sort_order'], name='LensIndexOp_lens_ty_ed2d66_idx'),
        ),
        migrations.AddConstraint(
            model_name='lensindexoption',
            constraint=models.UniqueConstraint(fields=('lens_type', 'index_value'), name='uq_lens_index_option_type_value'),
        ),
    ]
