# vendor/forms.py
from decimal import Decimal, InvalidOperation
from django import forms
from order import models as order_models
from django import forms
from django.utils.text import slugify
from decimal import Decimal
from store import models as store_models


class CouponForm(forms.ModelForm):
    """
    Validates the mutually exclusive discount fields
    and normalizes decimals/empties for JSON payloads.
    """
    class Meta:
        model = order_models.Coupon
        fields = [
            "code", "title", "description",
            "discount_type", "percent_off", "amount_off",
            "max_discount_amount", "min_order_amount",
            "starts_at", "ends_at",
            "usage_limit_total", "usage_limit_per_user",
            "is_active",
        ]

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.vendor = vendor

        # Make most fields optional so we can do custom validation
        for name in ["percent_off", "amount_off", "max_discount_amount", "min_order_amount"]:
            self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        dtype = cleaned.get("discount_type")
        percent_off = cleaned.get("percent_off")
        amount_off = cleaned.get("amount_off")

        # Ensure one discount input depending on type
        if dtype == order_models.Coupon.DiscountType.PERCENT:
            if percent_off is None:
                raise forms.ValidationError({"percent_off": "Percent off is required."})
            if percent_off <= 0 or percent_off > 100:
                raise forms.ValidationError({"percent_off": "Percent must be between 0 and 100."})
            cleaned["amount_off"] = None
        elif dtype == order_models.Coupon.DiscountType.FIXED:
            if amount_off is None or amount_off <= 0:
                raise forms.ValidationError({"amount_off": "Amount off must be > 0."})
            cleaned["percent_off"] = None
        else:
            raise forms.ValidationError({"discount_type": "Invalid discount type."})

        # Normalize empty strings (when sent as strings) to None
        for fld in ["max_discount_amount", "min_order_amount"]:
            if cleaned.get(fld) == "":
                cleaned[fld] = None

        # Date sanity (optional)
        starts_at, ends_at = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts_at and ends_at and starts_at > ends_at:
            raise forms.ValidationError("Start date cannot be after end date.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.vendor:
            obj.vendor = self.vendor
        if commit:
            obj.save()
        return obj


class ProductCreateForm(forms.ModelForm):
    class Meta:
        model = store_models.Product
        fields = ["category", "name", "description"]
        widgets = {
            "category": forms.Select(),
            "name": forms.TextInput(attrs={"maxlength": 255}),
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop("vendor", None)
        super().__init__(*args, **kwargs)
        # Only pick existing categories; vendor cannot create new
        self.fields["category"].queryset = store_models.Category.objects.filter(is_active=True).order_by("name")

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Product name is required.")
        return name

from django import forms
from store import models as store_models  # Adjust if needed

class ProductDetailsForm(forms.ModelForm):
    class Meta:
        model = store_models.Product
        fields = ["category", "name", "description", "status", "is_featured"]
        widgets = {
            "category": forms.Select(attrs={
                "class": "form-select block w-full mt-1 border-gray-300 rounded-md shadow-sm focus:ring focus:ring-indigo-200"
            }),
            "name": forms.TextInput(attrs={
                "class": "form-input block w-full mt-1 border-gray-300 rounded-md shadow-sm focus:ring focus:ring-indigo-200",
                "maxlength": 255
            }),
            "description": forms.Textarea(attrs={
                "class": "form-textarea block w-full mt-1 border-gray-300 rounded-md shadow-sm focus:ring focus:ring-indigo-200",
                "rows": 8
            }),
            "status": forms.Select(attrs={
                "class": "form-select block w-full mt-1 border-gray-300 rounded-md shadow-sm focus:ring focus:ring-indigo-200"
            }),
            "is_featured": forms.CheckboxInput(attrs={
                "class": "form-checkbox h-5 w-5 text-indigo-600"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = store_models.Category.objects.filter(is_active=True).order_by("name")

class VariationCategoryForm(forms.ModelForm):
    class Meta:
        model = store_models.VariationCategory
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"maxlength": 100})}

    def __init__(self, *args, **kwargs):
        self.vendor = kwargs.pop("vendor", None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.vendor:
            obj.vendor = self.vendor
        if commit:
            obj.save()
        return obj


class VariationValueForm(forms.ModelForm):
    class Meta:
        model = store_models.VariationValue
        fields = ["category", "value"]
        widgets = {
            "category": forms.Select(),
            "value": forms.TextInput(attrs={"maxlength": 100}),
        }

    def __init__(self, *args, **kwargs):
        vendor = kwargs.pop("vendor", None)
        super().__init__(*args, **kwargs)
        # Limit categories to this vendor
        if vendor:
            self.fields["category"].queryset = store_models.VariationCategory.objects.filter(vendor=vendor).order_by("name")


class ProductVariationForm(forms.ModelForm):
    # We'll accept an array of variation_value_ids from JS for the M2M
    variation_value_ids = forms.CharField(required=False)  # JSON or CSV handled in view

    class Meta:
        model = store_models.ProductVariation
        fields = [
            "sale_price", "regular_price", "show_regular_price", "show_discount_type",
            "deal_active", "deal_starts_at", "deal_ends_at",
            "stock_quantity", "sku", "is_active", "is_primary",
            "weight", "length", "height", "width", "label",
        ]
        widgets = {
            "sale_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "regular_price": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "stock_quantity": forms.NumberInput(attrs={"min": "0"}),
            "sku": forms.TextInput(attrs={"maxlength": 100}),
            "deal_starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "deal_ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "weight": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "length": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "height": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "width": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = store_models.ProductImage
        fields = ["image"]
