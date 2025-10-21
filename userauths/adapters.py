from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.models import EmailAddress
from allauth.account.adapter import DefaultAccountAdapter

from django.contrib import messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.utils.crypto import get_random_string
from django.conf import settings
from django.urls import reverse

from userauths.models import User

class AccountAdapter(DefaultAccountAdapter):
    def populate_username(self, request, user):
        if not user.username and user.email:
            base = user.email.split('@')[0][:30] or "user"
            user.username = f"{base}-{get_random_string(6)}"
    
    def get_email_confirmation_redirect_url(self, request):
        return reverse("userauths:login")



class SocialAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = (sociallogin.user.email or "").strip().lower()
        
        if not email:
            messages.error(request, "Google account has no email. Use standard signup.")
            sociallogin.state['process'] = 'connect'
            return

        try:
            existing = User.objects.get(email__iexact=email)
            if not sociallogin.is_existing:
                sociallogin.connect(request, existing)
                self._trust_or_demo_verify(existing, sociallogin)
        except User.DoesNotExist:
            pass  

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        self._trust_or_demo_verify(user, sociallogin)
        return user

    def _trust_or_demo_verify(self, user, sociallogin):
        demo_mode = not getattr(settings, "SEND_AUTH_EMAIL", True)
        trust_google = getattr(settings, "TRUST_GOOGLE_EMAIL", False) and \
                       getattr(sociallogin.account, "provider", "") == "google"
        if not (demo_mode or trust_google):
            return

        email = (user.email or "").strip().lower()
        if not email:
            return

        addr, _ = EmailAddress.objects.get_or_create(user=user, email=email)
        if not addr.primary:
            EmailAddress.objects.filter(user=user, primary=True).exclude(pk=addr.pk).update(primary=False)
        if (not addr.verified) or (not addr.primary):
            addr.verified = True
            addr.primary = True
            addr.save(update_fields=["verified", "primary"])

    def is_auto_signup_allowed(self, request, sociallogin):
        return True
