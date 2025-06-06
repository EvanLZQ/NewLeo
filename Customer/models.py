from datetime import timezone
from django.db import models
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import BaseUserManager, PermissionsMixin, AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from tinymce.models import HTMLField


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
    wish_list = models.ForeignKey('Customer.WishList', null=True,
                                  on_delete=models.SET_NULL, blank=True, related_name='customer')
    shopping_cart = models.ForeignKey('Customer.ShoppingCart', null=True,
                                      on_delete=models.SET_NULL, blank=True, related_name='customer')
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

    def save(self, *args, **kwargs):
        if not self.pk:
            wish_list = WishList.objects.create()
            self.wish_list = wish_list
            shopping_cart = ShoppingCart.objects.create()
            self.shopping_cart = shopping_cart
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'CustomerInfo'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'


class ShoppingCart(models.Model):
    eyeglasses_set = models.ManyToManyField('Order.CompleteSet', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def merge_with(self, other_cart):
        # Get CompleteSet IDs from both carts
        current_set_ids = set(self.eyeglasses_set.values_list('id', flat=True))
        other_set_ids = set(
            other_cart.eyeglasses_set.values_list('id', flat=True))

        # Find unique IDs
        unique_set_ids = current_set_ids.union(other_set_ids)

        # Update this cart with the union of both sets
        self.eyeglasses_set.set(unique_set_ids)
        self.save()

        # Clear the other cart
        other_cart.eyeglasses_set.clear()
        other_cart.save()

    def active_sets_subtotal(self):
        return sum([cs.sub_total for cs in self.eyeglasses_set.filter(saved_for_later=False)])

    class Meta:
        db_table = 'ShoppingCart'
        verbose_name = 'Shopping Cart'
        verbose_name_plural = 'Shopping Carts'


class WishList(models.Model):
    product = models.ManyToManyField('Product.ProductInfo', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'WishList'
        verbose_name = 'Wish List'
        verbose_name_plural = 'Wish Lists'


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


class CustomerMessage(models.Model):
    customer = models.ForeignKey(
        'Customer.CustomerInfo', null=True, on_delete=models.CASCADE, related_name='customer_message')
    subject = models.CharField(max_length=100, blank=True, null=True)
    content = models.TextField(blank=True)
    message_from = models.CharField(max_length=100, blank=True, null=True, choices=[
                                    ('Customer Service', 'Customer Service'), ('Customer', 'Customer')])
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    def mark_as_read(self):
        self.read_at = timezone.now()
        self.save()

    class Meta:
        db_table = "CustomerMessage"
        verbose_name = "Customer Message"
        verbose_name_plural = "Customer Messages"


class CustomerNotification(models.Model):
    customer = models.ForeignKey(
        'Customer.CustomerInfo', on_delete=models.CASCADE, related_name='customer_notification')
    title = models.CharField(max_length=150)
    brief = models.CharField(max_length=150, blank=True, null=True)
    content = HTMLField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        db_table = "CustomerNotification"
        verbose_name = "Customer Notification"
        verbose_name_plural = "Customer Notifications"
