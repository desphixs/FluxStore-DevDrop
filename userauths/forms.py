from django import forms
from .models import UserProfile, VendorProfile, User

class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
        'placeholder': 'Enter your password'
    }))
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput(attrs={
        'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
        'placeholder': 'Confirm your password'
    }))

    class Meta:
        model = User
        fields = [ 'email']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                'placeholder': 'Enter your email address'
            }),
        }

    def clean_password2(self):
        cd = self.cleaned_data
        if cd.get('password') != cd.get('password2'):
            raise forms.ValidationError('Passwords don\'t match.')
        return cd.get('password2')

    def clean_email(self):
        """
        Validates that the email is unique.
        """
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email

class LoginForm(forms.Form):
    """
    Form for user login.
    """
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
        'placeholder': 'your@email.com'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
        'placeholder': 'Password'
    }))


# vendor/forms.py
from django import forms
from django.utils.text import slugify
from decimal import Decimal

from userauths.models import VendorProfile 
from django.contrib.auth import get_user_model

User = get_user_model()


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"maxlength": 150}),
            "last_name": forms.TextInput(attrs={"maxlength": 150}),
            "email": forms.EmailInput(),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            raise forms.ValidationError("Email is required.")
        # Allow same email for this user; block others
        qs = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This email is already in use.")
        return email


class VendorProfileForm(forms.ModelForm):
    # Expose socials as separate optional fields; we’ll pack to JSON in clean()
    socials_instagram = forms.CharField(required=False)
    socials_twitter   = forms.CharField(required=False)
    socials_facebook  = forms.CharField(required=False)
    socials_tiktok    = forms.CharField(required=False)

    class Meta:
        model = VendorProfile
        fields = [
            "business_name", "slug", "contact_email", "business_phone", "business_address",
            "business_description", "logo", "banner",
            "website_url", "shipping_policy", "return_policy", "opening_hours",
            "currency", "country", "tax_id", "min_order_amount", "is_open",
            "bank_name", "account_name", "account_number",
        ]
        widgets = {
            "business_name": forms.TextInput(attrs={"maxlength": 255}),
            "slug": forms.TextInput(attrs={"maxlength": 255}),
            "contact_email": forms.EmailInput(),
            "business_phone": forms.TextInput(attrs={"maxlength": 20}),
            "business_address": forms.TextInput(attrs={"maxlength": 255}),
            "business_description": forms.Textarea(attrs={"rows": 3}),
            "website_url": forms.URLInput(),
            "shipping_policy": forms.Textarea(attrs={"rows": 3}),
            "return_policy": forms.Textarea(attrs={"rows": 3}),
            "opening_hours": forms.TextInput(attrs={"maxlength": 255}),
            "currency": forms.TextInput(attrs={"maxlength": 10}),
            "country": forms.TextInput(attrs={"maxlength": 60}),
            "tax_id": forms.TextInput(attrs={"maxlength": 60}),
            "min_order_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "bank_name": forms.TextInput(attrs={"maxlength": 120}),
            "account_name": forms.TextInput(attrs={"maxlength": 120}),
            "account_number": forms.TextInput(attrs={"maxlength": 60}),
        }

    def clean_contact_email(self):
        email = (self.cleaned_data.get("contact_email") or "").strip()
        if not email:
            raise forms.ValidationError("Contact email is required.")
        qs = VendorProfile.objects.filter(contact_email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This contact email is already in use.")
        return email

    def clean_business_name(self):
        name = (self.cleaned_data.get("business_name") or "").strip()
        if not name:
            raise forms.ValidationError("Business name is required.")
        qs = VendorProfile.objects.filter(business_name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This business name is already in use.")
        return name

    def clean_min_order_amount(self):
        val = self.cleaned_data.get("min_order_amount")
        if val is None:
            return Decimal("0.00")
        if val < 0:
            raise forms.ValidationError("Minimum order cannot be negative.")
        return val

    def clean(self):
        data = super().clean()

        # Slug default from business_name if blank
        slug = (data.get("slug") or "").strip()
        if not slug and data.get("business_name"):
            data["slug"] = slugify(data["business_name"])

        # Build socials JSON
        socials = {}
        for key in ("socials_instagram", "socials_twitter", "socials_facebook", "socials_tiktok"):
            v = (self.cleaned_data.get(key) or "").strip()
            if v:
                socials[key.replace("socials_", "")] = v
        data["socials"] = socials or None

        return data
