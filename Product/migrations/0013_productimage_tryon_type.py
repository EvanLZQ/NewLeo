from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the 'tryon' choice to ProductImage.image_type.

    Choices live only in Django's model state, so this is a no-op in
    Postgres in both directions (`sqlmigrate` prints no SQL). Rolling back
    to 0012 is safe and keeps any uploaded try-on rows untouched; they are
    simply not served, because every serializer filters by image_type.
    """

    dependencies = [
        ('Product', '0012_producttag_usage_category'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productimage',
            name='image_type',
            field=models.CharField(
                choices=[('carousel', 'Carousel'), ('detail', 'Detail'),
                         ('mask', 'Mask'), ('tryon', 'Try-on')],
                default='carousel', max_length=20),
        ),
    ]
