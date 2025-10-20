from django.urls import path
from . import views, products
from userauths import views as userauths_views
app_name = "vendor"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),

    # Products
    path("products/", views.product_list, name="products"),

    # Orders
    path("orders/", views.orders, name="orders"),
    path("orders/<str:order_id>/", views.order_detail, name="order_detail"),

    path("coupons/", views.coupons_page, name="coupons"),

    # JSON endpoints used by the template JS
    path("coupons/create/", views.coupon_create_ajax, name="coupon_create_ajax"),
    path("coupons/<int:pk>/get/", views.coupon_get_ajax, name="coupon_get_ajax"),
    path("coupons/<int:pk>/update/", views.coupon_update_ajax, name="coupon_update_ajax"),
    path("coupons/<int:pk>/delete/", views.coupon_delete_ajax, name="coupon_delete_ajax"),
    path("coupons/<int:pk>/toggle/", views.coupon_toggle_active_ajax, name="coupon_toggle_active_ajax"),
    
    # Reviews
    path("reviews/", views.reviews_page, name="reviews"),
    path("reviews/<int:pk>/reply/", views.review_reply_ajax, name="review_reply_ajax"),

    path("notifications/", views.notifications_page, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_mark_read_ajax, name="notification_mark_read_ajax"),
    path("notifications/read-all/", views.notification_mark_all_read_ajax, name="notification_mark_all_read_ajax"),
   
    # Settings
    path("settings/", views.settings_page, name="settings"),
    path("settings/user/update/", views.user_update_ajax, name="user_update_ajax"),
    path("settings/vendor/update/", views.vendor_update_ajax, name="vendor_update_ajax"),
    
    
]


urlpatterns += [
    path("products/", products.product_list, name="products"),

    # Create + Edit workspace
    path("products/new/", products.product_create, name="product_create"),

    # Details (AJAX)
    path("products/<int:pk>/update/", products.product_update_details_ajax, name="product_update_details_ajax"),
    path("products/<int:pk>/publish-toggle/", products.product_publish_toggle_ajax, name="product_publish_toggle_ajax"),
    path("products/<int:pk>/feature-toggle/", products.product_feature_toggle_ajax, name="product_feature_toggle_ajax"),

    # Variations (AJAX)
    path("products/<int:pk>/variants/create/", products.product_variation_create_ajax, name="product_variation_create_ajax"),
    path("variants/<int:vid>/update/", products.product_variation_update_ajax, name="product_variation_update_ajax"),
    path("variants/<int:vid>/delete/", products.product_variation_delete_ajax, name="product_variation_delete_ajax"),
    path("variants/<int:vid>/toggle-primary/", products.product_variation_toggle_primary_ajax, name="product_variation_toggle_primary_ajax"),
    path("variants/<int:vid>/toggle-active/", products.product_variation_toggle_active_ajax, name="product_variation_toggle_active_ajax"),
    path("products/<int:pk>/variants/generate/", products.product_variations_generate_ajax, name="product_variations_generate_ajax"),

    # Variation dictionary (vendor-owned) (AJAX)
    path("varcat/create/", products.varcat_create_ajax, name="varcat_create_ajax"),
    path("varcat/<int:cid>/update/", products.varcat_update_ajax, name="varcat_update_ajax"),
    path("varcat/<int:cid>/delete/", products.varcat_delete_ajax, name="varcat_delete_ajax"),
    path("varval/create/", products.varval_create_ajax, name="varval_create_ajax"),
    path("varval/<int:vid>/update/", products.varval_update_ajax, name="varval_update_ajax"),
    path("varval/<int:vid>/delete/", products.varval_delete_ajax, name="varval_delete_ajax"),

    # Images (AJAX)
    path("products/<int:pk>/images/upload/", products.product_image_upload_ajax, name="product_image_upload_ajax"),
    path("images/<int:iid>/delete/", products.product_image_delete_ajax, name="product_image_delete_ajax"),
    path("images/<int:iid>/mark-primary/", products.product_image_mark_primary_ajax, name="product_image_mark_primary_ajax"),

    # --- PRODUCT EDIT PAGE ---
    path("products/<int:pk>/edit/", products.product_edit, name="product_edit"),

    # --- VARIATION DICTIONARY (vendor-scoped) ---
    path("ajax/varcat/create/", products.varcat_create_ajax, name="varcat_create_ajax"),
    path("ajax/varcat/<int:pk>/update/", products.varcat_update_ajax, name="varcat_update_ajax"),
    path("ajax/varcat/<int:pk>/delete/", products.varcat_delete_ajax, name="varcat_delete_ajax"),

    path("ajax/varval/<int:cat_id>/add/", products.varval_add_ajax, name="varval_add_ajax"),
    path("ajax/varval/<int:pk>/delete/", products.varval_delete_ajax, name="varval_delete_ajax"),

    # --- PRODUCT VARIANTS (product-scoped) ---
    path("ajax/product/<int:product_id>/variant/create/", products.variant_create_ajax, name="variant_create_ajax"),
    path("ajax/variant/<int:pk>/get/", products.variant_get_ajax, name="variant_get_ajax"),
    path("ajax/variant/<int:pk>/update/", products.variant_update_ajax, name="variant_update_ajax"),
    path("ajax/variant/<int:pk>/toggle/", products.variant_toggle_active_ajax, name="variant_toggle_active_ajax"),
    path("ajax/variant/<int:pk>/primary/", products.variant_set_primary_ajax, name="variant_set_primary_ajax"),
    path("ajax/variant/<int:pk>/delete/", products.variant_delete_ajax, name="variant_delete_ajax"),


    path("register/", userauths_views.vendor_register_view, name="vendor_register"),
    path("", views.vendors_list, name="vendor_list"),
    path("<slug:slug>/", views.vendor_detail, name="vendor_detail"),

]
