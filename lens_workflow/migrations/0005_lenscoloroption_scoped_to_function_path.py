# Third-pass adjustment (part 1 of 2): wipe existing LensColorOption rows
# before rescoping the model in 0006. This has to be its own migration —
# not just its own operation — because Postgres queues deferred FK-trigger
# events on this table when rows are deleted (CompleteSet.color_option
# references it), and refuses ALTER TABLE on the same table while those
# events are still pending in the same transaction. Splitting the DELETE
# into its own migration lets it commit before 0006's ALTER TABLE ops run.
#
# CompleteSet.color_option is on_delete=SET_NULL, but that behavior is
# implemented by Django's ORM (Collector), not as a real "ON DELETE SET
# NULL" constraint in Postgres — raw SQL bypasses it entirely and just hits
# the underlying FK constraint (NO ACTION), which blocks the DELETE if any
# CompleteSet row (e.g. a real order) still references a color option. So
# this explicitly nulls out those references first, replicating what
# Django's ORM would have done, before the DELETE.
#
# This data is reseeded from scratch by import_lens_reference_guide, not
# hand-edited data worth preserving.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0004_prescription_first_and_index_recommendations'),
    ]

    operations = [
        migrations.RunSQL(
            sql='UPDATE "CompleteSet" SET color_option_id = NULL WHERE color_option_id IS NOT NULL;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='DELETE FROM "LensColorOption";',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
