# US customs/import fee — 15% of sub_total, $9 minimum, US addresses only.
# Confirmed with the business owner. Computed alongside shipping_cost (see
# OrderService.calculate_customs_fee / update_order_totals) and included in
# total_amount the same way shipping_cost already is.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Order', '0021_remove_ordertax'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderinfo',
            name='customs_fee',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=6),
        ),
    ]
