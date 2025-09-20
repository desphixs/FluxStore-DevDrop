from django.contrib import admin
from .models import Wishlist, WishlistItem
from django.utils.html import format_html


class WishlistItemInline(admin.StackedInline):
    model = WishlistItem
    extra = 1  # Number of empty forms to display
    fields = ['product', 'added_at', 'uuid']
    readonly_fields = [ 'added_at', 'uuid']
    show_change_link = True  # Add a link to change the item directly from the Wishlist

    def get_extra(self, request, obj=None, **kwargs):
        """Limit extra fields based on user role, for example."""
        return 0 if obj and obj.items.count() > 10 else super().get_extra(request, obj, **kwargs)


class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'uuid', 'created_at', 'updated_at', 'get_item_count')
    search_fields = ['user__username', 'user__email', 'uuid']
    list_filter = ['created_at', 'updated_at']
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    inlines = [WishlistItemInline]

    def get_item_count(self, obj):
        return obj.items.count()
    get_item_count.short_description = "Number of Items"

    def get_queryset(self, request):
        """Custom queryset to filter based on user or permissions."""
        queryset = super().get_queryset(request)
        return queryset.prefetch_related('items')


class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ('wishlist', 'product', 'added_at', 'uuid', 'display_name')
    search_fields = ['product__name', 'uuid']
    list_filter = ['added_at', 'wishlist__user']
    readonly_fields = ('uuid', 'added_at', 'wishlist', 'product')
    ordering = ['-added_at']
    
    def display_name(self, obj):
        return obj.display_name
    display_name.admin_order_field = 'product__name'  # Allows ordering by product name
    display_name.short_description = "Product Name"

    def get_queryset(self, request):
        """Custom queryset to filter based on user or permissions."""
        queryset = super().get_queryset(request)
        return queryset.select_related('wishlist', 'product')


admin.site.register(Wishlist, WishlistAdmin)
admin.site.register(WishlistItem, WishlistItemAdmin)
