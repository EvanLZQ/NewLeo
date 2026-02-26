from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.utils.safestring import mark_safe

__all__ = ['ProductTag', 'ProductInstance', 'ProductPromotion',
           'ProductInfo', 'ProductReview', 'ProductImage', 'ProductColorImg']


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
        'XS', 'XS'), ('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL')])
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
                              choices=[('Male', 'Male'), ('Female', 'Female'), ('Unisex', 'Unisex')], default='Unisex')
    nose_pad = models.CharField(max_length=20,
                                choices=[('Standard', 'Standard'), ('Asian Fit', 'Asian Fit'), ('Adjustable', 'Adjustable')])
    frame_style = models.CharField(max_length=20,
                                   choices=[('Full-Rim', 'Full-Rim'), ('Semi-Rimless', 'Semi-Rimless'), ('Rimless', 'Rimless')])
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
        'Product.ProductInstance', blank=True, related_name='productPromotion')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    promo_type = models.CharField(max_length=50, choices=[(
        '1+1', '1+1'), ('Price-Off', 'Price-Off'), ('Percentage-Off', 'Percentage-Off')], default='Price-Off')
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
        max_digits=5, decimal_places=2, blank=True, default=0)
    color_img = models.ForeignKey(
        'Product.ProductColorImg', on_delete=models.SET_NULL, null=True)
    color_base_name = models.CharField(max_length=20, choices=COLOR_CHOICES)
    color_display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    online = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.price and self.product_id:
            self.price = self.product.price
        super().save(*args, **kwargs)

    def color_image_preview(self):
        return mark_safe(f'<img src="{self.color_img_url}" style="max-width: 300px; margin: 5px; border-style: solid;">')

    def __str__(self):
        return self.sku

    class Meta:
        db_table = 'ProductInstance'
        verbose_name = 'Product Instance'
        verbose_name_plural = 'Product Instances'


class ProductImage(models.Model):
    productInstance = models.ForeignKey(
        'Product.ProductInstance', on_delete=models.CASCADE, related_name='productImage')
    image = models.ImageField(upload_to='product_images/')
    alt = models.CharField(max_length=100)
    image_type = models.CharField(max_length=20, choices=[(
        'carousel', 'Carousel'), ('detail', 'Detail')], default='carousel')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ProductImage'
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'


class ProductReview(models.Model):
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, related_name='approvedby', on_delete=models.SET_NULL, null=True)
    product = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE, related_name='productReview')
    customer = models.ForeignKey(
        'Customer.CustomerInfo', on_delete=models.SET_NULL, related_name='productReview', null=True)
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
    CATEGORY_CHOICES = [
        ('Material', 'Material'),
        ('Shape', 'Shape'),
        ('Undefined', 'Undefined'),
        ('Top Selection for All', 'Top Selection for All'),
        ('Top Selection for Men', 'Top Selection for Men'),
        ('Top Selection for Women', 'Top Selection for Women'),
        ('Top Selection for Fashionista', 'Top Selection for Fashionista'),
        ('Life Style', 'Life Style'),
        ('Collection', 'Collection'),
        ('Promotion', 'Promotion'),
        ('Other', 'Other')
    ]

    slug = models.SlugField(max_length=200, unique=True, null=True)
    product = models.ManyToManyField(
        'Product.ProductInfo', blank=True, related_name='productTag')
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default='Undefined')
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


class ProductColorImg(models.Model):
    title = models.CharField(max_length=100)
    color_img = models.ImageField(upload_to='product_color_images/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.title}'

    class Meta:
        db_table = 'ProductColorImg'
        verbose_name = 'Product Color Image'
        verbose_name_plural = 'Product Color Images'
