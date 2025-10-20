from .models import Cart
from customer import models as customer_models

def _get_cart_item_count(request):
    session = getattr(request, "session", None)
    if session is not None:
        cached_count = session.get("cart_item_count")
        if cached_count is not None:
            return cached_count

    cart = Cart.get_existing_for_request(request)
    if cart is None:
        if session is not None:
            session["cart_item_count"] = 0
            session.modified = True
        return 0

    count = cart.items.count()
    if session is not None:
        session["cart_item_count"] = count
        session.modified = True
    return count


def global_context(request):
    return {
        'cart_item_count': _get_cart_item_count(request),
        'wishlist_count': customer_models.Wishlist.objects.filter(user=request.user).count() if request.user else 0,
    }
