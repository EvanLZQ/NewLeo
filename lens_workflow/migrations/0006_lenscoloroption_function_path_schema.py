# Third-pass adjustment (part 2 of 2): the actual schema rescoping —
# LensColorOption.function_path replaces LensColorOption.index_option. See
# 0005 for why this is a separate migration (Postgres deferred-trigger /
# ALTER TABLE ordering constraint after the row-wiping DELETE).
#
# A color's extra price never varies by index tier (confirmed against the
# reference data), so it's rescoped to the Function Path instead. This lets
# the Sun Type step disappear entirely: two sibling function paths (Solid /
# Polarized-Mirrored) can show their colors together in one merged step, and
# whichever color the customer picks resolves which sibling applies to the
# Index step that follows.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0005_lenscoloroption_scoped_to_function_path'),
    ]

    operations = [
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
