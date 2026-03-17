from django.urls import path

from apps.locations import views

app_name = 'locations'

urlpatterns = [
    path('api/autocomplete/', views.autocomplete, name='autocomplete'),
]
