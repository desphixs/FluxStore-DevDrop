from django.contrib import admin
from . import models
from django_summernote.admin import SummernoteModelAdmin

@admin.register(models.SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not models.SiteConfiguration.objects.exists()
    

@admin.register(models.ThemeSettings)
class ThemeSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not models.ThemeSettings.objects.exists()

@admin.register(models.HeroSection)
class HeroSectionAdmin(admin.ModelAdmin):
    list_display = ("title", "active")
    list_editable = ("active",)

@admin.register(models.SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ("platform_name", "icon_class", "url")
    list_editable = ("icon_class", "url")


@admin.register(models.Page)
class PageAdmin(SummernoteModelAdmin):
    summernote_fields = ("content",)

    list_display = ("key", "title", "is_published", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("title", "content", "meta_title", "meta_description")
    list_editable = ("is_published",)
    readonly_fields = ("created_at", "updated_at")

class FAQInline(admin.StackedInline):
    pass


@admin.register(models.FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "is_active", "sort_order", "updated_at")
    list_filter = ("is_active", )
    search_fields = ("question", "answer")
    list_editable = ("is_active", "sort_order")


@admin.register(models.ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("email", "subject", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "email", "subject", "message")
