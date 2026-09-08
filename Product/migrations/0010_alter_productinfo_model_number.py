from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Product', '0009_productinstance_price_not_null'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productinfo',
            name='model_number',
            field=models.CharField(db_index=True, max_length=20),
        ),
    ]
