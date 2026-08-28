from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from .views import healthcheck

urlpatterns = [
    path('healthz/', healthcheck, name='healthcheck'),
    path('admin/', admin.site.urls),
    path('auth/', include('apps.accounts.urls')),
    path('productions/', include('apps.productions.urls')),
    path('locations/', include('apps.locations.urls')),
    path('', RedirectView.as_view(url='/productions/dashboard/'), name='index'),
]
