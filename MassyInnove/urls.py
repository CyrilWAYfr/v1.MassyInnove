# URL configuration for DevMassy project.

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.views.generic import TemplateView

from .views import home

from core.views import ConfirmEmailAndLoginRedirectView, profile

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("versions/", TemplateView.as_view(template_name="versioning.html"), name="versioning"),

    # Apps internes
    path("AssistantCR/", include("AssistantCR.urls", namespace="assistantcr")),
    path("ChatBotEngine/", include("ChatBotEngine.urls", namespace="chatbotengine")),
    path("Logement/", include("logement.urls", namespace="logement")),
    path("ingest/", include("logement.api.urls")),
    path("core/", include("core.urls")),
    path("", include("core.ai_audit.urls", namespace="ai_audit")),

    # Authentification / allauth
    path(
    "accounts/confirm-email/<key>/",
    ConfirmEmailAndLoginRedirectView.as_view(),
    name="account_confirm_email",
),
    path("accounts/", include("allauth.urls")),

]


# --- Gestion des fichiers médias en mode DEBUG ---
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)