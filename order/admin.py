from django.contrib import admin
from . import models
from django import forms
from django.db.models import Count, Q
from django.utils.html import format_html
from django.utils import timezone

class CartItemInline(admin.StackedInline):
    model = models.CartItem
    extra = 1
    readonly_fields = ("added_at",)
    show_change_link = True


@admin.register(models.Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "created_at", "updated_at")
    search_fields = ("user__email", "session_key")
    list_filter = ("created_at",)
    readonly_fields = ("created_at", "updated_at", "uuid")
    inlines = [CartItemInline]
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(models.CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "product_variation", "quantity", "added_at")
    search_fields = ("cart__user__email", "product_variation__product__name")
    list_filter = ("added_at",)
    readonly_fields = ("added_at", "uuid")
    ordering = ("-added_at",)


class OrderItemInline(admin.StackedInline):
    model = models.OrderItem
    extra = 1
    show_change_link = True





@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_id", "buyer", "total_amount", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("order_id", "buyer__email")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [OrderItemInline]
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(models.OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_variation", "vendor", "quantity", "price")
    list_filter = ("vendor", "order")
    search_fields = ("order__order_id", "vendor__email", "product_variation__product__name")
    readonly_fields = ("uuid",)
    ordering = ("order",)



class CouponForm(forms.ModelForm):
    class Meta:
        model = models.Coupon
        fields = [
            "code", "vendor", "title", "description",
            "discount_type", "percent_off", "amount_off", "max_discount_amount",
            "min_order_amount", "starts_at", "ends_at",
            "usage_limit_total", "usage_limit_per_user",
            "is_active",
        ]

    def clean(self):
        cleaned = super().clean()
        dtype = cleaned.get("discount_type")
        pct   = cleaned.get("percent_off")
        amt   = cleaned.get("amount_off")
        cap   = cleaned.get("max_discount_amount")
        min_order = cleaned.get("min_order_amount") or 0
        starts = cleaned.get("starts_at")
        ends   = cleaned.get("ends_at")

        
        if dtype == models.Coupon.DiscountType.PERCENT:
            if not pct or pct <= 0:
                self.add_error("percent_off", "Percent off must be > 0 for percent coupons.")
            
            if cap is not None and cap < 0:
                self.add_error("max_discount_amount", "Max discount cap must be ≥ 0.")
            
            if amt:
                self.add_error("amount_off", "For percent coupons, leave amount_off empty.")
        elif dtype == models.Coupon.DiscountType.FIXED:
            if not amt or amt <= 0:
                self.add_error("amount_off", "Fixed amount must be > 0 for fixed coupons.")
            
            if cap:
                self.add_error("max_discount_amount", "Max discount cap is only for percent coupons.")
            
            if pct:
                self.add_error("percent_off", "For fixed coupons, leave percent_off empty.")
        else:
            self.add_error("discount_type", "Choose a valid discount type.")

        if min_order < 0:
            self.add_error("min_order_amount", "Minimum order must be ≥ 0.")

        if starts and ends and starts >= ends:
            self.add_error("ends_at", "End time must be after start time.")

        return cleaned


# -------------------------
# Inlines (read-only, stacked)
# -------------------------

class CouponRedemptionInline(admin.StackedInline):
    model = models.CouponRedemption
    extra = 0
    can_delete = False
    readonly_fields = (
        "order_link", "user_link", "vendor_link",
        "discount_amount", "applied_at",
    )
    fields = readonly_fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("order", "user", "vendor", "coupon")

    @admin.display(description="Order")
    def order_link(self, obj):
        if not obj.order_id:
            return "-"
        return format_html('<a href="/admin/order/order/{}/change/">{}</a>', obj.order_id, obj.order.order_id)

    @admin.display(description="User")
    def user_link(self, obj):
        if not obj.user_id:
            return "-"
        
        return format_html('<a href="/admin/auth/user/{}/change/">{}</a>', obj.user_id, obj.user)

    @admin.display(description="Vendor")
    def vendor_link(self, obj):
        if not obj.vendor_id:
            return "-"
        
        return format_html('<a href="/admin/auth/user/{}/change/">{}</a>', obj.vendor_id, obj.vendor)


class OrderItemDiscountInline(admin.StackedInline):
    """
    Shows item-level allocations for this coupon.
    """
    model = models.OrderItemDiscount
    extra = 0
    can_delete = False
    readonly_fields = (
        "order_item_link", "vendor_link", "amount", "created_at",
    )
    fields = readonly_fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("order_item__order", "order_item__product_variation__product", "vendor", "coupon")

    @admin.display(description="Order item")
    def order_item_link(self, obj):
        oi = obj.order_item
        if not oi.id != getattr(oi, "id", None):
            return "-"
        order_admin_url = f"/admin/order/order/{oi.order_id}/change/" if oi.order_id else "#"
        product_name = getattr(oi.product_variation.product, "name", "Item")
        return format_html(
            '{} ×{} — <a href="{}">Order {}</a>',
            product_name, oi.quantity, order_admin_url, oi.order.order_id
        )

    @admin.display(description="Vendor")
    def vendor_link(self, obj):
        if not obj.vendor_id:
            return "-"
        return format_html('<a href="/admin/auth/user/{}/change/">{}</a>', obj.vendor_id, obj.vendor)


# -------------------------
# Coupon admin
# -------------------------

@admin.register(models.Coupon)
class CouponAdmin(admin.ModelAdmin):
    form = CouponForm
    inlines = [CouponRedemptionInline, OrderItemDiscountInline]

    list_display = (
        "code", "vendor", "discount_display", "min_order_amount",
        "window_display", "usage_display", "is_active", "is_live_badge",
        "created_at",
    )
    list_filter = (
        "is_active", "discount_type",
        ("starts_at", admin.DateFieldListFilter),
        ("ends_at", admin.DateFieldListFilter),
    )
    search_fields = ("code", "vendor__email", "vendor__username", "title")
    autocomplete_fields = ("vendor",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("vendor",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Identification", {
            "fields": ("code", "vendor", "is_active")
        }),
        ("Details", {
            "fields": ("title", "description")
        }),
        ("Discount", {
            "fields": ("discount_type", "percent_off", "amount_off", "max_discount_amount", "min_order_amount")
        }),
        ("Validity Window", {
            "fields": ("starts_at", "ends_at")
        }),
        ("Usage Limits", {
            "fields": ("usage_limit_total", "usage_limit_per_user")
        }),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at")
        }),
    )

    actions = ["activate_coupons", "deactivate_coupons"]

    

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("vendor").annotate(
            usage_count=Count("redemptions", distinct=True),
            active_redemptions=Count(
                "redemptions",
                filter=Q(redemptions__coupon_id__isnull=False),
                distinct=True
            ),
        )
        if request.user.is_superuser:
            return qs
        
        return qs.filter(vendor=request.user)

    def has_change_permission(self, request, obj=None):
        base = super().has_change_permission(request, obj)
        if not base:
            return False
        if obj and not request.user.is_superuser and obj.vendor_id != request.user.id:
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        if obj and not request.user.is_superuser and obj.vendor_id != request.user.id:
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        
        if not request.user.is_superuser:
            obj.vendor = request.user
        super().save_model(request, obj, form, change)

    

    @admin.display(description="Discount")
    def discount_display(self, obj: models.Coupon):
        if obj.discount_type == models.Coupon.DiscountType.PERCENT:
            base = f"{obj.percent_off}%"
            if obj.max_discount_amount:
                base += f" (cap ₹{obj.max_discount_amount})"
            return base
        return f"₹{obj.amount_off}"

    @admin.display(description="Validity")
    def window_display(self, obj: models.Coupon):
        if obj.starts_at and obj.ends_at:
            return f"{obj.starts_at:%Y-%m-%d %H:%M} → {obj.ends_at:%Y-%m-%d %H:%M}"
        if obj.starts_at and not obj.ends_at:
            return f"From {obj.starts_at:%Y-%m-%d %H:%M}"
        if obj.ends_at and not obj.starts_at:
            return f"Until {obj.ends_at:%Y-%m-%d %H:%M}"
        return "—"

    @admin.display(description="Usage")
    def usage_display(self, obj: models.Coupon):
        total = getattr(obj, "usage_count", None)
        if total is None:
            total = obj.redemptions.count()
        if obj.usage_limit_total:
            return f"{total}/{obj.usage_limit_total}"
        return str(total)

    @admin.display(boolean=True, description="Live")
    def is_live_badge(self, obj: models.Coupon):
        return obj.is_live()

    

    @admin.action(description="Activate selected coupons")
    def activate_coupons(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} coupon(s).")

    @admin.action(description="Deactivate selected coupons")
    def deactivate_coupons(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} coupon(s).")


# -------------------------
# Optional: read-only registrations for audit tables
# -------------------------

@admin.register(models.CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "order", "user", "vendor", "discount_amount", "applied_at")
    list_filter = (("applied_at", admin.DateFieldListFilter), "vendor")
    search_fields = ("coupon__code", "order__order_id", "user__email", "user__username", "vendor__email")
    autocomplete_fields = ("coupon", "order", "user", "vendor")
    date_hierarchy = "applied_at"
    readonly_fields = ("coupon", "order", "user", "vendor", "discount_amount", "applied_at")

    def has_add_permission(self, request):
        return False

@admin.register(models.OrderItemDiscount)
class OrderItemDiscountAdmin(admin.ModelAdmin):
    list_display = ("order_item", "coupon", "vendor", "amount", "created_at")
    list_filter = (("created_at", admin.DateFieldListFilter), "vendor")
    search_fields = ("order_item__order__order_id", "coupon__code", "vendor__email", "vendor__username")
    autocomplete_fields = ("order_item", "coupon", "vendor")
    date_hierarchy = "created_at"
    readonly_fields = ("order_item", "coupon", "vendor", "amount", "created_at")

    def has_add_permission(self, request):
        return False
    


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient", "ntype", "level", "title", "is_read", "created_at")
    list_filter = ("ntype", "level", "is_read", "created_at")
    search_fields = ("title", "message", "recipient__email", "recipient__username")