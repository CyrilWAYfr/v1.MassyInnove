import secrets
from django.conf import settings
from django.http import JsonResponse


def _extract_api_key(request) -> str | None:
    """
    Supporte :
      - Authorization: Bearer <token>
      - X-API-Key: <token>     (fallback utile si Authorization est filtré par Apache)
    """
    auth = request.META.get("HTTP_AUTHORIZATION", "") or ""
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip() or None

    x_api_key = request.META.get("HTTP_X_API_KEY", "") or ""
    return x_api_key.strip() or None


def api_key_required(view_func):
    def _wrapped(request, *args, **kwargs):
        expected = getattr(settings, "INGEST_API_KEY", "") or ""
        if not expected:
            return JsonResponse(
                {"ok": False, "error": "Server misconfigured: missing INGEST_API_KEY"},
                status=500,
            )

        token = _extract_api_key(request)
        if not token:
            return JsonResponse(
                {"ok": False, "error": "Missing API token"},
                status=401,
            )

        if not secrets.compare_digest(token, expected):
            return JsonResponse(
                {"ok": False, "error": "Invalid API token"},
                status=401,
            )

        return view_func(request, *args, **kwargs)

    return _wrapped
