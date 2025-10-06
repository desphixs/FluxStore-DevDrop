from django.db.models.signals import post_delete, post_save

from .cache import clear_addon_context_cache
from .models import HeroSection, SiteConfiguration, SocialLink, ThemeSettings


def _invalidate_addon_cache(**kwargs):
    clear_addon_context_cache()


for model in (SiteConfiguration, ThemeSettings, HeroSection, SocialLink):
    post_save.connect(
        _invalidate_addon_cache,
        sender=model,
        dispatch_uid=f"addon_cache_post_save_{model.__name__}",
    )
    post_delete.connect(
        _invalidate_addon_cache,
        sender=model,
        dispatch_uid=f"addon_cache_post_delete_{model.__name__}",
    )
