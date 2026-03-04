from django.urls import path

from . import views

app_name = 'performances'

urlpatterns = [
    path('', views.performance_list, name='list'),
    path('create/', views.performance_create, name='create'),
    path('<int:pk>/', views.performance_detail, name='detail'),
    path('<int:pk>/apply-template/', views.apply_template, name='apply_template'),
    path('<int:pk>/report/performance/', views.performance_report_pdf, name='report_performance'),
    path('<int:pk>/report/financial/', views.financial_report_pdf, name='report_financial'),
]
