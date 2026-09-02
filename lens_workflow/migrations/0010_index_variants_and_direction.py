# New pricing sheet (Eyelovewear Pricing(1).xlsx) follow-up, confirmed with
# the business owner:
#
# - LensIndexOption's uniqueness now includes tier, not just
#   (lens_type, index_value) — lets a single refractive index have more
#   than one priced variant under the same Lens Type (SVD's new "1.61
#   Driving", alongside the existing plain "1.61 Popular").
# - LensIndexRecommendationRule gains `direction` so Single Vision can use
#   real farsighted-specific bracket data from the pricing sheet's
#   "折射率算法" sheet, instead of reusing the nearsighted brackets for
#   every farsighted prescription (a known gap called out in this app's
#   original seed script). Bifocal/Progressive has no farsighted-specific
#   source data, so its rows stay direction="" (applies to both signs).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lens_workflow', '0009_shopping_flow_rebuild_schema'),
    ]

    operations = [
        migrations.AddField(
            model_name='lensindexrecommendationrule',
            name='direction',
            field=models.CharField(
                blank=True, default='', max_length=20,
                choices=[('NEARSIGHTED', 'Nearsighted'), ('FARSIGHTED', 'Farsighted')],
                help_text='Blank = applies to both directions (used where no direction-specific '
                          'bracket data exists). Set when this bracket only applies to one sign.',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='lensindexoption',
            name='uq_lens_index_option_type_value',
        ),
        migrations.AddConstraint(
            model_name='lensindexoption',
            constraint=models.UniqueConstraint(
                fields=['lens_type', 'index_value', 'tier'],
                name='uq_lens_index_option_type_value_tier',
            ),
        ),
    ]
