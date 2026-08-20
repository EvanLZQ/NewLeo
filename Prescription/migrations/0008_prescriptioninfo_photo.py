# Reserved field for the deferred "upload a photo" prescription flow — see
# the Shopping Flow Rebuild plan, §8. No upload UI or processing yet.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Prescription', '0007_alter_prescriptioninfo_axis_l_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='prescriptioninfo',
            name='photo',
            field=models.ImageField(
                blank=True,
                help_text="Reserved for the deferred 'upload a photo' prescription flow — "
                          "no upload UI or processing wired up yet. Not shipping this round; "
                          "kept here so adding the real feature later doesn't need a schema change.",
                null=True,
                upload_to='prescriptions/',
            ),
        ),
    ]
