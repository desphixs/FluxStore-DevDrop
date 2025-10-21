from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Prefetch, Sum, Avg, Case, When, IntegerField, F, Q, Min, Value
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.csrf import ensure_csrf_cookie

from django.core.exceptions import ValidationError
from django.db import transaction
from django.conf import settings
from django.db.models import Q, Count
from django.core.paginator import Paginator

from decimal import Decimal, getcontext, ROUND_HALF_UP
import json
import traceback
import math
import requests
import uuid
import logging
import re

from store import models as store_models
from order import models as order_models
from store.easebuzz import generate_easebuzz_form_data
from userauths import models as userauths_model
from store import forms as store_forms


from django.urls import reverse
from django.conf import settings
from django.utils import timezone

from .shiprocket import get_serviceability_and_rates, create_shiprocket_order, ShiprocketError
from userauths.models import Address 
from store.models import ProductVariation, ProductImage

getcontext().prec = 6


logger = logging.getLogger(__name__)


def _update_session_cart_count(request, cart):
    session = getattr(request, "session", None)
    if session is None or cart is None:
        return 0
    count = cart.items.count()
    session["cart_item_count"] = count
    session.modified = True
    return count

@ensure_csrf_cookie
def index(request):
    Product = store_models.Product
    ProductVariation = store_models.ProductVariation
    OrderItem = order_models.OrderItem
    ProductImage = store_models.ProductImage

    base_products_qs = Product.objects.filter(
        status=Product.ProductStatus.PUBLISHED
    ).select_related('vendor', 'category').prefetch_related(
        Prefetch('images', queryset=ProductImage.objects.filter(is_primary=True), to_attr='primary_images'),
        Prefetch('variations', queryset=ProductVariation.objects.filter(is_active=True), to_attr='active_variations'),
    )

    top_selling_agg = OrderItem.objects.filter(
        product_variation__product__status=Product.ProductStatus.PUBLISHED
    ).values('product_variation__product').annotate(
        total_sold=Sum('quantity')
    ).order_by('-total_sold')[:4]

    top_selling_ids = [item['product_variation__product'] for item in top_selling_agg]

    if top_selling_ids:
        preserved_order = Case(*[
            When(pk=pid, then=pos) for pos, pid in enumerate(top_selling_ids)
        ], output_field=IntegerField())
        top_selling = list(Product.objects.filter(pk__in=top_selling_ids).order_by(preserved_order))
    else:
        top_selling = []

    trending_products = list(
        base_products_qs.filter(variations__label='Trending').distinct()
    )[:12]

    recently_added = list(base_products_qs.order_by('-created_at'))[:12]

    
    top_rated = list(
        base_products_qs.annotate(avg_rating=Avg('reviews__rating'))
                        .filter(avg_rating__isnull=False)
                        .order_by('-avg_rating')[:12]
    )

    deals = store_models.ProductVariation.objects.filter(
        product__status=Product.ProductStatus.PUBLISHED,
        is_active=True,
        is_primary=True
    )[:4]

    context = {
        'products': base_products_qs,           
        'categories': store_models.Category.objects.filter(is_active=True, featured=True).order_by("id"),
        'trending_categories': store_models.Category.objects.filter(is_active=True, trending=True)[:8],
        'deals': deals,
        'top_selling': top_selling,
        'trending_products': trending_products,
        'recently_added': recently_added,
        'top_rated': top_rated,
    }
    return render(request, 'index.html', context)

@ensure_csrf_cookie
def product_detail_view(request, slug):
    Product = store_models.Product
    ProductVariation = store_models.ProductVariation
    ProductImage = store_models.ProductImage

    product = get_object_or_404(
        Product.objects.prefetch_related(
            Prefetch(
                'variations',
                queryset=ProductVariation.objects.filter(is_active=True).prefetch_related('variations', 'images'),
                to_attr='active_variations'  
            ),
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

    variation_options = {}
    for variation in getattr(product, 'active_variations', []):
        for vval in variation.variations.all():
            cat = vval.category.name
            variation_options.setdefault(cat, set()).add(vval)
    variation_options = {k: sorted(list(v), key=lambda x: x.value) for k, v in variation_options.items()}


    variation_map = {}
    for var in getattr(product, 'active_variations', []):
        pairs = [(vv.category.name, vv.value) for vv in var.variations.all()]
        pairs_sorted = sorted(pairs, key=lambda x: x[0].lower())
        key = "|".join([f"{cat}:{val}" for cat, val in pairs_sorted])
        images = [img.image.url for img in var.images.all()]  
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

    reviews = product.reviews.all()
    average_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0

    related_products = []
    if product.category:
        related_products = Product.objects.filter(
            category=product.category,
            status=Product.ProductStatus.PUBLISHED
        ).exclude(pk=product.pk)[:4]

    context = {
        'product': product,
        'variation_options': variation_options,
        'variation_map_json': json.dumps(variation_map),  
        'reviews': reviews,
        'average_rating': round(average_rating, 1),
        'related_products': related_products,
    }
    return render(request, 'product_detail.html', context)

def category_list(request):
    
    cats = (
        store_models.Category.objects.filter(is_active=True, parent__isnull=True)
        .annotate(
            direct_products=Count(
                "products",
                filter=Q(products__status=store_models.Product.ProductStatus.PUBLISHED),
                distinct=True,
            ),
            child_products=Count(
                "children__products",
                filter=Q(children__products__status=store_models.Product.ProductStatus.PUBLISHED),
                distinct=True,
            ),
        )
        .order_by("name")
        .prefetch_related("children")
    )

    return render(
        request,
        "category_list.html",
        {"page_title": "Categories", "categories": cats},
    )


def category_detail(request, slug, pk):
    category = get_object_or_404(
        store_models.Category.objects.filter(is_active=True).select_related("parent"),
        pk=pk,
        slug=slug,
    )

    subcats = store_models.Category.objects.filter(is_active=True, parent=category).order_by("name")

    products_qs = (
        store_models.Product.objects.filter(status=store_models.Product.ProductStatus.PUBLISHED)
        .filter(Q(category=category) | Q(category__parent=category))
        .select_related("category", "vendor")
        .prefetch_related("images", "variations", "reviews")
        .order_by("-created_at")
    )

    paginator = Paginator(products_qs, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    
    total_products = products_qs.count()

    return render(
        request,
        "category_detail.html",
        {
            "page_title": category.name,
            "category": category,
            "subcategories": subcats,
            "page_obj": page_obj,
            "total_products": total_products,
        },
    )


def products_by_label(request, label):
    normalized = label.replace("-", " ").strip().lower()
    valid_labels_map = {choice.lower(): choice for choice, _ in ProductVariation.LABEL_CHOICES}
    label_value = valid_labels_map[normalized]

    qs = (
        store_models.Product.objects
        .filter(
            status=store_models.Product.ProductStatus.PUBLISHED,
            variations__is_active=True,
            variations__label=label_value,
        )
        .select_related("category", "vendor")
        .distinct()
        .order_by("-updated_at")
    )

    page_obj = Paginator(qs, 24).get_page(request.GET.get("page") or 1)

    return render(
        request,
        "product_list_by_label.html",
        {
            "products": page_obj,
            "label": label_value,
            "title": f"{label_value} Products",
        },
    )

@ensure_csrf_cookie
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
    selected_variations = payload.get('selected_variations') or {}
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

    if not getattr(variation, "is_active", False):
        print("Variant not active:", getattr(variation, "id", None))
        return JsonResponse({"detail": "Variant not active"}, status=400)

    if getattr(variation, "stock_quantity", 0) < qty:
        print("Insufficient stock for variation:", variation.id, "requested:", qty, "available:", getattr(variation, "stock_quantity", 0))
        return JsonResponse({"detail": "Insufficient stock"}, status=400)

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

    resolved_vv_qs = store_models.VariationValue.objects.none()
    resolved_value_ids = []
    try:
        if selected_value_ids:
            print("Client provided selected_value_ids:", selected_value_ids)
            if isinstance(selected_value_ids, str):
                try:
                    selected_value_ids = json.loads(selected_value_ids)
                except Exception:
                    selected_value_ids = [int(x) for x in selected_value_ids.split(',') if x.strip().isdigit()]
            selected_value_ids = [int(x) for x in selected_value_ids] if hasattr(selected_value_ids, "__iter__") else [int(selected_value_ids)]
            resolved_vv_qs = store_models.VariationValue.objects.filter(id__in=selected_value_ids)
            resolved_value_ids = list(resolved_vv_qs.values_list('id', flat=True))
        elif selected_variations and isinstance(selected_variations, dict):
            
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

            print("cart_item.cart_id after create:", getattr(cart_item, "cart_id", None))
            if getattr(cart_item, "cart_id", None) is None:
                raise RuntimeError("cart_item.cart_id is None after creation")

            try:
                cart_item.price = price_snapshot
                cart_item.save()
            except Exception as e:
                print("Failed to save cart_item.price:", e)

            try:
                
                if hasattr(cart_item, "variation_values"):
                    if resolved_vv_qs.exists():
                        cart_item.variation_values.set(resolved_vv_qs)
                        print("Set cart_item.variation_values ->", list(resolved_vv_qs.values_list('id', flat=True)))
                    else:
                        
                        print("No resolved variation values to set (keeping existing).")
                else:
                    print("CartItem model does not have 'variation_values' M2M field; skipping.")

                backup = {}
                if resolved_value_ids:
                    backup['value_ids'] = resolved_value_ids
                if isinstance(selected_variations, dict) and selected_variations:
                    backup['display'] = {str(k): str(v) for k, v in selected_variations.items()}
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

    subtotal = None
    if hasattr(cart_item, "subtotal") and callable(getattr(cart_item, "subtotal")):
        try:
            subtotal = str(cart_item.subtotal())
        except Exception:
            subtotal = None

    item_count = _update_session_cart_count(request, cart)

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
            "item_count": item_count,
            "total_amount": str(cart.total_amount()) if hasattr(cart, "total_amount") else "0"
        }
    }
    print("add_to_cart success, resp:", resp)
    return JsonResponse(resp)


def cart_detail(request):
    
    cart = order_models.Cart.get_for_request(request)
    items = cart.items.select_related('product_variation', 'product_variation__product')\
            .prefetch_related('variation_values').all()
    
    if request.user.is_authenticated:
        addresses = userauths_model.Address.objects.filter(profile__user=request.user)
    else:
        addresses = None
 
    item_list = []
    total = Decimal('0.00')
    for it in items:
        current_price = it.product_variation.sale_price
        it.price = current_price
        subtotal = (it.price or Decimal('0.00')) * it.quantity
        total += subtotal
        item_list.append({
            'id': it.id,
            'product_name': it.product_variation.product.name,
            'product_image': it.product_variation.product.primary_image,
            'variation_str': ", ".join([v.value for v in it.product_variation.variations.all()]) if hasattr(it.product_variation, 'variations') else "",
            'price': it.price,
            'quantity': it.quantity,
            'subtotal': subtotal,
            'sku': it.product_variation.sku,
            'stock_quantity': it.product_variation.stock_quantity,
        })

    context = {
        'cart': cart,
        'items': item_list,
        'cart_total': total,
        'addresses': addresses,
    }
    return render(request, 'cart.html', context)


@require_POST
def update_cart_item_qty(request):
    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'ok': False, 'message': 'Invalid payload'}, status=400)

    cart_item_id = data.get('cart_item_id')
    try:
        qty = int(data.get('quantity', 0))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'message': 'Quantity must be an integer'}, status=400)

    if qty < 0:
        return JsonResponse({'ok': False, 'message': 'Quantity must be >= 0'}, status=400)

    cart = order_models.Cart.get_for_request(request)

    with transaction.atomic():
        try:
            cart_item = order_models.CartItem.objects.select_for_update().select_related('product_variation').get(pk=cart_item_id, cart=cart)
        except order_models.CartItem.DoesNotExist:
            return JsonResponse({'ok': False, 'message': 'Cart item not found'}, status=404)

        variation = cart_item.product_variation

        if qty == 0:
            cart_item.delete()
        else:
            
            if qty > variation.stock_quantity:
                return JsonResponse({
                    'ok': False,
                    'message': f'Only {variation.stock_quantity} units available in stock'
                }, status=400)

            cart_item.quantity = qty
            cart_item.price = variation.sale_price
            cart_item.save()

    agg = cart.items.aggregate(total=Sum(F('quantity') * F('price')))
    cart_total = agg['total'] or Decimal('0.00')

    
    item_subtotal = Decimal('0.00')
    if qty > 0:
        item_subtotal = (cart_item.price or Decimal('0.00')) * qty

    item_count = _update_session_cart_count(request, cart)

    return JsonResponse({
        'ok': True,
        'cart_item_id': cart_item_id,
        'quantity': qty,
        'item_subtotal': str(item_subtotal),   
        'cart_total': str(cart_total),
        "item_count": item_count,
    })

@login_required
def address_list_create(request):
    profile = request.user.profile  

    
    if request.method == "POST":
        form = store_forms.AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.profile = profile
            address.save()
            return redirect("store:address_list_create")
    else:
        form = store_forms.AddressForm()

    addresses = profile.addresses.all()
    return render(request, "address_list.html", {
        "form": form,
        "addresses": addresses,
    })


@login_required
def set_default_address(request, uuid):
    profile = request.user.profile
    address = get_object_or_404(userauths_model.Address, uuid=uuid, profile=profile)

    
    profile.addresses.filter(address_type=address.address_type).update(is_default=False)

    
    address.is_default = True
    address.save()

    return JsonResponse({"success": True, "uuid": str(address.uuid)})


def _normalize_resp(raw):
    if hasattr(raw, "json") and callable(raw.json):
        try:
            return raw.json()
        except Exception:
            try:
                return json.loads(getattr(raw, "text", "") or "")
            except Exception:
                return raw
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return raw


def _extract_rate_list(resp):
    if isinstance(resp, dict):
        for k in ("available_couriers", "couriers", "result", "results"):
            v = resp.get(k)
            if isinstance(v, list):
                return v
        
        data = resp.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("available_courier_companies", "available_couriers", "couriers", "results"):
                v = data.get(k)
                if isinstance(v, list):
                    return v
    elif isinstance(resp, list):
        return resp
    return []


def _choose_shiprocket_surface(opts):
    if not opts: return None
    
    for o in opts:
        name = (o.get('courier_name') or o.get('name') or o.get('courier') or "").lower()
        if "shiprocket" in name and "surface" in name:
            return o
    
    for o in opts:
        if "surface" in (o.get('courier_name') or o.get('name') or o.get('courier') or "").lower():
            return o
    
    return opts[0]


@login_required
@transaction.atomic
def begin_checkout_shiprocket(request):
    profile = request.user.profile
    cart = order_models.Cart.get_for_request(request)
    if cart.items.count() == 0:
        return redirect('store:cart')  

    addr = profile.addresses.filter(address_type=Address.AddressType.SHIPPING, is_default=True).first()
    if not addr:
        return redirect('store:address_list_create')

    
    item_total = Decimal('0.00')
    total_weight_kg = Decimal('0.00')
    for ci in cart.items.select_related('product_variation', 'product_variation__product'):
        unit_price = ci.price or ci.product_variation.sale_price
        item_total += (unit_price * ci.quantity)
        pv_w = ci.product_variation.weight or Decimal('0.0')
        total_weight_kg += (pv_w * ci.quantity)

    
    order = order_models.Order(
        buyer=request.user,
        address=addr,
        currency=getattr(settings, "DEFAULT_CURRENCY", "INR"),
        item_total=item_total,
        shipping_fee=Decimal('0.00'),
        total_amount=item_total,
        shipping_address_snapshot={
            "full_name": addr.full_name,
            "phone": addr.phone,
            "street_address": addr.street_address,
            "city": addr.city,
            "state": addr.state,
            "postal_code": addr.postal_code,
            "country": addr.country,
        },
    )
    order.set_order_id_if_missing()
    order.save()

    
    for ci in cart.items.select_related('product_variation', 'product_variation__product').all():
        unit_price = ci.price or ci.product_variation.sale_price
        try:
            vendor_user = getattr(ci.product_variation.product, "vendor", None) or request.user
        except Exception:
            vendor_user = request.user
        oi = order_models.OrderItem.objects.create(
            order=order,
            product_variation=ci.product_variation,
            vendor=vendor_user,
            quantity=ci.quantity,
            price=unit_price,
        )
        if ci.variation_values.exists():
            oi.variation_values.set(ci.variation_values.all())
    order.recompute_item_totals_from_items()
    order.recalc_total()
    order.save()
    print(f"DEBUG: after creating items -> item_total={order.item_total}, item_total_net={order.item_total_net}, shipping_fee={order.shipping_fee}, amount_payable={order.amount_payable}")

    pickup_pincode = getattr(settings, "SHIPROCKET_PICKUP_PINCODE", "")
    ship_weight = float(total_weight_kg) if total_weight_kg > 0 else 0.5
    try:
        raw = get_serviceability_and_rates(pickup_pincode, addr.postal_code.strip(), ship_weight, cod=0)
        resp = _normalize_resp(raw)
        opts = _extract_rate_list(resp)
        chosen = _choose_shiprocket_surface(opts)
        if chosen:
            order.apply_shipping_selection(
                rate_obj=chosen,
                fallback_currency=order.currency,
                chargeable_weight=ship_weight,
            )
            order.recompute_item_totals_from_items()
            order.recalc_total()
            order.save()
            print(f"DEBUG: after applying shipping -> shipping_fee={order.shipping_fee}, amount_payable={order.amount_payable}")
        else:
            
            order.recompute_item_totals_from_items()
            order.recalc_total()
            order.save()
            print("DEBUG: no shipping chosen; totals recomputed")

    except ShiprocketError as e:
        
        order.recompute_item_totals_from_items()
        order.recalc_total()
        order.save()
        print("DEBUG: ShiprocketError; totals recomputed with shipping_fee fallback")
    except Exception:
        order.recompute_item_totals_from_items()
        order.recalc_total()
        order.save()
        print("DEBUG: Unexpected exception; totals recomputed with shipping_fee fallback")


    return redirect(reverse('store:checkout', kwargs={'order_id': order.order_id}))


@login_required
@transaction.atomic
def begin_checkout(request):
    profile = request.user.profile
    cart = order_models.Cart.get_for_request(request)

    if cart.items.count() == 0:
        return redirect('store:cart')  

    
    addr = profile.addresses.filter(
        address_type=Address.AddressType.SHIPPING,
        is_default=True
    ).first()
    if not addr:
        return redirect('store:address_list_create')

    
    item_total = Decimal('0.00')
    shipping_total = Decimal('0.00')

    cart_items_qs = cart.items.select_related(
        'product_variation',
        'product_variation__product'
    )

    for ci in cart_items_qs:
        pv = ci.product_variation
        unit_price = ci.price or pv.sale_price
        item_total += (unit_price * ci.quantity)

        
        shipping_total += (pv.shipping_price or Decimal('0.00')) * ci.quantity

    order = order_models.Order(
        buyer=request.user,
        address=addr,
        currency=getattr(settings, "DEFAULT_CURRENCY", "INR"),
        item_total=item_total,                 
        shipping_fee=shipping_total,            
        total_amount=item_total + shipping_total,
        shipping_address_snapshot={
            "full_name": addr.full_name,
            "phone": addr.phone,
            "street_address": addr.street_address,
            "city": addr.city,
            "state": addr.state,
            "postal_code": addr.postal_code,
            "country": addr.country,
        },
    )
    order.set_order_id_if_missing()
    order.save()

    for ci in cart_items_qs:
        pv = ci.product_variation
        unit_price = ci.price or pv.sale_price

        try:
            vendor_user = getattr(pv.product, "vendor", None) or request.user
        except Exception:
            vendor_user = request.user

        oi = order_models.OrderItem.objects.create(
            order=order,
            product_variation=pv,
            vendor=vendor_user,
            quantity=ci.quantity,
            price=unit_price,
        )

        if ci.variation_values.exists():
            oi.variation_values.set(ci.variation_values.all())

        
        oi.recompute_line_totals()
        oi.save(update_fields=["line_subtotal_net"])

    
    order.recompute_item_totals_from_items()
    
    order.recalc_total()
    order.save()
    return redirect(reverse('store:checkout', kwargs={'order_id': order.order_id}))


@login_required
def checkout_view(request, order_id: str):
    order = get_object_or_404(order_models.Order, buyer=request.user, order_id=order_id)

    items_qs = order.items.select_related('product_variation', 'product_variation__product').all()
    display_items = []
    for it in items_qs:
        pv = it.product_variation
        display_items.append({
            "id": it.id,
            "product_name": pv.product.name,
            "variation": ", ".join([v.value for v in it.variation_values.all()]),
            "price": it.price,
            "quantity": it.quantity,
            "subtotal": it.price * it.quantity,
        })

    order.recompute_item_totals_from_items()
    order.recalc_total()
    order.save()

    context = {
        "order": order,
        "items": display_items,
        "item_total": order.item_total,            
        "shipping_fee": order.shipping_fee,      
        "grand_total": order.amount_payable or order.total_amount, 
        "default_address": order.address,
        "courier_name": order.courier_name,
        "etd_text": order.etd_text,
        "courier_code": order.courier_code,
    }
    return render(request, "checkout.html", context)



def _q(x: Decimal) -> Decimal:
    return (x or Decimal('0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def _vendor_gross(order, vendor_id) -> Decimal:
    total = Decimal('0.00')
    for it in order.items.select_related('product_variation', 'product_variation__product'):
        if it.vendor_id == vendor_id:
            total += it.subtotal
    return total

def _prorate_fixed(items, target_amount: Decimal):
    target = _q(target_amount)
    parts = [(it.id, it.subtotal) for it in items]
    gross = sum((g for _, g in parts), Decimal('0.00'))
    if gross <= 0 or target <= 0:
        return {it.id: Decimal('0.00') for it in items}
    alloc, running = {}, Decimal('0.00')
    for idx, (iid, g) in enumerate(parts):
        if idx < len(parts) - 1:
            share = _q(target * (g / gross))
            alloc[iid], running = share, running + share
        else:
            alloc[iid] = _q(target - running)
    return alloc

def _apply_coupon_to_order(order, coupon: order_models.Coupon, user):
    if not coupon.is_live():
        return False, "Coupon is not active."
    vendor_id = coupon.vendor_id
    vendor_items = list(order.items.filter(vendor_id=vendor_id))
    if not vendor_items:
        return False, "Coupon vendor has no items in this order."

    if coupon.usage_limit_total is not None:
        if coupon.redemptions.count() >= coupon.usage_limit_total:
            return False, "Coupon usage limit reached."
    if coupon.usage_limit_per_user is not None:
        if coupon.redemptions.filter(user=user).count() >= coupon.usage_limit_per_user:
            return False, "You have already used this coupon the maximum number of times."

    vendor_gross = _vendor_gross(order, vendor_id)
    if coupon.min_order_amount and vendor_gross < coupon.min_order_amount:
        return False, f"Vendor subtotal must be at least {coupon.min_order_amount}."

    discount = Decimal('0.00')
    if coupon.discount_type == order_models.Coupon.DiscountType.PERCENT:
        pct = Decimal(str(coupon.percent_off or 0)) / Decimal('100')
        discount = vendor_gross * pct
        if coupon.max_discount_amount:
            discount = min(discount, coupon.max_discount_amount)
    else:  
        discount = min(Decimal(str(coupon.amount_off or 0)), vendor_gross)

    discount = _q(discount)
    if discount <= 0:
        return False, "Coupon yields no discount for this order."

    if coupon.discount_type == order_models.Coupon.DiscountType.FIXED:
        allocation = _prorate_fixed(vendor_items, discount)
    else:
        allocation, running = {}, Decimal('0.00')
        for idx, it in enumerate(vendor_items):
            if idx < len(vendor_items) - 1:
                share = _q(it.subtotal * (Decimal(str(coupon.percent_off)) / Decimal('100')))
                allocation[it.id], running = share, running + share
            else:
                allocation[it.id] = _q(discount - running)

    with transaction.atomic():
        order_models.OrderItemDiscount.objects.filter(
            order_item__in=[it.id for it in vendor_items],
            coupon=coupon
        ).delete()
        red, _ = order_models.CouponRedemption.objects.update_or_create(
            coupon=coupon, order=order, user=user, vendor_id=vendor_id,
            defaults={"discount_amount": discount}
        )
        for it in vendor_items:
            add_amt = allocation.get(it.id, Decimal('0.00'))
            if add_amt > 0:
                order_models.OrderItemDiscount.objects.create(
                    order_item=it, coupon=coupon, vendor_id=vendor_id, amount=add_amt
                )
                it.line_discount_total = _q((it.line_discount_total or 0) + add_amt)
                it.recompute_line_totals()
                it.save(update_fields=["line_discount_total", "line_subtotal_net"])

        order.recompute_item_totals_from_items()
        order.recalc_total()
        order.save(update_fields=[
            "item_total", "item_discount_total", "item_total_net",
            "amount_payable", "total_amount"
        ])

    return True, f"Applied {coupon.code}."

@login_required
@transaction.atomic
def apply_coupon(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    code = (request.POST.get("code") or "").strip()
    order_id = request.POST.get("order_id")
    if not code or not order_id:
        return HttpResponseBadRequest("Missing code or order_id")

    order = get_object_or_404(order_models.Order, buyer=request.user, order_id=order_id)
    coupon = order_models.Coupon.objects.filter(code__iexact=code).select_related("vendor").first()
    if not coupon:
        return JsonResponse({"ok": False, "message": "Invalid coupon code."})
    
    if getattr(settings, "SINGLE_COUPON_PER_ORDER", False):
        if order.has_any_coupon_applied():
            return JsonResponse({"ok": False, "message": "You’ve already applied a coupon to this order."})

    if getattr(settings, "SINGLE_COUPON_PER_VENDOR", False):
        if order.has_coupon_for_vendor(coupon.vendor_id):
            return JsonResponse({"ok": False, "message": "A coupon is already applied for this vendor."})


    ok, msg = _apply_coupon_to_order(order, coupon, request.user)
    if not ok:
        return JsonResponse({"ok": False, "message": msg})

    return JsonResponse({
        "ok": True,
        "message": msg,
        "amounts": {
            "item_total":          str(order.item_total),
            "item_discount_total": str(order.item_discount_total),
            "item_total_net":      str(order.item_total_net),
            "shipping_fee":        str(order.shipping_fee),
            "amount_payable":      str(order.amount_payable),
        }
    })

@login_required
@transaction.atomic
def remove_coupon(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    code = (request.POST.get("code") or "").strip()
    order_id = request.POST.get("order_id")
    if not code or not order_id:
        return HttpResponseBadRequest("Missing code or order_id")

    order = get_object_or_404(order_models.Order, buyer=request.user, order_id=order_id)
    coupon = order_models.Coupon.objects.filter(code__iexact=code).first()
    if not coupon:
        return JsonResponse({"ok": False, "message": "Coupon not found."})

    vendor_id = coupon.vendor_id
    vendor_items = list(order.items.filter(vendor_id=vendor_id))

    with transaction.atomic():
        
        allocs = list(order_models.OrderItemDiscount.objects.filter(
            order_item__in=[it.id for it in vendor_items], coupon=coupon
        ))
        by_item = {}
        for a in allocs:
            by_item[a.order_item_id] = by_item.get(a.order_item_id, Decimal('0.00')) + a.amount

        order_models.OrderItemDiscount.objects.filter(
            order_item__in=[it.id for it in vendor_items], coupon=coupon
        ).delete()
        order_models.CouponRedemption.objects.filter(
            coupon=coupon, order=order, vendor_id=vendor_id
        ).delete()

        for it in vendor_items:
            undo = _q(by_item.get(it.id, Decimal('0.00')))
            if undo > 0:
                it.line_discount_total = _q(max((it.line_discount_total or 0) - undo, Decimal('0.00')))
                it.recompute_line_totals()
                it.save(update_fields=["line_discount_total", "line_subtotal_net"])

        order.recompute_item_totals_from_items()
        order.recalc_total()
        order.save(update_fields=[
            "item_total", "item_discount_total", "item_total_net",
            "amount_payable", "total_amount"
        ])

    return JsonResponse({
        "ok": True,
        "message": f"Removed {coupon.code}",
        "amounts": {
            "item_total":          str(order.item_total),
            "item_discount_total": str(order.item_discount_total),
            "item_total_net":      str(order.item_total_net),
            "shipping_fee":        str(order.shipping_fee),
            "amount_payable":      str(order.amount_payable),
        }
    })




def search(request):
    
    q = (request.GET.get("q") or "").strip()

    
    products = store_models.Product.objects.none()

    if q:
        terms = [t for t in re.split(r"\s+", q) if t]

        
        combined = Q()
        for t in terms:
            per_term = (
                Q(name__icontains=t) |
                Q(description__icontains=t) |
                Q(category__name__icontains=t) |
                Q(variations__sku__icontains=t) |
                Q(variations__variations__value__icontains=t)
            )
            combined &= per_term

        
        primary_images = ProductImage.objects.filter(is_primary=True)
        active_vars = ProductVariation.objects.filter(is_active=True).order_by("sale_price")

        
        name_hit = Case(When(name__icontains=q, then=Value(3)), default=Value(0), output_field=IntegerField())
        sku_hit  = Case(When(variations__sku__icontains=q, then=Value(2)), default=Value(0), output_field=IntegerField())
        cat_hit  = Case(When(category__name__icontains=q, then=Value(1)), default=Value(0), output_field=IntegerField())

        products = (
            store_models.Product.objects
            .filter(status=store_models.Product.ProductStatus.PUBLISHED)
            .filter(combined)
            .select_related("category", "vendor")
            .prefetch_related(
                Prefetch("images", queryset=primary_images, to_attr="primary_images_prefetch"),
                Prefetch("variations", queryset=active_vars, to_attr="active_variations_prefetch"),
            )
            .annotate(
                avg_rating=Avg("reviews__rating"),
                reviews_count=Count("reviews", distinct=True),
                _rank=name_hit + sku_hit + cat_hit,
            )
            .distinct()
            .order_by("-_rank", "-updated_at")
        )

    page = request.GET.get("page") or 1
    page_obj = Paginator(products, 24).get_page(page)

    return render(request, "search.html", {
        "q": q,
        "products": page_obj,
    })