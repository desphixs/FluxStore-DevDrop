from django.contrib import admin
from . import models

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