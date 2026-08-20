# Shopping-flow rebuild: CompleteSet.coating (single FK) becomes
# CompleteSet.coatings (many-to-many) so coating add-ons can stack (see
# LensCoating in lens_workflow — Anti-scratch/Anti-glare/UV-protection
# always included, Blue-light-filtering/Oleophobic/Hydrophobic optional
# add-ons). Also adds reader_strength for the new readymade-Reader Lens
# Type — the one choice that flow makes.
#
# Existing CompleteSet.coating_id values (real historical orders) are
# copied into the new coatings M2M before the old column is dropped, so no
# order history is lost — Django can't do this automatically for a
# FK -> M2M change, hence the RunPython step.

from django.db import migrations, models
import django.db.models.deletion


def copy_coating_fk_into_m2m(apps, schema_editor):
    CompleteSet = apps.get_model('Order', 'CompleteSet')
    for cs in CompleteSet.objects.exclude(coating_id=None).iterator():
        cs.coatings.add(cs.coating_id)


def noop_reverse(apps, schema_editor):
    # Not reversible without re-deriving a single "the" coating from a set
    # that might now hold more than one — intentionally a no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0009_shopping_flow_rebuild_schema'),
        ('Order', '0017_completeset_new_lens_reference_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='completeset',
            name='coatings',
            field=models.ManyToManyField(
                blank=True,
                help_text="At most one of any coatings sharing a non-empty exclusive_group "
                          "(e.g. Oleophobic/Hydrophobic) — enforced in lens_workflow's views, "
                          "not at the database level.",
                related_name='complete_sets',
                to='lens_workflow.lenscoating',
            ),
        ),
        migrations.RunPython(copy_coating_fk_into_m2m, noop_reverse),
        migrations.RemoveField(
            model_name='completeset',
            name='coating',
        ),
        migrations.AddField(
            model_name='completeset',
            name='reader_strength',
            field=models.ForeignKey(
                blank=True,
                help_text='Set only for LensType.is_reader orders — the one choice a readymade reader makes.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='complete_sets',
                to='lens_workflow.lensreaderstrength',
            ),
        ),
    ]
