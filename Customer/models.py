from django.db import models
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from phonenumber_field.modelfields import PhoneNumberField
from django.core.validators import MinValueValidator, MaxValueValidator


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        # Normalize the email address by lowercasing the domain part of it
        email = self.normalize_email(email)
        # Check if password is provided
        if password is None:
            raise ValueError('Password must be provided')
        # Create a new user object
        user = self.model(email=email, **extra_fields)
        # Set the user's password
        user.set_password(password)
        # Save the user object to the database
        user.save()
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        # Create a new user with superuser privileges
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)
        return self.create_user(email, password, **extra_fields)


class CustomerInfo(AbstractBaseUser, PermissionsMixin):
    customer_saved_addresses = models.ForeignKey(
        'General.Address', on_delete=models.SET_NULL, null=True)
    customer_saved_payment = models.ForeignKey(
        'Customer.CustomerSavedPayment', on_delete=models.SET_NULL, null=True, related_name='customer'
    )
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = PhoneNumberField(blank=True)
    ip_address = models.CharField(max_length=100, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    gender = models.CharField(max_length=15, choices=[
                              ("MALE", "Male"), ("FEMALE", "Female"), ("OTHER", "Other")], blank=True)
    birth_date = models.DateField(blank=True, null=True)
    icon_url = models.CharField(max_length=100, blank=True, null=True)
    store_credit = models.IntegerField(default=0)
    level = models.IntegerField(default=0)
    wish_list = models.ManyToManyField(
        'Product.ProductInfo', through='ShoppingList')
    in_blacklist = models.BooleanField(default=False)
    objects = CustomUserManager()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

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


class CustomerSavedPrescription(models.Model):
    customer = models.ForeignKey('CustomerInfo', on_delete=models.CASCADE)
    prescription = models.ForeignKey(
        'Prescription.PrescriptionInfo', on_delete=models.CASCADE)

    class Meta:
        db_table = 'customer_saved_prescription'


class CustomerSavedAddress(models.Model):
    customer = models.ForeignKey(
        'Customer.CustomerInfo', on_delete=models.CASCADE)
    address = models.ForeignKey(
        'General.Address', on_delete=models.CASCADE)

    class Meta:
        db_table = 'customer_saved_address'


class CustomerSavedPayment(models.Model):
    PAYMENT_METHOD_TYPES = [
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        # ... other types
    ]

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
