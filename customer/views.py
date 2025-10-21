from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Sum, Q, F
from django.http import Http404, HttpResponseBadRequest, JsonResponse, HttpResponseForbidden
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django import forms
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.db import IntegrityError, transaction
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash

from order import models as order_model
from store import models as store_model
from userauths import models as userauths_models
from .models import Wishlist, WishlistItem
from customer.forms import AccountSettingsForm
from store import models as store_models
from .models import Wishlist

from decimal import Decimal
from typing import Iterable


PAID_STATUSES = {"PAID", "SUCCESS", "CAPTURED"}  
EXCLUDE_ORDER_STATES_FROM_SPEND = {"CANCELED", "REFUNDED"}
ADDR_REQ_FIELDS = ("address_type","street_address","city","state","postal_code","country")


def _paid_orders_qs(user):
    return order_model.Order.objects.filter(
        buyer=user,
        payment_status__in=PAID_STATUSES
    ).exclude(status__in=EXCLUDE_ORDER_STATES_FROM_SPEND)


def _unpaid_open_orders_qs(user):
    return order_model.Order.objects.filter(
        buyer=user
    ).exclude(payment_status__in=PAID_STATUSES).exclude(status__in=EXCLUDE_ORDER_STATES_FROM_SPEND)


@login_required
def dashboard(request):
    user = request.user

    paid_qs = _paid_orders_qs(user)
    unpaid_qs = _unpaid_open_orders_qs(user)

    totals = paid_qs.aggregate(
        total_spent=Sum("amount_payable"),
        total_items=Sum("items__quantity"),
    )
    total_spent = totals.get("total_spent") or Decimal("0.00")
    total_items = totals.get("total_items") or 0

    total_orders = order_model.Order.objects.filter(buyer=user).count()
    unpaid_count = unpaid_qs.count()
    unpaid_amount = (unpaid_qs.aggregate(x=Sum("amount_payable"))["x"] or Decimal("0.00"))

    
    latest_paid = paid_qs.select_related("address").prefetch_related("items__product_variation__product")[:5]

    wl = Wishlist.for_user(user)
    wishlist_items = wl.items.select_related("product", "product_variation", "product_variation__product")[:5]

    ctx = {
        "stats": {
            "total_orders": total_orders,
            "total_spent": total_spent,
            "total_items_bought": total_items,
            "unpaid_orders": unpaid_count,
            "unpaid_amount": unpaid_amount,
        },
        "latest_paid_orders": latest_paid,
        "wishlist_preview": wishlist_items,
    }
    return render(request, "dashboard.html", ctx)



@login_required
def orders_list(request):
    user = request.user

    show = request.GET.get("show", "paid") 
    qs = order_model.Order.objects.filter(buyer=user)
    if show == "paid":
        qs = _paid_orders_qs(user)
    elif show == "unpaid":
        qs = _unpaid_open_orders_qs(user)
    else:
        pass

    qs = qs.select_related("address").order_by("-created_at")

    paginator = Paginator(qs, 12)
    page = request.GET.get("page") or 1
    page_obj = paginator.get_page(page)

    ctx = {
        "orders_page": page_obj,
        "show": show,
    }
    return render(request, "orders_list.html", ctx)


@login_required
def order_detail(request, order_id: str):
    order = get_object_or_404(
        order_model.Order.objects.select_related("address").prefetch_related(
            "items__product_variation__product", "items__variation_values"
        ),
        buyer=request.user,
        order_id=order_id,
    )
    order.recompute_item_totals_from_items()
    order.recalc_total()

    ctx = {
        "order": order,
        "items": order.items.all(),
        "is_paid": (order.payment_status in PAID_STATUSES),
    }
    return render(request, "order_detail.html", ctx)


def _resolve_product_variation(product_id=None, variation_id=None):
  
    if variation_id:
        pv = get_object_or_404(store_models.ProductVariation, pk=variation_id, is_active=True)
        return pv.product, pv
    if product_id:
        p = get_object_or_404(store_models.Product, pk=product_id, status=store_models.Product.ProductStatus.PUBLISHED)
        return p, None
    return None, None

@login_required
def wishlist_page(request):
    wl = Wishlist.for_user(request.user)
    
    items = (
        wl.items
          .select_related("product", "product_variation", "product_variation__product")
          .prefetch_related("product__images", "product_variation__images", "product_variation__variations")
          .order_by("-added_at")
    )
    return render(request, "wishlist.html", {"wishlist_items": items})

@login_required
@require_POST
@csrf_protect
def wishlist_toggle(request):
    
    
    product_id = request.POST.get("product_id")
    variation_id = request.POST.get("variation_id")

    if not product_id and not variation_id:
        
        try:
            import json
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            data = {}
        product_id = data.get("product_id")
        variation_id = data.get("variation_id")

    if not product_id and not variation_id:
        return HttpResponseBadRequest("Missing product_id or variation_id")

    product, pv = _resolve_product_variation(product_id, variation_id)
    if not product:
        return HttpResponseBadRequest("Invalid product/variation")

    wl = Wishlist.for_user(request.user)

    
    try:
        with transaction.atomic():
            existing = wl.items.filter(
                product=product,
                product_variation=pv
            ).first()

            if existing:
                existing.delete()
                return JsonResponse({
                    "ok": True,
                    "action": "removed",
                    "count": wl.items.count(),
                })
            else:
                created = wl.items.create(product=product, product_variation=pv)
                return JsonResponse({
                    "ok": True,
                    "action": "added",
                    "count": wl.items.count(),
                    "item_id": created.id,
                })
    except IntegrityError:
        
        has_now = wl.items.filter(product=product, product_variation=pv).exists()
        return JsonResponse({
            "ok": True,
            "action": "added" if has_now else "removed",
            "count": wl.items.count(),
        })


@login_required
def pending_reviews(request):
    user = request.user
    items_qs = (
        order_model.OrderItem.objects
        .select_related("product_variation", "product_variation__product", "order")
        .prefetch_related("product_variation__images", "product_variation__variations")
        .filter(
            order__buyer=user,
            order__status=order_model.Order.OrderStatus.DELIVERED,
            order__payment_status__in=PAID_STATUSES,
            product_variation__isnull=False,
        )
        .order_by("-order__created_at", "-id")
    )

    seen_product_ids = set()
    pending_items = []
    for it in items_qs:
        p = it.product_variation.product
        if p is None or p.id in seen_product_ids:
            continue
        
        if store_models.ProductReview.objects.filter(product=p, user=user).exists():
            continue
        pending_items.append(it)
        seen_product_ids.add(p.id)

    return render(request, "pending_reviews.html", {
        "pending_items": pending_items,
    })


@login_required
@require_POST
@csrf_protect
def submit_review(request):
  
    product_id = request.POST.get("product_id")
    rating = request.POST.get("rating")
    comment = (request.POST.get("comment") or "").strip()

    if not product_id or not rating:
        return HttpResponseBadRequest("product_id and rating are required")

    try:
        rating = int(rating)
    except ValueError:
        return HttpResponseBadRequest("Invalid rating")

    if rating < 1 or rating > 5:
        return HttpResponseBadRequest("Rating must be between 1 and 5")

    product = get_object_or_404(store_models.Product, pk=product_id)

    
    eligible = order_model.OrderItem.objects.filter(
        order__buyer=request.user,
        order__status=order_model.Order.OrderStatus.DELIVERED,
        order__payment_status__in=PAID_STATUSES,
        product_variation__product=product,
    ).exists()

    if not eligible:
        return HttpResponseForbidden("You’re not eligible to review this product yet")

    
    review, created = store_models.ProductReview.objects.update_or_create(
        product=product,
        user=request.user,
        defaults={"rating": rating, "comment": comment},
    )

    return JsonResponse({
        "ok": True,
        "created": created,
        "message": "Thanks for your review!",
        "product_id": product.id,
        "rating": rating,
    })



def _profile_or_404(user):
    try:
        return user.profile
    except userauths_models.UserProfile.DoesNotExist:
        raise Http404("Profile not found")

def _serialize_address(a: userauths_models.Address):
    return {
        "uuid": str(a.uuid),
        "address_type": a.address_type,
        "address_type_label": a.get_address_type_display(),
        "full_name": a.full_name or "",
        "phone": a.phone or "",
        "street_address": a.street_address,
        "city": a.city,
        "state": a.state,
        "postal_code": a.postal_code,
        "country": a.country,
        "is_default": bool(a.is_default),
    }

@login_required
def addresses_page(request):
    
    return render(request, "addresses.html", {
        "view": "customer:addresses",
    })

@login_required
def address_list_api(request):
    profile = _profile_or_404(request.user)
    qs = (profile.addresses
                  .order_by("-is_default","-id"))
    data = [_serialize_address(a) for a in qs]
    return JsonResponse({"ok": True, "items": data})

@login_required
@require_POST
@csrf_protect
def address_create_api(request):
    profile = _profile_or_404(request.user)
    payload = request.POST

    
    missing = [f for f in ADDR_REQ_FIELDS if not payload.get(f)]
    if missing:
        return HttpResponseBadRequest(f"Missing fields: {', '.join(missing)}")

    is_default = payload.get("is_default") in ("1","true","True","on","yes")
    addr = userauths_models.Address(
        profile=profile,
        address_type=payload["address_type"],
        full_name=payload.get("full_name") or "",
        phone=payload.get("phone") or "",
        street_address=payload["street_address"],
        city=payload["city"],
        state=payload["state"],
        postal_code=payload["postal_code"],
        country=payload["country"],
        is_default=is_default,
    )
    with transaction.atomic():
        addr.save()  

    return JsonResponse({"ok": True, "item": _serialize_address(addr)})

@login_required
@require_POST
@csrf_protect
def address_update_api(request, uuid):
    profile = _profile_or_404(request.user)
    addr = get_object_or_404(userauths_models.Address, uuid=uuid, profile=profile)

    payload = request.POST
    for f in ADDR_REQ_FIELDS:
        if f in payload and payload.get(f) == "":
            return HttpResponseBadRequest(f"{f} cannot be empty")

    
    for f in ("address_type","full_name","phone","street_address","city","state","postal_code","country"):
        if f in payload:
            setattr(addr, f, payload.get(f))

    if "is_default" in payload:
        addr.is_default = payload.get("is_default") in ("1","true","True","on","yes")

    with transaction.atomic():
        addr.save()

    return JsonResponse({"ok": True, "item": _serialize_address(addr)})

@login_required
@require_POST
@csrf_protect
def address_delete_api(request, uuid):
    profile = _profile_or_404(request.user)
    addr = get_object_or_404(userauths_models.Address, uuid=uuid, profile=profile)
    addr.delete()
    return JsonResponse({"ok": True})

@login_required
@require_POST
@csrf_protect
def address_set_default_api(request, uuid):
    profile = _profile_or_404(request.user)
    addr = get_object_or_404(userauths_models.Address, uuid=uuid, profile=profile)

    with transaction.atomic():
        
        userauths_models.Address.objects.filter(
            profile=profile, address_type=addr.address_type
        ).update(is_default=False)
        addr.is_default = True
        addr.save()

    return JsonResponse({"ok": True, "item": _serialize_address(addr)})

def _serialize_profile(p: userauths_models.UserProfile):
    return {
        "full_name": p.full_name or "",
        "phone_number": p.phone_number or "",
        "image_url": p.image.url if p.image else "",
        "email": p.user.email,
    }

@login_required
def settings_page(request):
    try:
        profile = request.user.profile
    except userauths_models.UserProfile.DoesNotExist:
        
        profile = userauths_models.UserProfile.objects.create(user=request.user)

    return render(request, "settings.html", {
        "view": "customer:settings",   
        "profile": profile,
    })

@login_required
@require_POST
@csrf_protect
def profile_update_api(request):
    user = request.user
    try:
        profile = user.profile
    except userauths_models.UserProfile.DoesNotExist:
        profile = userauths_models.UserProfile.objects.create(user=user)

    full_name = (request.POST.get("full_name") or "").strip()
    phone     = (request.POST.get("phone_number") or "").strip()
    remove_image = (request.POST.get("remove_image") in ("1","true","True","on","yes"))

    
    if len(full_name) > 100:
        return HttpResponseBadRequest("Full name is too long (max 100 chars).")
    if len(phone) > 20:
        return HttpResponseBadRequest("Phone is too long (max 20 chars).")

    file_obj = request.FILES.get("image")
    if file_obj and not isinstance(file_obj, (InMemoryUploadedFile, TemporaryUploadedFile)):
        return HttpResponseBadRequest("Bad file upload.")

    
    profile.full_name = full_name
    profile.phone_number = phone

    if remove_image:
        if profile.image:
            profile.image.delete(save=False)
        profile.image = None
    elif file_obj:
        
        if profile.image:
            profile.image.delete(save=False)
        profile.image = file_obj

    profile.save()

    return JsonResponse({
        "ok": True,
        "profile": _serialize_profile(profile),
        "message": "Profile updated.",
    })


from django.urls import reverse

@login_required
def password_change_view(request):
    changed = request.GET.get("changed") == "1"

    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  
            
            return redirect(f"{reverse('customer:password_change')}?changed=1")
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "password_change.html", {
        "view": "customer:settings",  
        "form": form,
        "changed": changed,
    })