# Generated by Django 4.2.2 on 2023-10-28 02:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Product', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='productinstance',
            name='carousel_img',
        ),
        migrations.RemoveField(
            model_name='productinstance',
            name='detail_img',
        ),
        migrations.CreateModel(
            name='ProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='product_images/')),
                ('alt', models.CharField(max_length=100)),
                ('image_type', models.CharField(choices=[('carousel', 'Carousel'), ('detail', 'Detail')], default='carousel', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('productInstance', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='productImage', to='Product.productinstance')),
            ],
            options={
                'verbose_name': 'Product Image',
                'verbose_name_plural': 'Product Images',
                'db_table': 'ProductImage',
            },
        ),
    ]
