# In your app's views.py

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import RegistrationForm, LoginForm
from .models import User


def register_view(request):
    if request.user.is_authenticated:
        return redirect('core:index')
        
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
        return redirect('core:index')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            password = form.cleaned_data.get('password')
            user = authenticate(request, email=email, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, 'Login successful')
                return redirect('core:index')
            else:
                messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
        
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been successfully logged out.')
    return redirect('userauths:login')
