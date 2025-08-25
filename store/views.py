# your_app/views.py

from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Avg
from .models import Product, ProductVariation, ProductImage, ProductReview
def product_list_view(request):
    
    products = Product.objects.filter(
        status=Product.ProductStatus.PUBLISHED
    )

    context = {
        'products': products,
    }
    return render(request, 'product_list.html', context)

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
        Product.objects.prefetch_related(
            # Prefetch active variations, their values (e.g., 'Red', 'Large'), and their specific images.
            Prefetch(
                'variations',
                queryset=ProductVariation.objects.filter(is_active=True).prefetch_related(
                    'variations__category',  # Prefetches VariationValue and its parent VariationCategory
                    'images'                 # Prefetches images linked to each ProductVariation
                )
            ),
            # Prefetch general product images that are not tied to a specific variation.
            Prefetch(
                'images',
                queryset=ProductImage.objects.filter(product_variation__isnull=True),
                to_attr='general_images'
            ),
            # Prefetch reviews along with the user who wrote them.
            'reviews__user'
        ).select_related('category', 'vendor'),  # Use select_related for one-to-one/foreign key relationships.
        slug=slug,
        status=Product.ProductStatus.PUBLISHED
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
        related_products = Product.objects.filter(
            category=product.category,
            status=Product.ProductStatus.PUBLISHED
        ).exclude(pk=product.pk)[:4]

    context = {
        'product': product,
        'variation_options': variation_options, # For building selection UI
        'reviews': reviews,
        'average_rating': round(average_rating, 1),
        'related_products': related_products,
    }

    return render(request, 'product_detail.html', context)