from django.urls import path

from . import views

app_name = 'performances'

urlpatterns = [
    path('', views.performance_root, name='list'),
]
