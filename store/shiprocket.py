# yourapp/services/shiprocket.py
import time
import requests
from django.conf import settings
from django.core.cache import cache

API_BASE = getattr(settings, "SHIPROCKET_API_BASE", "https://apiv2.shiprocket.in/v1/external")
EMAIL = getattr(settings, "SHIPROCKET_API_USER_EMAIL", None)
PASSWORD = getattr(settings, "SHIPROCKET_API_USER_PASSWORD", None)

CACHE_KEY = "shiprocket_token_v1"
CACHE_TTL = 60 * 50  # 50 minutes (token TTL usually ~1hr)

class ShiprocketError(Exception):
    pass

def _get_token():
    token = cache.get(CACHE_KEY)
    if token:
        return token

    if not (EMAIL and PASSWORD):
        raise ShiprocketError("Shiprocket credentials not configured in settings.")

    url = f"{API_BASE}/auth/login"
    resp = requests.post(url, json={"email": EMAIL, "password": PASSWORD}, timeout=12)
    if resp.status_code != 200:
        raise ShiprocketError(f"Auth failed: {resp.status_code} {resp.text}")

    data = resp.json()
    # docs show token in response, sometimes under 'token' or 'data' — check and adapt
    token = data.get("token") or data.get("data", {}).get("token") or data.get("data", {}).get("token")
    if not token:
        # some accounts return {"token": "xxx"} or {"data": {"token": "xxx"}}
        # fallback to raw 'message' if present
        raise ShiprocketError(f"Token not found in response: {data}")

    cache.set(CACHE_KEY, token, CACHE_TTL)
    return token

def _headers():
    token = _get_token()
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

def get_serviceability_and_rates(pickup_pincode, delivery_pincode, weight_kg, cod=0):
    """
    Returns list of available couriers with rate, serviceability info.
    - weight_kg: Decimal or float in KG
    """
    url = f"{API_BASE}/courier/serviceability/"
    params = {
        "pickup_postcode": str(pickup_pincode),
        "delivery_postcode": str(delivery_pincode),
        "weight": float(weight_kg),
        "cod": int(cod),  # 0 or 1
    }
    # Some docs use GET, others use POST. We'll try GET with params.
    resp = requests.get(url, headers=_headers(), params=params, timeout=12)
    if resp.status_code != 200:
        raise ShiprocketError(f"Serviceability failed: {resp.status_code} {resp.text}")
    return resp.json()

def create_shiprocket_order(order_payload):
    """
    order_payload: shaped per Shiprocket create/adhoc API.
    Example shape (simplified):
    {
      "order_id": "123",
      "order_date": "2023-01-01",
      "pickup_location": "Default",
      "shipping_is_billing": True,
      "billing_customer_name": "x",
      "billing_address": "x",
      "billing_city": "x",
      "billing_pincode": "110001",
      "billing_state": "Delhi",
      "billing_country": "India",
      "billing_email": "...",
      "billing_phone": "...",
      "order_items": [ {...} ],
      "sub_total": 1000,
      "length": 10,
      "breadth": 10,
      "height": 10,
      "weight": 0.5,
      "channel_id": "",
      "payment_method": "Prepaid"  # or "COD"
    }
    """
    url = f"{API_BASE}/orders/create/adhoc"
    resp = requests.post(url, headers=_headers(), json=order_payload, timeout=15)
    if resp.status_code not in (200, 201):
        raise ShiprocketError(f"Create order failed: {resp.status_code} {resp.text}")
    return resp.json()
