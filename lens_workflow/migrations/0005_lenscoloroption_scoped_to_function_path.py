# Third-pass adjustment: Color no longer belongs to a specific Index tier —
# a color's extra price never varies by index (confirmed against the
# reference data), so it's rescoped to the Function Path instead. This lets
# the Sun Type step disappear entirely: two sibling function paths (Solid /
# Polarized-Mirrored) can show their colors together in one merged step, and
# whichever color the customer picks resolves which sibling applies to the
# Index step that follows.
#
# Existing LensColorOption rows are wiped first (same precedent as earlier
# passes this project — this data is reseeded from scratch by
# import_lens_reference_guide, not hand-edited data worth preserving).
# CompleteSet.color_option is SET_NULL on delete, so this doesn't touch any
# existing CompleteSet/order rows beyond clearing that one FK.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0004_prescription_first_and_index_recommendations'),
    ]

    operations = [
        migrations.RunSQL(
            sql='DELETE FROM "LensColorOption";',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RemoveIndex(
            model_name='lenscoloroption',
            name='LensColorOp_index_o_f821e4_idx',
        ),
        migrations.RemoveConstraint(
            model_name='lenscoloroption',
            name='uq_lens_color_option_index_color',
        ),
        migrations.RemoveField(
            model_name='lenscoloroption',
            name='index_option',
        ),
        migrations.AddField(
            model_name='lenscoloroption',
            name='function_path',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='color_options', to='lens_workflow.lensfunctionpath'),
        ),
        migrations.AddConstraint(
            model_name='lenscoloroption',
            constraint=models.UniqueConstraint(fields=('function_path', 'color_name'), name='uq_lens_color_option_function_color'),
        ),
        migrations.AddIndex(
            model_name='lenscoloroption',
            index=models.Index(fields=['function_path', 'is_active', 'sort_order'], name='LensColorOp_functio_1a7d65_idx'),
        ),
        migrations.AlterModelOptions(
            name='lenscoloroption',
            options={'ordering': ['function_path__sort_order', 'sort_order', 'id'], 'verbose_name': 'Lens Color Option', 'verbose_name_plural': 'Lens Color Options'},
        ),
    ]
