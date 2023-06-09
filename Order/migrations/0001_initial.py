# Generated by Django 4.1.7 on 2023-04-16 18:45

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("General", "0001_initial"),
        ("Product", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderInfo",
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
                ("email", models.EmailField(max_length=254)),
                ("order_number", models.CharField(max_length=20)),
                (
                    "order_status",
                    models.CharField(
                        choices=[
                            ("NULL", "Null"),
                            ("PROCESSING", "Processing"),
                            ("SHIPPED", "Shipped"),
                            ("DELIVERED", "Delivered"),
                            ("COMPLETE", "Complete"),
                            ("CANCELED", "Canceled"),
                            ("REFUND", "Refund"),
                        ],
                        default="PROCESSING",
                        max_length=50,
                    ),
                ),
                ("refound_status", models.CharField(blank=True, max_length=20)),
                (
                    "refound_amount",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=5),
                ),
                (
                    "payment_status",
                    models.CharField(
                        choices=[
                            ("UNPAID", "Unpaid"),
                            ("PAID", "Paid"),
                            ("PROCESSING", "Processing"),
                            ("NULL", "Null"),
                        ],
                        default="UNPAID",
                        max_length=50,
                    ),
                ),
                ("payment_type", models.CharField(max_length=20, null=True)),
                (
                    "order_device",
                    models.CharField(
                        choices=[
                            ("WINDOWS", "Windows"),
                            ("MACOS", "Mac OS"),
                            ("ANDROID", "Android"),
                            ("IOS", "ios"),
                            ("UNKNOWN", "Unknown"),
                        ],
                        default="UNKNOWN",
                        max_length=50,
                    ),
                ),
                (
                    "store_credit_used",
                    models.DecimalField(decimal_places=2, default=0, max_digits=5),
                ),
                (
                    "store_credit_gained",
                    models.DecimalField(decimal_places=2, default=0, max_digits=5),
                ),
                ("shipping_company", models.CharField(blank=True, max_length=50)),
                ("tracking_number", models.CharField(blank=True, max_length=50)),
                (
                    "shipping_cost",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=5),
                ),
                (
                    "discount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=5),
                ),
                (
                    "accessory_total",
                    models.DecimalField(decimal_places=2, default=0, max_digits=5),
                ),
                ("sub_total", models.DecimalField(decimal_places=2, max_digits=6)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=6)),
                ("comment", models.TextField()),
                ("issue_order", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Order",
                "verbose_name_plural": "Orders",
                "db_table": "OrderInfo",
            },
        ),
        migrations.CreateModel(
            name="OrderTax",
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
                ("tax_number", models.CharField(max_length=100)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=5)),
                ("gst", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("hst", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("qst", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("pst", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "OrderID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Order.orderinfo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order Tax",
                "verbose_name_plural": "Order Tax",
                "db_table": "OrderTax",
            },
        ),
        migrations.CreateModel(
            name="OrderLineItem",
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
                        default=0,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(99),
                        ],
                    ),
                ),
                (
                    "OrderID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Order.orderinfo",
                    ),
                ),
                (
                    "ProductID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Product.productinfo",
                    ),
                ),
            ],
            options={"db_table": "order_line_item",},
        ),
        migrations.AddField(
            model_name="orderinfo",
            name="product",
            field=models.ManyToManyField(
                through="Order.OrderLineItem", to="Product.productinfo"
            ),
        ),
        migrations.CreateModel(
            name="OrderImage",
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
                ("image_type", models.CharField(max_length=20)),
                ("name", models.CharField(max_length=20)),
                ("path", models.URLField()),
                ("description", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "OrderID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Order.orderinfo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order Image",
                "verbose_name_plural": "Order Images",
                "db_table": "OrderImage",
            },
        ),
        migrations.CreateModel(
            name="OrderHasAddress",
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
                    "AddressID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="General.address",
                    ),
                ),
                (
                    "OrderID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Order.orderinfo",
                    ),
                ),
            ],
            options={"db_table": "order_has_address",},
        ),
    ]
