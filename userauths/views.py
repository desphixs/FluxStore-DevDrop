# In your app's views.py

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

from .models import UserProfile, VendorProfile, User

# vendor/views.py
import json
from decimal import Decimal


from django.db import transaction
from django.utils.text import slugify

from userauths.models import VendorProfile, User
from .forms import UserProfileForm, VendorProfileForm



def register_view(request):
    if request.user.is_authenticated:
        return redirect('store:index')
        
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # The form's clean_password2 method has already confirmed passwords match
            user.set_password(form.cleaned_data.get('password'))
            user.save()
            messages.success(request, 'Registration successful! You can now log in.')
            return redirect('userauths:login')
        else:
            # Form is not valid, messages will be displayed on the template
            pass
    else:
        form = RegistrationForm()
        
    return render(request, 'register.html', {'form': form})

def login_view(request):
    
    if request.user.is_authenticated:
        return redirect('store:index')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password')
            user = authenticate(request, email=email, password=password)

            if user is not None:
                # --- MERGE LOGIC STARTS HERE ---

                # Step 1: Capture the guest's session key BEFORE they are logged in.
                # This key is associated with the cart they were using as a guest.
                guest_session_key = request.session.session_key
                print("guest_session_key ==========", guest_session_key)
                # Step 2: Log the user in. This will change the request.user object
                # from AnonymousUser to the authenticated user.
                login(request, user)
                messages.success(request, 'Login successful')

                # Step 3: Now that the user is logged in, attempt to find the guest cart
                # using the key we saved.
                try:
                    # Find the cart that belonged to the guest session and has no user.
                    guest_cart = order_models.Cart.objects.get(session_key=guest_session_key, user__isnull=True)
                    print("guest_cart =============", guest_cart)
                    # Get the authenticated user's cart. get_for_request will create one if it doesn't exist.
                    user_cart = order_models.Cart.get_for_request(request)
                    print("user_cart =============", user_cart)

                    # Use your existing merge method. This will move items and delete the guest cart.
                    # We check if the carts are different to avoid merging a cart into itself.
                    if guest_cart != user_cart:
                        user_cart.merge_from(guest_cart)

                except order_models.Cart.DoesNotExist:
                    # If no guest cart is found, that's fine. Do nothing.
                    pass
                
                # --- MERGE LOGIC ENDS HERE ---

                return redirect('store:index')
            else:
                messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
        
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been successfully logged out.')
    return redirect('userauths:login')

