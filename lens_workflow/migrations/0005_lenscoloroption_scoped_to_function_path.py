# Third-pass adjustment (part 1 of 2): wipe existing LensColorOption rows
# before rescoping the model in 0006. This has to be its own migration —
# not just its own operation — because Postgres queues deferred FK-trigger
# events on this table when rows are deleted (CompleteSet.color_option
# references it), and refuses ALTER TABLE on the same table while those
# events are still pending in the same transaction. Splitting the DELETE
# into its own migration lets it commit before 0006's ALTER TABLE ops run.
#
# This data is reseeded from scratch by import_lens_reference_guide, not
# hand-edited data worth preserving. CompleteSet.color_option is SET_NULL
# on delete, so this doesn't touch any existing CompleteSet/order rows
# beyond clearing that one FK.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0004_prescription_first_and_index_recommendations'),
    ]

    operations = [
        migrations.RunSQL(
            sql='DELETE FROM "LensColorOption";',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
