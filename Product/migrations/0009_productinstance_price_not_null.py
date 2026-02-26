from django.db import migrations, models


def fill_price_from_product(apps, schema_editor):
    ProductInstance = apps.get_model('Product', 'ProductInstance')
    for instance in ProductInstance.objects.filter(price__isnull=True).select_related('product'):
        if instance.product_id:
            instance.price = instance.product.price
            instance.save(update_fields=['price'])


class Migration(migrations.Migration):

    dependencies = [
        ('Product', '0008_alter_productpromotion_productinstance'),
    ]

    operations = [
        migrations.RunPython(fill_price_from_product, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='productinstance',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=5),
        ),
    ]
