from django.contrib import admin
from userauths import models as userauths_models


class AddressInline(admin.StackedInline):
    model = userauths_models.Address
    extra = 1
    fields = ("street_address", "city", "state", "country", "postal_code", "is_default")
    show_change_link = True


@admin.register(userauths_models.UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    inlines = [AddressInline]
    list_display = ("user", "phone_number", "created_at")
    search_fields = ("user__email", "phone_number")
    list_filter = ("created_at",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)



@admin.register(userauths_models.VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ("business_name", "user", "contact_email", "is_verified", "created_at")
    list_filter = ("is_verified", "created_at")
    search_fields = ("business_name", "contact_email", "user__email")
    list_editable = ("is_verified",)
    date_hierarchy = "created_at"
    ordering = ("business_name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(userauths_models.User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "username", "role", "is_staff", "is_superuser", "last_login", "date_joined")
    list_filter = ("role", "is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email", "username")
    ordering = ("email",)
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        ("Account Info", {"fields": ("email", "username", "password")}),
        ("Permissions", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )


admin.site.register(userauths_models.Address)
