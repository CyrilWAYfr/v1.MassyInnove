from django.urls import path
from . import views

app_name = "assistantcr"

urlpatterns = [
    path('', views.upload_form, name='home'),
    path('uploadt/', views.upload_and_process, name='upload_and_process'),
    path('generate-meeting-minutes-from-form/', views.generate_meeting_minutes_from_form, name='generate_meeting_minutes_from_form'),
    path("generate/meeting-minutes/pdf/", views.generate_meeting_minutes_pdf, name="generate_meeting_minutes_pdf"),
    
]