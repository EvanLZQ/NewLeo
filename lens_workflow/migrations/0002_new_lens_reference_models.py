# Generated for the Lens Selection Reference Guide rebuild.
# Step 1 of 3: create the new tables alongside the old ones (Order.CompleteSet
# still points at the old LensOption-based tables until the Order migration
# that follows this one switches its FKs over).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LensType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=50, unique=True)),
                ('label', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('is_prescription_required', models.BooleanField(default=True, help_text='False for NON-PRESCRIPTION — frontend uses this to skip the Prescription step.')),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Lens Type',
                'verbose_name_plural': 'Lens Types',
                'db_table': 'LensType',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LensCoating',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(choices=[('NO_AR', 'No AR Coating'), ('STANDARD_AR', 'Standard AR Coating'), ('PREMIUM_AR', 'Premium AR Coating'), ('HYDRO', 'Hydrophobic'), ('OLEO', 'Oleophobic')], max_length=50, unique=True)),
                ('label', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('price', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Lens Coating',
                'verbose_name_plural': 'Lens Coatings',
                'db_table': 'LensWorkflowCoating',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LensFunctionPath',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('function_code', models.CharField(choices=[('CLEAR', 'Clear'), ('BLUE_LIGHT_BLOCKING', 'Blue Light Blocking'), ('SUN', 'Sun'), ('LIGHT_ADJUSTING', 'Light Adjusting')], max_length=50)),
                ('function_label', models.CharField(max_length=100)),
                ('function_description', models.TextField(blank=True)),
                ('sun_type', models.CharField(blank=True, choices=[('SOLID', 'Solid'), ('POLARIZED_MIRRORED', 'Polarized / Mirrored')], default='', max_length=30)),
                ('color_required', models.BooleanField(default=False)),
                ('extra_price', models.DecimalField(decimal_places=2, default=0, help_text='Step 2 extra price (currently 0 for every row in the reference guide).', max_digits=8)),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('lens_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='function_paths', to='lens_workflow.lenstype')),
            ],
            options={
                'verbose_name': 'Lens Function Path',
                'verbose_name_plural': 'Lens Function Paths',
                'db_table': 'LensFunctionPath',
                'ordering': ['lens_type__sort_order', 'sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LensIndexOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tier', models.CharField(max_length=50)),
                ('option_label', models.CharField(max_length=150)),
                ('index_value', models.DecimalField(decimal_places=2, max_digits=4)),
                ('price', models.DecimalField(decimal_places=2, max_digits=8)),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('function_path', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='index_options', to='lens_workflow.lensfunctionpath')),
            ],
            options={
                'verbose_name': 'Lens Index Option',
                'verbose_name_plural': 'Lens Index Options',
                'db_table': 'LensIndexOption',
                'ordering': ['function_path__sort_order', 'sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='LensColorOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('color_name', models.CharField(max_length=100)),
                ('extra_price', models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('index_option', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='color_options', to='lens_workflow.lensindexoption')),
            ],
            options={
                'verbose_name': 'Lens Color Option',
                'verbose_name_plural': 'Lens Color Options',
                'db_table': 'LensColorOption',
                'ordering': ['index_option__sort_order', 'sort_order', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='lensfunctionpath',
            constraint=models.UniqueConstraint(fields=('lens_type', 'function_code', 'sun_type'), name='uq_lens_function_path'),
        ),
        migrations.AddIndex(
            model_name='lensfunctionpath',
            index=models.Index(fields=['lens_type', 'is_active', 'sort_order'], name='LensFunctio_lens_ty_19afc4_idx'),
        ),
        migrations.AddIndex(
            model_name='lensfunctionpath',
            index=models.Index(fields=['function_code', 'is_active'], name='LensFunctio_functio_59bfbe_idx'),
        ),
        migrations.AddIndex(
            model_name='lensindexoption',
            index=models.Index(fields=['function_path', 'is_active', 'sort_order'], name='LensIndexOp_functio_f3ce9b_idx'),
        ),
        migrations.AddConstraint(
            model_name='lenscoloroption',
            constraint=models.UniqueConstraint(fields=('index_option', 'color_name'), name='uq_lens_color_option_index_color'),
        ),
        migrations.AddIndex(
            model_name='lenscoloroption',
            index=models.Index(fields=['index_option', 'is_active', 'sort_order'], name='LensColorOp_index_o_f821e4_idx'),
        ),
    ]
