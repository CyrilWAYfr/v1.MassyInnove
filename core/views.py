
# Validation des demandes d'inscription

from allauth.account.views import ConfirmEmailView
from django.shortcuts import redirect
from django.urls import reverse

class ConfirmEmailAndSetPasswordView(ConfirmEmailView):
    def get(self, *args, **kwargs):
        self.object = self.get_object()
        self.object.confirm(self.request)  # confirme l'email
        # Redirige direct vers la page "set password"
        return redirect(reverse("account_set_password"))


from django.shortcuts import render
from django.db.models import Sum
from core.ai_audit.models import AiCallLog


def profile(request):
    # Agrège le coût total et les émissions CO₂ de l'utilisateur connecté
    agg = AiCallLog.objects.filter(user=request.user).aggregate(
        total_cost=Sum("cost_eur"),
        total_co2=Sum("co2_grams"),
    )

    context = {
        "total_cost": round(agg["total_cost"] or 0, 4),  # arrondi à 4 décimales
        "total_co2": round(agg["total_co2"] or 0, 2),    # arrondi à 2 décimales
    }
    return render(request, "core/profile.html", context)


# core/views.py
from allauth.account.views import ConfirmEmailView
from django.shortcuts import redirect
from django.urls import reverse

class ConfirmEmailAndLoginRedirectView(ConfirmEmailView):
    def get(self, *args, **kwargs):
        # Confirme l’email
        self.object = self.get_object()
        email_address = self.object.email_address
        self.object.confirm(self.request)

        # Redirige vers la page de login avec email pré-rempli
        login_url = f"{reverse('account_login')}?email={email_address.email}"
        return redirect(login_url)




    
############    POUR ADMIN SEULEMENT : IDENTIFICATION DES EVENTUELS FICHIERS ORPHELINS COTE MISTRAL    ###############

from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods
from django.conf import settings
import requests
from .models import UserProfile

MISTRAL_API_KEY = settings.MISTRAL_API_KEY
MISTRAL_API_BASE = "https://api.mistral.ai/v1"


@require_http_methods(["POST"])
@user_passes_test(lambda u: u.is_superuser)
def preview_clean_all_libraries(request):
    """Vérifie combien de fichiers 'fantômes' existent chez Mistral par utilisateur, sans les supprimer."""

    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    report = []

    for profile in UserProfile.objects.exclude(mistral_library_id__isnull=True):
        library_id = profile.mistral_library_id
        user_email = profile.user.email

        resp = requests.get(f"{MISTRAL_API_BASE}/libraries/{library_id}/documents", headers=headers)
        if resp.status_code != 200:
            report.append(f"⚠️ Erreur API pour {user_email}: {resp.status_code}")
            continue

        mistral_docs = {doc["id"]: doc for doc in resp.json().get("data", [])}
        local_docs = set(
            FileAsset.objects.filter(owner=profile.user, mistral_library_id=library_id)
            .values_list("mistral_document_id", flat=True)
        )

        orphans = [doc_id for doc_id in mistral_docs.keys() if doc_id not in local_docs]

        if orphans:
            report.append(f"👤 {user_email} → {len(orphans)} fichier(s) fantôme")
        else:
            report.append(f"👤 {user_email} → aucun fichier fantôme")

    if report:
        messages.info(request, " • ".join(report))
    else:
        messages.success(request, "✅ Aucune bibliothèque trouvée à analyser.")

    return redirect("core:my_files")


@require_http_methods(["POST"])
@user_passes_test(lambda u: u.is_superuser)
def clean_all_libraries(request):
    """Nettoie toutes les bibliothèques Mistral des fichiers fantômes pour tous les utilisateurs (rapport détaillé)."""

    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    report = []

    for profile in UserProfile.objects.exclude(mistral_library_id__isnull=True):
        library_id = profile.mistral_library_id
        user_email = profile.user.email

        resp = requests.get(f"{MISTRAL_API_BASE}/libraries/{library_id}/documents", headers=headers)
        if resp.status_code != 200:
            report.append(f"⚠️ Erreur API pour {user_email}: {resp.status_code}")
            continue

        mistral_docs = {doc["id"]: doc for doc in resp.json().get("data", [])}
        local_docs = set(
            FileAsset.objects.filter(owner=profile.user, mistral_library_id=library_id)
            .values_list("mistral_document_id", flat=True)
        )

        orphans = [doc_id for doc_id in mistral_docs.keys() if doc_id not in local_docs]

        deleted_count = 0
        for doc_id in orphans:
            del_resp = requests.delete(
                f"{MISTRAL_API_BASE}/libraries/{library_id}/documents/{doc_id}",
                headers=headers,
            )
            if del_resp.status_code in (200, 204, 404):
                deleted_count += 1
            else:
                report.append(f"⚠️ Suppression échouée {doc_id} ({user_email})")

        if deleted_count:
            report.append(f"👤 {user_email} → {deleted_count} fichier(s) supprimé(s)")
        else:
            report.append(f"👤 {user_email} → aucun fichier supprimé")

    if report:
        messages.success(request, " • ".join(report))
    else:
        messages.info(request, "✅ Rien à supprimer.")

    return redirect("core:my_files")
    
################     LOG DIFFERE DES CHARGEMENTS DE FICHIERS      ############################



# Vue d'admin listant tous les agents existants côté Mistral et permettant leur suppression

import requests
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.contrib import messages
from datetime import datetime
from django.http import HttpResponseRedirect
from django.urls import reverse

MISTRAL_API_BASE = "https://api.mistral.ai/v1"


@staff_member_required
def admin_mistral_agents(request):
    """Liste et supprime les agents Mistral, avec pagination."""
    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }

    # Suppression
    # 🔹 Suppression d’un agent
    if request.method == "POST":
        agent_id = request.POST.get("agent_id")
        current_page = request.POST.get("current_page", "1")
        if agent_id:
            resp = requests.delete(f"{MISTRAL_API_BASE}/agents/{agent_id}", headers=headers)
            if resp.status_code in (200, 204):
                messages.success(request, f"Agent {agent_id} supprimé avec succès.")
            else:
                try:
                    err = resp.json()
                except Exception:
                    err = resp.text
                messages.error(request, f"Erreur lors de la suppression : {err}")
        # 👉 redirige vers la même page
        
        redirect_url = f"{reverse('core:admin_mistral_agents')}?page={current_page}"
        return HttpResponseRedirect(redirect_url)


    # Pagination
    page = int(request.GET.get("page", 1))
    page_size = 20
    params = {"page": page, "page_size": page_size}

    # Récupération
    resp = requests.get(f"{MISTRAL_API_BASE}/agents", headers=headers, params=params)
    if resp.status_code != 200:
        try:
            error = resp.json()
        except Exception:
            error = resp.text
        return render(request, "core/admin_mistral_agents.html", {"error": error})

    data = resp.json()

    # Certains endpoints renvoient directement une liste, d'autres un dict
    if isinstance(data, list):
        agents = data
        meta = {}
    else:
        agents = data.get("data", data.get("results", []))
        meta = data.get("meta", data.get("pagination", {}))

    # Formatage des dates
    for agent in agents:
        created_raw = agent.get("created") or agent.get("created_at")
        if created_raw:
            try:
                if isinstance(created_raw, (int, float)):  # timestamp
                    dt = datetime.fromtimestamp(created_raw)
                else:
                    dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                agent["created_display"] = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                agent["created_display"] = created_raw
        else:
            agent["created_display"] = ""

    # Détermination des pages
    next_page = meta.get("next_page") or (page + 1 if len(agents) == page_size else None)
    prev_page = meta.get("previous_page") or (page - 1 if page > 1 else None)

    context = {
        "agents": agents,
        "page": page,
        "next_page": next_page,
        "prev_page": prev_page,
    }
    return render(request, "core/admin_mistral_agents.html", context)
    
    
## VUE D'ADMIN GENERALE

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

@staff_member_required
def admin_dashboard(request):
    """Page d'accueil de l'administration interne."""
    return render(request, "core/admin_dashboard.html")

