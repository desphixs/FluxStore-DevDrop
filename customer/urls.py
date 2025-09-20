from django.urls import path
from . import views

app_name = "customer"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    path("orders/", views.orders_list, name="orders"),
    path("orders/<str:order_id>/", views.order_detail, name="order_detail"),

    path("wishlist/", views.wishlist_page, name="wishlist"),
    path("wishlist/toggle/", views.wishlist_toggle, name="wishlist_toggle"),

    path("reviews/pending/", views.pending_reviews, name="pending_reviews"),
    path("reviews/submit/", views.submit_review, name="submit_review"),

    path("addresses/", views.addresses_page, name="addresses"),

    # ajax
    path("addresses/list/", views.address_list_api, name="address_list_api"),
    path("addresses/create/", views.address_create_api, name="address_create_api"),
    path("addresses/<str:uuid>/update/", views.address_update_api, name="address_update_api"),
    path("addresses/<str:uuid>/delete/", views.address_delete_api, name="address_delete_api"),
    path("addresses/<str:uuid>/set-default/", views.address_set_default_api, name="address_set_default_api"),
    
    path("settings/", views.settings_page, name="settings"),
    path("settings/profile/update/", views.profile_update_api, name="profile_update_api"),

    path("password/change/", views.password_change_view, name="password_change"),

]
