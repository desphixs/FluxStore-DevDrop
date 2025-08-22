# In your app's urls.py (create this file if it doesn't exist)

from django.urls import path
from . import views

app_name = "userauths"

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
