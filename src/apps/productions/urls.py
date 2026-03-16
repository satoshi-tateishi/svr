from django.urls import path

from . import views

app_name = 'productions'

urlpatterns = [
    path('', views.ProductionListView.as_view(), name='list'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path(
        'dashboard/vehicle-assignments/',
        views.production_vehicle_assignment_dashboard,
        name='production_vehicle_assignments',
    ),
    path(
        'dashboard/vehicle-assignments/<str:date_str>/edit/',
        views.production_vehicle_assignment_day_edit,
        name='production_vehicle_assignments_day_edit',
    ),
    path(
        'dashboard/vehicle-assignments/<int:pk>/assign/',
        views.production_vehicle_assignment_assign,
        name='production_vehicle_assignment_assign',
    ),
    path(
        'dashboard/vehicle-assignments/<int:pk>/assign/cancel/',
        views.production_vehicle_assignment_assign_cancel,
        name='production_vehicle_assignment_assign_cancel',
    ),
    path(
        'dashboard/vehicle-assignments/<int:pk>/dnd-assign/',
        views.production_vehicle_assignment_dnd_assign,
        name='production_vehicle_assignment_dnd_assign',
    ),
    path(
        'dashboard/vehicle-assignments/<int:pk>/dnd-remove/',
        views.production_vehicle_assignment_dnd_remove,
        name='production_vehicle_assignment_dnd_remove',
    ),
    path('create/', views.ProductionCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', views.ProductionEditView.as_view(), name='edit'),
    path('<int:pk>/', views.ProductionDetailView.as_view(), name='detail'),
    path(
        '<int:pk>/processes-partial/',
        views.ProductionProcessesPartialView.as_view(),
        name='processes_partial',
    ),
    path(
        '<int:pk>/vehicle-assignments/',
        views.VehicleAssignmentListView.as_view(),
        name='vehicle_assignment_list',
    ),
    path(
        'vehicle-assignments/<int:pk>/edit/',
        views.VehicleAssignmentEditView.as_view(),
        name='vehicle_assignment_edit',
    ),
    path(
        '<int:production_pk>/members/add/',
        views.ProductionMemberEditView.as_view(),
        name='member_add',
    ),
    path(
        'members/<int:pk>/edit/',
        views.ProductionMemberEditView.as_view(),
        name='member_edit',
    ),
    path(
        'members/<int:pk>/delete/',
        views.ProductionMemberDeleteView.as_view(),
        name='member_delete',
    ),
    path(
        'block/<int:process_pk>/edit/',
        views.ProcessBlockEditView.as_view(),
        name='block_edit',
    ),
]
