# Generated by Django 4.2.2 on 2023-07-05 21:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Lens', '0005_alter_lensoptions_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='lensoptions',
            name='image_url',
            field=models.CharField(default='', max_length=4096),
        ),
    ]
