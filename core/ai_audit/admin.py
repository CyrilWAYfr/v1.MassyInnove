# core/ai_audit/admin.py
from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone
import csv

from .models import AiCallLog


@admin.register(AiCallLog)
class AiCallLogAdmin(admin.ModelAdmin):
    date_hierarchy = "timestamp"

    list_display = (
        "timestamp",
        "user",
        "source_app",
        "source_module",
        "provider",
        "model",
        "tokens_total",
        "cost_eur",
        "co2_grams",
        "status",
        "latency_ms",
    )
    list_filter = (
        "source_app",
        "provider",
        "model",
        "status",
        ("timestamp", admin.DateFieldListFilter),
    )
    search_fields = (
        "user__email",
        "user__username",
        "source_app",
        "source_module",
        "model",
        "request_hash",
    )
    readonly_fields = (
        "timestamp",
        "user",
        "source_app",
        "source_module",
        "provider",
        "model",
        "tokens_input",
        "tokens_output",
        "tokens_total",
        "cost_eur",
        "co2_grams",
        "latency_ms",
        "status",
        "request_hash",
        "metadata",
    )

    actions = ["export_csv", "stats_selection"]

    @admin.action(description="Exporter en CSV (sélection)")
    def export_csv(self, request, queryset):
        now = timezone.now().strftime("%Y%m%d-%H%M%S")
        filename = f"aicalls_{now}.csv"
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow([
            "timestamp", "user_id", "user_email",
            "source_app", "source_module",
            "provider", "model",
            "tokens_input", "tokens_output", "tokens_total",
            "cost_eur", "co2_grams",
            "latency_ms", "status", "request_hash", "metadata",
        ])
        for r in queryset.select_related("user"):
            writer.writerow([
                r.timestamp.isoformat(),
                r.user_id,
                getattr(r.user, "email", "") if r.user_id else "",
                r.source_app,
                r.source_module,
                r.provider,
                r.model,
                r.tokens_input,
                r.tokens_output,
                r.tokens_total,
                str(r.cost_eur),
                str(r.co2_grams),
                r.latency_ms,
                r.status,
                r.request_hash,
                r.metadata if r.metadata is not None else "",
            ])
        return response

    @admin.action(description="Afficher stats (totaux) dans la barre de messages")
    def stats_selection(self, request, queryset):
        agg = queryset.aggregate(
            total_tokens=models.Sum("tokens_total"),
            total_cost=models.Sum("cost_eur"),
            total_co2=models.Sum("co2_grams"),
        )
        self.message_user(
            request,
            f"Totaux sur la sélection — tokens: {agg['total_tokens'] or 0:,} | "
            f"€: {agg['total_cost'] or 0} | CO₂ (g): {agg['total_co2'] or 0}"
        )
