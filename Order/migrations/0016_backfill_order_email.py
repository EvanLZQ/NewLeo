from django.db import migrations


def backfill_order_emails(apps, schema_editor):
    OrderInfo = apps.get_model('Order', 'OrderInfo')
    orders = (
        OrderInfo.objects
        .filter(email='', customer__isnull=False)
        .select_related('customer')
    )
    count = 0
    for order in orders:
        if order.customer.email:
            OrderInfo.objects.filter(pk=order.pk).update(email=order.customer.email)
            count += 1
    print(f'Backfilled email for {count} order(s).')


class Migration(migrations.Migration):

    dependencies = [
        ('Order', '0015_alter_completeset_coating_alter_completeset_color_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_order_emails, migrations.RunPython.noop),
    ]
