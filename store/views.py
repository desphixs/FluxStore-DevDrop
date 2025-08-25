# your_app/views.py

from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Sum, Avg, Case, When, IntegerField
from store import models as store_models
from order import models as order_models
# def index(request):
    
#     products = store_models.Product.objects.filter(status=store_models.Product.ProductStatus.PUBLISHED)
#     categories = store_models.Category.objects.filter(is_active=True, featured=True)[:2]
#     trending_categories = store_models.Category.objects.filter(is_active=True, trending=True)[:8]
#     deals = store_models.ProductVariation.objects.filter(product__status=store_models.Product.ProductStatus.PUBLISHED, is_active=True, is_primary=True)
    
#     context = {
#         'products': products,
#         'categories': categories,
#         'trending_categories': trending_categories,
#         'deals': deals,
#     }
#     return render(request, 'index.html', context)

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
    """
    Displays the details of a single product.

    This view retrieves a specific product by its slug and gathers all
    related information:
    - Variations (e.g., color, size) with their specific prices and images.
    - General product images.
    - Customer reviews and the average rating.
    - A list of related products from the same category.
    """
    # Use get_object_or_404 to fetch the product or return a 404 error if not found.
    # We extensively use prefetch_related to load all related data in an efficient manner.
    product = get_object_or_404(
        store_models.Product.objects.prefetch_related(
            # Prefetch active variations, their values (e.g., 'Red', 'Large'), and their specific images.
            Prefetch(
                'variations',
                queryset=store_models.ProductVariation.objects.filter(is_active=True).prefetch_related(
                    'variations__category',  # Prefetches VariationValue and its parent VariationCategory
                    'images'                 # Prefetches images linked to each ProductVariation
                )
            ),
            # Prefetch general product images that are not tied to a specific variation.
            Prefetch(
                'images',
                queryset=store_models.ProductImage.objects.filter(product_variation__isnull=True),
                to_attr='general_images'
            ),
            # Prefetch reviews along with the user who wrote them.
            'reviews__user'
        ).select_related('category', 'vendor'),  # Use select_related for one-to-one/foreign key relationships.
        slug=slug,
        status=store_models.Product.ProductStatus.PUBLISHED
    )

    # --- Structure Variation Data for Selection Menus (e.g., dropdowns) ---
    # This creates a dictionary like: {'Color': {'Red', 'Blue'}, 'Size': {'M', 'L'}}
    variation_options = {}
    for variation in product.variations.all():
        for value in variation.variations.all():
            category_name = value.category.name
            if category_name not in variation_options:
                variation_options[category_name] = set()
            variation_options[category_name].add(value.value)

    # --- Calculate Average Rating ---
    reviews = product.reviews.all()
    average_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0

    # --- Get Related Products ---
    # Fetches up to 4 other published products from the same category, excluding the current one.
    related_products = []
    if product.category:
        related_products = store_models.Product.objects.filter(
            category=product.category,
            status=store_models.Product.ProductStatus.PUBLISHED
        ).exclude(pk=product.pk)[:4]

    context = {
        'product': product,
        'variation_options': variation_options, # For building selection UI
        'reviews': reviews,
        'average_rating': round(average_rating, 1),
        'related_products': related_products,
    }

    return render(request, 'product_detail.html', context)