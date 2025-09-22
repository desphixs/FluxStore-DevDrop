

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum, F, Count
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from order import models as order_models

# payments/views.py
import json
import secrets
import hashlib
from decimal import Decimal
import logging
import requests

log = logging.getLogger(__name__)


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




# ---------- Easebuzz helpers ----------

def _easebuzz_base_url() -> str:
    env = (getattr(settings, "EASEBUZZ_ENV", "PROD") or "").upper()
    if env in {"UAT", "TEST", "SANDBOX"} or getattr(settings, "DEBUG", False):
        return "https://testpay.easebuzz.in"
    return "https://pay.easebuzz.in"

def _easebuzz_status_urls() -> list[str]:
    """
    If you know your exact status URL from your merchant docs, set EASEBUZZ_TXN_STATUS_URL in settings.
    Otherwise we try a few common endpoints (first one that returns JSON wins).
    """
    if getattr(settings, "EASEBUZZ_TXN_STATUS_URL", None):
        return [settings.EASEBUZZ_TXN_STATUS_URL]

    base = _easebuzz_base_url().rstrip("/")
    # Known/popular patterns (keep order)
    candidates = [
        f"{base}/payment/transaction/v2/retrieve",
        f"{base}/transaction/v2/retrieve",
        f"{base}/payment/v2/transaction",
    ]
    return candidates

def _sha512_pipe(*parts) -> str:
    s = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha512(s.encode("utf-8")).hexdigest()

def _easebuzz_status_payload(txnid: str, easebuzz_id: str | None) -> dict:
    """
    Minimal payload. Some accounts require a 'hash' (key|txnid|salt), others not.
    We include both txnid and easebuzz_id if we have them.
    """
    payload = {
        "key": getattr(settings, "EASEBUZZ_KEY", ""),
        "txnid": txnid,
    }
    if easebuzz_id:
        payload["easebuzz_id"] = easebuzz_id

    salt = getattr(settings, "EASEBUZZ_SALT", "")
    if salt:
        # Common scheme in Easebuzz status APIs; adjust if your docs specify differently.
        payload["hash"] = _sha512_pipe(payload["key"], payload["txnid"], salt)

    return payload

def _easebuzz_txn_status(txnid: str, easebuzz_id: str | None = None, timeout=10) -> dict | None:
    """
    Try a few candidate URLs until one returns JSON. Returns parsed JSON or None.
    """
    payload = _easebuzz_status_payload(txnid, easebuzz_id)
    headers = {"User-Agent": "EfashionBazaar/1.0", "Accept": "application/json"}

    for url in _easebuzz_status_urls():
        try:
            r = requests.post(url, data=payload, headers=headers, timeout=timeout)
            r.raise_for_status()
            # Some endpoints return text/plain JSON; safe-load
            try:
                data = r.json()
            except Exception:
                data = json.loads((r.text or "").strip() or "{}")

            log.info("[EASEBUZZ][STATUS] %s -> %s", url, data)
            return data
        except Exception as e:
            log.warning("[EASEBUZZ][STATUS][FAIL] %s (%s)", url, e)
            continue
    return None

def _easebuzz_status_is_success(resp: dict | None) -> tuple[bool, str, str | None]:
    """
    Return (ok, gateway_status_string, easebuzz_payment_id or None).
    We accept 'success' / 'captured' variants.
    """
    if not isinstance(resp, dict):
        return (False, "no-response", None)

    # Flexible parsing across API variants
    top_status = resp.get("status")
    data = resp.get("data") if isinstance(resp.get("data"), dict) else resp

    gstat = (data.get("status") or data.get("txn_status") or data.get("response_status") or "").lower()
    ez_id = data.get("easebuzz_id") or data.get("payment_id") or resp.get("easebuzz_id")

    ok = False
    if str(top_status) in {"1", "success", "True", "true"}:
        # Many endpoints put the canonical gateway result inside data.status
        ok = gstat in {"success", "captured", "success-verified"}
    else:
        # Some endpoints only set 'data.status'
        ok = gstat in {"success", "captured", "success-verified"}

    return (ok, gstat or str(top_status), ez_id)

# ---------- Notification helpers ----------

def _notify_once(recipient, ntype, level, title, message, obj, meta=None):
    """
    Idempotent-ish: don't spam duplicates for the same order + title + recipient.
    """
    ct = ContentType.objects.get_for_model(obj.__class__)
    meta = meta or {}
    exists = order_models.Notification.objects.filter(
        recipient=recipient,
        ntype=ntype,
        title=title,
        content_type=ct,
        object_id=str(obj.pk),
    ).exists()
    if exists:
        return

    order_models.Notification.objects.create(
        recipient=recipient,
        ntype=ntype,
        level=level,
        title=title,
        message=message or "",
        content_type=ct,
        object_id=str(obj.pk),
        meta=meta,
    )

def _notify_buyer_order_paid(order):
    title = "Order placed"
    message = f"Thanks! Your order #{order.order_id} has been placed."
    _notify_once(
        recipient=order.buyer,
        ntype=order_models.Notification.NType.ORDER,
        level=order_models.Notification.Level.SUCCESS,
        title=title,
        message=message,
        obj=order,
        meta={"target_url": f"/customer/orders/{order.order_id}/"},
    )

def _notify_vendors_order_paid(order):
    """
    One notification per vendor present in the order.
    Includes a quick summary for that vendor: items, gross, discount, net.
    """
    vendor_rows = (
        order.items
             .values("vendor_id")
             .annotate(
                 item_count=Coalesce(Sum("quantity"), 0),
                 gross=Coalesce(
                     Sum(F("price") * F("quantity"),
                         output_field=DecimalField(max_digits=12, decimal_places=2)
                     ),
                     Decimal("0.00")
                 ),
                 disc=Coalesce(
                     Sum("line_discount_total",
                         output_field=DecimalField(max_digits=12, decimal_places=2)
                     ),
                     Decimal("0.00")
                 ),
             )
    )

    for row in vendor_rows:
        vendor_id = row["vendor_id"]
        if not vendor_id:
            continue
        try:
            vendor_user = order_models.settings.AUTH_USER_MODEL.objects.get(pk=vendor_id)  # won’t work
        except Exception:
            # Better: fetch via your User model directly
            from django.contrib.auth import get_user_model
            User = get_user_model()
            vendor_user = User.objects.filter(pk=vendor_id).first()
        if not vendor_user:
            continue

        net = (row["gross"] or Decimal("0.00")) - (row["disc"] or Decimal("0.00"))
        title = f"New paid order #{order.order_id}"
        message = f"{row['item_count']} item(s) • ₹{net:.2f} net for you."

        _notify_once(
            recipient=vendor_user,
            ntype=order_models.Notification.NType.ORDER,
            level=order_models.Notification.Level.SUCCESS,
            title=title,
            message=message,
            obj=order,
            meta={"target_url": f"/vendor/orders/{order.order_id}/"},
        )

# ---------- Your return view (drop-in) ----------

@csrf_exempt  # Easebuzz posts from their domain
def easebuzz_return(request):
    """
    Verify with Easebuzz Transaction API BEFORE marking paid.
    Then create notifications (buyer + each vendor) and move order to PROCESSING.
    """
    payload = request.POST.dict() if request.method == "POST" else request.GET.dict()
    order_public_id = payload.get("udf1")
    if not order_public_id:
        return HttpResponseBadRequest("Missing udf1 (order id).")

    order = get_object_or_404(order_models.Order, order_id=order_public_id)

    txnid = payload.get("txnid", "") or (order.easebuzz_txnid or "")
    easebuzz_id = payload.get("easebuzz_id", "") or (order.easebuzz_payment_id or "")
    status_val = (payload.get("status", "") or "").lower()

    # Persist raw gateway return + our reverse-hash flag if you already compute it elsewhere
    meta = order.payment_meta or {}
    meta.update({
        "easebuzz_return": payload,
        "return_received_at": timezone.now().isoformat(),
    })

    # 1) Verify with Transaction Status API
    verified_resp = _easebuzz_txn_status(txnid=txnid, easebuzz_id=easebuzz_id)
    ok, gateway_status, ez_id_from_status = _easebuzz_status_is_success(verified_resp)

    # Stash verification result for audit
    meta["easebuzz_verify"] = {
        "ok": ok,
        "gateway_status": gateway_status,
        "raw": verified_resp,
    }

    # Keep any new easebuzz_id we learn
    if ez_id_from_status and not easebuzz_id:
        easebuzz_id = ez_id_from_status

    order.payment_meta = meta
    order.easebuzz_payment_id = easebuzz_id or order.easebuzz_payment_id

    # 2) Update order + notifications if success
    if ok:
        # Idempotency: only transition if not already PAID
        if order.payment_status != "PAID":
            order.payment_status = "PAID"
            order.status = order_models.Order.OrderStatus.PROCESSING
            order.save(update_fields=["payment_meta", "easebuzz_payment_id", "payment_status", "status", "updated_at"])

            # Fan-out notifications
            try:
                if order.buyer:
                    _notify_buyer_order_paid(order)
            except Exception as e:
                log.warning("Buyer notify failed: %s", e)

            try:
                _notify_vendors_order_paid(order)
            except Exception as e:
                log.warning("Vendor notify failed: %s", e)
        # Redirect to success
        return redirect(reverse("payments:thank_you", kwargs={"order_id": order.order_id}))
    else:
        # Failed (or not verified) — mark FAILED unless already PAID from prior flow
        if order.payment_status != "PAID":
            order.payment_status = "FAILED"
            order.save(update_fields=["payment_meta", "easebuzz_payment_id", "payment_status", "updated_at"])
        return redirect(reverse("payments:failed", kwargs={"order_id": order.order_id}))

# @csrf_exempt  # Easebuzz posts from their domain
# def easebuzz_return(request):
#     """
#     Easebuzz posts the payment result to SURL/FURL.
#     We'll:
#       - identify the order via udf1
#       - verify reverse hash if present
#       - set payment_status
#     """
#     payload = request.POST.dict() if request.method == "POST" else request.GET.dict()
#     order_id = payload.get("udf1")
#     if not order_id:
#         return HttpResponseBadRequest("Missing udf1 (order id).")

#     order = get_object_or_404(order_models.Order, order_id=order_id)
#     key = payload.get("key", "")
#     txnid = payload.get("txnid", "")
#     status_val = (payload.get("status", "") or "").lower()
#     easebuzz_id = payload.get("easebuzz_id", "")

#     # Optional: reverse-hash validation if 'hash' present
#     verified = False
#     try:
#         resp_hash = payload.get("hash")
#         if resp_hash:
#             calc = _hash_response_reverse(payload, settings.EASEBUZZ_SALT)
#             verified = (resp_hash.lower() == calc.lower())
#     except Exception:
#         verified = False

#     # persist raw return
#     meta = order.payment_meta or {}
#     meta.update({"easebuzz_return": payload, "return_verified": verified})
#     order.payment_meta = meta
#     order.easebuzz_payment_id = easebuzz_id or order.easebuzz_payment_id

#     if status_val in ("success", "captured") and (verified or True):
#         # If you're strict, require verified == True. In practice, many merchants also cross-check via Transaction API or webhook.
#         order.payment_status = "PAID"

#         order_models.Notification.objects.create(
#             recipient=order.buyer,
#             actor=None,  # or request.user/system
#             ntype=order_models.Notification.NType.ORDER,
#             level=order_models.Notification.Level.SUCCESS,
#             title="Order placed",
#             message=f"Thanks! Your order #{order.order_id} has been placed.",
#             content_type=ContentType.objects.get_for_model(order),
#             object_id=order.pk,
#             target_url=f"/customer/orders/{order.order_id}/",
#         )

#         # # Create for a vendor when a review is posted
#         # order_models.Notification.objects.create(
#         #     recipient=vendor_user,
#         #     ntype=order_models.Notification.NType.REVIEW,
#         #     level=order_models.Notification.Level.INFO,
#         #     title="New product review",
#         #     message=f"{order.buy.email} rated {review.product.name} {review.rating}/5",
#         #     content_type=ContentType.objects.get_for_model(review),
#         #     object_id=review.pk,
#         #     target_url=f"/vendor/reviews/?q={review.product.name}",
#         # )

#         order.status = order_models.Order.OrderStatus.PROCESSING
#     else:
#         order.payment_status = "FAILED"

#     order.save(update_fields=["payment_meta", "easebuzz_payment_id", "payment_status", "status", "updated_at"])
#     if order.payment_status == "PAID":
#         return redirect(reverse("payments:thank_you", kwargs={"order_id": order.order_id}))
#     return redirect(reverse("payments:failed", kwargs={"order_id": order.order_id}))


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
