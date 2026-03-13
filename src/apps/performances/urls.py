from django.urls import path

from . import views

app_name = 'performances'

urlpatterns = [
    path('', views.performance_root, name='list'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path(
        'dashboard/vehicle-assignments/',
        views.production_vehicle_assignment_dashboard,
        name='production_vehicle_assignments',
    ),
    path(
        'dashboard/vehicle-requests/<int:pk>/edit/',
        views.production_vehicle_assignment_edit,
        name='production_vehicle_assignment_edit',
    ),
]
