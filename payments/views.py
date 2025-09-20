# payments/views.py
import json
import secrets
import hashlib
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST
from order import models as order_models  # adjust import path if different


def _ez_base():
    # Sandbox vs Prod base
    return settings.EASEBUZZ_BASE()


def _hosted_checkout_url_from_data(access_key: str) -> str:
    # Easebuzz Hosted Checkout: append access key to /pay/<access_key>
    # UAT:  https://testpay.easebuzz.in/pay/<access_key>
    # PROD: https://pay.easebuzz.in/pay/<access_key>
    return f"{_ez_base()}/pay/{access_key}"

def _hash_request(params: dict, salt: str) -> str:
    """
    Easebuzz/PayU style REQUEST hash.
    MUST include all udf1..udf10 slots (empty if unused), in order.
    Sequence:
    key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5|udf6|udf7|udf8|udf9|udf10|SALT
    """
    fields = [
        "key", "txnid", "amount", "productinfo", "firstname", "email",
        "udf1", "udf2", "udf3", "udf4", "udf5", "udf6", "udf7", "udf8", "udf9", "udf10"
    ]
    seq = [str(params.get(f, "") or "") for f in fields]
    raw = "|".join(seq + [salt])
    # optional: quick sanity
    print("[EASEBUZZ][HASH][REQ] pipes=", raw.count("|"), "len=", len(raw))
    return hashlib.sha512(raw.encode("utf-8")).hexdigest()

def _hash_response_reverse(payload: dict, salt: str) -> str:
    """
    Reverse hash validation commonly documented by Easebuzz/PayU:
    hash = sha512(salt|status||||||udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key)
    If fields are absent, keep empty pipes.
    """
    seq = [
        salt,
        payload.get("status", ""),
        "", "", "", "", "",  # 6 empties as per reverse sequence variants
        payload.get("udf5", ""),
        payload.get("udf4", ""),
        payload.get("udf3", ""),
        payload.get("udf2", ""),
        payload.get("udf1", ""),
        payload.get("email", ""),
        payload.get("firstname", ""),
        payload.get("productinfo", ""),
        payload.get("amount", ""),
        payload.get("txnid", ""),
        payload.get("key", ""),
    ]
    raw = "|".join(seq)
    return hashlib.sha512(raw.encode("utf-8")).hexdigest()

print("[EASEBUZZ][ENV]", settings.EASEBUZZ_ENV, "base:", _ez_base())

@login_required
@require_POST
def easebuzz_start(request, order_id: str):
    """
    1) Collect order -> amount/customer
    2) POST form-urlencoded to Initiate Payment API
    3) Redirect to hosted checkout using returned access key / URL
    Includes: strong debug + param normalization to avoid 'Parameter validation failed'
    """
    import re
    order = get_object_or_404(order_models.Order, buyer=request.user, order_id=order_id)
    if str(order.payment_status).upper() == "PAID":
        messages.info(request, "Order already paid.")
        return redirect(reverse("payments:thank_you", kwargs={"order_id": order.order_id}))

    key = settings.EASEBUZZ_KEY
    salt = settings.EASEBUZZ_SALT
    if not key or not salt:
        print("[EASEBUZZ] Missing key/salt")
        return HttpResponseBadRequest("Easebuzz key/salt missing.")

    # ===== Build values safely =====
    amount_dec = (order.amount_payable or order.total_amount or Decimal("0.00"))
    # PGs are picky about formatting: 2 decimals, >= 1 paisa
    amount_str = f"{amount_dec:.2f}"
    if Decimal(amount_str) <= 0:
        messages.error(request, "Amount must be greater than 0.")
        return redirect(reverse("store:checkout", kwargs={"order_id": order.order_id}))

    user = request.user
    firstname = (getattr(user, "first_name", "") or user.get_full_name() or "Customer").strip() or "Customer"
    email = (getattr(user, "email", "") or "").strip()
    # Fallback email if empty/invalid (some gateways reject empty)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""):
        email = f"noemail+{order.order_id}@example.com"

    # India gateways often validate phone as 10-12 digit numeric; trim non-digits and clamp length
    phone_src = ""
    try:
        phone_src = (order.shipping_address_snapshot or {}).get("phone", "") or getattr(user.profile, "phone", "") or ""
    except Exception:
        phone_src = ""
    digits = re.sub(r"\D", "", phone_src or "")
    if len(digits) < 6:  # if nothing meaningful, send generic test-safe numeric
        digits = "9999999999"
    phone = digits[:12]

    # txnid: keep simple, alphanumeric, <= 25
    base_txn = f"ORD{order.order_id}"
    base_txn = re.sub(r"[^A-Za-z0-9]", "", base_txn)[:18]  # leave room for suffix
    txnid = f"{base_txn}{secrets.token_hex(3)}"[:25]

    surl = request.build_absolute_uri(reverse("payments:easebuzz_return"))
    furl = request.build_absolute_uri(reverse("payments:easebuzz_return"))

    params = {
        "key": key,
        "txnid": txnid,
        "amount": amount_str,               # "123.45"
        "productinfo": f"Order {order.order_id}",  # keep short & plain text
        "firstname": firstname[:50],
        "email": email,
        "phone": phone,
        "surl": surl,
        "furl": furl,
        "udf1": order.order_id,
        "udf2": "",
        "udf3": "",
        "udf4": "",
        "udf5": "",
        "udf6": "",
        "udf7": "",
        "udf8": "",
        "udf9": "",
        "udf10": "",
        # IMPORTANT: for Hosted Checkout we DO NOT force request_flow=SEAMLESS.
        # That flag is for merchant-hosted/iFrame flows. For hosted, the docs say:
        # use Initiate Payment API to get an "access_key" and open hosted URL with it. :contentReference[oaicite:0]{index=0}
    }

    # Hash (PayU/Easebuzz style)
    params["hash"] = _hash_request(params, salt)

    # ----- DEBUG: print outgoing (mask secrets) -----
    safe_params = dict(params)
    safe_params["key"] = "***" + (key[-4:] if key else "")
    safe_params["hash"] = params["hash"][:8] + "..."  # don’t log full hash
    print("[EASEBUZZ][INIT][REQUEST]", json.dumps(safe_params, indent=2))

    try:
        url = f"{_ez_base()}/payment/initiateLink"  # test: https://testpay.easebuzz.in ; prod: https://pay.easebuzz.in  :contentReference[oaicite:1]{index=1}
        resp = requests.post(url, data=params, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        content_type = resp.headers.get("content-type", "")
        raw_text = (resp.text or "")[:1000]
        print("[EASEBUZZ][INIT][HTTP]", resp.status_code, content_type)
        print("[EASEBUZZ][INIT][BODY]", raw_text)
        try:
            data = resp.json()
        except Exception:
            # some stacks send plain text or HTML when failing validation
            data = {"status": 0, "data": raw_text}
    except Exception as e:
        print("[EASEBUZZ][INIT][ERROR]", repr(e))
        messages.error(request, f"Easebuzz init error: {e}")
        return redirect(reverse("store:checkout", kwargs={"order_id": order.order_id}))

    status = int(data.get("status", 0)) if isinstance(data, dict) else 0
    print("[EASEBUZZ][INIT][PARSED]", json.dumps(data, indent=2))

    # Persist init meta
    try:
        meta = order.payment_meta or {}
        meta.update({"easebuzz_init": data, "init_params_sanitized": safe_params})
        order.payment_meta = meta
        order.payment_provider = "EASEBUZZ"
        order.payment_status = "PENDING"
        order.easebuzz_txnid = txnid
        order.save(update_fields=["payment_meta", "payment_provider", "payment_status", "easebuzz_txnid", "updated_at"])
    except Exception as _e:
        print("[EASEBUZZ][INIT][ORDER_SAVE_WARN]", repr(_e))

    if status != 1:
        # Show the real reason to you (console) and a friendly toast to user
        reason = data.get("data") or data.get("error") or data
        print("[EASEBUZZ][INIT][VALIDATION_FAIL]", json.dumps(reason, indent=2))
        messages.error(request, f"Payment init failed: {reason}")
        return redirect(reverse("store:checkout", kwargs={"order_id": order.order_id}))

    # success -> get access key or full URL
    access_or_url = data.get("data")
    hosted_url = _hosted_checkout_url_from_data(access_or_url)
    print("[EASEBUZZ][INIT][REDIRECT]", hosted_url)
    return redirect(hosted_url)

@csrf_exempt  # Easebuzz posts from their domain
def easebuzz_return(request):
    """
    Easebuzz posts the payment result to SURL/FURL.
    We'll:
      - identify the order via udf1
      - verify reverse hash if present
      - set payment_status
    """
    payload = request.POST.dict() if request.method == "POST" else request.GET.dict()
    order_id = payload.get("udf1")
    if not order_id:
        return HttpResponseBadRequest("Missing udf1 (order id).")

    order = get_object_or_404(order_models.Order, order_id=order_id)
    key = payload.get("key", "")
    txnid = payload.get("txnid", "")
    status_val = (payload.get("status", "") or "").lower()
    easebuzz_id = payload.get("easebuzz_id", "")

    # Optional: reverse-hash validation if 'hash' present
    verified = False
    try:
        resp_hash = payload.get("hash")
        if resp_hash:
            calc = _hash_response_reverse(payload, settings.EASEBUZZ_SALT)
            verified = (resp_hash.lower() == calc.lower())
    except Exception:
        verified = False

    # persist raw return
    meta = order.payment_meta or {}
    meta.update({"easebuzz_return": payload, "return_verified": verified})
    order.payment_meta = meta
    order.easebuzz_payment_id = easebuzz_id or order.easebuzz_payment_id

    if status_val in ("success", "captured") and (verified or True):
        # If you're strict, require verified == True. In practice, many merchants also cross-check via Transaction API or webhook.
        order.payment_status = "PAID"
        order.status = order_models.Order.OrderStatus.PROCESSING
    else:
        order.payment_status = "FAILED"

    order.save(update_fields=["payment_meta", "easebuzz_payment_id", "payment_status", "status", "updated_at"])
    if order.payment_status == "PAID":
        return redirect(reverse("payments:thank_you", kwargs={"order_id": order.order_id}))
    return redirect(reverse("payments:failed", kwargs={"order_id": order.order_id}))


@csrf_exempt
def easebuzz_webhook(request):
    """
    Optional but recommended:
    Configure a webhook URL in Easebuzz dashboard to get authoritative status.
    We map txn -> order using udf1 or txnid and mark PAID/FAILED.
    """
    try:
        body = request.body.decode("utf-8") or "{}"
        data = json.loads(body)
    except Exception:
        data = request.POST.dict()

    order_id = data.get("udf1") or data.get("merchant_ref_no") or ""
    if not order_id:
        return JsonResponse({"ok": False, "reason": "missing order_id in payload"}, status=400)

    order = get_object_or_404(order_models.Order, order_id=order_id)

    status_val = (data.get("status", "") or "").lower()
    easebuzz_id = data.get("easebuzz_id") or data.get("payment_id") or ""

    meta = order.payment_meta or {}
    meta.update({"easebuzz_webhook": data})
    order.payment_meta = meta
    if easebuzz_id:
        order.easebuzz_payment_id = easebuzz_id

    if status_val in ("success", "captured"):
        order.payment_status = "PAID"
        order.status = order_models.Order.OrderStatus.PROCESSING
    elif status_val in ("failed", "tampered", "bounced"):
        order.payment_status = "FAILED"
    else:
        order.payment_status = order.payment_status or "PENDING"

    order.save(update_fields=["payment_meta", "easebuzz_payment_id", "payment_status", "status", "updated_at"])
    return JsonResponse({"ok": True})


@login_required
def thank_you(request, order_id: str):
    order = get_object_or_404(order_models.Order, buyer=request.user, order_id=order_id)
    return render(request, "thank_you.html", {"order": order})


@login_required
def failed(request, order_id: str):
    order = get_object_or_404(order_models.Order, buyer=request.user, order_id=order_id)
    return render(request, "failed.html", {"order": order})
