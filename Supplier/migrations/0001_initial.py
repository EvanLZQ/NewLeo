# Generated by Django 4.1.7 on 2023-05-04 01:27

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SupplierInfo",
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
                ("name", models.CharField(max_length=100)),
                ("website", models.URLField(blank=True)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(max_length=15)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Supplier",
                "verbose_name_plural": "Suppliers",
                "db_table": "SupplierInfo",
            },
        ),
    ]