# pages/urls.py
from django.urls import path
from . import views

app_name = "addon"

urlpatterns = [
    path("refund-policy/", views.refund_policy, name="refund_policy"),
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
    path("terms-and-conditions/", views.terms_and_conditions, name="terms_and_conditions"),
    path("cookie-policy/", views.cookie_policy, name="cookie_policy"),
    path("shipping-policy/", views.shipping_policy, name="shipping_policy"),

    path("about/", views.about, name="about"),
    path("faqs/", views.faqs, name="faqs"),
    path("contact/", views.contact, name="contact"),
    path("api/contact/submit/", views.contact_submit, name="contact_submit"),
]
