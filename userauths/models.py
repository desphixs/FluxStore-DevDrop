from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings 
from shortuuid.django_fields import ShortUUIDField

class User(AbstractUser):
    class Role(models.TextChoices):
        BUYER = "BUYER", "Buyer"
        VENDOR = "VENDOR", "Vendor"

    email = models.EmailField(unique=True) 
    username = models.CharField(unique=True, max_length=50)
    role = models.CharField(max_length=50, choices=Role.choices, default=Role.BUYER)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def save(self, *args, **kwargs):
        # If no username is set, fallback to email as username
        if not self.username and self.email:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    image = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    def __str__(self):
        return f"{self.user.email}'s Profile"
    

class VendorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vendor_profile', limit_choices_to={'role': User.Role.BUYER})
    business_name = models.CharField(max_length=255, unique=True)
    business_description = models.TextField(blank=True, null=True)
    business_phone = models.CharField(max_length=20)
    business_address = models.CharField(max_length=255)
    contact_email = models.EmailField(unique=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    def __str__(self):
        return self.business_name

class Address(models.Model):
    class AddressType(models.TextChoices):
        SHIPPING = "SHIPPING", "Shipping"
        BILLING = "BILLING", "Billing"

    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='addresses')
    address_type = models.CharField(max_length=10, choices=AddressType.choices)
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    def __str__(self):
        return f"{self.profile.user.email} - {self.get_address_type_display()} Address"