import json
import re
from decimal import Decimal
from typing import List, Tuple

from django.conf import settings
from django.db import connection
from django.db.models import Q, F, Value, Avg, Count, Min, Max
from django.db.models.functions import Lower, Greatest
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.core.paginator import Paginator

from .models import (
    Product, ProductVariation, ProductImage, Category, ProductReview
)

# ---------- Optional fuzzy libs ----------
try:
    from rapidfuzz import fuzz
    _HAVE_RAPIDFUZZ = True
except Exception:
    from difflib import SequenceMatcher
    _HAVE_RAPIDFUZZ = False

def _fuzzy_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if _HAVE_RAPIDFUZZ:
        return 0.6 * (fuzz.token_set_ratio(a, b) / 100.0) + 0.4 * (fuzz.partial_ratio(a, b) / 100.0)
    return SequenceMatcher(None, a, b).ratio()

# ---------- Optional Postgres FT search ----------
try:
    from django.contrib.postgres.search import (
        SearchVector, SearchQuery, SearchRank, TrigramSimilarity
    )
    _HAVE_PG_EXTS = True
except Exception:
    TrigramSimilarity = None
    _HAVE_PG_EXTS = False

def is_postgres() -> bool:
    return connection.vendor == "postgresql" and _HAVE_PG_EXTS

# ---------- String helpers ----------
def normalize_query(s: str) -> str:
    return re.sub(r'[^0-9a-z]+', '', (s or '').lower())

def camel_to_space(s: str) -> str:
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s or '')
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', s)
    return s

def spaced_guess(s: str) -> str:
    s = camel_to_space(s or '')
    s = re.sub(r'([A-Za-z])(\d)', r'\1 \2', s)
    s = re.sub(r'(\d)([A-Za-z])', r'\1 \2', s)
    return s.lower().strip()

def similarity_cutoffs(q: str) -> Tuple[float, float]:
    L = len(normalize_query(q))
    primary = 0.20 if L >= 12 else 0.15 if L >= 8 else 0.12
    suggest = 0.08 if L >= 12 else 0.06 if L >= 8 else 0.04
    return primary, suggest

# ---------- Serializers ----------
def _serialize_product(p: Product):
    
    primary = p.primary_item()  
    img = p.primary_image
    avg_int = p.average_rating_int()  
    avg = p.average_rating()
    total_reviews = p.total_reviews()

    
    sale_price = float(primary.sale_price) if primary else 0.0
    regular_price = float(primary.regular_price) if (primary and primary.show_regular_price) else float(primary.sale_price) if primary else 0.0
    show_regular = bool(primary.show_regular_price) if primary else False
    label = primary.label if primary else "New"
    label_color = primary.label_color if primary else "bg-gray-300 text-black"
    show_discount_type = primary.show_discount_type if primary else "none"
    discount_amount = float(primary.discount_amount()) if primary else 0.0

    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "category": {"name": p.category.name if p.category else "", "slug": p.category.slug if p.category else ""},
        "vendor_name": getattr(getattr(p, "vendor", None), "vendor_profile", None).business_name
                         if getattr(p, "vendor", None) and getattr(p.vendor, "vendor_profile", None) else "",
        "average_rating_int": avg_int,
        "average_rating": float(avg),
        "reviews_count": total_reviews,
        "image_url": (img.image.url if img and getattr(img.image, "url", "") else ""),
        "primary": {
            "sale_price": sale_price,
            "regular_price": float(regular_price),
            "show_regular_price": show_regular,
            "label": label,
            "label_color": label_color,
            "show_discount_type": show_discount_type,
            "discount_amount": float(discount_amount),
        },
        "flags": {
            "deal_active": bool(primary.deal_active) if primary else False,
            "in_stock": (primary.stock_quantity > 0) if primary else False,
        }
    }

# ---------- Shop page ----------
def shop(request):
    categories = Category.objects.filter(is_active=True).order_by("name")
    price_bounds = ProductVariation.objects.filter(
        is_primary=True, product__status=Product.ProductStatus.PUBLISHED
    ).aggregate(min_price=Min("sale_price"), max_price=Max("sale_price"))

    labels = [
        "Hot","New","Sale","Bestseller","Limited","Featured","Exclusive",
        "Coming Soon","Back in Stock","Trending","Clearance","Popular","Gift"
    ]

    context = {
        "page_title": "Shop",
        "categories": categories,
        "min_price": price_bounds["min_price"] or 0,
        "max_price": price_bounds["max_price"] or 0,
        "labels": labels,
    }
    return render(request, "shop.html", context)

# ---------- JSON API (GET) ----------
def product_list_api(request):
    qs = Product.objects.filter(
        status=Product.ProductStatus.PUBLISHED
    ).select_related("category", "vendor").prefetch_related(
        "reviews",
        "images",
        "variations",
    ).annotate(
        avg_rating=Avg("reviews__rating"),
        reviews_count=Count("reviews"),
    )

    
    q = (request.GET.get("q") or "").strip()
    cat = request.GET.get("category")  
    label = request.GET.get("label")
    deal = request.GET.get("deal")     
    stock = request.GET.get("stock")   
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    rating_min = request.GET.get("rating_min")
    sort = request.GET.get("sort", "newest")
    page = int(request.GET.get("page", "1"))
    page_size = min(int(request.GET.get("page_size", "24")), 60)

    if cat:
        qs = qs.filter(Q(category__slug=cat) | Q(category__parent__slug=cat))

    if label:
        qs = qs.filter(variations__is_primary=True, variations__label=label)

    if deal == "1":
        qs = qs.filter(variations__is_primary=True, variations__deal_active=True)

    if stock == "1":
        qs = qs.filter(variations__is_primary=True, variations__stock_quantity__gt=0)

    if min_price:
        try:
            qs = qs.filter(variations__is_primary=True, variations__sale_price__gte=Decimal(min_price))
        except Exception:
            pass

    if max_price:
        try:
            qs = qs.filter(variations__is_primary=True, variations__sale_price__lte=Decimal(max_price))
        except Exception:
            pass

    if rating_min:
        try:
            qs = qs.filter(avg_rating__gte=float(rating_min))
        except Exception:
            pass

    
    if q:
        norm_q = normalize_query(q)
        loose_q = spaced_guess(q)
        tokens: List[str] = [t for t in re.findall(r'\w+', loose_q) if len(t) > 1]
        p_cut, s_cut = similarity_cutoffs(q)

        if is_postgres():
            vector = SearchVector('name', weight='A') + SearchVector('description', weight='B')
            sq = SearchQuery(q)
            qs = qs.annotate(
                rank=SearchRank(vector, sq),
                sim=Greatest(
                    TrigramSimilarity('name', q),
                    TrigramSimilarity('description', q),
                ),
            ).filter(
                Q(rank__gt=0.0) | Q(sim__gt=p_cut) |
                Q(name__icontains=loose_q) | Q(description__icontains=loose_q)
            )
        else:
            loose = Q(name__icontains=loose_q) | Q(description__icontains=loose_q)
            token_or = Q()
            for t in tokens:
                token_or |= Q(name__icontains=t) | Q(description__icontains=t)
            qs = qs.filter(loose | token_or | Q(name__icontains=q) | Q(description__icontains=q))

    
    if sort == "price_low":
        qs = qs.order_by("variations__sale_price")
    elif sort == "price_high":
        qs = qs.order_by("-variations__sale_price")
    elif sort == "rating":
        qs = qs.order_by("-avg_rating", "-reviews_count")
    elif sort == "popular":
        qs = qs.order_by("-reviews_count", "-avg_rating")
    else:  
        qs = qs.order_by("-created_at")

    qs = qs.distinct()

    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page)

    items = [_serialize_product(p) for p in page_obj.object_list]

    return JsonResponse({
        "ok": True,
        "page": page_obj.number,
        "total_pages": paginator.num_pages,
        "total": paginator.count,
        "items": items,
    })