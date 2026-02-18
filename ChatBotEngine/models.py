from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

class MistralModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    input_cost = models.FloatField(
        verbose_name="Coût d'entrée",
        help_text="Coût par token d'entrée",
        default=0.0
    )
    output_cost = models.FloatField(
        verbose_name="Coût de sortie",
        help_text="Coût par token de sortie",
        default=0.0
    )

    def __str__(self):
        return self.name



class AgentInstruction(models.Model):

    mistral_agent_id = models.CharField(
        max_length=128, blank=True, null=True, db_index=True,
        help_text="ID de l’agent persistant chez Mistral."
    )

    title = models.CharField(max_length=200)
    intro_text = models.TextField(verbose_name="Texte introductif")
    content = models.TextField(verbose_name="Contenu des instructions")
    mistral_model = models.ForeignKey(MistralModel, on_delete=models.RESTRICT)
    temperature = models.FloatField(
        verbose_name="Temperature",
        default=0.7,
        help_text="Valeur pour contrôler la créativité du modèle."
    )
    top_p = models.FloatField(
        verbose_name="Top P",
        default=0.95,
        help_text="Valeur pour le nucleus sampling."
    )
    

    mistral_library_id = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="ID de la librairie Mistral dédiée à cet agent."
    )

    
    enable_image_tool = models.BooleanField(
        default=False,
        verbose_name="Activer la génération d'images",
        help_text="Si désactivé, le tool image_generation ne sera pas transmis à Mistral"
    )
    
    enable_web_search = models.BooleanField(
        default=False,
        verbose_name="Autoriser la recherche web"
        )

    enable_file_upload = models.BooleanField(
        default=False,
        verbose_name="Autoriser le dépôt de fichiers",
        help_text="Si désactivé, l’utilisateur ne pourra pas joindre de fichier dans ses conversations avec cet agent."
    )
    
    # pour la gestion des conversations avec upload de fichiers
    
    source_agent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clones",
        help_text="Agent d’origine si cet agent est un clone temporaire."
    )

    is_temporary = models.BooleanField(
        default=False,
        help_text="True si cet agent est un clone temporaire (lié à une conversation utilisateur)."
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date de péremption pour les agents temporaires (purge automatique)."
    )
    
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chatbots",
        default=1,   # provisoire pour migration
    )

    is_public = models.BooleanField(
        default=False,
        help_text="Accessible à tous les utilisateurs connectés si activé."
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="chatbots_shared_with_me",
        blank=True,
        help_text="Utilisateurs spécifiques avec lesquels ce ChatBot est partagé."
    )

    class Meta:
        ordering = ["title"]   # par défaut tri alphabétique
        verbose_name = "Chatbot"
        verbose_name_plural = "Chatbots"

    def is_clone(self) -> bool:
        """Retourne True si l’agent est un clone d’un autre."""
        return self.source_agent_id is not None

    def set_default_expiration(self, days: int = 7):
        """Définit une date d’expiration par défaut (utile lors du clonage)."""
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=days)
            self.save(update_fields=["expires_at"])

    def is_expired(self) -> bool:
        """Retourne True si la date de péremption est passée."""
        return self.is_temporary and self.expires_at and self.expires_at < timezone.now()

    def __str__(self):
        return f"{self.title} {'(clone)' if self.is_clone() else ''}"
        

# --- PERSISTENCE DES CONVERSATIONS ---

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone

# Reprend tes modèles existants si besoin de types :
# from .models import AgentInstruction, MistralModel  # déjà dans ce fichier


class Conversation(models.Model):
    """
    Une conversation de chat liée à un utilisateur et à un agent (AgentInstruction).
    Stocke un titre (optionnel), la persistance (jetable/persistant), dates, et
    des compteurs simples pour lister rapidement.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chatbot_conversations",
    )
    agent_instruction = models.ForeignKey(
        "ChatBotEngine.AgentInstruction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
    )
    agent_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Nom/court libellé de l'agent au moment de la création (cache).",
    )

    title = models.CharField(max_length=200, blank=True)
    is_persistent = models.BooleanField(
        default=True,
        help_text="Si faux, conversation jetable (peut expirer automatiquement).",
    )
    mistral_conversation_id = models.CharField(max_length=255, blank=True, null=True)
    
    archived_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Compteurs et dates utiles pour lister/ordonner sans recalcul
    messages_count = models.PositiveIntegerField(default=0)
    tokens_input_total = models.PositiveIntegerField(default=0)
    tokens_output_total = models.PositiveIntegerField(default=0)

    last_activity_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-last_activity_at",)
        indexes = [
            models.Index(fields=("owner", "-last_activity_at")),
            models.Index(fields=("is_persistent",)),
        ]
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"

    def __str__(self):
        base = self.title or f"Conv {str(self.id)[:8]}"
        return f"{base} · {self.owner}"

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def touch(self):
        """Forcer la mise à jour de last_activity_at."""
        self.last_activity_at = timezone.now()
        self.save(update_fields=["last_activity_at"])

    def set_title_if_empty(self, suggestion: str | None):
        """Définir un titre si vide (ex: à partir du 1er prompt tronqué)."""
        if suggestion and not self.title:
            self.title = (suggestion.strip()[:180] + "…") if len(suggestion) > 180 else suggestion.strip()
            self.save(update_fields=["title"])


class Message(models.Model):
    ROLE_CHOICES = (
        ("user", "user"),
        ("assistant", "assistant"),
        ("system", "system"),
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=12, choices=ROLE_CHOICES)
    content = models.TextField(blank=True)  # si tu veux éviter le texte en clair: laisse vide + stocke un hash
    content_hash = models.CharField(
        max_length=128, blank=True, help_text="Empreinte du contenu (blake2/sha256), si content non conservé."
    )

    model = models.CharField(max_length=120, blank=True)  # ex: "mistral-large-latest"
    tokens_input = models.PositiveIntegerField(default=0)
    tokens_output = models.PositiveIntegerField(default=0)

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=("conversation", "created_at")),
        ]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"{self.role} · {self.conversation_id} · {self.created_at:%Y-%m-%d %H:%M:%S}"


###############################   FICHIERS ATTACHES A LA DEFINITION DE L'AGENT ####################################

class AgentFileLink(models.Model):
    agent = models.ForeignKey(
        "ChatBotEngine.AgentInstruction",
        on_delete=models.CASCADE,
        related_name="linked_files",
    )
    file = models.ForeignKey(
        "core.FileAsset",
        on_delete=models.CASCADE,
        related_name="used_in_agents",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fichier associé à un agent"
        verbose_name_plural = "Fichiers associés à des agents"
        unique_together = ("agent", "file")

    def __str__(self):
        return f"{self.file.original_name} → {self.agent.title}"


