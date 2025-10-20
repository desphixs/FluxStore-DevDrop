from decimal import Decimal
from typing import Optional
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, F, Sum, Count, DecimalField, ExpressionWrapper
from django.db.models import Q, F, Sum, Value, IntegerField, DecimalField, Case, When, ExpressionWrapper

from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from order import models as order_models
from store import models as store_models
from .models import Notification
from .forms import CouponForm

from django.db.models.functions import Coalesce
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.utils import timezone
from .forms import CouponForm


import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from store import models as store_models

# vendor/views.py
import json
from decimal import Decimal


from django.db import transaction
from django.utils.text import slugify

from userauths.models import VendorProfile, User
from userauths.forms import UserProfileForm, VendorProfileForm


from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count, Avg, Min, Max
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator

from userauths.models import VendorProfile
from store.models import Product  


def vendors_list(request):
    q = (request.GET.get("q") or "").strip()

    vendors = (
        VendorProfile.objects.select_related("user")
        .annotate(
            total_products=Count(
                "user__products",
                filter=Q(user__products__status=Product.ProductStatus.PUBLISHED),
                distinct=True,
            ),
            avg_rating=Coalesce(Avg("user__products__reviews__rating"), 0.0),
            reviews_count=Count("user__products__reviews", distinct=True),
            in_stock_skus=Count(
                "user__products__variations",
                filter=Q(
                    user__products__variations__is_active=True,
                    user__products__variations__stock_quantity__gt=0,
                ),
                distinct=True,
            ),
            active_deals=Count(
                "user__products__variations",
                filter=Q(
                    user__products__variations__is_active=True,
                    user__products__variations__deal_active=True,
                ),
                distinct=True,
            ),
            min_price=Min(
                "user__products__variations__sale_price",
                filter=Q(user__products__variations__is_primary=True),
            ),
            max_price=Max(
                "user__products__variations__sale_price",
                filter=Q(user__products__variations__is_primary=True),
            ),
        )
        .order_by("-is_verified", "business_name")
    )

    if q:
        vendors = vendors.filter(
            Q(business_name__icontains=q) | Q(user__email__icontains=q)
        )

    paginator = Paginator(vendors, 24)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "vendor/vendor_list.html",
        {
            "page_title": "Vendors",
            "page_obj": page_obj,
            "q": q,
        },
    )

def vendor_detail(request, slug):
    vendor = get_object_or_404(
        VendorProfile.objects.select_related("user"),
        slug=slug,
    )

    products_qs = (
        Product.objects.filter(
            vendor=vendor.user,
            status=Product.ProductStatus.PUBLISHED,
        )
        .select_related("category")
        .prefetch_related("images", "variations", "reviews")
        .order_by("-created_at")
    )

    stats = products_qs.aggregate(
        avg_rating=Avg("reviews__rating"),
        reviews_count=Count("reviews", distinct=True),
        total_products=Count("id", distinct=True),
        min_price=Min("variations__sale_price", filter=Q(variations__is_primary=True)),
        max_price=Max("variations__sale_price", filter=Q(variations__is_primary=True)),
        in_stock_skus=Count(
            "variations",
            filter=Q(variations__is_active=True, variations__stock_quantity__gt=0),
            distinct=True,
        ),
        active_deals=Count(
            "variations",
            filter=Q(variations__is_active=True, variations__deal_active=True),
            distinct=True,
        ),
    )

    paginator = Paginator(products_qs, 12)  # 12 per page
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "vendor/vendor_detail.html",
        {
            "page_title": vendor.business_name,
            "vendor": vendor,
            "page_obj": page_obj,
            "stats": stats,
        },
    )




def _is_ajax(request):
    # fetch() won’t set this automatically, so we just accept JSON or form posts as “ajax”.
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or request.content_type in (
        "application/json", "multipart/form-data", "application/x-www-form-urlencoded"
    )

def is_vendor(user):
    try:
        return user.is_authenticated and str(getattr(user, "role", "")).upper() == "VENDOR"
    except Exception:
        return False

vendor_required = user_passes_test(is_vendor)

def paginate(request, qs, per_page=20):
    page = request.GET.get("page") or 1
    paginator = Paginator(qs, per_page)
    return paginator.get_page(page)

def money(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(Decimal("0.01"))

def vendor_order_annotations(vendor):
    gross = Sum(
        F("items__price") * F("items__quantity"),
        filter=Q(items__vendor=vendor),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    disc = Sum(
        F("items__line_discount_total"),
        filter=Q(items__vendor=vendor),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    item_count = Count("items", filter=Q(items__vendor=vendor))
    return {
        "v_gross": Coalesce(gross, Decimal(0)),
        "v_disc": Coalesce(disc, Decimal(0)),
        "v_item_count": Coalesce(item_count, 0),
    }

@login_required
@vendor_required
def dashboard(request):
    vendor = request.user

    # Core stats
    total_products = store_models.Product.objects.filter(vendor=vendor).count()

    vendor_items = order_models.OrderItem.objects.filter(vendor=vendor)
    total_orders = (
        order_models.Order.objects.filter(items__vendor=vendor)
        .distinct()
        .count()
    )
    unpaid_orders = (
        order_models.Order.objects.filter(items__vendor=vendor)
        .exclude(payment_status="PAID")
        .distinct()
        .count()
    )

    paid_items = vendor_items.filter(order__payment_status="PAID")
    agg = paid_items.aggregate(
        gross=Coalesce(Sum(F("price") * F("quantity"), output_field=DecimalField(max_digits=12, decimal_places=2)), Decimal(0)),
        disc=Coalesce(Sum("line_discount_total", output_field=DecimalField(max_digits=12, decimal_places=2)), Decimal(0)),
    )
    revenue_net = money(agg["gross"] - agg["disc"])

    unread_notifs = Notification.objects.filter(recipient=vendor, is_read=False).count()

    # Latest paid orders (vendor-scoped)
    paid_orders = (
        order_models.Order.objects.filter(items__vendor=vendor, payment_status="PAID")
        .annotate(**vendor_order_annotations(vendor))
        .annotate(
            v_net=ExpressionWrapper(F("v_gross") - F("v_disc"), output_field=DecimalField(max_digits=12, decimal_places=2))
        )
        .select_related("buyer")
        .order_by("-created_at")[:10]
    )

    ctx = {
        "stats": {
            "total_products": total_products,
            "total_orders": total_orders,
            "unpaid_orders": unpaid_orders,
            "revenue_net": revenue_net,
            "unread_notifications": unread_notifs,
        },
        "paid_orders": paid_orders,
    }
    return render(request, "vendor/vendor_dashboard.html", ctx)


@login_required
@vendor_required
def product_list(request):
    from decimal import Decimal
    from django.db.models import (
        Q, Sum, Count, F, DecimalField, IntegerField, OuterRef, Subquery, Value
    )
    from django.db.models.functions import Coalesce

    vendor = request.user
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").upper()

    qs = (
        store_models.Product.objects
        .filter(vendor=vendor)
        .select_related("category")
        .prefetch_related("images", "variations", "reviews")
    )

    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(slug__icontains=q) |
            Q(description__icontains=q)
        )
    if status in dict(store_models.Product.ProductStatus.choices):
        qs = qs.filter(status=status)

    # --- counts/stock (Integer) ---
    qs = qs.annotate(
        variant_count=Coalesce(
            Count("variations", distinct=True),
            Value(0),
            output_field=IntegerField(),
        ),
        stock_total=Coalesce(
            Sum("variations__stock_quantity", output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        ),
    )

    # --- sold qty / revenue (qty = Integer, revenue = Decimal) ---
    oi_base = (
        order_models.OrderItem.objects
        .filter(
            vendor=vendor,
            product_variation__product=OuterRef("pk"),
            order__payment_status="PAID",
        )
    )

    sold_qty_subq = (
        oi_base.values("product_variation__product")
        .annotate(
            total_qty=Coalesce(
                Sum("quantity", output_field=IntegerField()),
                Value(0),
                output_field=IntegerField(),
            )
        )
        .values("total_qty")[:1]
    )

    sold_rev_subq = (
        oi_base.values("product_variation__product")
        .annotate(
            total_rev=Coalesce(
                # ensure Decimal math and type
                Sum(
                    F("price") * F("quantity"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        .values("total_rev")[:1]
    )

    qs = qs.annotate(
        sold_qty=Coalesce(
            Subquery(sold_qty_subq, output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        ),
        sold_revenue=Coalesce(
            Subquery(sold_rev_subq, output_field=DecimalField(max_digits=12, decimal_places=2)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
    ).order_by("-created_at")

    page = paginate(request, qs, per_page=20)
    status_choices = list(store_models.Product.ProductStatus.choices)

    mode = (request.GET.get("view") or request.session.get("vendor_products_view") or "grid").lower()
    if mode not in ("grid", "list"):
        mode = "grid"
    # persist user choice only when explicitly provided
    if "view" in request.GET:
        request.session["vendor_products_view"] = mode

    return render(
        request,
        "vendor/products_list.html",
        {
            "page": page,
            "q": q,
            "status": status,
            "status_choices": status_choices,
            "mode": mode,
        }
    )



@login_required
@vendor_required
def order_detail(request, order_id: str):
    vendor = request.user

    order = get_object_or_404(
        order_models.Order.objects.select_related("buyer", "address"),
        order_id=order_id,
        items__vendor=vendor,
    )

    dec = DecimalField(max_digits=12, decimal_places=2)
    intf = IntegerField()

    items = (
        order_models.OrderItem.objects
        .filter(order=order, vendor=vendor)
        .select_related("product_variation", "product_variation__product")
        .prefetch_related("variation_values", "product_variation__product__images")
        .annotate(
            line_subtotal=ExpressionWrapper(F("price") * F("quantity"), output_field=dec),
            line_net=ExpressionWrapper(F("price") * F("quantity") - F("line_discount_total"), output_field=dec),
        )
        .order_by("id")
    )

    agg = items.aggregate(
        gross=Coalesce(Sum("line_subtotal", output_field=dec), Value(0, output_field=dec)),
        disc=Coalesce(Sum("line_discount_total", output_field=dec), Value(0, output_field=dec)),
        qty=Coalesce(Sum("quantity", output_field=intf), Value(0, output_field=intf)),
    )
    totals = {
        "items_count": agg["qty"],
        "gross": agg["gross"],
        "discount": agg["disc"],
        "net": (agg["gross"] or 0) - (agg["disc"] or 0),
        "currency": order.currency or "INR",
    }

    coupons_for_vendor = []
    if hasattr(order, "applied_coupons_summary"):
        for c in order.applied_coupons_summary():
            if c.get("vendor_id") == vendor.id:
                coupons_for_vendor.append(c)

    ctx = {
        "order": order,
        "items": items,
        "totals": totals,
        "is_paid": (order.payment_status == "PAID"),
        "is_unpaid": (order.payment_status != "PAID"),
        "coupons": coupons_for_vendor,
    }
    return render(request, "vendor/order_detail.html", ctx)





def coupon_to_dict(c: order_models.Coupon, with_stats=False):
    d = {
        "id": c.id,
        "code": c.code,
        "title": c.title or "",
        "description": c.description or "",
        "discount_type": c.discount_type,
        "percent_off": str(c.percent_off) if c.percent_off is not None else None,
        "amount_off": str(c.amount_off) if c.amount_off is not None else None,
        "max_discount_amount": str(c.max_discount_amount) if c.max_discount_amount is not None else None,
        "min_order_amount": str(c.min_order_amount) if c.min_order_amount is not None else None,
        "starts_at": c.starts_at.isoformat() if c.starts_at else None,
        "ends_at": c.ends_at.isoformat() if c.ends_at else None,
        "usage_limit_total": c.usage_limit_total,
        "usage_limit_per_user": c.usage_limit_per_user,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }
    if with_stats:
        uses = c.redemptions.aggregate(
            cnt=Coalesce(Count("id"), Value(0, output_field=IntegerField())),
            sum_amt=Coalesce(Sum("discount_amount", output_field=DecimalField(max_digits=12, decimal_places=2)),
                             Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))),
        )
        d["redemptions_count"] = int(uses["cnt"] or 0)
        d["discount_granted_total"] = str(uses["sum_amt"] or Decimal("0"))
    return d




def coupon_to_dict(c, with_stats=False):
    def _str(x):
        return None if x is None else str(x)

    data = {
        "id": c.id,
        "code": c.code,
        "title": c.title or "",
        "description": c.description or "",
        "discount_type": c.discount_type,
        "percent_off": _str(c.percent_off),
        "amount_off": _str(c.amount_off),
        "max_discount_amount": _str(c.max_discount_amount),
        "min_order_amount": _str(c.min_order_amount),
        "is_active": bool(c.is_active),
        "starts_at": c.starts_at.isoformat() if c.starts_at else None,
        "ends_at": c.ends_at.isoformat() if c.ends_at else None,
        "usage_limit_total": c.usage_limit_total,
        "usage_limit_per_user": c.usage_limit_per_user,
    }
    if with_stats:
        # annotate-access (when present) or compute zeros
        data["redemptions_count"] = getattr(c, "redemptions_count", 0) or 0
        dgt = getattr(c, "discount_granted_total", None)
        data["discount_granted_total"] = _str(dgt or Decimal("0.00"))
    return data



@login_required
@vendor_required
def coupons_page(request):
   
    vendor = request.user

    q = (request.GET.get("q") or "").strip()
    state = (request.GET.get("state") or "").lower() 

    qs = order_models.Coupon.objects.filter(vendor=vendor)

    if q:
        qs = qs.filter(
            Q(code__icontains=q) |
            Q(title__icontains=q) |
            Q(description__icontains=q)
        )

    now = timezone.now()
    if state == "active":
        qs = qs.filter(is_active=True)
    elif state == "inactive":
        qs = qs.filter(is_active=False)
    elif state == "live":
        qs = qs.filter(is_active=True).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gte=now),
        )
    elif state == "scheduled":
        qs = qs.filter(is_active=True, starts_at__gt=now)
    elif state == "expired":
        qs = qs.filter(ends_at__lt=now)

    zero_dec = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))

    coupons = (
        qs
        .annotate(
            redemptions_count=Coalesce(Count("redemptions"), 0),
            discount_granted_total=Coalesce(Sum("redemptions__discount_amount"), zero_dec),
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "vendor/coupons.html",
        {
            "filters": {"q": q, "state": state},
            "coupons": coupons,  # loop server-side
        },
    )


# ---------- JSON endpoints (modals) ----------

@login_required
@vendor_required
def coupon_get_ajax(request, pk: int):
    if request.method != "GET" or not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vendor = request.user
    c = get_object_or_404(order_models.Coupon, pk=pk, vendor=vendor)

    # annotate stats for modal (optional)
    c.redemptions_count = c.redemptions.count()
    c.discount_granted_total = c.redemptions.aggregate(
        s=Coalesce(Sum("discount_amount"), Decimal("0.00"))
    )["s"]

    return JsonResponse({"ok": True, "coupon": coupon_to_dict(c, with_stats=True)})


@login_required
@vendor_required
@require_POST
def coupon_create_ajax(request):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vendor = request.user

    # Accept JSON or form-encoded
    data = request.POST.dict()
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            data = {}

    form = CouponForm(data=data, vendor=vendor)
    if form.is_valid():
        c = form.save()
        # add stats for card
        c.redemptions_count = 0
        c.discount_granted_total = Decimal("0.00")
        return JsonResponse({"ok": True, "message": "Coupon created.", "coupon": coupon_to_dict(c, with_stats=True)})
    else:
        return JsonResponse({"ok": False, "message": "Validation error.", "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
def coupon_update_ajax(request, pk: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vendor = request.user
    c = get_object_or_404(order_models.Coupon, pk=pk, vendor=vendor)

    data = request.POST.dict()
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            data = {}

    form = CouponForm(data=data, instance=c, vendor=vendor)
    if form.is_valid():
        c = form.save()
        # include fresh stats
        c.redemptions_count = c.redemptions.count()
        c.discount_granted_total = c.redemptions.aggregate(
            s=Coalesce(Sum("discount_amount"), Decimal("0.00"))
        )["s"]
        return JsonResponse({"ok": True, "message": "Coupon updated.", "coupon": coupon_to_dict(c, with_stats=True)})
    else:
        return JsonResponse({"ok": False, "message": "Validation error.", "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
def coupon_delete_ajax(request, pk: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vendor = request.user
    c = get_object_or_404(order_models.Coupon, pk=pk, vendor=vendor)
    c.delete()
    return JsonResponse({"ok": True, "message": "Coupon deleted.", "id": pk})


@login_required
@vendor_required
@require_POST
def coupon_toggle_active_ajax(request, pk: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vendor = request.user
    c = get_object_or_404(order_models.Coupon, pk=pk, vendor=vendor)
    c.is_active = not c.is_active
    c.save(update_fields=["is_active", "updated_at"])

    # return full payload so the card can re-render
    c.redemptions_count = c.redemptions.count()
    c.discount_granted_total = c.redemptions.aggregate(
        s=Coalesce(Sum("discount_amount"), Decimal("0.00"))
    )["s"]
    return JsonResponse({"ok": True, "message": "Toggled.", "coupon": coupon_to_dict(c, with_stats=True)})


def _paginate(request, qs, per_page=20):
    paginator = Paginator(qs, per_page)
    page_num = request.GET.get("page")
    try:
        page = paginator.page(page_num)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)
    return page


def _review_to_dict(r):
    return {
        "id": r.id,
        "product_id": r.product_id,
        "product_name": r.product.name,
        "user_id": r.user_id,
        "user_name": (r.user.get_full_name() or r.user.username or r.user.email),
        "user_email": r.user.email,
        "rating": r.rating,
        "comment": r.comment or "",
        "reply": r.reply or "",
        "created_at": r.created_at.isoformat(),
    }


@login_required
@vendor_required
def reviews_page(request):
    
    vendor = request.user
    q = (request.GET.get("q") or "").strip()
    rating = request.GET.get("rating")
    status = (request.GET.get("status") or "").lower()

    qs = (
        store_models.ProductReview.objects
        .filter(product__vendor=vendor)
        .select_related("product", "user")
        .prefetch_related("product__images")
        .order_by("-created_at")
    )

    if q:
        qs = qs.filter(
            Q(product__name__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__username__icontains=q) |
            Q(comment__icontains=q)
        )

    if rating and rating.isdigit():
        r = int(rating)
        if 1 <= r <= 5:
            qs = qs.filter(rating=r)

    if status == "replied":
        qs = qs.exclude(reply__isnull=True).exclude(reply__exact="")
    elif status == "unreplied":
        qs = qs.filter(Q(reply__isnull=True) | Q(reply__exact=""))

    page = _paginate(request, qs, per_page=15)

    ctx = {
        "page": page,
        "filters": {
            "q": q,
            "rating": rating or "",
            "status": status,
        },
    }
    return render(request, "vendor/reviews.html", ctx)


@login_required
@vendor_required
@require_POST
def review_reply_ajax(request, pk: int):
   
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")

    vendor = request.user
    review = get_object_or_404(
        store_models.ProductReview.objects.select_related("product", "user"),
        pk=pk,
        product__vendor=vendor,
    )

    # Accept JSON or form-encoded
    data = request.POST.dict()
    if request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            data = {}

    reply = (data.get("reply") or "").strip()
    # Set to None to "clear"
    review.reply = reply if reply else None
    review.save(update_fields=["reply"])

    return JsonResponse({"ok": True, "review": _review_to_dict(review)})



@login_required
@vendor_required
def settings_view(request):
    vendor = request.user
    vprof = getattr(vendor, "vendor_profile", None)  # you referenced vendor_profile in VariationCategory.__str__

    if request.method == "POST":
        # Example: update business_name, support_email if fields exist
        updated = 0
        if vprof and hasattr(vprof, "business_name"):
            name = (request.POST.get("business_name") or "").strip()
            if name:
                vprof.business_name = name
                updated += 1
        if vprof and hasattr(vprof, "support_email"):
            semail = (request.POST.get("support_email") or "").strip()
            if semail:
                vprof.support_email = semail
                updated += 1
        if updated and vprof:
            vprof.save()
            messages.success(request, "Settings saved.")
        else:
            messages.info(request, "No changes.")
        return redirect(reverse("vendor:settings"))

    ctx = {"vendor": vendor, "vendor_profile": vprof}
    return render(request, "settings.html", ctx)

def paginate(request, qs, per_page=24):
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)

@login_required
@vendor_required
def orders(request):
    vendor = request.user
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").upper()
    pay = (request.GET.get("pay") or "").upper() 
    view_mode = (request.GET.get("view") or "grid").lower()

    qs = (
        order_models.Order.objects
        .filter(items__vendor=vendor)
        .select_related("buyer")
        .distinct()
    )

    if q:
        qs = qs.filter(
            Q(order_id__icontains=q) |
            Q(buyer__email__icontains=q) |
            Q(buyer__first_name__icontains=q) |
            Q(buyer__last_name__icontains=q)
        )

    # Fulfillment status filter
    valid_status = dict(order_models.Order.OrderStatus.choices)
    if status in valid_status:
        qs = qs.filter(status=status)

    # Payment status filter
    if pay == "PAID":
        qs = qs.filter(payment_status="PAID")
    elif pay == "UNPAID":
        qs = qs.exclude(payment_status="PAID")

    # Safe annotations (set output_field to avoid Decimal/Integer mixing errors)
    dec = DecimalField(max_digits=12, decimal_places=2)
    intf = IntegerField()

    v_gross = Coalesce(Sum(
        Case(
            When(items__vendor=vendor, then=F("items__price") * F("items__quantity")),
            default=Value(0),
            output_field=dec,
        )
    ), Value(0, output_field=dec))

    v_disc = Coalesce(Sum(
        Case(
            When(items__vendor=vendor, then=F("items__line_discount_total")),
            default=Value(0),
            output_field=dec,
        )
    ), Value(0, output_field=dec))

    v_item_count = Coalesce(Sum(
        Case(
            When(items__vendor=vendor, then=F("items__quantity")),
            default=Value(0),
            output_field=intf,
        )
    ), Value(0, output_field=intf))

    qs = qs.annotate(
        v_gross=v_gross,
        v_disc=v_disc,
        v_item_count=v_item_count,
    ).annotate(
        v_net=ExpressionWrapper(F("v_gross") - F("v_disc"), output_field=dec)
    ).order_by("-created_at")

    page = paginate(request, qs, per_page=24)

    ctx = {
        "page": page,
        "q": q,
        "status": status,
        "pay": pay,
        "view_mode": "list" if view_mode == "list" else "grid",
        "status_choices": order_models.Order.OrderStatus.choices,
    }
    return render(request, "vendor/orders_list.html", ctx)




@login_required
@vendor_required
def notifications_page(request):
    
    user = request.user

    q = (request.GET.get("q") or "").strip()
    state = (request.GET.get("state") or "").lower()          # '', 'unread', 'read'
    ntype = (request.GET.get("ntype") or "").upper()          # ORDER, PRODUCT, REVIEW, COUPON, PAYOUT, SYSTEM
    level = (request.GET.get("level") or "").upper()          # INFO, SUCCESS, WARNING, ERROR
    view_mode = (request.GET.get("view") or "grid").lower()   # 'grid' or 'list'

    qs = order_models.Notification.objects.filter(recipient=user).select_related("content_type").order_by("-created_at")

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(message__icontains=q))
    if state == "unread":
        qs = qs.filter(is_read=False)
    elif state == "read":
        qs = qs.filter(is_read=True)
    if ntype in dict(order_models.Notification.NType.choices):
        qs = qs.filter(ntype=ntype)
    if level in dict(order_models.Notification.Level.choices):
        qs = qs.filter(level=level)

    unread_count = order_models.Notification.objects.filter(recipient=user, is_read=False).count()

    page = paginate(request, qs, per_page=20)

    return render(
        request,
        "vendor/notifications.html",
        {
            "filters": {
                "q": q,
                "state": state,
                "ntype": ntype,
                "level": level,
                "view": view_mode,
            },
            "page": page,
            "unread_count": unread_count,
            "ntype_choices": order_models.Notification.NType.choices,
            "level_choices": order_models.Notification.Level.choices,
        },
    )


@login_required
@vendor_required
@require_POST
def notification_mark_read_ajax(request, pk: int):
    
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")

    n = get_object_or_404(order_models.Notification, pk=pk, recipient=request.user)
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=["is_read"])
    return JsonResponse({"ok": True, "id": pk, "is_read": True})


@login_required
@vendor_required
@require_POST
def notification_mark_all_read_ajax(request):
    
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")

    updated = order_models.Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"ok": True, "updated": updated})





def vendor_required(view_func):
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        # assumes you have user.role == "VENDOR"
        if getattr(user, "role", "").upper() != "VENDOR":
            return HttpResponseBadRequest("Vendor account required.")
        return view_func(request, *args, **kwargs)
    return _wrapped




def _is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _ensure_vendor_profile(user: User) -> VendorProfile:
   
    try:
        return user.vendor_profile
    except VendorProfile.DoesNotExist:
        # Create minimal, satisfying NOT NULL fields
        business_name = f"Store-{user.id or user.pk}"
        contact_email = user.email or f"vendor-{user.id}@example.com"
        vp = VendorProfile.objects.create(
            user=user,
            business_name=business_name,
            slug=slugify(business_name),
            contact_email=contact_email,
            business_phone="",
            business_address="",
            currency="USD",
            country="NG",
            min_order_amount=Decimal("0.00"),
            is_open=True,
        )
        return vp


@login_required
@vendor_required
def settings_page(request):
    
    user = request.user
    vprof = _ensure_vendor_profile(user)

    user_form = UserProfileForm(instance=user)
    # seed socials_* for rendering
    initial_vendor = {}
    if vprof.socials:
        for k in ("instagram", "twitter", "facebook", "tiktok"):
            initial_vendor[f"socials_{k}"] = vprof.socials.get(k, "")
    vendor_form = VendorProfileForm(instance=vprof, initial=initial_vendor)

    ctx = {
        "user_form": user_form,
        "vendor_form": vendor_form,
    }
    return render(request, "vendor/vendor_settings.html", ctx)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def user_update_ajax(request):
    
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    user = request.user

    data = request.POST if request.content_type.startswith("multipart/") else None
    if data is None:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            data = {}

    form = UserProfileForm(data=data, instance=user)
    if form.is_valid():
        u = form.save()
        return JsonResponse({
            "ok": True,
            "message": "Profile updated.",
            "user": {
                "first_name": u.first_name,
                "last_name": u.last_name,
                "email": u.email,
            }
        })
    return JsonResponse({"ok": False, "message": "Validation error.", "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def vendor_update_ajax(request):
    
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    user = request.user
    vprof = _ensure_vendor_profile(user)

    if request.content_type.startswith("multipart/"):
        # Files + regular fields
        data = request.POST
        files = request.FILES
        form = VendorProfileForm(data=data, files=files, instance=vprof)
    else:
        # JSON; no files (cannot send files in JSON)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        form = VendorProfileForm(data=payload, instance=vprof)

    if form.is_valid():
        vp = form.save(commit=False)
        # socials were put into cleaned_data in clean()
        vp.socials = form.cleaned_data.get("socials")
        vp.save()

        # handle optional clear flags for images
        # if you add checkboxes named logo_clear/banner_clear in the template
        if request.POST.get("logo_clear") == "on":
            vp.logo.delete(save=False)
            vp.logo = None
        if request.POST.get("banner_clear") == "on":
            vp.banner.delete(save=False)
            vp.banner = None
        vp.save()

        return JsonResponse({
            "ok": True,
            "message": "Store profile updated.",
            "vendor": {
                "business_name": vp.business_name,
                "slug": vp.slug,
                "contact_email": vp.contact_email,
                "business_phone": vp.business_phone,
                "business_address": vp.business_address,
                "business_description": vp.business_description or "",
                "website_url": vp.website_url or "",
                "currency": vp.currency,
                "country": vp.country,
                "min_order_amount": str(vp.min_order_amount or "0.00"),
                "is_open": bool(vp.is_open),
                "logo_url": (vp.logo.url if vp.logo else ""),
                "banner_url": (vp.banner.url if vp.banner else ""),
                "socials": vp.socials or {},
                "shipping_policy": vp.shipping_policy or "",
                "return_policy": vp.return_policy or "",
                "opening_hours": vp.opening_hours or "",
                "bank_name": vp.bank_name or "",
                "account_name": vp.account_name or "",
                "account_number": vp.account_number or "",
            }
        })

    return JsonResponse({"ok": False, "message": "Validation error.", "errors": form.errors}, status=400)
