from django.conf import settings

def portal_context(request):
    """
    Template context processor to provide portal_url to all templates.
    """
    return {
        'portal_url': getattr(settings, 'PORTAL_URL', 'http://localhost/'),
    }
