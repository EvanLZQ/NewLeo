# Generated by Django 4.2.2 on 2023-12-02 03:33

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Product', '0007_alter_producttag_category'),
        ('Customer', '0015_alter_customersavedaddress_phone'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shoppinglist',
            name='customer',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shopping_list', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='WishList',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='wish_list', to=settings.AUTH_USER_MODEL)),
                ('product', models.ManyToManyField(to='Product.productinfo')),
            ],
            options={
                'verbose_name': 'Wish List',
                'verbose_name_plural': 'Wish Lists',
                'db_table': 'WishList',
            },
        ),
    ]
