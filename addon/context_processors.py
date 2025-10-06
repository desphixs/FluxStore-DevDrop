from django.conf import settings
from django.core.cache import cache

from . import models
from .cache import GLOBAL_CONTEXT_CACHE_KEY


def _build_context():
    return {
        'site_config': models.SiteConfiguration.get_solo(),
        'theme_settings': models.ThemeSettings.get_solo(),
        'hero_section': models.HeroSection.objects.filter(active=True).first(),
        'social_links': tuple(models.SocialLink.objects.all()),
    }


def global_context(request):
    timeout = getattr(settings, 'ADDON_GLOBAL_CONTEXT_CACHE_TIMEOUT', 300)
    cached = cache.get(GLOBAL_CONTEXT_CACHE_KEY)
    if cached is None:
        cached = _build_context()
        cache.set(GLOBAL_CONTEXT_CACHE_KEY, cached, timeout)

    context = cached.copy()
    context['social_links'] = list(cached.get('social_links', ()))
    return context
