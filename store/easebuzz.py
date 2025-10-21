# payments/utils.py
import hashlib
from django.conf import settings

def generate_easebuzz_form_data(order):
    """
    Prepares POST data for Easebuzz checkout.
    If your account supports EMI, it'll show EMI options automatically.
    """
    data = {
        "key": settings.EASEBUZZ_API_KEY,
        "txnid": order.uuid,
        "amount": str(order.total_amount),
        "productinfo": f"Order {order.uuid}",
        "firstname": order.buyer.get_full_name() or order.buyer.email,
        "email": order.buyer.email,
        "phone": order.address.phone if hasattr(order.address, 'phone') else "",
        "surl": settings.SITE_URL + f"/payments/success/{order.uuid}/",
        "furl": settings.SITE_URL + f"/payments/failure/{order.uuid}/",
        
        "offer_type": "EMI",
    }
    
    hash_str = "|".join([
        data["key"], data["txnid"], data["amount"], data["productinfo"],
        data["firstname"], data["email"], '', '', '', '', '', '', '', '', '', settings.EASEBUZZ_SALT
    ])
    data["hash"] = hashlib.sha512(hash_str.encode('utf-8')).hexdigest()
    return data
