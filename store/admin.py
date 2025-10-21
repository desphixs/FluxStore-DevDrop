from django.contrib import admin
from . import models
from django.utils.html import format_html

class ChildCategoryInline(admin.TabularInline):
    model = models.Category
    fk_name = "parent"
    extra = 1
    verbose_name = "Subcategory"
    verbose_name_plural = "Subcategories"


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active",  "trending", "featured", "image_preview")
    list_editable = ["featured", "trending", "is_active"]
    list_filter = ("is_active", "parent")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)
    inlines = [ChildCategoryInline]

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="60" height="60" style="object-fit:cover; border-radius:6px;" />', obj.image.url)
        else:
            return format_html(
                '<a href="{}">Upload Image</a>',
                f"/admin/store/category/{obj.id}/change/"
            )
    image_preview.short_description = "Image"


class ProductImageInline(admin.StackedInline):
    model = models.ProductImage
    extra = 1
    fields = ("image", "image_preview", "is_primary")  
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj and obj.image:  
            return format_html('<img src="{}" width="100" style="border-radius: 8px;" />', obj.image.url)
        return "No image"

    image_preview.short_description = "Preview"


class ProductVariationInline(admin.StackedInline):
    model = models.ProductVariation
    extra = 1
    show_change_link = True
    filter_horizontal = ("variations",)


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "vendor", "category", "status", "is_featured", "created_at")
    list_filter = ("status", "is_featured", "created_at", "category")
    search_fields = ("name", "slug", "vendor__email", "category__name")
    prepopulated_fields = {"slug": ("name",)}
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [ProductVariationInline, ProductImageInline]
    readonly_fields = ("created_at", "updated_at", "uuid")


@admin.register(models.VariationCategory)
class VariationCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "vendor")
    search_fields = ("name", "vendor__email")
    ordering = ("name",)


@admin.register(models.VariationValue)
class VariationValueAdmin(admin.ModelAdmin):
    list_display = ("category", "value")
    search_fields = ("category__name", "value")
    list_filter = ("category",)


class ProductImageInlineForVariation(admin.StackedInline):
    model = models.ProductImage
    extra = 1
    fields = ("image", "is_primary")
    show_change_link = True


@admin.register(models.ProductVariation)
class ProductVariationAdmin(admin.ModelAdmin):
    list_display = ("product", "sale_price", "stock_quantity", "label", "sku", "is_active")
    list_filter = ("is_active", "product")
    search_fields = ("product__name", "sku")
    ordering = ("sale_price",)
    filter_horizontal = ("variations",)  
    inlines = [ProductImageInlineForVariation]
    readonly_fields = ("uuid",)


@admin.register(models.ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "is_primary")
    list_filter = ("is_primary",)


@admin.register(models.ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("product__name", "user__email", "comment")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "uuid")
