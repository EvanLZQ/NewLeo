# Generated by Django 4.2.2 on 2023-07-14 04:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Customer', '0007_alter_customerinfo_saved_prescription'),
    ]

    operations = [
        migrations.RenameField(
            model_name='customerinfo',
            old_name='email',
            new_name='username',
        ),
    ]
