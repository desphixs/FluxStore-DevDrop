from django.contrib import admin
from . import models


class CartItemInline(admin.StackedInline):
    model = models.CartItem
    extra = 1
    fields = ("product_variation", "quantity", "added_at")
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
    fields = ("product_variation", "vendor", "quantity", "price")
    show_change_link = True


class OrderAddressInline(admin.StackedInline):
    model = models.OrderAddress
    extra = 0
    fields = ("street_address", "city", "state", "postal_code", "country")
    show_change_link = True


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_id", "buyer", "total_amount", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("order_id", "buyer__email")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [OrderItemInline, OrderAddressInline]
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(models.OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_variation", "vendor", "quantity", "price")
    list_filter = ("vendor", "order")
    search_fields = ("order__order_id", "vendor__email", "product_variation__product__name")
    readonly_fields = ("uuid",)
    ordering = ("order",)


@admin.register(models.OrderAddress)
class OrderAddressAdmin(admin.ModelAdmin):
    list_display = ("order", "street_address", "city", "state", "postal_code", "country")
    search_fields = ("order__order_id", "city", "state", "postal_code", "country")
    readonly_fields = ("uuid",)
