from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.accounts.urls')),
    path('performances/', include('apps.performances.urls')),
    path('', RedirectView.as_view(url='/performances/'), name='index'),
]
