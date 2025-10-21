
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import RegistrationForm, LoginForm
from .models import User
from store import models as store_models
from order import models as order_models

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.utils.text import slugify


from allauth.account.models import EmailAddress

from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect

from .models import UserProfile, VendorProfile, User

import json
from decimal import Decimal


from django.db import transaction
from django.utils.text import slugify

from userauths.models import VendorProfile, User
from .forms import UserProfileForm, VendorProfileForm


from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import RegistrationForm


def _auto_verify_email(user):
    """Create/mark EmailAddress as verified without sending mail (demo mode)."""
    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return
    addr, _ = EmailAddress.objects.get_or_create(user=user, email=email)
    changed = False
    if not addr.verified:
        addr.verified = True
        changed = True

    if not addr.primary:
        EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
        addr.primary = True
        changed = True
    if changed:
        addr.save(update_fields=["verified", "primary"])


try:
    from allauth.account.utils import send_email_confirmation as _send_email_confirmation
except Exception:
    _send_email_confirmation = None

def _send_verify_email(request, user, *, signup: bool):
    """
    Always tries the official util if present; otherwise fall back to creating
    (or reusing) EmailAddress and triggering a confirmation mail.
    """
    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return
    if _send_email_confirmation:
        _send_email_confirmation(request, user, signup=signup)
    else:
        EmailAddress.objects.add_email(
            request, user, email, confirm=True, signup=signup
        )

def register_view(request):
    if request.user.is_authenticated:
        return redirect('store:index')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data.get('password'))
            user.save()

            _send_verify_email(request, user, signup=True)
            messages.success(request, 'Registration successful. Check your email to verify your account.')
            return redirect('userauths:login')
    else:
        form = RegistrationForm()

    return render(request, 'register.html', {'form': form, "SEND_AUTH_EMAIL": settings.SEND_AUTH_EMAIL})




def _get_next_url(request, fallback="store:index"):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return getattr(settings, "LOGIN_REDIRECT_URL", None) or fallback

def login_view(request):
    if request.user.is_authenticated:
        return redirect(_get_next_url(request))

    next_url = request.GET.get("next", "")

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password')
            user = authenticate(request, email=email, password=password)

            if user is None:
                messages.error(request, 'Invalid email or password.')
                return render(request, 'login.html', {'form': form, 'next_url': next_url})


            if settings.SEND_AUTH_EMAIL:
                if not EmailAddress.objects.filter(user=user, verified=True).exists():
                    _send_verify_email(request, user, signup=False)
                    messages.error(request, "We sent a verification link to your email. Verify to log in.")
                    return render(request, 'login.html', {'form': form, 'next_url': next_url})
            else:

                _auto_verify_email(user)


            guest_session_key = request.session.session_key
            login(request, user)
            messages.success(request, 'Login successful')

            try:
                guest_cart = order_models.Cart.objects.get(
                    session_key=guest_session_key, user__isnull=True
                )
                user_cart = order_models.Cart.get_for_request(request)
                if guest_cart != user_cart:
                    user_cart.merge_from(guest_cart)
            except order_models.Cart.DoesNotExist:
                pass

            return redirect(_get_next_url(request))
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form, 'next_url': next_url, "SEND_AUTH_EMAIL": settings.SEND_AUTH_EMAIL})



def logout_view(request):
    logout(request)
    messages.info(request, 'You have been successfully logged out.')
    return redirect('userauths:login')

from django.db import transaction
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.utils.text import slugify

from userauths.models import User

def _unique_slug(model, base):
    slug = slugify(base) or "vendor"
    i = 1
    qs = model.objects
    s = slug
    while qs.filter(slug=s).exists():
        i += 1
        s = f"{slug}-{i}"
    return s

@transaction.atomic
def vendor_register_view(request):
    if request.user.is_authenticated:
        return redirect('store:index')

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        password2 = request.POST.get("password2") or ""

        business_name = (request.POST.get("business_name") or "").strip()
        contact_email = (request.POST.get("contact_email") or email).strip().lower()
        business_phone = (request.POST.get("business_phone") or "").strip()
        business_address = (request.POST.get("business_address") or "").strip()

        errors = []
        if not email or not username or not password or not password2:
            errors.append("Email, username and passwords are required.")
        if password != password2:
            errors.append("Passwords do not match.")
        if not business_name:
            errors.append("Business name is required.")
        if User.objects.filter(email=email).exists():
            errors.append("Email already in use.")
        if VendorProfile.objects.filter(business_name=business_name).exists():
            errors.append("Business name already taken.")
        if errors:
            for e in errors:
                messages.error(request, e)
            ctx = {"prefill": request.POST}
            return render(request, "auth/vendor_register.html", ctx)


        user = User(email=email, username=username, role=User.Role.VENDOR)
        user.set_password(password)
        user.save()

        VendorProfile.objects.create(
            user=user,
            business_name=business_name,
            slug=_unique_slug(VendorProfile, business_name),
            contact_email=contact_email,
            business_phone=business_phone,
            business_address=business_address,
        )

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.full_name = business_name
        profile.save(update_fields=["full_name"])

        messages.success(request, "Vendor account created!")
        login(request, user)
        nxt = request.POST.get('next') or request.GET.get('next')
        if nxt:
            return redirect(nxt)
        return redirect('vendor:vendor_detail', slug=user.vendor_profile.slug)

    return render(request, "vendor_register.html", {})


@login_required
def resend_verification_view(request):
    _send_verify_email(request, request.user, signup=False)
    messages.success(request, "Verification email sent.")
    return redirect('userauths:login')