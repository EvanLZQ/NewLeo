# Shopping-flow rebuild (Phase 1, part 1 of 2): wipe LensIndexOption,
# LensColorOption, and LensFunctionPath — all reseeded from scratch once the
# new mind-map-driven data lands (see the "Shopping Flow Rebuild" plan).
# Same precedent as every earlier reference-data restructuring this project:
# these are catalog/pricing rows, not customer records, and get rebuilt
# wholesale rather than migrated field-by-field.
#
# Has to be a separate migration from the schema change in 0009 — Postgres
# queues deferred FK-trigger events on a table when rows referencing it are
# deleted (CompleteSet has FKs to all three of these), and refuses to
# ALTER TABLE that same table again within the same transaction. Splitting
# the DELETE into its own migration lets it commit first. Same reasoning as
# migrations 0005/0006 earlier in this app.
#
# CompleteSet.index_option / color_option / function_path are all
# on_delete=SET_NULL, but that's implemented by Django's ORM (Collector),
# not a real database-level "ON DELETE SET NULL" — raw SQL bypasses it and
# hits the actual FK constraint (NO ACTION), which blocks the DELETE if any
# CompleteSet row (a real order) still references these rows. So each
# referencing column is nulled out explicitly first, replicating what the
# ORM would have done.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0007_lenscoloroption_available_index_values'),
    ]

    operations = [
        migrations.RunSQL(
            sql='UPDATE "CompleteSet" SET index_option_id = NULL WHERE index_option_id IS NOT NULL;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='UPDATE "CompleteSet" SET color_option_id = NULL WHERE color_option_id IS NOT NULL;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='UPDATE "CompleteSet" SET function_path_id = NULL WHERE function_path_id IS NOT NULL;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='DELETE FROM "LensIndexOption";',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='DELETE FROM "LensColorOption";',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql='DELETE FROM "LensFunctionPath";',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
