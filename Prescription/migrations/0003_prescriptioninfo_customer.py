# Generated by Django 4.2.2 on 2023-11-28 20:14

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Prescription', '0002_alter_prescriptionprism_prescription'),
    ]

    operations = [
        migrations.AddField(
            model_name='prescriptioninfo',
            name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='prescription', to=settings.AUTH_USER_MODEL),
        ),
    ]
