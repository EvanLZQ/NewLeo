# Generated by Django 4.2.2 on 2023-11-23 01:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Customer', '0010_delete_user_customerinfo_date_joined_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customerinfo',
            name='birth_date',
            field=models.CharField(blank=True, max_length=6, null=True),
        ),
    ]
