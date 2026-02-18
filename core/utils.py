import requests
from django.conf import settings

MISTRAL_API_KEY = settings.MISTRAL_API_KEY
MISTRAL_API_BASE = "https://api.mistral.ai/v1"

def get_or_create_user_library(user):
    if hasattr(user, "profile") and user.profile.mistral_library_id:
        return user.profile.mistral_library_id

    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    resp = requests.post(
        f"{MISTRAL_API_BASE}/libraries",
        headers=headers,
        json={"name": f"Library utilisateur {user.id}"}
    )
    resp.raise_for_status()
    lib_id = resp.json()["id"]

    user.profile.mistral_library_id = lib_id
    user.profile.save()

    return lib_id
