# pages/views.py
from django.shortcuts import render, get_object_or_404
from .models import Page, FAQ
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from .models import ContactMessage


def refund_policy(request):
    page = get_object_or_404(Page, key=Page.Key.REFUND_POLICY, is_published=True)
    context = {"page_title": page.title, "page": page}
    return render(request, "pages/refund_policy.html", context)

def privacy_policy(request):
    page = get_object_or_404(Page, key=Page.Key.PRIVACY_POLICY, is_published=True)
    return render(request, "pages/privacy_policy.html", {"page_title": page.title, "page": page})

def terms_and_conditions(request):
    page = get_object_or_404(Page, key=Page.Key.TERMS_AND_CONDITIONS, is_published=True)
    return render(request, "pages/terms_and_conditions.html", {"page_title": page.title, "page": page})

def cookie_policy(request):
    page = get_object_or_404(Page, key=Page.Key.COOKIE_POLICY, is_published=True)
    return render(request, "pages/cookie_policy.html", {"page_title": page.title, "page": page})

def shipping_policy(request):
    page = get_object_or_404(Page, key=Page.Key.SHIPPING_POLICY, is_published=True)
    return render(request, "pages/shipping_policy.html", {"page_title": page.title, "page": page})

def about(request):
    page = get_object_or_404(Page, key=Page.Key.ABOUT, is_published=True)
    return render(request, "pages/about.html", {"page_title": page.title, "page": page})

def faqs(request):
    faqs = FAQ.objects.filter(is_active=True).select_related("category").order_by("sort_order", "id")
    categories = {}
    for f in faqs:
        categories.setdefault(f.category.name if f.category else "General", []).append(f)
    return render(request, "pages/faqs.html", {"page_title": "FAQs", "categories": categories, "faqs": faqs})

def contact(request):
    faqs = FAQ.objects.filter(is_active=True)
    context = {
        "page_title": "Contact Us",
        "faqs": faqs,
    }
    return render(request, "pages/contact.html", context)


@require_POST
def contact_submit(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    consent = bool(data.get("consent", False))

    # Basic validations
    if not name or not email or not message:
        return JsonResponse({"ok": False, "error": "Name, email and message are required."}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"ok": False, "error": "Please provide a valid email."}, status=400)

    # Save
    ContactMessage.objects.create(
        name=name,
        email=email,
        subject=subject,
        message=message,
        consent=consent,
    )

    return JsonResponse({"ok": True, "message": "Thanks! Your message has been received."}, status=201)