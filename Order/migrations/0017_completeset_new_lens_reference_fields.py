# Step 2 of 3 in the Lens Selection Reference Guide rebuild: point CompleteSet
# at the new lens_workflow models instead of the retiring LensOption graph.
# No data migration is needed — these fields only ever held dummy/seed data
# from the pre-launch lens_workflow scaffolding.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0002_new_lens_reference_models'),
        ('Order', '0016_backfill_order_email'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='completeset',
            name='usage',
        ),
        migrations.RemoveField(
            model_name='completeset',
            name='color',
        ),
        migrations.RemoveField(
            model_name='completeset',
            name='index',
        ),
        migrations.RemoveField(
            model_name='completeset',
            name='coating',
        ),
        migrations.AddField(
            model_name='completeset',
            name='lens_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='complete_sets', to='lens_workflow.lenstype'),
        ),
        migrations.AddField(
            model_name='completeset',
            name='function_path',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='complete_sets', to='lens_workflow.lensfunctionpath'),
        ),
        migrations.AddField(
            model_name='completeset',
            name='index_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='complete_sets', to='lens_workflow.lensindexoption'),
        ),
        migrations.AddField(
            model_name='completeset',
            name='color_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='complete_sets', to='lens_workflow.lenscoloroption'),
        ),
        migrations.AddField(
            model_name='completeset',
            name='coating',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='complete_sets', to='lens_workflow.lenscoating'),
        ),
    ]
