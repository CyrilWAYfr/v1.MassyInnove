# core/ai_audit/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone


class AiCallLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        ERROR = "error", "Error"

    # Qui / Quand / D'où
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, db_index=True
    )
    source_app = models.CharField(max_length=100, db_index=True)  # ex: "ChatBotEngine"
    source_module = models.CharField(max_length=150, blank=True, default="", help_text="Vue/Job/Task optionnel")

    # Détails IA
    provider = models.CharField(max_length=50, default="mistral")
    model = models.CharField(max_length=120)  # ex: "mistral-large-latest"

    # Usage tokens
    tokens_input = models.PositiveIntegerField(default=0)
    tokens_output = models.PositiveIntegerField(default=0)
    tokens_total = models.PositiveIntegerField(default=0)

    # Impact (€ / CO2)
    # -> 6 décimales pour précision fine, ajustable si besoin.
    cost_eur = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    co2_grams = models.DecimalField(max_digits=12, decimal_places=6, default=0)

    # Traçabilité / Perf
    request_hash = models.CharField(
        max_length=128, blank=True, default="", db_index=True,
        help_text="Hash du prompt (pas de stockage en clair)"
    )
    latency_ms = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESS)

    # Divers
    metadata = models.JSONField(blank=True, null=True)

    class Meta:
        app_label = "core"  # le modèle appartient à l'app 'core'
        indexes = [
            models.Index(fields=["timestamp", "source_app"]),
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["model"]),
        ]
        ordering = ["-timestamp"]

    def __str__(self):
        who = getattr(self.user, "email", None) or self.user_id or "anonymous"
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {who} · {self.source_app} · {self.model} · {self.tokens_total} tok"
