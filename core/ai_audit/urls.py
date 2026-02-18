# core/ai_audit/urls.py
from django.urls import path
from .views import MyAiUsageListView, my_ai_usage_export_csv

app_name = "ai_audit"

urlpatterns = [
    path("me/ai-usage/", MyAiUsageListView.as_view(), name="my_usage"),
    path("me/ai-usage/export/", my_ai_usage_export_csv, name="my_usage_export"),
]
