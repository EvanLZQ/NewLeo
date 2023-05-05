from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User

__all__ = ['ProductDimension', 'ProductTag', 'ProductFeature',
           'ProductImage', 'ProductInfo', 'ProductReview', 'ProductCollection']


class ProductInfo(models.Model):
    supplierID = models.ForeignKey(
        'Supplier.SupplierInfo', on_delete=models.SET_NULL, null=True)
    colorID = models.ForeignKey(
        'Color.ColorInfo', on_delete=models.CASCADE, null=True)
    slug = models.SlugField(unique=True, default='', null=False,
                            db_index=True, help_text='Do not edit this field!')
    model_number = models.CharField(max_length=20)
    name = models.CharField(max_length=100, blank=True)
    sku = models.CharField(unique=True, max_length=20)
    original_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    stock = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0)
    price = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(null=True)
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
    online = models.BooleanField(default=False)
    reduced_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.sku

    class Meta:
        db_table = 'ProductInfo'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'


class ProductCollection(models.Model):
    product = models.ManyToManyField('Product.ProductInfo', blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    slug = models.SlugField(unique=True, default='', null=False,
                            db_index=True, help_text='Do not edit this field!')
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    display_order = models.IntegerField(validators=[MinValueValidator(1)],
                                        default=1)
    image_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'ProductCollection'
        verbose_name = 'Product Collection'
        verbose_name_plural = 'Product Collections'


class ProductDimension(models.Model):
    productID = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE, related_name='product_dimension')
    slug = models.SlugField(max_length=200, unique=True, null=True)
    frame_width = models.IntegerField()
    lens_width = models.IntegerField()
    bridge = models.IntegerField()
    temple_length = models.IntegerField()
    lens_height = models.IntegerField()
    upper_wearable_width = models.IntegerField()
    lower_wearable_width = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'ProductDimension'
        verbose_name = 'Product Dimension'
        verbose_name_plural = 'Product Dimensions'


class ProductFeature(models.Model):
    product = models.ManyToManyField('Product.ProductInfo', blank=True)
    slug = models.SlugField(max_length=200, unique=True, null=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    image = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'ProductFeature'
        verbose_name = 'Product Feature'
        verbose_name_plural = 'Product Features'


class ProductImage(models.Model):
    productID = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE)
    slug = models.SlugField(max_length=200, unique=True, null=True)
    image_type = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    path = models.URLField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'ProductImage'
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'


class ProductReview(models.Model):
    ProductID = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE)
    slug = models.SlugField(max_length=200, unique=True, null=True)
    title = models.CharField(max_length=50)
    content = models.TextField(blank=True)
    user_email = models.EmailField()
    online = models.BooleanField(default=False)
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_by = models.ManyToManyField(User, blank=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'ProductReview'
        verbose_name = 'Product Review'
        verbose_name_plural = 'Product Reviews'


class ProductTag(models.Model):
    slug = models.SlugField(max_length=200, unique=True, null=True)
    product = models.ManyToManyField('Product.ProductInfo', blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'ProductTag'
        verbose_name = 'Product Tag'
        verbose_name_plural = 'Product Tags'
