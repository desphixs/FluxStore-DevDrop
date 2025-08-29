from . import models

def global_context(request):
    context = {}
    context['site_config'] = models.SiteConfiguration.get_solo()
    context['theme_settings'] = models.ThemeSettings.get_solo()
    context['hero_section'] = models.HeroSection.objects.filter(active=True).first()
    context['social_links'] = models.SocialLink.objects.all()
    
    return context