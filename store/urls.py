from django.urls import path
from . import views

app_name = 'store'  # Optional: Use a namespace for better URL management

urlpatterns = [
    path('', views.index, name='index'),
    path('products/<slug:slug>/', views.product_detail_view, name='product_detail'),
]