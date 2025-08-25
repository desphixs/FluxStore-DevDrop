from django.urls import path
from . import views

app_name = 'store'  # Optional: Use a namespace for better URL management

urlpatterns = [
    path('', views.product_list_view, name='product_list'),
    path('products/<slug:slug>/', views.product_detail_view, name='product_detail'),
]