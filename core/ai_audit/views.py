# core/ai_audit/views.py
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import ListView



from .models import AiCallLog


def _apply_filters(qs, request):
    """
    Filtres simples via GET:
      ?q=<search on model/source_app>
      &source_app=ChatBotEngine
      &model=mistral-large-latest
      &status=success|error
      &date_from=2025-09-01
      &date_to=2025-09-04
    """
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(model__icontains=q) | qs.filter(source_app__icontains=q)

    source_app = (request.GET.get("source_app") or "").strip()
    if source_app:
        qs = qs.filter(source_app=source_app)

    model = (request.GET.get("model") or "").strip()
    if model:
        qs = qs.filter(model=model)

    status = (request.GET.get("status") or "").strip()
    if status in dict(AiCallLog.Status.choices):
        qs = qs.filter(status=status)

    # Dates (inclusives), attendues au format YYYY-MM-DD (local Paris)
    date_from = parse_date(request.GET.get("date_from") or "")
    date_to = parse_date(request.GET.get("date_to") or "")
    if date_from:
        # début de journée Europe/Paris -> converti en aware UTC
        dt_start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()), timezone.get_current_timezone())
        qs = qs.filter(timestamp__gte=dt_start)
    if date_to:
        dt_end = timezone.make_aware(datetime.combine(date_to, datetime.max.time()), timezone.get_current_timezone())
        qs = qs.filter(timestamp__lte=dt_end)

    return qs


from urllib.parse import urlencode


class MyAiUsageListView(LoginRequiredMixin, ListView):
    """
    Liste paginée des logs appartenant à l'utilisateur courant.
    """
    model = AiCallLog
    template_name = "core/ai_audit/my_usage_list.html"
    context_object_name = "rows"
    paginate_by = 25

    def get_queryset(self):
        qs = AiCallLog.objects.filter(user=self.request.user).order_by("-timestamp")
        qs = _apply_filters(qs, self.request)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_qs = AiCallLog.objects.filter(user=self.request.user)
        ctx["available_apps"] = list(base_qs.values_list("source_app", flat=True).distinct().order_by("source_app"))
        ctx["available_models"] = list(base_qs.values_list("model", flat=True).distinct().order_by("model"))
        ctx["status_choices"] = AiCallLog.Status.choices

        # Copie des params GET et suppression de 'page'
        params = self.request.GET.copy()
        if "page" in params:
            params.pop("page")
        ctx["params"] = params
        ctx["query_without_page"] = urlencode([(k, v) for k in params for v in (params.getlist(k) or [""]) if v != ""])
        # -> string "a=1&b=2" (ou "" si aucun filtre)
        return ctx

@login_required
def my_ai_usage_export_csv(request):
    """
    Export CSV des logs de l'utilisateur courant (avec les mêmes filtres que la liste).
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    qs = AiCallLog.objects.filter(user=request.user).order_by("-timestamp")
    qs = _apply_filters(qs, request)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="my_ai_usage.csv"'

    # Écriture CSV
    from csv import writer
    w = writer(response)
    w.writerow([
        "timestamp", "source_app", "source_module", "provider", "model",
        "tokens_input", "tokens_output", "tokens_total",
        "cost_eur", "co2_grams", "latency_ms", "status", "request_hash"
    ])
    for r in qs:
        w.writerow([
            timezone.localtime(r.timestamp).isoformat(),
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
        ])
    return response


