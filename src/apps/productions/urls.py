from django.urls import path

from . import views

app_name = 'productions'

urlpatterns = [
    path('', views.ProductionListView.as_view(), name='list'),
    path('create/', views.ProductionCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ProductionDetailView.as_view(), name='detail'),
    path('<int:pk>/setup/', views.ProductionSetupView.as_view(), name='setup'),
    path('templates/api/', views.ProductionTemplateListView.as_view(), name='template_api'),
    path('process-day/<int:pk>/edit/', views.ProcessDayEditView.as_view(), name='process_day_edit'),
    path(
        'process-day/<int:day_pk>/staff-request/',
        views.StaffRequestEditView.as_view(),
        name='staff_request_edit',
    ),
    path(
        'process-day/<int:day_pk>/staff-requests/',
        views.StaffRequestBulkEditView.as_view(),
        name='staff_requests_bulk_edit',
    ),
    path(
        'process-day/<int:day_pk>/staff-requests/previous/',
        views.PreviousStaffRequestView.as_view(),
        name='staff_requests_previous',
    ),
    path(
        'process-day/<int:day_pk>/vehicle-requests/',
        views.VehicleRequestBulkEditView.as_view(),
        name='vehicle_requests_bulk_edit',
    ),
    path(
        'process-day/<int:day_pk>/vehicle-requests/previous/',
        views.PreviousVehicleRequestView.as_view(),
        name='vehicle_requests_previous',
    ),
    path(
        '<int:production_id>/process-day/add/',
        views.ProcessDayCreateView.as_view(),
        name='process_day_add',
    ),
    path(
        '<int:pk>/vehicle-assignments/',
        views.VehicleAssignmentListView.as_view(),
        name='vehicle_assignment_list',
    ),
    path(
        'vehicle-request/<int:pk>/assignment/',
        views.VehicleAssignmentEditView.as_view(),
        name='vehicle_assignment_edit',
    ),
    path(
        '<int:production_pk>/members/add/',
        views.ProductionMemberBulkAddView.as_view(),
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
]
