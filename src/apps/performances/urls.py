from django.urls import path

from . import views

app_name = 'performances'

urlpatterns = [
    path('', views.performance_list, name='list'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('create/', views.performance_create, name='create'),
    path('<int:pk>/', views.performance_detail, name='detail'),
    path('<int:pk>/delete/', views.performance_delete, name='delete'),
    path('<int:pk>/apply-template/', views.apply_template, name='apply_template'),
    path('<int:pk>/phases/add/', views.phase_create, name='phase_add'),
    path('phases/<int:pk>/delete/', views.phase_delete, name='phase_delete'),
    path('phases/<int:pk>/update/', views.phase_update, name='phase_update'),
    path('<int:pk>/phases/reorder/', views.phase_reorder, name='phase_reorder'),
    path('<int:pk>/vehicles/add/', views.vehicle_operation_create, name='vehicle_operation_add'),
    path('vehicles/<int:pk>/delete/', views.vehicle_operation_delete, name='vehicle_operation_delete'),
    path('<int:pk>/report/performance/', views.performance_report_pdf, name='report_performance'),
    path('<int:pk>/report/financial/', views.financial_report_pdf, name='report_financial'),
]
