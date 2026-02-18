# core/urls.py
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    #path("files/", views.my_files, name="my_files"),
    #path("files/upload/", views.upload_file, name="upload_file"),
    #path("files/<int:file_id>/delete/", views.delete_file, name="delete_file"),
    #path("files/<int:file_id>/refresh/", views.refresh_document_status, name="refresh_document_status"),
    #path("files/clean-preview/", views.preview_clean_all_libraries, name="preview_clean_all_libraries"),
    #path("files/clean-all/", views.clean_all_libraries, name="clean_all_libraries"),
    #path("files/sync-all/", views.sync_all_files, name="sync_all_files"),
    
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("agents/", views.admin_mistral_agents, name="admin_mistral_agents"),

]
