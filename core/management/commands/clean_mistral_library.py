from django.core.management.base import BaseCommand
from django.conf import settings
import requests
from core.models import FileAsset, UserProfile  # ajuste selon ton projet

MISTRAL_API_KEY = settings.MISTRAL_API_KEY
MISTRAL_API_BASE = "https://api.mistral.ai/v1"


class Command(BaseCommand):
    help = "Nettoie les documents 'fantômes' encore présents dans Mistral mais plus dans la DB locale"

    def handle(self, *args, **options):
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}

        for profile in UserProfile.objects.exclude(mistral_library_id__isnull=True):
            library_id = profile.mistral_library_id
            self.stdout.write(f"🔍 Vérification de la library {library_id} (user {profile.user.email})")

            resp = requests.get(f"{MISTRAL_API_BASE}/libraries/{library_id}/documents", headers=headers)
            if resp.status_code != 200:
                self.stderr.write(f"⚠️ Erreur API: {resp.status_code} {resp.text}")
                continue

            mistral_docs = {doc["id"]: doc for doc in resp.json().get("data", [])}
            local_docs = set(FileAsset.objects.filter(
                owner=profile.user,
                mistral_library_id=library_id
            ).values_list("mistral_document_id", flat=True))

            # Différence = docs à supprimer
            orphans = [doc_id for doc_id in mistral_docs.keys() if doc_id not in local_docs]

            for doc_id in orphans:
                self.stdout.write(f"🗑️ Suppression du doc fantôme {doc_id}")
                del_resp = requests.delete(
                    f"{MISTRAL_API_BASE}/libraries/{library_id}/documents/{doc_id}",
                    headers=headers,
                )
                if del_resp.status_code not in (200, 204, 404):
                    self.stderr.write(f"⚠️ Erreur suppression {doc_id}: {del_resp.status_code} {del_resp.text}")
