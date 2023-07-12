from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.utils.safestring import mark_safe

__all__ = ['ProductTag', 'ProductInstance', 'ProductPromotion',
           'ProductInfo', 'ProductReview']


class ProductInfo(models.Model):
    supplier = models.ForeignKey(
        'Supplier.SupplierInfo', on_delete=models.SET_NULL, null=True)
    model_number = models.CharField(max_length=20)
    name = models.CharField(max_length=100, blank=True)
    rmb_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(null=True)
    letter_size = models.CharField(max_length=10, choices=[(
        'XS', 'xs'), ('S', 's'), ('M', 'm'), ('L', 'l'), ('XL', 'xl')])
    string_size = models.CharField(max_length=10)
    frame_weight = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(999)])
    bifocal = models.BooleanField(default=False)
    frame_width = models.IntegerField()
    lens_width = models.IntegerField()
    bridge = models.IntegerField()
    temple_length = models.IntegerField()
    lens_height = models.IntegerField()
    upper_wearable_width = models.IntegerField()
    lower_wearable_width = models.IntegerField()
    gender = models.CharField(max_length=20,
                              choices=[('MALE', 'Male'), ('FEMALE', 'Female'), ('UNISEX', 'Unisex')], default='UNISEX')
    nose_pad = models.CharField(max_length=20,
                                choices=[('STANDARD', 'Standard'), ('ASIANFIT', 'Asian Fit'), ('ADJUSTABLE', 'Adjustable')])
    frame_style = models.CharField(max_length=20,
                                   choices=[('FULLRIM', 'Full-Rim'), ('SEMIRIMLESS', 'Semi-Rimless'), ('RIMLESS', 'Rimless')])
    pd_upper_range = models.IntegerField(default=80)
    pd_lower_range = models.IntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.model_number

    class Meta:
        db_table = 'ProductInfo'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'


class ProductPromotion(models.Model):
    productInstance = models.ManyToManyField(
        'Product.ProductInstance', blank=True)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    promo_type = models.CharField(max_length=50, choices=[(
        '1+1', '1+1'), ('priceoff', 'Price-Off'), ('percentoff', 'Percentage-Off')], default='priceoff')
    promo_value = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)], default=0)
    description = models.TextField(blank=True)
    slug = models.SlugField(unique=True, default='', null=False,
                            db_index=True, help_text='Do not edit this field!')
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    promo_img = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'ProductPromotion'
        verbose_name = 'Product Promotion'
        verbose_name_plural = 'Product Promotions'


class ProductInstance(models.Model):
    COLOR_CHOICES = (
        ('aqua', 'Aqua'),
        ('black', 'Black'),
        ('blue', 'Blue'),
        ('fuchsia', 'Fuchsia'),
        ('gray', 'Gray'),
        ('green', 'Green'),
        ('lime', 'Lime'),
        ('maroon', 'Maroon'),
        ('navy', 'Navy'),
        ('olive', 'Olive'),
        ('orange', 'Orange'),
        ('purple', 'Purple'),
        ('red', 'Red'),
        ('silver', 'Silver'),
        ('teal', 'Teal'),
        ('white', 'White'),
        ('yellow', 'Yellow'),
    )
    product = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE, related_name='productInstance', null=True)
    slug = models.SlugField(max_length=200, unique=True, null=True)
    sku = models.CharField(unique=True, max_length=20)
    stock = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0)
    reduced_price = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)
    price = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True)
    carousel_img = models.CharField(max_length=1000)
    detail_img = models.CharField(max_length=1000)
    color_img_url = models.URLField()
    color_base_name = models.CharField(max_length=20, choices=COLOR_CHOICES)
    color_display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    online = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def carousel_image_preview(self):
        images = self.carousel_img.split(',') if self.carousel_img else []
        html = ""
        for image in images:
            html += f'<img src="{image}" style="max-width: 300px; margin: 5px;">'
        return mark_safe(html)

    def detail_image_preview(self):
        images = self.detail_img.split(',') if self.detail_img else []
        html = ""
        for image in images:
            html += f'<img src="{image}" style="max-width: 300px; margin: 5px;">'
        return mark_safe(html)

    def color_image_preview(self):
        return mark_safe(f'<img src="{self.color_img_url}" style="max-width: 300px; margin: 5px; border-style: solid;">')

    def __str__(self):
        return self.sku

    class Meta:
        db_table = 'ProductInstance'
        verbose_name = 'Product Instance'
        verbose_name_plural = 'Product Instances'


class ProductReview(models.Model):
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, related_name='approvedby', on_delete=models.SET_NULL, null=True)
    product = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE, related_name='productReview')
    customer = models.ForeignKey(
        'Customer.CustomerInfo', on_delete=models.SET_NULL, related_name='productReivew', null=True)
    slug = models.SlugField(max_length=200, unique=True, null=True)
    title = models.CharField(max_length=50)
    content = models.TextField(blank=True)
    online = models.BooleanField(default=False)
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = 'ProductReview'
        verbose_name = 'Product Review'
        verbose_name_plural = 'Product Reviews'


class ProductTag(models.Model):
    slug = models.SlugField(max_length=200, unique=True, null=True)
    product = models.ManyToManyField('Product.ProductInfo', blank=True)
    category = models.CharField(max_length=100, null=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'ProductTag'
        verbose_name = 'Product Tag'
        verbose_name_plural = 'Product Tags'
