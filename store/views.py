from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Sum, Avg, Case, When, IntegerField


from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import ValidationError
from django.db import transaction

import json
import traceback

from store import models as store_models
from order import models as order_models

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
        base_products_qs.filter(variations__label='Trending').distinct()[:2]
    )

    # ---------- Recently Added ----------
    recently_added = list(base_products_qs.order_by('-created_at')[:2])

    # ---------- Top Rated ----------
    # Annotate avg rating and pick top 4 (ignore null-rated products)
    top_rated = list(
        base_products_qs.annotate(avg_rating=Avg('reviews__rating'))
                        .filter(avg_rating__isnull=False)
                        .order_by('-avg_rating')[:2]
    )

    # ---------- Deals (existing) ----------
    deals = store_models.ProductVariation.objects.filter(
        product__status=Product.ProductStatus.PUBLISHED,
        is_active=True,
        is_primary=True
    )[:4]

    context = {
        'products': base_products_qs,           # full list if you still need it elsewhere
        'categories': store_models.Category.objects.filter(is_active=True, featured=True).order_by("id")[:2],
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
            variation_options.setdefault(cat, set()).add(vval)
    # convert sets -> sorted lists for deterministic UI
    variation_options = {k: sorted(list(v), key=lambda x: x.value) for k, v in variation_options.items()}


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

@require_POST
@csrf_protect
def add_to_cart(request):
    print("---- add_to_cart called ----")
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception as e:
        print("Invalid JSON:", e)
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    print("payload:", payload)
    variation_id = payload.get('variation_id')
    product_id = payload.get('product_id')
    # either a dict {"Color":"Black", "Size":"XL"} OR None
    selected_variations = payload.get('selected_variations') or {}
    # prefer explicit ids when client sends them
    selected_value_ids = payload.get('selected_value_ids') or payload.get('selected_value_ids[]') or None

    print("selected_value_ids ====", selected_value_ids)
    print("selected_variations ====", selected_variations)

    try:
        qty = int(payload.get('quantity', 1) or 1)
    except Exception:
        qty = 1

    if qty < 1:
        print("Bad quantity:", qty)
        return JsonResponse({"detail": "Quantity must be at least 1"}, status=400)

    variation = None

    # resolve variation (unchanged)
    if variation_id:
        print("Resolving by variation_id:", variation_id)
        variation = get_object_or_404(
            store_models.ProductVariation.objects.select_related('product'),
            pk=variation_id,
            is_active=True
        )
    elif selected_variations and product_id:
        print("Resolving by selected_variations for product:", product_id, selected_variations)
        product = get_object_or_404(store_models.Product, pk=product_id)
        qs = store_models.ProductVariation.objects.filter(product=product, is_active=True)
        for cat, val in selected_variations.items():
            qs = qs.filter(variations__category__name=cat, variations__value=val)
        qs = qs.distinct()
        variation = qs.first()
        if not variation:
            print("No matching variant for selections:", selected_variations)
            return JsonResponse({"detail": "No matching variant for those selections"}, status=404)
    elif product_id:
        print("Resolving by product_id fallback:", product_id)
        product = get_object_or_404(store_models.Product, pk=product_id)
        primary = product.primary_item() if callable(getattr(product, "primary_item", None)) else getattr(product, "primary_item", None)
        variation = primary or product.variations.filter(is_active=True).first()
        if not variation:
            print("No available variant for product:", product_id)
            return JsonResponse({"detail": "No available variant for this product"}, status=404)
    else:
        print("No variation_id or product_id provided")
        return JsonResponse({"detail": "Provide variation_id or product_id"}, status=400)

    # final validations
    if not getattr(variation, "is_active", False):
        print("Variant not active:", getattr(variation, "id", None))
        return JsonResponse({"detail": "Variant not active"}, status=400)

    if getattr(variation, "stock_quantity", 0) < qty:
        print("Insufficient stock for variation:", variation.id, "requested:", qty, "available:", getattr(variation, "stock_quantity", 0))
        return JsonResponse({"detail": "Insufficient stock"}, status=400)

    # get/create cart
    print("Attempting to get cart via order_models.Cart.get_for_request")
    cart = None
    try:
        cart = order_models.Cart.get_for_request(request)
    except Exception as e:
        print("get_for_request raised:", e)
        cart = None

    if not cart or getattr(cart, "id", None) is None:
        print("Fallback: creating/getting cart manually")
        if request.user.is_authenticated:
            cart, created = order_models.Cart.objects.get_or_create(user=request.user)
            print("Cart for user:", request.user, "created:", created, "cart_id:", cart.id)
        else:
            if not request.session.session_key:
                request.session.create()
                print("Created session_key:", request.session.session_key)
            session_key = request.session.session_key
            cart, created = order_models.Cart.objects.get_or_create(session_key=session_key)
            print("Cart for session:", session_key, "created:", created, "cart_id:", cart.id)

    if getattr(cart, "id", None) is None:
        try:
            cart.save()
            print("Saved cart, new id:", cart.id)
        except Exception as e:
            print("Failed to save cart:", e)
            return JsonResponse({"detail": "Could not initialize cart"}, status=500)

    print("Final cart id:", cart.id)
    price_snapshot = variation.sale_price

    cart_item = None
    created = False

    # ---- NEW: resolve VariationValue objects from payload ----
    resolved_vv_qs = store_models.VariationValue.objects.none()
    resolved_value_ids = []
    try:
        if selected_value_ids:
            # if client sent ids (preferred)
            print("Client provided selected_value_ids:", selected_value_ids)
            # ensure list of ints
            if isinstance(selected_value_ids, str):
                # client might send JSON-string, try to parse
                try:
                    selected_value_ids = json.loads(selected_value_ids)
                except Exception:
                    selected_value_ids = [int(x) for x in selected_value_ids.split(',') if x.strip().isdigit()]
            selected_value_ids = [int(x) for x in selected_value_ids] if hasattr(selected_value_ids, "__iter__") else [int(selected_value_ids)]
            resolved_vv_qs = store_models.VariationValue.objects.filter(id__in=selected_value_ids)
            resolved_value_ids = list(resolved_vv_qs.values_list('id', flat=True))
        elif selected_variations and isinstance(selected_variations, dict):
            # fallback: resolve by category name + value (case-insensitive)
            print("Resolving VariationValue by category/value pairs:", selected_variations)
            found_ids = []
            for cat, val in selected_variations.items():
                vv = store_models.VariationValue.objects.filter(category__name__iexact=str(cat).strip(), value__iexact=str(val).strip()).first()
                if vv:
                    found_ids.append(vv.id)
            if found_ids:
                resolved_vv_qs = store_models.VariationValue.objects.filter(id__in=found_ids)
                resolved_value_ids = found_ids
    except Exception as e:
        print("Error resolving VariationValue objects:", e)
        resolved_vv_qs = store_models.VariationValue.objects.none()
        resolved_value_ids = []

    print("Resolved VariationValue ids:", resolved_value_ids)

    try:
        with transaction.atomic():
            print("Adding item to cart (cart_id=%s, variation_id=%s, qty=%s)" % (cart.id, variation.id, qty))

            add_item_error = None
            if hasattr(cart, "add_item") and callable(getattr(cart, "add_item")):
                try:
                    result = cart.add_item(variation, quantity=qty)
                    if isinstance(result, tuple) and len(result) >= 2:
                        cart_item, created = result[0], result[1]
                    else:
                        cart_item = result
                        created = False
                    print("Used cart.add_item; returned:", getattr(cart_item, "id", None), "created:", created)
                except Exception as e:
                    add_item_error = e
                    print("cart.add_item raised, will fallback to manual create. Error:", e)

            # manual fallback
            if cart_item is None:
                print("Manual fallback: detecting CartItem FK to ProductVariation")
                fk_field_name = None
                for f in order_models.CartItem._meta.fields:
                    related = getattr(f, "related_model", None)
                    if related is store_models.ProductVariation:
                        fk_field_name = f.name
                        break

                if not fk_field_name:
                    for candidate in ("product_variation", "variation", "product_variation_id", "variation_id"):
                        try:
                            order_models.CartItem._meta.get_field(candidate)
                            fk_field_name = candidate
                            break
                        except Exception:
                            continue

                if not fk_field_name:
                    print("Could not auto-detect ProductVariation FK field on CartItem. Fields:", [f.name for f in order_models.CartItem._meta.fields])
                    raise RuntimeError("CartItem model does not have FK to ProductVariation (cannot fallback)")

                print("Detected FK field name on CartItem:", fk_field_name)

                kwargs = {"cart": cart, fk_field_name: variation}
                defaults = {"quantity": qty, "price": price_snapshot}
                try:
                    cart_item, created = order_models.CartItem.objects.get_or_create(defaults=defaults, **kwargs)
                    if not created:
                        cart_item.quantity = (cart_item.quantity or 0) + qty
                        cart_item.price = price_snapshot
                        cart_item.save()
                    print("Manual CartItem done; id:", cart_item.id, "created:", created)
                except InterruptedError as ie:
                    print("IntegrityError creating CartItem:", ie)
                    raise

            # SANITY: ensure item references cart
            print("cart_item.cart_id after create:", getattr(cart_item, "cart_id", None))
            if getattr(cart_item, "cart_id", None) is None:
                raise RuntimeError("cart_item.cart_id is None after creation")

            # persist price (defensive)
            try:
                cart_item.price = price_snapshot
                cart_item.save()
            except Exception as e:
                print("Failed to save cart_item.price:", e)

            # ---- NEW: attach resolved VariationValue M2M and save selected_variations_json backup ----
            try:
                # attach M2M if field exists and we resolved any ids
                if hasattr(cart_item, "variation_values"):
                    if resolved_vv_qs.exists():
                        cart_item.variation_values.set(resolved_vv_qs)
                        print("Set cart_item.variation_values ->", list(resolved_vv_qs.values_list('id', flat=True)))
                    else:
                        # If no vv resolved, clear if you want or keep existing (we'll keep existing if present)
                        print("No resolved variation values to set (keeping existing).")
                else:
                    print("CartItem model does not have 'variation_values' M2M field; skipping.")

                # always save a JSON backup (if field exists)
                backup = {}
                if resolved_value_ids:
                    backup['value_ids'] = resolved_value_ids
                if isinstance(selected_variations, dict) and selected_variations:
                    backup['display'] = {str(k): str(v) for k, v in selected_variations.items()}
                # if nothing resolved, you may still want to store display
                if hasattr(cart_item, "selected_variations_json"):
                    cart_item.selected_variations_json = backup or None
                    cart_item.save()
                    print("Saved selected_variations_json:", cart_item.selected_variations_json)
                else:
                    print("CartItem model does not have 'selected_variations_json' field; skipping backup save.")
            except Exception as e:
                print("Failed to attach variation_values / save backup:", e)

    except ValidationError as e:
        print("ValidationError while adding to cart:", e)
        return JsonResponse({"detail": str(e)}, status=400)
    except Exception as e:
        print("Exception while adding to cart:", e)
        print(traceback.format_exc())
        return JsonResponse({"detail": "Could not add to cart"}, status=500)

    # build response (safely convert decimals)
    subtotal = None
    if hasattr(cart_item, "subtotal") and callable(getattr(cart_item, "subtotal")):
        try:
            subtotal = str(cart_item.subtotal())
        except Exception:
            subtotal = None

    resp = {
        "ok": True,
        "created": bool(created),
        "cart_item": {
            "id": cart_item.id,
            "variation_id": variation.id,
            "product_id": getattr(getattr(variation, 'product', None), 'id', None),
            "quantity": cart_item.quantity,
            "price": str(cart_item.price),
            "subtotal": subtotal or (str(cart_item.quantity * cart_item.price) if getattr(cart_item, "price", None) is not None else None),
        },
        "cart": {
            "item_count": order_models.CartItem.objects.filter(cart=cart).count(),
            "total_amount": str(cart.total_amount()) if hasattr(cart, "total_amount") else "0"
        }
    }
    print("add_to_cart success, resp:", resp)
    return JsonResponse(resp)