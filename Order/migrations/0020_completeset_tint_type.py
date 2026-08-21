# tint_type is a separate FK from function_path: for Sun, function_path holds
# the base Sun row and tint_type holds the specific Solid/Gradient/Mirrored/
# Polarized LensFunctionPath the customer picked. Both extra_price values
# stack into sub_total (see OrderService.calculate_complete_set_sub_total).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0009_shopping_flow_rebuild_schema'),
        # 0019_orderinfo_field_drift_catchup was deleted — it duplicated
        # order_number/order_status/payment_status changes production already
        # had via 0017_alter_orderinfo_order_number_and_more (recovered into
        # this repo alongside the 0018 merge — see that migration's comment).
        ('Order', '0018_completeset_coatings_reader_strength'),
    ]

    operations = [
        migrations.AddField(
            model_name='completeset',
            name='tint_type',
            field=models.ForeignKey(
                blank=True,
                help_text="Set only when function_path is the Sun function: the specific "
                          "tint-type LensFunctionPath (Solid/Gradient/Mirrored/Polarized) the "
                          "customer picked. Its extra_price stacks on top of function_path's own "
                          "(the Sun base price) — both are added into sub_total independently.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='complete_sets_as_tint',
                to='lens_workflow.lensfunctionpath',
            ),
        ),
    ]
