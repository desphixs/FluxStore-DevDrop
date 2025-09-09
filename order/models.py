
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum

from shortuuid.django_fields import ShortUUIDField
from decimal import Decimal


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart', null=True, blank=True)
    session_key = models.CharField(max_length=40, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    def __str__(self):
        if self.user:
            return f"Cart for {self.user.email}"
        return f"Guest Cart (Session: {self.session_key})"
    
    @classmethod
    def get_for_request(cls, request):
        """
        Return the Cart instance for the request. Create one if missing.
        - If user is authenticated: cart is tied to user (OneToOne).
        - If guest: cart is tied to request.session.session_key.
        """
        if request.user.is_authenticated:
            cart, _ = cls.objects.get_or_create(user=request.user)
            return cart

        # ensure session exists
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        cart, _ = cls.objects.get_or_create(session_key=session_key, user=None)
        return cart

    @transaction.atomic
    def add_item(self, product_variation, quantity=1, override_quantity=False):
        """
        Add a ProductVariation to this cart.
        - If same variation exists, increment quantity (unless override_quantity True).
        - Validate stock (does NOT decrement real stock; only checks availability).
        Returns: (cart_item, created_bool)
        Raises ValidationError on bad quantity / out of stock
        """
        if quantity < 1:
            raise ValidationError("Quantity must be >= 1")

        # verify variation belongs to a published product and is active
        if not product_variation.is_active:
            raise ValidationError("Variant is not active")

        # check stock
        if product_variation.stock_quantity < quantity:
            raise ValidationError("Insufficient stock for requested quantity")

        cart_item, created = self.items.select_for_update().get_or_create(
            product_variation=product_variation,
            defaults={"quantity": quantity}
        )

        if not created:
            if override_quantity:
                new_qty = quantity
            else:
                new_qty = cart_item.quantity + quantity

            if product_variation.stock_quantity < new_qty:
                raise ValidationError("Insufficient stock to update quantity")

            cart_item.quantity = new_qty
            cart_item.save()

        return cart_item, created

    
    def total_amount(self):
        # returns Decimal
        agg = self.items.aggregate(total=Sum(F('quantity') * F('price')))
        return agg['total'] or 0

    @transaction.atomic
    def merge_from(self, other_cart):
        """
        Merge items from other_cart into this cart by "re-parenting" them.
        This is more efficient and robust than creating new items.
        """
        # Loop through all items in the guest cart
        for item_to_merge in other_cart.items.all():
            # Check if the user's cart ALREADY has this specific product variation
            existing_item, created = self.items.get_or_create(
                product_variation=item_to_merge.product_variation,
                defaults={'quantity': item_to_merge.quantity}
            )

            if not created:
                # If the item already existed in the user's cart, just add the quantity
                existing_item.quantity += item_to_merge.quantity
                existing_item.save()
                # The original item from the guest cart is now redundant, so we can delete it
                item_to_merge.delete()
        
        # After merging quantities and handling duplicates, delete the now-empty guest cart.
        # This will also delete any remaining items in it due to the CASCADE relationship.
        other_cart.delete()


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product_variation = models.ForeignKey('store.ProductVariation', on_delete=models.CASCADE)
    variation_values = models.ManyToManyField("store.VariationValue", blank=True, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    added_at = models.DateTimeField(auto_now_add=True)
    selected_variations_json = models.JSONField(null=True, blank=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    class Meta:
        unique_together = ('cart', 'product_variation')

    def __str__(self):
        return f"{self.quantity} of {self.product_variation}"
    
    def subtotal(self):
        return (self.price or Decimal('0.00')) * self.quantity
class Order(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        SHIPPED = "SHIPPED", "Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELED = "CANCELED", "Canceled"
        REFUNDED = "REFUNDED", "Refunded"

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='orders')
    address = models.ForeignKey("userauths.Address", on_delete=models.SET_NULL, null=True, blank=True)

    order_id = models.CharField(max_length=120, unique=True, blank=True)  # public 8-digit for URLs
    currency = models.CharField(max_length=10, default="INR")

    # Existing (gross items total)
    item_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # NEW: discount + net totals (don’t break item_total / total_amount usage)
    item_discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    item_total_net      = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    shipping_fee   = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    amount_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)  # item_total_net + shipping
    total_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)  # mirrors amount_payable

    # Shipping selection (unchanged)
    courier_code = models.CharField(max_length=120, blank=True)
    courier_name = models.CharField(max_length=200, blank=True)
    courier_service_name = models.CharField(max_length=200, blank=True)
    courier_mode = models.CharField(max_length=20, blank=True)
    rate_currency = models.CharField(max_length=10, default="INR")
    chargeable_weight_kg = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    volumetric_weight_kg = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    etd_text = models.CharField(max_length=120, blank=True)
    etd_days = models.PositiveIntegerField(null=True, blank=True)
    shipping_rate_raw = models.JSONField(null=True, blank=True)
    shipping_rate_fetched_at = models.DateTimeField(null=True, blank=True)

    # Shiprocket integration bits (optional/back-compat)
    selected_courier_code = models.CharField(max_length=120, blank=True)
    shiprocket_rate_id = models.CharField(max_length=120, blank=True)
    shiprocket_order_id = models.CharField(max_length=120, blank=True)
    shiprocket_meta = models.JSONField(null=True, blank=True)

    payment_provider = models.CharField(max_length=50, blank=True)
    payment_status = models.CharField(max_length=20, default="UNPAID")
    shipping_address_snapshot = models.JSONField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.order_id

    def set_order_id_if_missing(self):
        if self.order_id:
            return
        import secrets
        while True:
            candidate = str(secrets.randbelow(10**8)).zfill(8)
            if not Order.objects.filter(order_id=candidate).exists():
                self.order_id = candidate
                break

    # --- totals helpers (do NOT rename existing fields) ---
    def recompute_item_totals_from_items(self):
        """
        Recompute:
          - item_total          (gross)
          - item_discount_total
          - item_total_net
        from OrderItems (uses existing .price and new .line_discount_total).
        """
        from decimal import Decimal
        gross = Decimal('0.00')
        disc  = Decimal('0.00')
        for it in self.items.all():
            gross += (it.price or 0) * it.quantity
            disc  += (it.line_discount_total or 0)
        self.item_total = gross
        self.item_discount_total = disc
        self.item_total_net = max(gross - disc, Decimal('0.00'))

    def recalc_total(self):
        """
        Final payable = item_total_net + shipping_fee.
        Mirror to total_amount for back-compat.
        """
        self.amount_payable = (self.item_total_net or 0) + (self.shipping_fee or 0)
        self.total_amount   = self.amount_payable

    def apply_shipping_selection(self, rate_obj: dict, fallback_currency="INR", chargeable_weight=None, volumetric_weight=None):
        # unchanged from your version (kept here)
        if not isinstance(rate_obj, dict):
            return
        name = rate_obj.get('courier_name') or rate_obj.get('name') or rate_obj.get('courier') or ""
        code = (rate_obj.get('courier_code') or rate_obj.get('id') or rate_obj.get('service_id')
                or rate_obj.get('courier_id') or rate_obj.get('code') or "")
        rate = (rate_obj.get('rate') or rate_obj.get('shipping_charges') or rate_obj.get('cost')
                or rate_obj.get('freight_charge') or rate_obj.get('charge') or rate_obj.get('charges') or 0)
        etd = rate_obj.get('etd') or rate_obj.get('estimated_delivery_days') or rate_obj.get('delivery_time') or rate_obj.get('edd')

        self.courier_code = str(code)
        self.selected_courier_code = str(code)
        self.courier_name = str(name or "")
        self.courier_service_name = str(rate_obj.get('service') or rate_obj.get('service_name') or "")
        self.courier_mode = "surface" if "surface" in (name or "").lower() else ("air" if "air" in (name or "").lower() else "")
        from decimal import Decimal
        self.shipping_fee = Decimal(str(rate or 0))
        self.rate_currency = rate_obj.get('currency') or fallback_currency
        self.etd_text = str(etd or "")
        try:
            self.etd_days = int(rate_obj.get('api_edd') or rate_obj.get('estimated_delivery_days') or 0) or None
        except Exception:
            self.etd_days = None

        if chargeable_weight is not None:
            from decimal import Decimal
            self.chargeable_weight_kg = Decimal(str(chargeable_weight))
        if volumetric_weight is not None:
            from decimal import Decimal
            self.volumetric_weight_kg = Decimal(str(volumetric_weight))

        from django.utils import timezone
        self.shipping_rate_fetched_at = timezone.now()
        self.shipping_rate_raw = rate_obj

    # order/models.py (inside Order)
    def has_any_coupon_applied(self) -> bool:
        return self.coupon_redemptions.exists()

    def has_coupon_for_vendor(self, vendor_id) -> bool:
        return self.coupon_redemptions.filter(vendor_id=vendor_id).exists()

    def applied_coupons_summary(self):
        """
        Returns a list of dicts with all coupons applied to this order.
        """
        return list(
            self.coupon_redemptions
                .select_related("coupon", "vendor")
                .values(
                    "coupon__code", "coupon__discount_type", "vendor_id",
                    "discount_amount", "applied_at"
                )
        )


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_variation = models.ForeignKey('store.ProductVariation', on_delete=models.SET_NULL, null=True)
    variation_values = models.ManyToManyField("store.VariationValue", blank=True, related_name="variations")
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='order_items')

    quantity = models.PositiveIntegerField(default=1)
    price    = models.DecimalField(max_digits=10, decimal_places=2)  # KEEPING your existing field

    # NEW
    line_discount_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    line_subtotal_net   = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    def __str__(self):
        return f"{self.quantity} of {self.product_variation} in order {self.order.order_id}"

    @property
    def subtotal(self):
        from decimal import Decimal
        return (self.price or Decimal('0.00')) * self.quantity

    def recompute_line_totals(self):
        from decimal import Decimal
        gross = self.subtotal
        disc  = self.line_discount_total or Decimal('0.00')
        self.line_subtotal_net = max(gross - disc, Decimal('0.00'))


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "PERCENT", "Percent Off"
        FIXED   = "FIXED", "Fixed Amount Off"

    code = models.CharField(max_length=40, unique=True, db_index=True)
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupons")

    title = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)

    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    percent_off = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    amount_off  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at   = models.DateTimeField(null=True, blank=True)

    usage_limit_total = models.PositiveIntegerField(null=True, blank=True)
    usage_limit_per_user = models.PositiveIntegerField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} ({self.vendor_id})"

    def is_live(self):
        from django.utils import timezone
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    order  = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="coupon_redemptions")
    user   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_redemptions")
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_redemptions_as_vendor")

    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("coupon", "order", "vendor")


class OrderItemDiscount(models.Model):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="discount_allocations")
    coupon     = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    vendor     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="order_item_discounts_as_vendor")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
