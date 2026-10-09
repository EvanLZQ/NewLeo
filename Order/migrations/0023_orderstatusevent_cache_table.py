import django.db.models.deletion
from django.core.management import call_command
from django.db import migrations, models


def create_cache_table(apps, schema_editor):
    # settings.CACHES now points at a database cache (shared by every
    # gunicorn worker — the old per-process default cache made the login/
    # password-reset/order-tracking rate limits leaky). It needs its table
    # to exist before the first request, and `migrate` already runs on every
    # deploy, so create it here instead of asking for a manual
    # `createcachetable` step. No-op if the table already exists.
    call_command('createcachetable', verbosity=0)


class Migration(migrations.Migration):

    dependencies = [
        ('Order', '0022_orderinfo_customs_fee'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderStatusEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_events', to='Order.orderinfo')),
            ],
            options={
                'db_table': 'OrderStatusEvent',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.RunPython(create_cache_table, migrations.RunPython.noop),
    ]
