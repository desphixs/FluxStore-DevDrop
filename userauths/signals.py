from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, UserProfile, VendorProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Always create a UserProfile for every user
        UserProfile.objects.create(user=instance)

        # If the user is a vendor, also create a VendorProfile stub
        if instance.role == User.Role.VENDOR:
            VendorProfile.objects.create(
                user=instance,
                business_name=f"{instance.username}'s Business",
                business_phone="",
                business_address="",
                contact_email=instance.email,
            )


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Ensure profile is saved when user updates
    if hasattr(instance, "profile"):
        instance.profile.save()
    if instance.role == User.Role.VENDOR and hasattr(instance, "vendor_profile"):
        instance.vendor_profile.save()
