# Generated by Django 4.1.7 on 2023-04-27 15:03

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("Prescription", "0001_initial"),
        ("Customer", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="shoppinglist", old_name="customer", new_name="CustomerID",
        ),
        migrations.RenameField(
            model_name="shoppinglist", old_name="product", new_name="ProductID",
        ),
        migrations.CreateModel(
            name="CustomerSavedPrescription",
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
                    "CustomerID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Customer.customerinfo",
                    ),
                ),
                (
                    "PrescriptionID",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="Prescription.prescriptioninfo",
                    ),
                ),
            ],
            options={"db_table": "customer_saved_prescription",},
        ),
    ]