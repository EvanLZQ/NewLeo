# Generated by Django 4.1.7 on 2023-07-05 02:56

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import phonenumber_field.modelfields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("General", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerSavedAddress",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
            options={"db_table": "customer_saved_address",},
        ),
        migrations.CreateModel(
            name="CustomerSavedPayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "payment_method_type",
                    models.CharField(
                        choices=[
                            ("credit_card", "Credit Card"),
                            ("debit_card", "Debit Card"),
                        ],
                        max_length=20,
                        verbose_name="Payment Method Type",
                    ),
                ),
                ("token", models.CharField(max_length=100, verbose_name="Token")),
                (
                    "card_brand",
                    models.CharField(
                        blank=True, max_length=20, verbose_name="Card Brand"
                    ),
                ),
                (
                    "last4",
                    models.CharField(
                        blank=True, max_length=4, verbose_name="Last 4 Digits"
                    ),
                ),
                (
                    "expiry_date",
                    models.DateField(blank=True, null=True, verbose_name="Expiry Date"),
                ),
                (
                    "is_default",
                    models.BooleanField(default=False, verbose_name="Is Default"),
                ),
            ],
            options={
                "verbose_name": "Saved Payment Method",
                "verbose_name_plural": "Saved Payment Methods",
                "db_table": "CustomerSavedPayment",
            },
        ),
        migrations.CreateModel(
            name="CustomerSavedPrescription",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
            options={"db_table": "customer_saved_prescription",},
        ),
        migrations.CreateModel(
            name="ShoppingList",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity",
                    models.IntegerField(
                        default=1,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(99),
                        ],
                    ),
                ),
                (
                    "list_type",
                    models.CharField(
                        choices=[
                            ("SHOPPINGCART", "Shopping Cart"),
                            ("WISHLIST", "Wish List"),
                        ],
                        max_length=30,
                    ),
                ),
            ],
            options={
                "verbose_name": "Shopping List",
                "verbose_name_plural": "Shopping Lists",
                "db_table": "ShoppingList",
            },
        ),
        migrations.CreateModel(
            name="CustomerInfo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last login"
                    ),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "email",
                    models.EmailField(db_index=True, max_length=254, unique=True),
                ),
                ("first_name", models.CharField(blank=True, max_length=100)),
                ("last_name", models.CharField(blank=True, max_length=100)),
                (
                    "phone",
                    phonenumber_field.modelfields.PhoneNumberField(
                        blank=True, max_length=128, region=None
                    ),
                ),
                ("ip_address", models.CharField(blank=True, max_length=100, null=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "gender",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("MALE", "Male"),
                            ("FEMALE", "Female"),
                            ("OTHER", "Other"),
                        ],
                        max_length=15,
                    ),
                ),
                ("birth_date", models.DateField(blank=True)),
                ("icon_url", models.CharField(blank=True, max_length=100)),
                ("store_credit", models.IntegerField(default=0)),
                ("level", models.IntegerField(default=0)),
                ("in_blacklist", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "customer_saved_addresses",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="General.address",
                    ),
                ),
                (
                    "customer_saved_payment",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="customer",
                        to="Customer.customersavedpayment",
                    ),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "Customer",
                "verbose_name_plural": "Customers",
                "db_table": "CustomerInfo",
            },
        ),
    ]
