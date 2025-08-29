
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
    order_id = models.CharField(max_length=120, unique=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.order_id

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_variation = models.ForeignKey('store.ProductVariation', on_delete=models.SET_NULL, null=True)
    vendor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='order_items')
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    def __str__(self):
        return f"{self.quantity} of {self.product_variation} in order {self.order.order_id}"

class OrderAddress(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='shipping_address')
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    class Meta:
        verbose_name_plural = 'Order Addresses'

    def __str__(self):
        return f"Shipping Address for Order {self.order.order_id}"
    
