# Generated by Django 4.1.7 on 2023-04-27 22:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Product", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="productdimension",
            name="slug",
            field=models.SlugField(max_length=200, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="productfeature",
            name="slug",
            field=models.SlugField(max_length=200, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="productimage",
            name="slug",
            field=models.SlugField(max_length=200, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="productinfo",
            name="slug",
            field=models.SlugField(max_length=200, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="productreview",
            name="slug",
            field=models.SlugField(max_length=200, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="producttag",
            name="slug",
            field=models.SlugField(max_length=200, null=True, unique=True),
        ),
    ]