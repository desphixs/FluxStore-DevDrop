# payments/urls.py
from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path('easebuzz/start/<str:order_id>/', views.easebuzz_start, name='easebuzz_start'),
    path('easebuzz/return/', views.easebuzz_return, name='easebuzz_return'),   # SURL & FURL can both point here
    path('easebuzz/webhook/', views.easebuzz_webhook, name='easebuzz_webhook'),
    path("confirm/<str:order_id>/", views.confirm_payment, name="confirm_payment"),
    path('thank-you/<str:order_id>/', views.thank_you, name='thank_you'),
    path('failed/<str:order_id>/', views.failed, name='failed'),
]
