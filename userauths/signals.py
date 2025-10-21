from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, UserProfile, VendorProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

        
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    
    if hasattr(instance, "profile"):
        instance.profile.save()
    if instance.role == User.Role.VENDOR and hasattr(instance, "vendor_profile"):
        instance.vendor_profile.save()



from django.dispatch import receiver
from allauth.account.signals import email_confirmed, user_signed_up
from allauth.socialaccount.signals import social_account_added
from allauth.account.models import EmailAddress

from userauths.models import UserProfile

def _ensure_profile(user):
    
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.full_name:
        profile.full_name = user.get_full_name() or user.email.split("@")[0]
        profile.save(update_fields=["full_name"])

@receiver(email_confirmed)
def on_email_confirmed(request, email_address, **kwargs):
    
    user = email_address.user
    _ensure_profile(user)

@receiver(user_signed_up)
def on_user_signed_up(request, user, **kwargs):
    
    
    is_verified = EmailAddress.objects.filter(user=user, verified=True).exists()
    if is_verified:
        _ensure_profile(user)

@receiver(social_account_added)
def on_social_added(request, sociallogin, **kwargs):
    
    user = sociallogin.user
    is_verified = EmailAddress.objects.filter(user=user, verified=True).exists()
    if is_verified:
        _ensure_profile(user)
