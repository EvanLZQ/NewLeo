# Generated by Django 4.1.7 on 2023-04-27 22:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("Order", "0002_completeset_ordercompleteprescription"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderUpdates",
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
                ("title", models.CharField(max_length=50)),
                ("details", models.TextField()),
                ("by", models.CharField(max_length=50)),
                (
                    "OrderID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Order.orderinfo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order Update",
                "verbose_name_plural": "Order Updates",
                "db_table": "OrderUpdates",
            },
        ),
    ]