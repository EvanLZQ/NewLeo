# Generated by Django 4.2.2 on 2023-10-28 02:04

from django.db import migrations, models
import tinymce.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BlogInfo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=100)),
                ('slug', models.SlugField(blank=True, max_length=200, null=True, unique=True)),
                ('content', tinymce.models.HTMLField()),
                ('sub_title', models.CharField(blank=True, max_length=200, null=True)),
                ('brief', models.TextField(blank=True, null=True)),
                ('home_page_img', models.ImageField(blank=True, null=True, upload_to='blog_images/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Blog',
                'verbose_name_plural': 'Blogs',
                'db_table': 'BlogInfo',
            },
        ),
    ]
