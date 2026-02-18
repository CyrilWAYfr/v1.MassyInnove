from django.urls import path
from . import views
from .views import ingest_contact_entrant

urlpatterns = [
    path("contact-entrant/", ingest_contact_entrant, name="api_ingest_contact_entrant"),
    path("contact-entrant-json/", views.ingest_contact_entrant_json, name="api_ingest_contact_entrant_json"),
]
