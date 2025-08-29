from django.urls import path
from . import views

app_name = 'store'  # Optional: Use a namespace for better URL management

urlpatterns = [
    path('', views.index, name='index'),
    path('<slug:slug>/', views.product_detail_view, name='product_detail'),
    path('cart/add/', views.add_to_cart, name='cart_add'),
]