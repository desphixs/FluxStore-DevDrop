
from django.db import models
from django.conf import settings
from shortuuid.django_fields import ShortUUIDField

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

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product_variation = models.ForeignKey('store.ProductVariation', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    class Meta:
        unique_together = ('cart', 'product_variation')

    def __str__(self):
        return f"{self.quantity} of {self.product_variation}"

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
    
