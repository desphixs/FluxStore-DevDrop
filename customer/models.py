from django.db import models
from django.conf import settings
from shortuuid.django_fields import ShortUUIDField

class Wishlist(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist"
    )
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Wishlist({self.user_id})"

    @classmethod
    def for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj


class WishlistItem(models.Model):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("store.Product", on_delete=models.CASCADE, related_name="wishlisted_items")
    product_variation = models.ForeignKey(
        "store.ProductVariation", on_delete=models.SET_NULL, null=True, blank=True, related_name="wishlisted_items"
    )
    added_at = models.DateTimeField(auto_now_add=True)
    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")

    class Meta:
        unique_together = (("wishlist", "product", "product_variation"),)
        ordering = ["-added_at"]

    def __str__(self) -> str:
        pv = f" / {self.product_variation_id}" if self.product_variation_id else ""
        return f"WL#{self.wishlist_id}: {self.product_id}{pv}"

    @property
    def display_name(self):
        if self.product_variation_id:
            vs = ", ".join(v.value for v in self.product_variation.variations.all())
            return f"{self.product.name} ({vs})"
        return self.product.name
