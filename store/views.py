# your_app/views.py

from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Sum, Avg, Case, When, IntegerField
from store import models as store_models
from order import models as order_models

import json

def index(request):
    Product = store_models.Product
    ProductVariation = store_models.ProductVariation
    OrderItem = order_models.OrderItem
    ProductImage = store_models.ProductImage

    # Base published products queryset (with some eager loading)
    base_products_qs = Product.objects.filter(
        status=Product.ProductStatus.PUBLISHED
    ).select_related('vendor', 'category').prefetch_related(
        # primary image prefetched as .primary_images (list, usually 0/1)
        Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images'),
        # active variations prefetched as .active_variations
        Prefetch('variations', queryset=ProductVariation.objects.filter(is_active=True), to_attr='active_variations'),
    )

    # ---------- Top Selling (by quantity sold) ----------
    # Get top product ids by summing quantities from OrderItem
    top_selling_agg = OrderItem.objects.filter(
        product_variation__product__status=Product.ProductStatus.PUBLISHED
    ).values('product_variation__product').annotate(
        total_sold=Sum('quantity')
    ).order_by('-total_sold')[:4]

    top_selling_ids = [item['product_variation__product'] for item in top_selling_agg]

    if top_selling_ids:
        # preserve ordering returned by the aggregation
        preserved_order = Case(*[
            When(pk=pid, then=pos) for pos, pid in enumerate(top_selling_ids)
        ], output_field=IntegerField())
        top_selling = list(Product.objects.filter(pk__in=top_selling_ids).order_by(preserved_order))
    else:
        top_selling = []

    # ---------- Trending Products ----------
    # Products that have at least one variation labeled "Trending"
    trending_products = list(
        base_products_qs.filter(variations__label='Trending').distinct()[:4]
    )

    # ---------- Recently Added ----------
    recently_added = list(base_products_qs.order_by('-created_at')[:4])

    # ---------- Top Rated ----------
    # Annotate avg rating and pick top 4 (ignore null-rated products)
    top_rated = list(
        base_products_qs.annotate(avg_rating=Avg('reviews__rating'))
                        .filter(avg_rating__isnull=False)
                        .order_by('-avg_rating')[:4]
    )

    # ---------- Deals (existing) ----------
    deals = store_models.ProductVariation.objects.filter(
        product__status=Product.ProductStatus.PUBLISHED,
        is_active=True,
        is_primary=True
    )

    context = {
        'products': base_products_qs,           # full list if you still need it elsewhere
        'categories': store_models.Category.objects.filter(is_active=True, featured=True)[:2],
        'trending_categories': store_models.Category.objects.filter(is_active=True, trending=True)[:8],
        'deals': deals,
        'top_selling': top_selling,
        'trending_products': trending_products,
        'recently_added': recently_added,
        'top_rated': top_rated,
    }
    return render(request, 'index.html', context)

def product_detail_view(request, slug):
    Product = store_models.Product
    ProductVariation = store_models.ProductVariation
    ProductImage = store_models.ProductImage

    product = get_object_or_404(
        Product.objects.prefetch_related(
            # Prefetch active variations and their images + variation values & categories
            Prefetch(
                'variations',
                queryset=ProductVariation.objects.filter(is_active=True).prefetch_related('variations', 'images'),
                to_attr='active_variations'   # -> product.active_variations (list)
            ),
            # Prefetch general product images (not tied to a variation)
            Prefetch(
                'images',
                queryset=ProductImage.objects.filter(product_variation__isnull=True),
                to_attr='general_images'
            ),
            'reviews__user'
        ).select_related('category', 'vendor'),
        slug=slug,
        status=Product.ProductStatus.PUBLISHED
    )

    # Build variation options grouped by VariationCategory to render selectors
    variation_options = {}
    for variation in getattr(product, 'active_variations', []):
        for vval in variation.variations.all():
            cat = vval.category.name
            variation_options.setdefault(cat, set()).add(vval.value)
    # convert sets -> sorted lists for deterministic UI
    variation_options = {k: sorted(list(v)) for k, v in variation_options.items()}

    # Build a variation_map -> key is deterministic string: "Color:Red|Size:M" (sorted by category)
    # value contains id, sale_price, regular_price, stock, is_primary, images (urls), deal info, label, etc.
    variation_map = {}
    for var in getattr(product, 'active_variations', []):
        # collect (category, value) for each variation value
        pairs = [(vv.category.name, vv.value) for vv in var.variations.all()]
        # sort by category name to make key deterministic
        pairs_sorted = sorted(pairs, key=lambda x: x[0].lower())
        key = "|".join([f"{cat}:{val}" for cat, val in pairs_sorted])
        images = [img.image.url for img in var.images.all()]  # variation-specific images
        variation_map[key] = {
            "id": var.id,
            "sale_price": float(var.sale_price),
            "regular_price": float(var.regular_price),
            "discount_amount": float(var.discount_amount()),
            "discount_percentage": float(var.discount_percentage()),
            "stock_quantity": var.stock_quantity,
            "is_primary": var.is_primary,
            "label": var.label,
            "label_color": var.label_color,
            "images": images,
            "deal_active": var.deal_active,
            "deal_starts_at": var.deal_starts_at.isoformat() if var.deal_starts_at else None,
            "deal_ends_at": var.deal_ends_at.isoformat() if var.deal_ends_at else None,
        }

    # Average rating & reviews
    reviews = product.reviews.all()
    average_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0

    # Related products (same category)
    related_products = []
    if product.category:
        related_products = Product.objects.filter(
            category=product.category,
            status=Product.ProductStatus.PUBLISHED
        ).exclude(pk=product.pk)[:4]

    context = {
        'product': product,
        'variation_options': variation_options,
        'variation_map_json': json.dumps(variation_map),  # will be embedded via json_script
        'reviews': reviews,
        'average_rating': round(average_rating, 1),
        'related_products': related_products,
    }
    return render(request, 'product_detail.html', context)