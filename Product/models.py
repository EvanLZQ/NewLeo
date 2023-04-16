from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User


class ProductDimension(models.Model):
    productID = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE, related_name='product_dimension')
    frame_width = models.IntegerField()
    lens_width = models.IntegerField()
    bridge = models.IntegerField()
    temple_length = models.IntegerField()
    lens_height = models.IntegerField()
    upper_wearable_width = models.IntegerField()
    lower_wearable_width = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ProductDimension'
        verbose_name = 'Product Dimension'
        verbose_name_plural = 'Product Dimensions'


class ProductFeature(models.Model):
    product = models.ManyToManyField('Product.ProductInfo')
    name = models.CharField(max_length=20)
    description = models.TextField()
    image = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ProductFeature'
        verbose_name = 'Product Feature'
        verbose_name_plural = 'Product Features'


class ProductImage(models.Model):
    productID = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE)
    image_type = models.CharField(max_length=50)
    name = models.CharField(max_length=20)
    path = models.URLField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ProductImage'
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'


class ProductInfo(models.Model):
    model_number = models.CharField(max_length=20)
    sku = models.CharField(unique=True, max_length=20)
    stock = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0)
    price = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(null=True)
    # Multiple size?
    letter_size = models.CharField(max_length=10, choices=[(
        'XS', 'xs'), ('S', 's'), ('M', 'm'), ('L', 'l'), ('XL', 'xl')])
    string_size = models.CharField(max_length=10)
    frame_weight = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(999)])
    bifocal = models.BooleanField(default=False)
    material = models.CharField(max_length=50,
                                choices=[
                                    ('ACETATE', 'Acetate'),
                                    ('TITANIUM', 'Titanium'),
                                    ('PLASTIC', 'Plastic'),
                                    ('CARBONFIBER', 'Carbon Fiber'),
                                    ('MIXED', 'Mixed'),
                                    ('METAL', 'Metal'),
                                    ('ALUMINIUMALLOY', 'Aluminium Alloy'),
                                    ('WOOD', 'Wood'),
                                    ('TR90', 'tr90'),
                                    ('ULTEM', 'Ultem'),
                                    ('MEMORYTITANIUM', 'Memory Titanium'),
                                    ('STAINLESSSTEEL', 'Stainless Steel')])
    shape = models.CharField(max_length=50,
                             choices=[
                                 ('RECTANGLE', 'Rectangle'),
                                 ('ROUND', 'Round'),
                                 ('SQUARE', 'Square'),
                                 ('OVAL', 'Oval'),
                                 ('CATEYE', 'Cat-Eye'),
                                 ('AVIATOR', 'Aviator'),
                                 ('HORN', 'Horn'),
                                 ('BROWLINE', 'Browline'),
                                 ('GEOMETRIC', 'Geometric'),
                                 ('HEART', 'Heart'),
                                 ('BUTTERFLY', 'Butterfly'),
                                 ('IRREGULAR', 'Irregular'),
                                 ('OTHER', 'Other')])
    gender = models.CharField(max_length=20,
                              choices=[('MALE', 'Male'), ('FEMALE', 'Female'), ('UNISEX', 'Unisex')], default='UNISEX')
    nose_pad = models.CharField(max_length=20,
                                choices=[('STANDARD', 'Standard'), ('ASIANFIT', 'Asian Fit'), ('ADJUSTABLE', 'Adjustable')])
    frame_style = models.CharField(max_length=20,
                                   choices=[('FULLRIM', 'Full-Rim'), ('SEMIRIMLESS', 'Semi-Rimless'), ('RIMLESS', 'Rimless')])
    pd_upper_range = models.IntegerField(default=80)
    pd_lower_range = models.IntegerField(default=30)
    color_name = models.CharField(max_length=50)
    online = models.BooleanField(default=False)
    reduced_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ProductInfo'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'


class ProductReview(models.Model):
    ProductID = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE)
    title = models.CharField(max_length=50)
    content = models.TextField(blank=True)
    user_email = models.EmailField()
    online = models.BooleanField(default=False)
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_by = models.ManyToManyField(User, blank=True)

    class Meta:
        db_table = 'ProductReview'
        verbose_name = 'Product Review'
        verbose_name_plural = 'Product Reviews'


class ProductTag(models.Model):
    product = models.ManyToManyField('Product.ProductInfo')
    name = models.CharField(max_length=20)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ProductTag'
        verbose_name = 'Product Tag'
        verbose_name_plural = 'Product Tags'
