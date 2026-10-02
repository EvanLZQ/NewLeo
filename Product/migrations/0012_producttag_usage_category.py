from django.db import migrations, models

# Names the storefront can show as entry points (Sunglasses/Driving/
# Reading/Progressive/Photochromic) plus two that exist in the database
# but aren't linked from the storefront yet (Distance/Bifocal).
USAGE_TAGS = [
    "Sunglasses", "Driving", "Reading", "Progressive", "Photochromic",
    "Distance", "Bifocal",
]


def create_usage_tags(apps, schema_editor):
    ProductTag = apps.get_model('Product', 'ProductTag')
    for name in USAGE_TAGS:
        ProductTag.objects.get_or_create(
            category='Usage', name=name,
            defaults={'slug': f'usage_{name.lower()}'},
        )


def remove_empty_usage_tags(apps, schema_editor):
    # Reverse: only drop the seeded rows if nobody has attached products
    # to them since — never delete real tagging work.
    ProductTag = apps.get_model('Product', 'ProductTag')
    for tag in ProductTag.objects.filter(category='Usage', name__in=USAGE_TAGS):
        if not tag.product.exists():
            tag.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('Product', '0011_merge_model_number_and_mask_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='producttag',
            name='category',
            field=models.CharField(
                choices=[
                    ('Material', 'Material'), ('Shape', 'Shape'),
                    ('Undefined', 'Undefined'),
                    ('Top Selection for All', 'Top Selection for All'),
                    ('Top Selection for Men', 'Top Selection for Men'),
                    ('Top Selection for Women', 'Top Selection for Women'),
                    ('Top Selection for Fashionista', 'Top Selection for Fashionista'),
                    ('Life Style', 'Life Style'), ('Collection', 'Collection'),
                    ('Promotion', 'Promotion'), ('Usage', 'Usage'),
                    ('Other', 'Other'),
                ],
                default='Undefined', max_length=50),
        ),
        migrations.RunPython(create_usage_tags, remove_empty_usage_tags),
    ]
