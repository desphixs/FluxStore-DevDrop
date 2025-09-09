# userauths/forms.py

from django import forms
from userauths.models import Address

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["address_type", "street_address", "city", "state", "postal_code", "country"]

        widgets = {
            'address_type': forms.Select(attrs={
                'class': 'block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
            'street_address': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': '123 Main Street'
            }),
            'city': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'San Francisco'
            }),
            'state': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'California'
            }),
            'postal_code': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': '94103'
            }),
            'country': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'United States'
            }),
        }