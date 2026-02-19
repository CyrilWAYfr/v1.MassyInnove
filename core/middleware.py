# core/middleware.py
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, resolve_url
from django.urls import resolve
import logging

logger = logging.getLogger(__name__)

ALLAUTH_PUBLIC = {
    "account_login", "account_logout", "account_signup",
    "account_reset_password", "account_reset_password_done",
    "account_reset_password_from_key", "account_reset_password_from_key_done",
    "account_email_verification_sent", "account_confirm_email",
}

PUBLIC_PATHS = {
    "/",
    "/healthz/",
    "/ingest/contact-entrant",
    "/ingest/contact-entrant/",
    "/ingest/contact-entrant-json",
    "/ingest/contact-entrant-json/",
    "/ingest/sender-authorization",
    "/ingest/sender-authorization/",
}

def _is_static_or_media(path: str) -> bool:
    su = getattr(settings, "STATIC_URL", None)
    mu = getattr(settings, "MEDIA_URL", None)
    ok_static = bool(su) and su != "/" and path.startswith(su)
    ok_media  = bool(mu) and mu != "/" and path.startswith(mu)
    return ok_static or ok_media

def _wants_json(request) -> bool:
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.path.startswith("/api/")

class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        if _is_static_or_media(path):
            logger.debug("Skip auth (static/media): %s", path)
            return self.get_response(request)

        if path in PUBLIC_PATHS:
            logger.debug("Skip auth (public path): %s", path)
            return self.get_response(request)

        try:
            match = resolve(path)
            url_name = match.url_name
            app_name = match.app_name
        except Exception:
            match = None
            url_name = None
            app_name = None

        if url_name in ALLAUTH_PUBLIC:
            logger.debug("Skip auth (allauth public view): %s", url_name)
            return self.get_response(request)

        if app_name == "admin" or (match and str(match.func.__module__).startswith("django.contrib.admin")):
            logger.debug("Skip auth (admin): %s", path)
            return self.get_response(request)

        if request.user.is_authenticated:
            return self.get_response(request)

        # Redirection fiable même si LOGIN_URL est un nom de vue
        login_url = resolve_url(settings.LOGIN_URL)
        if _wants_json(request):
            return JsonResponse({"detail": "Authentication required."}, status=401)
        return redirect(f"{login_url}?next={path}")



# core/middleware.py
from django.utils import timezone

class ForceParisTZMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Ne PAS activer Europe/Paris sur l'admin pour éviter CONVERT_TZ
        # (admin = namespace 'admin' ou URL commençant par /admin/)
        if request.path.startswith("/admin/"):
            # Laisse UTC (pas d'activate) -> pas de CONVERT_TZ en SQL
            return self.get_response(request)

        timezone.activate("Europe/Paris")
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()

