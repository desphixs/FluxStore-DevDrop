from django.db import models

class SiteConfiguration(models.Model):
    site_name = models.CharField(max_length=255, default="My Website")
    site_header = models.CharField(max_length=255, default="My Website Admin")
    site_brand = models.CharField(max_length=255, default="My Website Brand")

    # Logos / favicon
    site_logo = models.ImageField(upload_to="branding/", null=True, blank=True)
    login_logo = models.ImageField(upload_to="branding/", null=True, blank=True)
    favicon = models.ImageField(upload_to="branding/", null=True, blank=True)

    # Optional extras
    welcome_text = models.CharField(max_length=255, default="Welcome to My Website")
    footer_text = models.CharField(max_length=255, default="© 2025 My Website")

    address = models.CharField(max_length=255, blank=True, null=True, help_text="Company address shown in footer/contact")
    phone = models.CharField(max_length=50, blank=True, null=True, help_text="Primary phone number")
    email = models.EmailField(blank=True, null=True, help_text="Support or sales email")
    working_hours = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. 10:00 - 18:00, Mon - Sat")

    # Only allow one config row
    singleton = models.BooleanField(default=True, editable=False)

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def __str__(self):
        return "Site Configuration"

    def save(self, *args, **kwargs):
        # Enforce singleton: only one config object
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """Safe getter to always return a config instance"""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class SocialLink(models.Model):
    platform_name = models.CharField(max_length=100, help_text='e.g. "Twitter", "LinkedIn"')
    icon_class = models.CharField( max_length=100,  help_text="FontAwesome: fab fa-youtube")
    url = models.CharField(null=True, blank=True)

    def __str__(self):
        return f"{self.platform_name} ({self.url})"
    

class ThemeSettings(models.Model):
    header_bg_color = models.CharField(
        max_length=20, default="#ffffff", help_text="Header background color (hex or CSS color)"
    )
    header_text_color = models.CharField(
        max_length=20, default="#000000", help_text="Header text color (hex or CSS color)"
    )
    
    singleton = models.BooleanField(default=True, editable=False)

    class Meta:
        verbose_name = "Theme Settings"
        verbose_name_plural = "Theme Settings"

    def __str__(self):
        return "Theme Settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
    

class HeroSection(models.Model):
    BACKGROUND_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
    ]

    title = models.CharField(max_length=255, default="Welcome to Our Site")
    subtitle = models.CharField(max_length=500, blank=True, null=True)
    cta_text = models.CharField(max_length=100, default="Get Started")
    cta_link = models.URLField(default="/")

    background_type = models.CharField(
        max_length=10,
        choices=BACKGROUND_CHOICES,
        default="image",
        help_text="Choose whether hero background is an image or video"
    )
    background_image = models.ImageField(upload_to="hero/", blank=True, null=True)
    background_video = models.FileField(
        upload_to="hero/", blank=True, null=True,
        help_text="Optional background video (mp4, webm)"
    )

    overlay_color = models.CharField(
        max_length=20, default="rgba(0,0,0,0.5)",
        help_text="Overlay color on top of background"
    )

    active = models.BooleanField(default=True)

    def __str__(self):
        return f"Hero Section: {self.title}"