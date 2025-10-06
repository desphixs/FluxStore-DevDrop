from django.core.cache import cache

GLOBAL_CONTEXT_CACHE_KEY = "addon:global_context"


def clear_addon_context_cache():
    cache.delete(GLOBAL_CONTEXT_CACHE_KEY)
