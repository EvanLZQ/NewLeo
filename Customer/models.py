from django.db import models
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import BaseUserManager, PermissionsMixin, AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator


class CustomUserManager(BaseUserManager):
    def normalize_username(self, username):
        # Normalize the username by lowercasing the domain part of the email
        return self.normalize_email(username)

    def create_user(self, username, password=None, **extra_fields):
        # Normalize the username address by lowercasing the domain part of it
        username = self.normalize_username(username)
        # Check if password is provided
        if password is None:
            raise ValueError('Password must be provided')
        # Create a new user object
        user = self.model(username=username, **extra_fields)
        # Set the user's password
        user.password = make_password(password)
        # Save the user object to the database
        user.save()
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        # Create a new user with superuser privileges
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)
        return self.create_user(username, password, **extra_fields)


class CustomerInfo(AbstractUser, PermissionsMixin):
    username = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    ip_address = models.CharField(max_length=100, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    gender = models.CharField(max_length=15, choices=[
                              ("MALE", "Male"), ("FEMALE", "Female"), ("OTHER", "Other")], blank=True)
    # DD/MM
    birth_date = models.CharField(max_length=6, blank=True, null=True)
    icon_url = models.CharField(max_length=100, blank=True, null=True)
    # store_credit = models.IntegerField(default=0)
    level = models.IntegerField(default=0)
    # wish_list = models.ManyToManyField(
    #     'Product.ProductInfo', through='ShoppingList')
    in_blacklist = models.BooleanField(default=False)
    objects = CustomUserManager()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.username

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    class Meta:
        db_table = 'CustomerInfo'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'


class ShoppingList(models.Model):
    customer = models.ForeignKey(
        'Customer.CustomerInfo', null=True, on_delete=models.SET_NULL)
    product = models.ManyToManyField('Order.CompleteSet')
    list_type = models.CharField(max_length=30,
                                 choices=[('SHOPPINGCART', 'Shopping Cart'), ('WISHLIST', 'Wish List')])

    class Meta:
        db_table = 'ShoppingList'
        verbose_name = 'Shopping List'
        verbose_name_plural = 'Shopping Lists'


class CustomerSavedAddress(models.Model):
    customer = models.ForeignKey(
        'Customer.CustomerInfo', null=True, on_delete=models.CASCADE, related_name='saved_address')
    full_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=15)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=50)
    province_state = models.CharField(max_length=50)
    country = models.CharField(max_length=50)
    post_code = models.CharField(max_length=10)
    instruction = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'CustomerSavedAddress'
        verbose_name = 'CustomerSavedAddress'
        verbose_name_plural = 'CustomerSavedAddresses'


class CustomerSavedPayment(models.Model):
    PAYMENT_METHOD_TYPES = [
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
    ]

    customer = models.ForeignKey(
        'Customer.CustomerInfo', null=True, on_delete=models.CASCADE, related_name='saved_payment_method')
    payment_method_type = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_TYPES, verbose_name="Payment Method Type")
    token = models.CharField(max_length=100, verbose_name="Token")
    card_brand = models.CharField(
        max_length=20, blank=True, verbose_name="Card Brand")
    last4 = models.CharField(max_length=4, blank=True,
                             verbose_name="Last 4 Digits")
    expiry_date = models.DateField(
        blank=True, null=True, verbose_name="Expiry Date")
    is_default = models.BooleanField(default=False, verbose_name="Is Default")

    class Meta:
        db_table = "CustomerSavedPayment"
        verbose_name = "Saved Payment Method"
        verbose_name_plural = "Saved Payment Methods"


class StoreCreditActivity(models.Model):
    customer = models.ForeignKey(
        'Customer.CustomerInfo', null=True, on_delete=models.CASCADE, related_name='store_credit_activity')
    total_amount = models.IntegerField(default=0)
    change_amount = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "StoreCreditActivity"
        verbose_name = "Store Credit Activity"
        verbose_name_plural = "Store Credit Activities"
