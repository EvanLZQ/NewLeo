# Generated by Django 4.1.7 on 2023-04-28 04:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Product", "0003_alter_productfeature_product_and_more"),
        ("Order", "0003_orderupdates"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="completeset",
            options={
                "verbose_name": "Complete Set",
                "verbose_name_plural": "Complete Sets",
            },
        ),
        migrations.AlterField(
            model_name="orderinfo",
            name="product",
            field=models.ManyToManyField(
                blank=True, through="Order.OrderLineItem", to="Product.productinfo"
            ),
        ),
    ]
