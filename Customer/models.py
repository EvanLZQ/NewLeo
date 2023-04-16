from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from django.core.validators import MinValueValidator, MaxValueValidator


class CustomerSavedAddress(models.Model):
    CustomerID = models.ForeignKey(
        'Customer.CustomerInfo', on_delete=models.CASCADE)
    AddressID = models.ForeignKey(
        'General.Address', on_delete=models.CASCADE)

    class Meta:
        db_table = 'customer_saved_address'


class CustomerInfo(models.Model):
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=30)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = PhoneNumberField(blank=True)
    ip_address = models.CharField(max_length=100, null=True, blank=True)
    account_is_active = models.BooleanField(default=True)
    gender = models.CharField(max_length=15, choices=[
                              ("MALE", "Male"), ("FEMALE", "Female"), ("OTHER", "Other")], blank=True)
    birth_date = models.DateField(blank=True)
    icon_url = models.CharField(max_length=100, blank=True)
    store_credit = models.IntegerField(default=0)
    level = models.IntegerField(default=0)
    wish_list = models.ManyToManyField(
        'Product.ProductInfo', through='ShoppingList')
    # TODO address model
    # address = models.ForeignKey()
    in_blacklist = models.BooleanField(default=False)
    # TODO payment model
    # payment_method = models.ManyToManyField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    class Meta:
        db_table = 'CustomerInfo'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'


class ShoppingList(models.Model):
    customer = models.ForeignKey('CustomerInfo', on_delete=models.CASCADE)
    product = models.ForeignKey(
        'Product.ProductInfo', on_delete=models.CASCADE)
    quantity = models.IntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(99)])
    list_type = models.CharField(max_length=30,
                                 choices=[('SHOPPINGCART', 'Shopping Cart'), ('WISHLIST', 'Wish List')])

    class Meta:
        db_table = 'ShoppingList'
        verbose_name = 'Shopping List'
        verbose_name_plural = 'Shopping Lists'
