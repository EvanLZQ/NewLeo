# Second-pass adjustment to the lens selection rebuild:
#   - Blue Light Blocking retires as a Function, reborn as a Coating option.
#   - LensType gains an index-recommendation category (blank = no recommendation,
#     e.g. Non-Prescription).
#   - New LensIndexRecommendationRule table drives the Index step's
#     recommend-first / "choose your own" UI.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0003_remove_old_generic_option_graph'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lensfunctionpath',
            name='function_code',
            field=models.CharField(choices=[('CLEAR', 'Clear'), ('SUN', 'Sun'), ('LIGHT_ADJUSTING', 'Light Adjusting')], max_length=50),
        ),
        migrations.AddField(
            model_name='lenscoating',
            name='is_recommended',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='lenscoating',
            name='code',
            field=models.CharField(choices=[('NO_AR', 'No AR Coating'), ('STANDARD_AR', 'Standard AR Coating'), ('PREMIUM_AR', 'Premium AR Coating'), ('BLUE_LIGHT_FILTERING', 'Blue Light Filtering'), ('HYDRO', 'Hydrophobic'), ('OLEO', 'Oleophobic')], max_length=50, unique=True),
        ),
        migrations.AddField(
            model_name='lenstype',
            name='index_recommendation_category',
            field=models.CharField(blank=True, choices=[('SINGLE_VISION', 'Single Vision'), ('BIFOCAL_PROGRESSIVE', 'Bifocal / Progressive')], default='', help_text='Blank for lens types with no index recommendation (e.g. Non-Prescription).', max_length=30),
        ),
        migrations.CreateModel(
            name='LensIndexRecommendationRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.CharField(choices=[('SINGLE_VISION', 'Single Vision'), ('BIFOCAL_PROGRESSIVE', 'Bifocal / Progressive')], max_length=30)),
                ('max_combined_power', models.DecimalField(blank=True, decimal_places=2, help_text='Upper bound in diopters for |sphere|+|cylinder| (worse eye). Null means no upper bound (the last/highest bracket).', max_digits=5, null=True)),
                ('available_index_values', models.JSONField(help_text='Index values selectable in this bracket, e.g. ["1.56", "1.61"].')),
                ('recommended_index_value', models.CharField(max_length=10)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Lens Index Recommendation Rule',
                'verbose_name_plural': 'Lens Index Recommendation Rules',
                'db_table': 'LensIndexRecommendationRule',
                'ordering': ['category', 'sort_order'],
            },
        ),
    ]
