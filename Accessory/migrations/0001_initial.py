# Generated by Django 4.1.7 on 2023-04-28 04:30

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("Order", "0004_alter_completeset_options_alter_orderinfo_product"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccessoryInfo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("slug", models.SlugField(max_length=200, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("type", models.CharField(max_length=100)),
                (
                    "price",
                    models.DecimalField(decimal_places=2, default=0, max_digits=5),
                ),
                ("description", models.TextField(blank=True)),
                ("color", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Accessory",
                "verbose_name_plural": "Accessories",
                "db_table": "AccessoryInfo",
            },
        ),
        migrations.CreateModel(
            name="OrderLineAccessory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity",
                    models.IntegerField(
                        default=1,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                (
                    "accessoryID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Accessory.accessoryinfo",
                    ),
                ),
                (
                    "orderID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Order.orderinfo",
                    ),
                ),
            ],
            options={"db_table": "order_line_accessory",},
        ),
        migrations.AddField(
            model_name="accessoryinfo",
            name="order",
            field=models.ManyToManyField(
                blank=True, through="Accessory.OrderLineAccessory", to="Order.orderinfo"
            ),
        ),
        migrations.CreateModel(
            name="AccessoryImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("image_type", models.CharField(blank=True, max_length=200)),
                ("name", models.CharField(max_length=100)),
                ("path", models.URLField()),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "accessoryID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Accessory.accessoryinfo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Accessory Image",
                "verbose_name_plural": "Accessory Images",
                "db_table": "AccessoryImage",
            },
        ),
    ]