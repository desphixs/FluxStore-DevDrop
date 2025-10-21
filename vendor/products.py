# vendor/views.py
import json
from itertools import product as cartesian
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST


from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg, F, IntegerField, DecimalField, OuterRef, Subquery, ExpressionWrapper, Value
from django.db.models.functions import Coalesce

from order import models as order_models 

from decimal import Decimal
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Sum, F, Count, Q
from django.db import transaction

from store import models as store_models
from order import models as order_models

from store import models as store_models
from .forms import (
    ProductCreateForm, ProductDetailsForm,
    VariationCategoryForm, VariationValueForm,
    ProductVariationForm, ProductImageForm
)

from datetime import datetime
from django.utils import timezone
from django.utils.dateparse import parse_datetime

def _parse_dt(val):
    """
    Accepts '', None, datetime, or an ISO-ish string from <input type="datetime-local">.
    Returns timezone-aware datetime or None.
    """
    if not val:
        return None
    if isinstance(val, datetime):
        return timezone.make_aware(val) if timezone.is_naive(val) else val
    s = str(val).strip()
    
    
    dt = parse_datetime(s.replace('Z', '+00:00'))
    if dt is None:
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt

# You already have this in your project; keeping a light fallback:
def vendor_required(view_func):
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if getattr(request.user, "role", "").upper() != "VENDOR":
            return HttpResponseBadRequest("Vendor account required.")
        return view_func(request, *args, **kwargs)
    return _wrapped

def _is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"



@login_required
@vendor_required
def product_list(request):
    """
    Vendor products list with search, status filter, grid/list toggle, and
    per-product stats (variants, stock, sold qty & revenue, ratings).
    """
    vendor = request.user

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").upper()
    view_mode = (request.GET.get("view") or "grid").lower()
    if view_mode not in {"grid", "list"}:
        view_mode = "grid"

    
    oi_paid = order_models.OrderItem.objects.filter(
        product_variation__product=OuterRef("pk"),
        order__payment_status="PAID",
    )

    
    sold_qty_sq = oi_paid.values("product_variation__product").annotate(
        total_qty=Coalesce(Sum("quantity"), 0)
    ).values("total_qty")[:1]

    
    line_total_expr = ExpressionWrapper(
        F("quantity") * F("sale_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    sold_rev_sq = oi_paid.values("product_variation__product").annotate(
        total_rev=Coalesce(Sum(line_total_expr), Value(Decimal("0.00")))
    ).values("total_rev")[:1]

    
    qs = (
        store_models.Product.objects
        .filter(vendor=vendor)
        .select_related("category")
        .prefetch_related("images")  
        .annotate(
            variant_count=Count("variations", distinct=True),
            stock_total=Coalesce(Sum("variations__stock_quantity"), 0),
            average_rating=Coalesce(Avg("reviews__rating"), 0.0),
            total_reviews=Count("reviews", distinct=True),
            sold_qty=Coalesce(Subquery(sold_qty_sq, output_field=IntegerField()), 0),
            sold_revenue=Coalesce(
                Subquery(sold_rev_sq, output_field=DecimalField(max_digits=14, decimal_places=2)),
                Value(Decimal("0.00"))
            ),
        )
    )

    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(slug__icontains=q) | Q(description__icontains=q)
        )

    status_codes = dict(store_models.Product.ProductStatus.choices)
    if status in status_codes:
        qs = qs.filter(status=status)

    qs = qs.order_by("-created_at")

    
    per_page = int(request.GET.get("per_page") or 18)
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "vendor/products_list.html",
        {
            "page": page,
            "q": q,
            "status": status,
            "status_choices": store_models.Product.ProductStatus.choices,
            "view": view_mode,  
        },
    )

# ---------- Create + Edit workspace ----------

@login_required
@vendor_required
def product_create(request):
    """
    Step 1: tiny form -> create DRAFT product -> redirect to edit workspace.
    """
    if request.method == "POST":
        form = ProductCreateForm(request.POST, vendor=request.user)
        if form.is_valid():
            p = form.save(commit=False)
            p.vendor = request.user
            
            p.status = store_models.Product.ProductStatus.DRAFT
            p.save()
            return redirect(reverse("vendor:product_edit", kwargs={"pk": p.pk}))
    else:
        form = ProductCreateForm(vendor=request.user)

    return render(request, "vendor/products_create.html", {"form": form})



@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_update_details_ajax(request, pk: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    product = get_object_or_404(store_models.Product, pk=pk, vendor=request.user)

    data = request.POST if request.content_type.startswith("multipart/") else None
    if data is None:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            data = {}

    form = ProductDetailsForm(data=data, instance=product)
    if form.is_valid():
        p = form.save()
        return JsonResponse({
            "ok": True,
            "message": "Details saved.",
            "product": {
                "name": p.name,
                "status": p.status,
                "is_featured": p.is_featured,
                "category": p.category.name if p.category else "",
            }
        })
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_publish_toggle_ajax(request, pk: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    p = get_object_or_404(store_models.Product, pk=pk, vendor=request.user)
    
    p.status = (
        store_models.Product.ProductStatus.DRAFT
        if p.status == store_models.Product.ProductStatus.PUBLISHED
        else store_models.Product.ProductStatus.PUBLISHED
    )
    p.save(update_fields=["status", "updated_at"])
    return JsonResponse({"ok": True, "status": p.status})


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_feature_toggle_ajax(request, pk: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    p = get_object_or_404(store_models.Product, pk=pk, vendor=request.user)
    p.is_featured = not p.is_featured
    p.save(update_fields=["is_featured", "updated_at"])
    return JsonResponse({"ok": True, "is_featured": p.is_featured})


# ---------- Variation Dictionary (vendor-owned) ----------

@login_required
@vendor_required
@require_POST
@transaction.atomic
def varcat_create_ajax(request):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    data = request.POST or json.loads(request.body.decode("utf-8") or "{}")
    form = VariationCategoryForm(data=data, vendor=request.user)
    if form.is_valid():
        vc = form.save()
        return JsonResponse({"ok": True, "category": {"id": vc.id, "name": vc.name}})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def varcat_update_ajax(request, cid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vc = get_object_or_404(store_models.VariationCategory, pk=cid, vendor=request.user)
    data = request.POST or json.loads(request.body.decode("utf-8") or "{}")
    form = VariationCategoryForm(data=data, instance=vc, vendor=request.user)
    if form.is_valid():
        vc = form.save()
        return JsonResponse({"ok": True, "category": {"id": vc.id, "name": vc.name}})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def varcat_delete_ajax(request, cid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vc = get_object_or_404(store_models.VariationCategory, pk=cid, vendor=request.user)
    vc.delete()
    return JsonResponse({"ok": True, "id": cid})


@login_required
@vendor_required
@require_POST
@transaction.atomic
def varval_create_ajax(request):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    data = request.POST or json.loads(request.body.decode("utf-8") or "{}")
    form = VariationValueForm(data=data, vendor=request.user)
    if form.is_valid():
        vv = form.save()
        return JsonResponse({"ok": True, "value": {"id": vv.id, "category_id": vv.category_id, "value": vv.value}})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def varval_update_ajax(request, vid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vv = get_object_or_404(store_models.VariationValue, pk=vid, category__vendor=request.user)
    data = request.POST or json.loads(request.body.decode("utf-8") or "{}")
    form = VariationValueForm(data=data, instance=vv, vendor=request.user)
    if form.is_valid():
        vv = form.save()
        return JsonResponse({"ok": True, "value": {"id": vv.id, "category_id": vv.category_id, "value": vv.value}})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def varval_delete_ajax(request, vid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    vv = get_object_or_404(store_models.VariationValue, pk=vid, category__vendor=request.user)
    vv.delete()
    return JsonResponse({"ok": True, "id": vid})


# ---------- Product Variations ----------

def _parse_ids(value):
    """
    Accept JSON list or CSV string of ints.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [int(x) for x in value if str(x).isdigit()]
    s = str(value).strip()
    if s.startswith("["):
        try:
            arr = json.loads(s)
            return [int(x) for x in arr if str(x).isdigit()]
        except Exception:
            return []
    return [int(x) for x in s.split(",") if x.strip().isdigit()]


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_variation_create_ajax(request, pk: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    product = get_object_or_404(store_models.Product, pk=pk, vendor=request.user)

    data = request.POST if request.content_type.startswith("multipart/") else json.loads(request.body.decode("utf-8") or "{}")
    form = ProductVariationForm(data=data)
    if form.is_valid():
        pv = form.save(commit=False)
        pv.product = product
        pv.save()
        
        value_ids = _parse_ids(form.cleaned_data.get("variation_value_ids"))
        if value_ids:
            vqs = store_models.VariationValue.objects.filter(id__in=value_ids, category__vendor=request.user)
            pv.variations.set(vqs)
        else:
            pv.variations.clear()

        
        if pv.is_primary:
            store_models.ProductVariation.objects.filter(product=product).exclude(pk=pv.pk).update(is_primary=False)

        return JsonResponse({
            "ok": True,
            "variant": variant_to_dict(pv),
            "message": "Variant created."
        })
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_variation_update_ajax(request, vid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    pv = get_object_or_404(store_models.ProductVariation, pk=vid, product__vendor=request.user)

    data = request.POST if request.content_type.startswith("multipart/") else json.loads(request.body.decode("utf-8") or "{}")
    form = ProductVariationForm(data=data, instance=pv)
    if form.is_valid():
        pv = form.save()
        value_ids = _parse_ids(form.cleaned_data.get("variation_value_ids"))
        if value_ids is not None:
            vqs = store_models.VariationValue.objects.filter(id__in=value_ids, category__vendor=request.user)
            pv.variations.set(vqs)

        if pv.is_primary:
            store_models.ProductVariation.objects.filter(product=pv.product).exclude(pk=pv.pk).update(is_primary=False)

        return JsonResponse({"ok": True, "variant": variant_to_dict(pv), "message": "Variant updated."})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_variation_delete_ajax(request, vid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    pv = get_object_or_404(store_models.ProductVariation, pk=vid, product__vendor=request.user)
    pv.delete()
    return JsonResponse({"ok": True, "id": vid})


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_variation_toggle_primary_ajax(request, vid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    pv = get_object_or_404(store_models.ProductVariation, pk=vid, product__vendor=request.user)
    pv.is_primary = not pv.is_primary
    pv.save(update_fields=["is_primary"])
    if pv.is_primary:
        store_models.ProductVariation.objects.filter(product=pv.product).exclude(pk=pv.pk).update(is_primary=False)
    return JsonResponse({"ok": True, "variant": variant_to_dict(pv)})


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_variation_toggle_active_ajax(request, vid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    pv = get_object_or_404(store_models.ProductVariation, pk=vid, product__vendor=request.user)
    pv.is_active = not pv.is_active
    pv.save(update_fields=["is_active"])
    return JsonResponse({"ok": True, "variant": variant_to_dict(pv)})


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_variations_generate_ajax(request, pk: int):
    """
    Generate variants from selected values for 1..N categories.
    Expect JSON:
      {
        "value_ids_by_category": { "<cat_id>": [<val_id>, ...], ... },
        "sale_price": "0.00",
        "regular_price": "0.00",
        "stock_quantity": 0,
        "label": "New",
        "show_regular_price": true/false,
        "show_discount_type": "none"
      }
    """
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    product = get_object_or_404(store_models.Product, pk=pk, vendor=request.user)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    mapping = payload.get("value_ids_by_category") or {}
    
    cat_ids = [int(k) for k in mapping.keys() if str(k).isdigit()]
    value_lists = []
    for cid in cat_ids:
        ids = [int(x) for x in mapping[str(cid)] if str(x).isdigit()]
        if not ids:
            continue
        qs = store_models.VariationValue.objects.filter(id__in=ids, category_id=cid, category__vendor=request.user)
        value_lists.append(list(qs.values_list("id", flat=True)))

    if not value_lists:
        return JsonResponse({"ok": False, "message": "Select at least one value."}, status=400)

    sale_price = Decimal(str(payload.get("sale_price", "0")))
    regular_price = Decimal(str(payload.get("regular_price", "0")))
    stock_quantity = int(payload.get("stock_quantity") or 0)
    label = payload.get("label") or "New"
    show_regular_price = bool(payload.get("show_regular_price"))
    show_discount_type = payload.get("show_discount_type") or "none"

    created = []
    existing_sets = {
        frozenset(pv.variations.values_list("id", flat=True))
        for pv in store_models.ProductVariation.objects.filter(product=product).prefetch_related("variations")
    }

    for combo in cartesian(*value_lists):
        key = frozenset(combo)
        if key in existing_sets:
            continue
        pv = store_models.ProductVariation.objects.create(
            product=product,
            sale_price=sale_price,
            regular_price=regular_price,
            show_regular_price=show_regular_price,
            show_discount_type=show_discount_type,
            deal_active=False,
            stock_quantity=stock_quantity,
            sku=f"{product.uuid}-{len(created)+1:03d}",
            is_active=True,
            is_primary=False,
            weight=Decimal("0.00"), length=Decimal("0.00"), height=Decimal("0.00"), width=Decimal("0.00"),
            label=label,
        )
        pv.variations.set(list(combo))
        created.append(pv)

    return JsonResponse({
        "ok": True,
        "created": [variant_to_dict(x) for x in created],
        "count": len(created)
    })


def variant_to_dict(pv: store_models.ProductVariation):
    return {
        "id": pv.id,
        "sku": pv.sku,
        "sale_price": str(pv.sale_price),
        "regular_price": str(pv.regular_price),
        "show_regular_price": pv.show_regular_price,
        "show_discount_type": pv.show_discount_type,
        "stock_quantity": pv.stock_quantity,
        "is_active": pv.is_active,
        "is_primary": pv.is_primary,
        "label": pv.label,
        "values": [{"id": v.id, "name": v.value, "cat": v.category.name} for v in pv.variations.all()],
        "discount_amount": str(pv.discount_amount()),
        "discount_percentage": pv.discount_percentage(),
    }


# ---------- Images ----------
@ensure_csrf_cookie
@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_image_upload_ajax(request, pk: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    product = get_object_or_404(store_models.Product, pk=pk, vendor=request.user)
    files = request.FILES.getlist("images")
    out = []
    for f in files:
        img = store_models.ProductImage.objects.create(product=product, image=f, is_primary=False)
        out.append({"id": img.id, "url": img.image.url, "is_primary": img.is_primary})
    
    if not store_models.ProductImage.objects.filter(product=product, is_primary=True).exists():
        first = store_models.ProductImage.objects.filter(product=product).order_by("id").first()
        if first:
            first.is_primary = True
            first.save(update_fields=["is_primary"])
            
            for i in out:
                if i["id"] == first.id:
                    i["is_primary"] = True
                    break
    return JsonResponse({"ok": True, "images": out})


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_image_delete_ajax(request, iid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    img = get_object_or_404(store_models.ProductImage, pk=iid, product__vendor=request.user)
    pid = img.product_id
    was_primary = img.is_primary
    img.delete()
    if was_primary:
        
        other = store_models.ProductImage.objects.filter(product_id=pid).order_by("id").first()
        if other:
            other.is_primary = True
            other.save(update_fields=["is_primary"])
    return JsonResponse({"ok": True, "id": iid})


@login_required
@vendor_required
@require_POST
@transaction.atomic
def product_image_mark_primary_ajax(request, iid: int):
    if not _is_ajax(request):
        return HttpResponseBadRequest("Invalid request")
    img = get_object_or_404(store_models.ProductImage, pk=iid, product__vendor=request.user)
    store_models.ProductImage.objects.filter(product=img.product).update(is_primary=False)
    img.is_primary = True
    img.save(update_fields=["is_primary"])
    return JsonResponse({"ok": True, "id": img.id})






def _is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"

def _json_error(msg="Invalid request", status=400, **extra):
    data = {"ok": False, "message": msg}
    if extra:
        data.update(extra)
    return JsonResponse(data, status=status)

# ---------- helpers to serialize ----------
def varcat_to_dict(cat: store_models.VariationCategory):
    return {
        "id": cat.id,
        "name": cat.name,
        "values": [{"id": v.id, "value": v.value} for v in cat.values.order_by("value")],
    }

def variant_to_dict(v: store_models.ProductVariation):
    return {
        "id": v.id,
        "sku": v.sku,
        "is_active": v.is_active,
        "is_primary": v.is_primary,
        "sale_price": str(v.sale_price),
        "regular_price": str(v.regular_price),
        "show_regular_price": v.show_regular_price,
        "show_discount_type": v.show_discount_type,
        "stock_quantity": v.stock_quantity,
        "label": v.label,
        "deal_active": v.deal_active,
        "deal_starts_at": (v.deal_starts_at.isoformat() if hasattr(v.deal_starts_at, "isoformat") and v.deal_starts_at else None),
        "deal_ends_at":   (v.deal_ends_at.isoformat() if hasattr(v.deal_ends_at, "isoformat") and v.deal_ends_at else None),
        "weight": str(v.weight),
        "length": str(v.length),
        "height": str(v.height),
        "width": str(v.width),
        "values": [vv.id for vv in v.variations.all()],
        "values_text": ", ".join(vv.value for vv in v.variations.all()),
        "discount_pct": v.discount_percentage(),
    }

@ensure_csrf_cookie
@login_required
@vendor_required
def product_edit(request, pk: int):
    """
    Full workspace with tabs:
      - Details (product fields, publish/feature toggles)
      - Variants (your existing UI/JS)
      - Images (upload / delete / set primary)
    """
    product = get_object_or_404(store_models.Product, pk=pk, vendor=request.user)

    
    varcats = (
        store_models.VariationCategory.objects
        .filter(vendor=request.user)
        .prefetch_related("values")
        .order_by("name")
    )

    
    variants = (
        product.variations
        .prefetch_related("variations")
        .order_by("-is_primary", "-is_active", "sale_price")
    )

    
    sold_map = {
        it["product_variation"]: it["qty"]
        for it in order_models.OrderItem.objects
            .filter(order__payment_status="PAID", product_variation__product=product)
            .values("product_variation").annotate(qty=Sum("quantity"))
    }

    
    images = (
        store_models.ProductImage.objects
        .filter(product=product)
        .select_related("product_variation")
        .order_by("id")
    )

    return render(request, "vendor/product_edit.html", {
        "product": product,
        "details_form": ProductDetailsForm(instance=product),  
        "varcats": varcats,
        "variants": variants,
        "images": images,                                       
        "sold_map": sold_map,
        "label_choices": store_models.ProductVariation.LABEL_CHOICES,
        "show_discount_choices": store_models.ProductVariation.SHOW_DISCOUNT_TYPE,

    })

# ---------- VARIATION DICTIONARY (vendor) ----------
@login_required
@vendor_required
@require_POST
def varcat_create_ajax(request):
    if not _is_ajax(request): return _json_error()
    name = (request.POST.get("name") or "").strip()
    if not name:
        return _json_error("Name required.")
    
    if store_models.VariationCategory.objects.filter(vendor=request.user, name__iexact=name).exists():
        return _json_error("A category with this name already exists.")
    cat = store_models.VariationCategory.objects.create(vendor=request.user, name=name)
    return JsonResponse({"ok": True, "cat": varcat_to_dict(cat)})

@login_required
@vendor_required
@require_POST
def varcat_update_ajax(request, pk: int):
    if not _is_ajax(request): return _json_error()
    cat = get_object_or_404(store_models.VariationCategory, pk=pk, vendor=request.user)
    name = (request.POST.get("name") or "").strip()
    if not name:
        return _json_error("Name required.")
    if store_models.VariationCategory.objects.filter(vendor=request.user, name__iexact=name).exclude(pk=pk).exists():
        return _json_error("Another category with this name exists.")
    cat.name = name
    cat.save(update_fields=["name"])
    return JsonResponse({"ok": True, "cat": varcat_to_dict(cat)})

@login_required
@vendor_required
@require_POST
def varcat_delete_ajax(request, pk: int):
    if not _is_ajax(request): return _json_error()
    cat = get_object_or_404(store_models.VariationCategory, pk=pk, vendor=request.user)
    cat.delete()
    return JsonResponse({"ok": True, "id": pk})

@login_required
@vendor_required
@require_POST
def varval_add_ajax(request, cat_id: int):
    if not _is_ajax(request): return _json_error()
    cat = get_object_or_404(store_models.VariationCategory, pk=cat_id, vendor=request.user)
    value = (request.POST.get("value") or "").strip()
    if not value:
        return _json_error("Value required.")
    vv, created = store_models.VariationValue.objects.get_or_create(category=cat, value=value)
    return JsonResponse({"ok": True, "value": {"id": vv.id, "value": vv.value}, "created": created})

@login_required
@vendor_required
@require_POST
def varval_delete_ajax(request, pk: int):
    if not _is_ajax(request): return _json_error()
    vv = get_object_or_404(store_models.VariationValue, pk=pk, category__vendor=request.user)
    vv.delete()
    return JsonResponse({"ok": True, "id": pk})

# ---------- PRODUCT VARIANTS (product) ----------
def _product_owned_or_404(user, product_id):
    return get_object_or_404(store_models.Product, pk=product_id, vendor=user)

def _variant_owned_or_404(user, pk):
    return get_object_or_404(store_models.ProductVariation, pk=pk, product__vendor=user)

@login_required
@vendor_required
@require_POST
def variant_create_ajax(request, product_id: int):
    if not _is_ajax(request): return _json_error()
    product = _product_owned_or_404(request.user, product_id)

    data = request.POST
    try:
        with transaction.atomic():
           

            v = store_models.ProductVariation.objects.create(
                product=product,
                sale_price=Decimal(data.get("sale_price") or "0"),
                regular_price=Decimal(data.get("regular_price") or "0"),
                show_regular_price=bool(data.get("show_regular_price")),
                show_discount_type=data.get("show_discount_type") or "none",
                stock_quantity=int(data.get("stock_quantity") or 0),
                sku=(data.get("sku") or "").strip(),
                is_active=bool(data.get("is_active")),
                is_primary=bool(data.get("is_primary")),
                label=data.get("label") or "New",
                deal_active=bool(data.get("deal_active")),
                weight=Decimal(data.get("weight") or "0"),
                length=Decimal(data.get("length") or "0"),
                height=Decimal(data.get("height") or "0"),
                width=Decimal(data.get("width") or "0"),
            )
            
            v.deal_starts_at = _parse_dt(data.get("deal_starts_at"))
            v.deal_ends_at   = _parse_dt(data.get("deal_ends_at"))
            v.save()

            
            ids = [int(x) for x in (data.getlist("values[]") or data.getlist("values"))]
            if ids:
                v.variations.set(store_models.VariationValue.objects.filter(id__in=ids, category__vendor=request.user))

            
            if v.is_primary:
                product.variations.exclude(pk=v.pk).update(is_primary=False)

    except Exception as e:
        return _json_error(str(e))

    return JsonResponse({"ok": True, "variant": variant_to_dict(v)})

@login_required
@vendor_required
def variant_get_ajax(request, pk: int):
    if not _is_ajax(request): return _json_error()
    v = _variant_owned_or_404(request.user, pk)
    return JsonResponse({"ok": True, "variant": variant_to_dict(v)})

@login_required
@vendor_required
@require_POST
def variant_update_ajax(request, pk: int):
    if not _is_ajax(request): return _json_error()
    v = _variant_owned_or_404(request.user, pk)
    data = request.POST
    try:
        with transaction.atomic():
            v.sale_price = Decimal(data.get("sale_price") or "0")
            v.regular_price = Decimal(data.get("regular_price") or "0")
            v.show_regular_price = bool(data.get("show_regular_price"))
            v.show_discount_type = data.get("show_discount_type") or "none"
            v.stock_quantity = int(data.get("stock_quantity") or 0)
            v.sku = (data.get("sku") or v.sku).strip()
            v.is_active = bool(data.get("is_active"))
            make_primary = bool(data.get("is_primary"))
            v.label = data.get("label") or v.label
            v.deal_active = bool(data.get("deal_active"))
            v.weight = Decimal(data.get("weight") or "0")
            v.length = Decimal(data.get("length") or "0")
            v.height = Decimal(data.get("height") or "0")
            v.width = Decimal(data.get("width") or "0")
            v.save()

            ids = [int(x) for x in (data.getlist("values[]") or data.getlist("values"))]
            v.variations.set(store_models.VariationValue.objects.filter(id__in=ids, category__vendor=request.user))

            if make_primary and not v.is_primary:
                v.is_primary = True
                v.save(update_fields=["is_primary"])
                v.product.variations.exclude(pk=v.pk).update(is_primary=False)
            elif not make_primary and v.is_primary:
                
                v.is_primary = False
                v.save(update_fields=["is_primary"])

    except Exception as e:
        return _json_error(str(e))
    return JsonResponse({"ok": True, "variant": variant_to_dict(v)})

@login_required
@vendor_required
@require_POST
def variant_toggle_active_ajax(request, pk: int):
    if not _is_ajax(request): return _json_error()
    v = _variant_owned_or_404(request.user, pk)
    v.is_active = not v.is_active
    v.save(update_fields=["is_active"])
    return JsonResponse({"ok": True, "variant": variant_to_dict(v)})

@login_required
@vendor_required
@require_POST
def variant_set_primary_ajax(request, pk: int):
    if not _is_ajax(request): return _json_error()
    v = _variant_owned_or_404(request.user, pk)
    with transaction.atomic():
        v.product.variations.update(is_primary=False)
        v.is_primary = True
        v.save(update_fields=["is_primary"])
    return JsonResponse({"ok": True, "variant": variant_to_dict(v)})

@login_required
@vendor_required
@require_POST
def variant_delete_ajax(request, pk: int):
    if not _is_ajax(request): return _json_error()
    v = _variant_owned_or_404(request.user, pk)
    vid = v.id
    v.delete()
    return JsonResponse({"ok": True, "id": vid})
