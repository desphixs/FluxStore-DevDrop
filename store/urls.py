from django.urls import path
from . import views

app_name = 'store'  # Optional: Use a namespace for better URL management

urlpatterns = [
    # Store
    path('', views.index, name='index'),

    # Address
    path("addresses/", views.address_list_create, name="address_list_create"),
    path("addresses/<str:uuid>/set-default/", views.set_default_address, name="set_default_address"),

    # Cart
    path('cart/', views.cart_detail, name='cart'),
    path('cart/add/', views.add_to_cart, name='cart_add'),
    path('cart/item/update/', views.update_cart_item_qty, name='update_cart_item_qty'),
    
    # Checkout
    path('checkout/start/', views.begin_checkout, name='checkout_start'),
    path("checkout/<str:order_id>/", views.checkout_view, name="checkout"),

    # Coupon
    path('coupon/apply/', views.apply_coupon, name='apply_coupon'),
    path('coupon/remove/', views.remove_coupon, name='remove_coupon'),
   
    path('<slug:slug>/', views.product_detail_view, name='product_detail'),
]