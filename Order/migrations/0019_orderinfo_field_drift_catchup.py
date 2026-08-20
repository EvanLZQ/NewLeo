# Pre-existing drift, unrelated to the shopping-flow rebuild: OrderInfo's
# order_number/order_status/payment_status fields already had db_index and
# their current choices in models.py, but no migration had ever been
# generated for them (predates this rebuild — surfaced by makemigrations
# while working on 0018, kept separate since it's incidental).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Order', '0018_completeset_coatings_reader_strength'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderinfo',
            name='order_number',
            field=models.CharField(db_index=True, max_length=20),
        ),
        migrations.AlterField(
            model_name='orderinfo',
            name='order_status',
            field=models.CharField(choices=[('NULL', 'Null'), ('PROCESSING', 'Processing'), ('SHIPPED', 'Shipped'), ('DELIVERED', 'Delivered'), ('COMPLETE', 'Complete'), ('CANCELED', 'Canceled'), ('REFUND', 'Refund')], db_index=True, default='PROCESSING', max_length=50),
        ),
        migrations.AlterField(
            model_name='orderinfo',
            name='payment_status',
            field=models.CharField(choices=[('UNPAID', 'Unpaid'), ('PAID', 'Paid'), ('PROCESSING', 'Processing'), ('NULL', 'Null')], db_index=True, default='UNPAID', max_length=50),
        ),
    ]
