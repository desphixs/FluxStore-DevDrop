from django.urls import path
from . import views
from . import shoppage

app_name = 'store'  

urlpatterns = [
    
    path('', views.index, name='index'),

    
    path("addresses/", views.address_list_create, name="address_list_create"),
    path("addresses/<str:uuid>/set-default/", views.set_default_address, name="set_default_address"),

    
    path('cart/', views.cart_detail, name='cart'),
    path('cart/add/', views.add_to_cart, name='cart_add'),
    path('cart/item/update/', views.update_cart_item_qty, name='update_cart_item_qty'),
    
    
    path('checkout/start/', views.begin_checkout, name='checkout_start'),
    path("checkout/<str:order_id>/", views.checkout_view, name="checkout"),

    
    path('coupon/apply/', views.apply_coupon, name='apply_coupon'),
    path('coupon/remove/', views.remove_coupon, name='remove_coupon'),

    
    path("shop/", shoppage.shop, name="shop"),
    path("api/products/", shoppage.product_list_api, name="product_list_api"),

    path("shop/label/<slug:label>/", views.products_by_label, name="products_by_label"),
    path("search/", views.search, name="search"),


    path("categories/", views.category_list, name="category_list"),
    path("categories/<slug:slug>-<int:pk>/", views.category_detail, name="category_detail"),
   
    path('<slug:slug>/', views.product_detail_view, name='product_detail'),
]