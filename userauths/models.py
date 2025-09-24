from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings 
from shortuuid.django_fields import ShortUUIDField
from django.db.models.signals import post_save
from django.dispatch import receiver

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone
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
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='vendor_profile',
        limit_choices_to={'role': User.Role.VENDOR},  # <-- FIXED
    )
    # Core business info
    business_name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, null=True, blank=True) 
    contact_email = models.EmailField(unique=True)
    business_phone = models.CharField(max_length=20)
    business_address = models.CharField(max_length=255)
    business_description = models.TextField(blank=True, null=True)

    # Branding
    logo = models.ImageField(upload_to='vendor/logo/', blank=True, null=True)
    banner = models.ImageField(upload_to='vendor/banner/', blank=True, null=True)

    # Meta / policies
    website_url = models.URLField(blank=True, null=True)
    socials = models.JSONField(blank=True, null=True)  # {"instagram": "...", "twitter": "..."}
    shipping_policy = models.TextField(blank=True, null=True)
    return_policy = models.TextField(blank=True, null=True)
    opening_hours = models.CharField(max_length=255, blank=True, null=True)

    # Commerce
    currency = models.CharField(max_length=10, default="USD")  # "NGN", "USD", etc.
    country = models.CharField(max_length=60, default="NG")
    tax_id = models.CharField(max_length=60, blank=True, null=True)
    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_open = models.BooleanField(default=True)

    # Payout (basic fields; swap to your payments provider later)
    bank_name = models.CharField(max_length=120, blank=True, null=True)
    account_name = models.CharField(max_length=120, blank=True, null=True)
    account_number = models.CharField(max_length=60, blank=True, null=True)

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
    full_name = models.CharField(max_length=150, blank=True)   # optional
    phone = models.CharField(max_length=30, blank=True)        # optional
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    class Meta:
        indexes = [
            models.Index(fields=['profile', 'address_type']),
        ]

    def __str__(self):
        return f"{self.profile.user.email} - {self.get_address_type_display()} Address"

    def save(self, *args, **kwargs):
        # if marking this address default, clear other defaults for this profile+type
        if self.is_default:
            # NOTE: using update avoids signals and prevents recursion
            Address.objects.filter(profile=self.profile, address_type=self.address_type).update(is_default=False)
        super().save(*args, **kwargs)



# @receiver(post_save, sender=User)
# def ensure_user_profile(sender, instance, created, **kwargs):
#     if created:
#         # Safe if something else already created it
#         UserProfile.objects.get_or_create(user=instance)