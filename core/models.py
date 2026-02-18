# core/models.py
from django.db import models

# core/models.py
# (garde tes imports / modèles existants s’il y en a)
from .ai_audit.models import AiCallLog  # re-export pour l’app registry

__all__ = ["AiCallLog"]  # + ajoute ici d’autres modèles de core s’il y en a

from django.conf import settings
from django.db import models

class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    
    is_plateforme_admin = models.BooleanField(
        default=False,
        help_text="Administrateur de la plateforme (domaines, canaux, salutations)."
    )

    def __str__(self):
        return f"Profil de {self.user.email}"


import os, hashlib
from django.conf import settings
from django.db import models

def fileasset_upload_to(instance, filename):
    # Organisation : files/<user_id>/<sha256>.<ext>
    name, ext = os.path.splitext(filename)
    return f"files/{instance.owner_id}/{instance.sha256}{ext.lower()}"

class FileAsset(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="files"
    )
    file = models.FileField(upload_to=fileasset_upload_to)

    processing_status = models.CharField(max_length=20, default="Running")
    number_of_pages = models.IntegerField(null=True, blank=True)
    tokens_processing_total = models.IntegerField(null=True, blank=True)
    tokens_logged = models.BooleanField(default=False)


    uploaded_to_mistral = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)   # <-- rajoute ça


    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)

    # Synchronisation Mistral
    mistral_library_id = models.CharField(max_length=100, blank=True, null=True)
    mistral_document_id = models.CharField(max_length=100, blank=True, null=True)
    uploaded_to_mistral = models.BooleanField(default=False)
