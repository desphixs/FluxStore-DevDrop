from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from shortuuid.django_fields import ShortUUIDField

class Notification(models.Model):
    class NType(models.TextChoices):
        ORDER = "ORDER", "Order"
        PRODUCT = "PRODUCT", "Product"
        REVIEW = "REVIEW", "Review"
        COUPON = "COUPON", "Coupon"
        PAYOUT = "PAYOUT", "Payout"
        SYSTEM = "SYSTEM", "System"

    class Level(models.TextChoices):
        INFO = "INFO", "Info"
        SUCCESS = "SUCCESS", "Success"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        limit_choices_to={"role": "VENDOR"},
    )
    ntype = models.CharField(max_length=20, choices=NType.choices, default=NType.SYSTEM)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=64, null=True, blank=True)
    context_object = GenericForeignKey("content_type", "object_id")

    is_read = models.BooleanField(default=False)
    meta = models.JSONField(null=True, blank=True)

    uuid = ShortUUIDField(length=12, max_length=50, alphabet="1234567890")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ntype} • {self.title} ({self.recipient_id})"

    def mark_read(self, save=True):
        self.is_read = True
        if save:
            self.save(update_fields=["is_read"])
