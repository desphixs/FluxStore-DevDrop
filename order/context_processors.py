from .models import Cart, CartItem

def global_context(request):
    
    context = {}

    cart = Cart.get_for_request(request)
    context['cart_item_count'] = CartItem.objects.filter(cart=cart).count()
    
    
    return context