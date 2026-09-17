"""
PROJECT CUSTOM CONFIGURATION FILE
"""
from django.conf import settings

class About:
    project_name = "AbuReports"
    project_cachphrase = "Reliable Source, Trusted hands."
    version = "1.0.0"
    
    #   SOCIALS     -   public / group / hanNDLES
    facebook = ""
    whatsapp = "https://wa.link/ebvff1/"
    tweeter = "https://x.com/ABUSUAD01/"
    contact_email = "hello@abureports.ng"
    domain = getattr(settings, "DOMAIN_NAME") or "http://localhost:8000"

    #   CONTACTS - personal / one to one /consultancy
    email = "marketing@gmail.com"
    whatsapp_dm = "https://wa.me.09112"
    mobile = "+234xxxxxxxxxxxx"
    
    
def custom_context_processors(request):
    from BLOG.models import CATEGORY

    theme = "light"
    if request and request.COOKIES.get("abureports-theme") in {"dark", "light"}:
        theme = request.COOKIES.get("abureports-theme")

    return {
        "project_name": About.project_name,
        "version": About.version,
        'project_cachphrase': About.project_cachphrase,
        'facebook': About.facebook,
        'whatsapp': About.whatsapp,
        'tweeter': About.tweeter,
        'contact_email': About.contact_email,
        'domain': About.domain,
        'nav_categories': CATEGORY,
        'partnership_email': About.email,
        'whatsapp_dm': About.whatsapp_dm,
        'mobile': About.mobile,
        'theme_preference': theme,
    }