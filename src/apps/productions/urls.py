from django.urls import path
from . import views

app_name = "productions"

urlpatterns = [
    path("", views.ProductionListView.as_view(), name="list"),
    path("create/", views.ProductionCreateView.as_view(), name="create"),
    path("<int:pk>/", views.ProductionDetailView.as_view(), name="detail"),
    path("<int:pk>/setup/", views.ProductionSetupView.as_view(), name="setup"),
    path("templates/api/", views.ProductionTemplateListView.as_view(), name="template_api"),
    path("process-day/<int:pk>/edit/", views.ProcessDayEditView.as_view(), name="process_day_edit"),
    path("<int:production_id>/process-day/add/", views.ProcessDayCreateView.as_view(), name="process_day_add"),
]
