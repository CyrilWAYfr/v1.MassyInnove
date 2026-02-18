# --- IMPORTS --- PROD
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.views.decorators.http import require_POST
from django.http import HttpRequest, HttpResponse
from django.db.models import Prefetch
from logement.models import DomaineUser
from django.http import HttpResponseForbidden




from mistralai import Mistral
import json


from .models import ContactEntrant, Demandeur, Canal, Thematique, Domaine, Groupe, Salutations
from .forms import EmailEntrantStep1Form, EmailEntrantStep2Form

from ChatBotEngine.models import AgentInstruction

#  VUE ACCUEIL

# logement/views.py

from collections import defaultdict
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Domaine
from .stats import repartition_statut_par_mois_ytd, top_thematiques_mtd

@login_required
def logement_dashboard(request):
        
    profile = getattr(request.user, "profile", None)

    is_plateforme_admin = bool(profile and profile.is_plateforme_admin)

    is_domaine_admin = Domaine.objects.filter(
        user_links__user=request.user,
        user_links__is_admin=True,
    ).exists()


    
    domaine = (
        Domaine.objects
        .filter(user_links__user=request.user)
        .order_by("ordre", "libelle")
        .first()
    )
        
    if not domaine:
        return render(request, "logement/dashboard.html", {
            "is_plateforme_admin": is_plateforme_admin,
            "is_domaine_admin": is_domaine_admin,

            "domaine": None,
            "statut_mois_ytd": [],
            "stats_statut_mois": [],
            "stats_month_label": None,
            "top_thematiques_mtd": [],
        })

    
    statut_mois_ytd = repartition_statut_par_mois_ytd(domaine)
    
    stats_statut_mois = []
    stats_month_label = None
    
    if statut_mois_ytd:
        last_year, last_month = max((r["year"], r["month"]) for r in statut_mois_ytd)
        stats_month_label = f"{last_month:02d}/{last_year}"
    
        acc = defaultdict(int)
        for r in statut_mois_ytd:
            if r["year"] == last_year and r["month"] == last_month:
                acc[r["statut_libelle"] or "Non défini"] += int(r["total"])
    
        stats_statut_mois = [
            {"statut_libelle": k, "total": v}
            for k, v in acc.items()
        ]
    
    context = {
        "is_plateforme_admin": is_plateforme_admin,
        "is_domaine_admin": is_domaine_admin,

        "domaine": domaine,
    
        "statut_mois_ytd": statut_mois_ytd,
        "stats_statut_mois": stats_statut_mois,
        "stats_month_label": stats_month_label,
    
        "top_thematiques_mtd": top_thematiques_mtd(domaine),
    }
    
    return render(request, "logement/dashboard.html", context)


@login_required
def home_demo(request):
        
    profile = getattr(request.user, "profile", None)

    is_plateforme_admin = bool(profile and profile.is_plateforme_admin)

    is_domaine_admin = Domaine.objects.filter(
        user_links__user=request.user,
        user_links__is_admin=True,
    ).exists()


    
    domaine = (
        Domaine.objects
        .filter(user_links__user=request.user)
        .order_by("ordre", "libelle")
        .first()
    )
        
    if not domaine:
        return render(request, "logement/home_demo.html", {
            "is_plateforme_admin": is_plateforme_admin,
            "is_domaine_admin": is_domaine_admin,
            "domaine": None,
        })

    

    
    context = {
        "is_plateforme_admin": is_plateforme_admin,
        "is_domaine_admin": is_domaine_admin,

        "domaine": domaine,
    }
    
    return render(request, "logement/home_demo.html", context)


@login_required
def home_vincent(request):
        
    profile = getattr(request.user, "profile", None)

    is_plateforme_admin = bool(profile and profile.is_plateforme_admin)

    is_domaine_admin = Domaine.objects.filter(
        user_links__user=request.user,
        user_links__is_admin=True,
    ).exists()


    
    domaine = (
        Domaine.objects
        .filter(user_links__user=request.user)
        .order_by("ordre", "libelle")
        .first()
    )
        
    if not domaine:
        return render(request, "logement/home_demo.html", {
            "is_plateforme_admin": is_plateforme_admin,
            "is_domaine_admin": is_domaine_admin,
            "domaine": None,
        })

    

    
    context = {
        "is_plateforme_admin": is_plateforme_admin,
        "is_domaine_admin": is_domaine_admin,

        "domaine": domaine,
    }
    
    return render(request, "logement/home_vincent.html", context)


# -----------------------------------------------
# CONTACTS ENTRANTS – LISTE / RECHERCHE / TRI / SUPPRESSION
# -----------------------------------------------
from .decorators import domaine_required
from django.db.models import Q
from django.shortcuts import render
from .models import ContactEntrant


from .security import get_contacts_for_user

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.core.paginator import Paginator, EmptyPage

from .models import StatutContact

@login_required
def contact_list(request):
    search = request.GET.get("search", "").strip()
    statut = request.GET.get("statut", "").strip()   # <-- NOUVEAU
    order = request.GET.get("order", "-date")
    return_url = request.GET.get("return_url")

    contacts = (
        get_contacts_for_user(request.user)
        .select_related("demandeur", "canal", "statut")
    )

    if search:
        contacts = contacts.filter(
            Q(demandeur__email__icontains=search)
            | Q(objet__icontains=search)
            | Q(txtdemande__icontains=search)
            | Q(demandeur__num_unique__icontains=search)
        )

    # --- Filtre statut (id)
    if statut:
        contacts = contacts.filter(statut_id=statut)

    valid_orders = [
        "date", "-date",
        "demandeur__email", "-demandeur__email",
        "demandeur__num_unique", "-demandeur__num_unique",
        "statut__id", "-statut__id",
        "canal__libelle", "-canal__libelle",
    ]

    if order not in valid_orders:
        order = "-date"

    contacts = contacts.order_by(order)
    paginator = Paginator(contacts, 25)
    page_number = request.GET.get("page", 1)
    try:
        contacts = paginator.page(page_number)
    except EmptyPage:
        contacts = paginator.page(1)

    # --- Liste des statuts pour le dropdown
    statuts = StatutContact.objects.all().order_by("id")

    return render(request, "logement/contact_list.html", {
        "contacts": contacts,
        "search": search,
        "statut": statut,     # <-- NOUVEAU (pour garder la sélection)
        "statuts": statuts,   # <-- NOUVEAU (pour remplir le dropdown)
        "order": order,
        "return_url": return_url,
    })



from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .decorators import domaine_required

@require_POST
@domaine_required
def contact_delete(request, domaine_id, contact_id):
    contact = get_object_or_404(
        ContactEntrant,
        id=contact_id,
        domaine=request.domaine
    )
    return_url = request.POST.get("return_url")
    contact.delete()

    messages.success(request, "Contact supprimé.")
    if return_url:
        return redirect(return_url)

    return redirect("logement:contact_list")



# -----------------------------------------------
# TRAITEMENT DES MAILS – ETAPE 1
# -----------------------------------------------
from datetime import datetime
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse

from .models import Demandeur, ContactEntrant
from .forms import EmailEntrantStep1Form

from .decorators import domaine_required
from .security import get_contacts_for_user

from django.urls import reverse
from urllib.parse import quote as urlquote


@domaine_required
def email_create_step1(request, domaine_id, demandeur_id=None):
    
    domaine = request.domaine
    return_url = request.GET.get("return_url") or request.POST.get("return_url")

    """
    Étape 1 de la création d'un contact entrant.
    Gère à la fois :
    - GET vierge (mode 'initial')
    - GET avec demandeur pré-rempli
    - POST avec validation + erreurs
    """

    # Fonction interne pour normaliser les emails
    def normalize_email(email: str | None):
        if not email:
            return ""
        return email.strip().lower()

    # ----------------------------------------------------
    # 1) GET — ouverture de la page
    # ----------------------------------------------------
    if request.method == "GET":

        # Cas 1 : demandeur pré-rempli depuis l'URL
        if demandeur_id is not None:
            demandeur = get_object_or_404(Demandeur, id=demandeur_id)

            initial = {
                "email": demandeur.email,
                "date": timezone.localdate(),
                "statut": 1,
                "canal": 1,
            }

            form = EmailEntrantStep1Form(initial=initial)

            # Charger l'historique du demandeur
            contacts = (
                get_contacts_for_user(request.user)
                .filter(demandeur=demandeur)
                .select_related("statut", "canal")
                .prefetch_related("thematiques")
                .order_by("-date")
            )

            history = list(contacts)  # [] si aucun historique

        else:
            # Cas 2 : formulaire vierge (aucune recherche effectuée)
            form = EmailEntrantStep1Form(initial={
                "date": timezone.localdate(),
                "statut": 1,
                "canal": 1,
            })
            history = "initial"

        return render(request, "logement/email_step1.html", {
            "form": form,
            "history": history,
            "domaine_id": domaine_id,
            "return_url": return_url,
        })

    # ----------------------------------------------------
    # 2) POST — validation du formulaire
    # ----------------------------------------------------
    form = EmailEntrantStep1Form(request.POST)

    if not form.is_valid():
        # Le formulaire a des erreurs → on tente quand même d'afficher l'historique si email saisi

        email_raw = normalize_email(request.POST.get("email"))

        if email_raw:
            demandeur = Demandeur.objects.filter(email=email_raw).first()
            if demandeur:
                qs = (
                    get_contacts_for_user(request.user)
                    .filter(demandeur=demandeur)
                    .select_related("statut", "canal")
                    .prefetch_related("thematiques")
                    .order_by("-date")
                )
                history = list(qs)
            else:
                history = None
        else:
            history = "initial"


        return render(request, "logement/email_step1.html", {
            "form": form,
            "history": history,
            "domaine_id": domaine_id,
            "return_url": return_url,
        })

    # ----------------------------------------------------
    # 3) POST valide → création ou mise à jour des données
    # ----------------------------------------------------
    email = normalize_email(form.cleaned_data["email"])
    objet = form.cleaned_data["objet"]
    texte = form.cleaned_data["texte"]
    canal = form.cleaned_data["canal"]
    statut = form.cleaned_data["statut"]
    date_selected = form.cleaned_data["date"]

    date_mail = timezone.make_aware(datetime.combine(date_selected, datetime.min.time()))

    # Chercher le demandeur
    demandeur = Demandeur.objects.filter(email=email).first()

    if not demandeur:
        # Création silencieuse d'un nouveau demandeur
        demandeur = Demandeur.objects.create(email=email)

    # Création du contact entrant
    ce = ContactEntrant.objects.create(
        date=date_mail,
        canal=canal,
        statut=statut,
        demandeur=demandeur,
        objet=objet,
        txtdemande=texte,
        domaine=domaine,
    )

    # ----------------------------------------------------------
    # Appliquer les thématiques cochées par défaut
    # UNIQUEMENT pour un NOUVEAU contact
    # ----------------------------------------------------------
    default_thematics = list(
        Thematique.objects.filter(
            cocher_par_defaut=True,
            groupe__domaine=domaine
        ).values_list("id", flat=True)
    )


    if default_thematics:
        ce.thematiques.set(default_thematics)

    if return_url:
        return redirect(
            f"{reverse('logement:email_create_step2', args=[ce.id])}"
            f"?return_url={urlquote(return_url)}"
        )

    return redirect("logement:email_create_step2", contact_id=ce.id)




from datetime import datetime

from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.template.loader import render_to_string

from .models import Demandeur, ContactEntrant
from .forms import EmailEntrantStep1Form
from .security import get_contacts_for_user

def _get_contacts_qs_for_demandeur(request, demandeur):
    return (
        get_contacts_for_user(request.user)
        .filter(demandeur=demandeur)
        .select_related("statut", "canal")
        .prefetch_related("thematiques")
        .order_by("-date")
    )






def check_demandeur(request):
    email = request.GET.get("email", "").strip().lower()
    demandeur = None

    if email:
        demandeur = Demandeur.objects.filter(email=email).first()

    if not demandeur:
        html = render_to_string(
            "logement/_contacts_history.html",
            {"contacts": None},   # <<<<< important
            request=request,
        )
        return JsonResponse({"exists": False, "html": html})

    contacts = _get_contacts_qs_for_demandeur(request, demandeur)

    html = render_to_string(
        "logement/_contacts_history.html",
        {"contacts": contacts},
        request=request,
    )
    return JsonResponse({"exists": True, "html": html})







# -----------------------------------------------
# TRAITEMENT DES MAILS – ETAPE 2
# -----------------------------------------------

# Synchro formulaire / BDD

def sync_contact_from_step2_form(contact, form, request):
    """
    Synchronise les champs du formulaire step2 vers ContactEntrant
    (hors champ 'reponse', géré séparément).
    """

    # --- Numéro unique (Demandeur) ---
    numero_unique = form.cleaned_data.get("numero_unique")
    contact.demandeur.num_unique = numero_unique or None
    contact.demandeur.save()

    # --- Statut ---
    contact.statut = form.cleaned_data.get("statut")

    # --- Salutation ---
    contact.salutation = form.cleaned_data.get("salutation")

    # --- Thématiques (hors form Django) ---
    selected_ids = request.POST.getlist("thematiques")
    contact.thematiques.set(selected_ids)

    contact.save()


from .decorators import domaine_required
from .security import user_has_domaine
from django.urls import reverse
from urllib.parse import quote as urlquote

#PROD
@login_required
def email_create_step2(request, contact_id):
    
    contact = get_object_or_404(
        ContactEntrant.objects
            .select_related("domaine", "demandeur")
            .prefetch_related("pieces_jointes"),
        id=contact_id
    )


    if not user_has_domaine(request.user, contact.domaine):
        return HttpResponseForbidden("Accès interdit à ce domaine")

    domaine = contact.domaine
    return_url = request.GET.get("return_url") or request.POST.get("return_url")
    
    
    # ------------------------------------------------------
    # 🔥 POST : enregistrement du formulaire
    # ------------------------------------------------------
    if request.method == "POST":
        form = EmailEntrantStep2Form(request.POST)

        if form.is_valid():

            sync_contact_from_step2_form(contact, form, request)
            
            evaluation = form.cleaned_data.get("evaluation_reponse")
            contact.evaluation_reponse = evaluation or None
            contact.save(update_fields=["evaluation_reponse"])


            # --- Réponse (reste spécifique ici) ---
            contact.reponse = form.cleaned_data.get("reponse") or ""
            contact.save(update_fields=["reponse"])

            if return_url:
                return redirect(
                    f"{reverse('logement:email_create_step2', args=[contact.id])}"
                    f"?return_url={urlquote(return_url)}"
                )

            return redirect("logement:email_create_step2", contact_id=contact.id)


    else:
        # ------------------------------------------------------
        # 🔥 GET : valeurs initiales
        # ------------------------------------------------------
        form = EmailEntrantStep2Form(initial={
            "numero_unique": contact.demandeur.num_unique,
            "reponse": contact.reponse,
            "statut": contact.statut_id,
            "salutation": contact.salutation_id,
            "evaluation_reponse": contact.evaluation_reponse,
        })

    # ------------------------------------------------------
    # 🔥 Charger les groupes et thématiques
    # ------------------------------------------------------
    if domaine:
        groupes = Groupe.objects.filter(domaine=domaine).order_by("ordre")
    else:
        groupes = Groupe.objects.order_by("domaine__ordre", "ordre")

    groupes = groupes.prefetch_related(
        Prefetch("thematiques", queryset=Thematique.objects.order_by("ordre"))
    )
    
    has_multiple_groups = groupes.count() > 1

    # ------------------------------------------------------
    # 🔥 Logique dépliage / repliage
    # ------------------------------------------------------
    selected_ids = list(contact.thematiques.values_list("id", flat=True))
    is_new_contact = not selected_ids

    groups_to_expand = set()

    if not is_new_contact:
        for groupe in groupes:
            if any(th.id in selected_ids for th in groupe.thematiques.all()):
                groups_to_expand.add(groupe.id)

    # ------------------------------------------------------
    # 🔥 Rendu template
    # ------------------------------------------------------
    return render(request, "logement/email_step2.html", {
        "contact": contact,
        "form": form,
        "groups": groupes,
        "selected_ids": selected_ids,
        "groups_to_expand": groups_to_expand,
        "is_new_contact": is_new_contact,
        "has_multiple_groups": has_multiple_groups,
        "domaine": domaine,
        "return_url": return_url,
    })







# PROPOSITION DE REPONSE

from django.conf import settings
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from mistralai import Mistral
import json

from .models import ContactEntrant, Thematique
from ChatBotEngine.models import AgentInstruction


# TRAITEMENT DES TEXT CHUNKS MISTRAL DANS LA REPONSE

def extract_mistral_text(response):
    """
    Extrait uniquement les chunks de type 'text' depuis la réponse Mistral.
    Compatible SDK mistralai 1.9.x
    """
    try:
        chunks = response.choices[0].message.content
        result_parts = []

        for chunk in chunks:
            if getattr(chunk, "type", None) == "text":
                txt = getattr(chunk, "text", "").strip()
                if txt:
                    result_parts.append(txt)

        return "\n\n".join(result_parts).strip()

    except Exception as e:
        return f"[Erreur lors de l'extraction du texte Mistral : {e}]"



def proposition_ia(request, ce, domaine):
    import json
    from mistralai import Mistral
    from django.conf import settings
    from django.db import connection

    agent = domaine.agent

    thematique_ids = request.POST.getlist("thematiques")
    th_list = list(Thematique.objects.filter(id__in=thematique_ids))

    ce.thematiques.set(th_list)

    payload = {
        "thematiques": [
            {
                "id": t.id,
                "reponse_type": t.reponse_type or ""
            }
            for t in th_list
        ]
    }

    client = Mistral(api_key=settings.MISTRAL_API_KEY)

    response = client.chat.complete(
        model=agent.mistral_model.name,
        temperature=agent.temperature,
        top_p=agent.top_p,
        messages=[
            {"role": "system", "content": agent.content},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )

    final_text = extract_mistral_text(response)

    # 🔥 reconnexion MySQL
    connection.close()

    return final_text


# Composition de la réponse globale : Salutations + Proposition IA + Signature

from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from urllib.parse import quote as urlquote

from .models import ContactEntrant
from .security import user_has_domaine
from .forms import EmailEntrantStep2Form
from logement.models import Thematique
from django.utils.formats import date_format

@require_POST
@login_required
def proposer_reponse(request, contact_id):

    ce = get_object_or_404(
        ContactEntrant.objects.select_related("domaine"),
        id=contact_id,
    )

    domaine = ce.domaine
    return_url = request.POST.get("return_url") or request.GET.get("return_url")


    # 🔐 Contrôle d’accès (droits OU domaine public)
    if not user_has_domaine(request.user, domaine):
        return HttpResponseForbidden("Accès interdit à ce domaine")

    # -------------------------------
    # Adhérence BDD
    # -------------------------------
    STATUT_BROUILLON_ID = 2

    # 🔹 1. Valider le formulaire step2
    form = EmailEntrantStep2Form(request.POST)
    if not form.is_valid():
        messages.error(request, "Le formulaire contient des erreurs.")
        if return_url:
            return redirect(
                f"{reverse('logement:email_create_step2', args=[contact_id])}"
                f"?return_url={urlquote(return_url)}"
            )

        return redirect("logement:email_create_step2", contact_id=contact_id)

    # 🔹 2. Synchroniser l’état du formulaire
    sync_contact_from_step2_form(ce, form, request)

    # 🔹 3. Cas sans agent IA
    if not domaine.agent_id:

        salutation = ce.salutation.libelle if ce.salutation else ""
        intro = domaine.intro or ""

        thematiques = ce.thematiques.all()

        lignes = []
        for t in thematiques:
            rt = (t.reponse_type or "").strip()
            texte = rt if rt else t.libelle_thematique
            lignes.append(f"- {texte}")

        liste_thematiques = "\n".join(lignes)

        signature = domaine.signature or ""

        blocs = []
        if salutation:
            blocs.append(salutation)
        if intro:
            blocs.append(intro)
        if liste_thematiques:
            blocs.append(liste_thematiques)
        if signature:
            blocs.append(signature)

        ce.reponse = "\n\n".join(blocs)
        ce.statut_id = STATUT_BROUILLON_ID
        ce.save(update_fields=["reponse", "statut_id"])

        if return_url:
            return redirect(
                f"{reverse('logement:email_create_step2', args=[contact_id])}"
                f"?return_url={urlquote(return_url)}"
            )

        return redirect("logement:email_create_step2", contact_id=contact_id)


    # 🔹 4. Génération IA
    texte_ia = proposition_ia(request, ce, domaine)

    # 🔹 5. Assemblage final
    salutation = (
        ce.salutation.libelle
        if ce.salutation
        else "Pas de salutation définie"
    )

    signature = domaine.signature or ""

    blocs = [salutation, texte_ia]
    if signature:
        blocs.append(signature)


    # -------------------------------------------------
    # Bloc "message initial" façon client mail
    # -------------------------------------------------
    if ce.txtdemande:

        date_str = (
            ce.date.strftime("%d/%m/%Y")
            if ce.date else ""
        )

        message_cite = "\n".join(
            f"> {line}" if line.strip() else ">"
            for line in ce.txtdemande.splitlines()
        )

        bloc_message_initial = "\n".join([
            "-" * 40,
            f"De : {ce.demandeur.email}",
            f"Le : {date_str}",
            f"Objet : {ce.objet}",
            "",
            message_cite,
        ])

        blocs.append(bloc_message_initial)

    ce.reponse = "\n\n".join(blocs)
    ce.statut_id = STATUT_BROUILLON_ID
    ce.save(update_fields=["reponse", "statut_id"])

    if return_url:
        return redirect(
            f"{reverse('logement:email_create_step2', args=[contact_id])}"
            f"?return_url={urlquote(return_url)}"
        )

    return redirect("logement:email_create_step2", contact_id=contact_id)




# -----------------------------------------------
# GESTION DES DEMANDEURS – ETAPE 2
# -----------------------------------------------

from django.db.models import Count, Max
from django.core.paginator import Paginator
from django.shortcuts import render
from .models import Demandeur
from .security import get_contacts_for_user
from django.contrib.auth.decorators import login_required


def demandeurs_list(request):
    """
    Liste des demandeurs visibles par l'utilisateur,
    basée exclusivement sur les contacts entrants auxquels il a accès.
    """

    contacts = get_contacts_for_user(request.user)
    return_url = request.GET.get("return_url")
    search_num_unique = request.GET.get("num_unique", "").strip()
    search_email = request.GET.get("email", "").strip()

    # Aucun contact accessible → aucun demandeur visible
    if not contacts.exists():
        demandeurs = Demandeur.objects.none()
    else:
        demandeurs = (
            Demandeur.objects
            .filter(contacts_entrants__in=contacts)
            .annotate(
                dernier_contact=Max("contacts_entrants__date"),
                nb_contacts=Count("contacts_entrants", distinct=True),
            )
            .distinct()
        )
        if search_num_unique:
            demandeurs = demandeurs.filter(num_unique__icontains=search_num_unique)
        if search_email:
            demandeurs = demandeurs.filter(email__icontains=search_email)

        demandeurs = demandeurs.order_by(
            "-dernier_contact",
            "email",
            "telephone",
        )

    paginator = Paginator(demandeurs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "logement/demandeurs_list.html", {
        "demandeurs": page_obj,
        "page_obj": page_obj,
        "return_url": return_url,
        "search_num_unique": search_num_unique,
        "search_email": search_email,
    })


from django.shortcuts import render, get_object_or_404, redirect
from django.forms import ModelForm
from .models import Demandeur
from .forms import DemandeurForm



def demandeur_edit(request, demandeur_id):
    demandeur = get_object_or_404(Demandeur, id=demandeur_id)
    return_url = request.GET.get("return_url") or request.POST.get("return_url")

    if request.method == "POST":
        form = DemandeurForm(request.POST, instance=demandeur)
        if form.is_valid():
            form.save()
            return redirect("logement:demandeurs_list")
    else:
        form = DemandeurForm(instance=demandeur)

    return render(request, "logement/demandeur_edit.html", {
        "form": form,
        "demandeur": demandeur,
        "return_url": return_url,
    })

from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET", "POST"])
def demandeur_delete(request, demandeur_id):
    demandeur = get_object_or_404(Demandeur, id=demandeur_id)

    # 🔑 récupération du return_url
    return_url = request.GET.get("return_url") or request.POST.get("return_url")

    if request.method == "POST":
        demandeur.delete()

        if return_url:
            return redirect(return_url)

        return redirect("logement:demandeurs_list")

    return render(request, "logement/demandeur_delete_confirm.html", {
        "demandeur": demandeur,
        "return_url": return_url,
    })


from django.shortcuts import render, get_object_or_404
from logement.models import Demandeur, ContactEntrant

def demandeur_detail(request, demandeur_id):
    d = get_object_or_404(Demandeur, id=demandeur_id)
    return_url = request.GET.get("return_url")

    contacts = (
        get_contacts_for_user(request.user)
        .filter(demandeur=d)
        .select_related("statut", "canal")
        .prefetch_related("thematiques")
        .order_by("-date")
    )

    history = []
    for c in contacts:
        full_text = c.txtdemande
        truncated = len(full_text) > 20
        short_text = full_text[:20] + "…" if truncated else full_text

        history.append({
            "id": c.id,
            "date": c.date.strftime("%d/%m/%Y"),
            "canal": c.canal.libelle,
            "objet": c.objet or "",
            "thematiques": ", ".join(t.libelle_thematique for t in c.thematiques.all()),
            "txt_full": full_text,
            "txt_short": short_text,
            "truncated": truncated,
            "statut": c.statut.libelle,
            "statut_id": c.statut.id,
        })

    return render(request, "logement/demandeur_detail.html", {
        "demandeur": d,
        "history": history,
        "return_url": return_url,
    })


####### POUR LE TRAITEMENT EN MODE INSTRUCTION DE DOSSIER (PAS DE VRAI CONTACT ENTRANT)

# logement/services/contacts.py
from datetime import datetime
from django.utils import timezone

from logement.models import ContactEntrant, Thematique


def create_default_contact_entrant(*, demandeur, domaine):
    """
    Crée un ContactEntrant 'fictif' mais techniquement standard,
    avec les valeurs par défaut (non figées ici, facilement modifiables ensuite).
    """
    ce = ContactEntrant.objects.create(
        date=timezone.now(),
        canal_id=4,   # Instruction de dossier
        statut_id=1,  # Nouveau
        demandeur=demandeur,
        objet="Instruction de dossier",
        txtdemande="Instruction de dossier",
        domaine=domaine,
    )

    # Thématiques cochées par défaut (même logique que step1)
    default_thematics = list(
        Thematique.objects.filter(
            cocher_par_defaut=True,
            groupe__domaine=domaine
        ).values_list("id", flat=True)
    )
    if default_thematics:
        ce.thematiques.set(default_thematics)

    return ce


from django.db.models import Count, Max, Q
from django.db.models.functions import Coalesce
from django.utils.timezone import make_aware
from datetime import datetime
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.contrib import messages
from django.urls import reverse
from urllib.parse import quote as urlquote



from .decorators import domaine_required
from .models import Demandeur
from .forms import DemandeurForm

#Choix ou création d'un demandeur et création d'un contact entrant fictif, correspondant à une instruction, alternative à email_create_step1

@domaine_required
@require_http_methods(["GET", "POST"])
def demandeur_entry_point(request, domaine_id):
    
    domaine = request.domaine
    return_url = request.GET.get("return_url") or request.POST.get("return_url")

    # --------------------------------------------------
    # POST : actions
    # --------------------------------------------------
    if request.method == "POST":
        action = request.POST.get("action")

        # === Utiliser un demandeur existant ===
        if action == "use_existing":
            demandeur = get_object_or_404(
                Demandeur,
                id=request.POST.get("demandeur_id"),
            )

            ce = create_default_contact_entrant(
                demandeur=demandeur,
                domaine=domaine,
            )
            if return_url:
                return redirect(
                    f"{reverse('logement:email_create_step2', args=[ce.id])}"
                    f"?return_url={urlquote(return_url)}"
                )

            return redirect("logement:email_create_step2", contact_id=ce.id)


        # === Créer un nouveau demandeur ===
        if action == "create_demandeur":
            create_form = DemandeurForm(request.POST)

            if create_form.is_valid():
                demandeur = create_form.save()

                ce = create_default_contact_entrant(
                    demandeur=demandeur,
                    domaine=domaine,
                )
                if return_url:
                    return redirect(
                        f"{reverse('logement:email_create_step2', args=[ce.id])}"
                        f"?return_url={urlquote(return_url)}"
                    )

                return redirect("logement:email_create_step2", contact_id=ce.id)


            messages.error(request, "Le formulaire demandeur contient des erreurs.")
        else:
            create_form = DemandeurForm()
    else:
        create_form = DemandeurForm()

    # --------------------------------------------------
    # GET : liste des demandeurs
    # --------------------------------------------------
    q = (request.GET.get("q") or "").strip()
    sort = request.GET.get("sort") or "email"

    qs = Demandeur.objects.all()

    if q:
        qs = qs.filter(
            Q(email__icontains=q) |
            Q(num_unique__icontains=q)
        )

    contacts_visibles_q = (
        Q(contacts_entrants__domaine__is_public=True)
        | Q(contacts_entrants__domaine__user_links__user=request.user)
    )


    qs = qs.annotate(
        last_contact=Max(
            "contacts_entrants__date",
            filter=contacts_visibles_q,
        ),
    )


    sort_map = {
        "email": "email",
        "-email": "-email",
        "last": "last_contact",
        "-last": "-last_contact",
    }
    qs = qs.order_by(sort_map.get(sort, "email"))

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "logement/demandeur_entry_point.html",
        {
            "domaine": domaine,
            "domaine_id": domaine_id,
            "page": page,
            "q": q,
            "sort": sort,
            "create_form": create_form,
            "return_url": return_url,
        },
    )


from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import PieceJointeContactEntrant
from .security import user_has_domaine


@login_required
def piece_jointe_contact_download(request, piece_id):
    pj = get_object_or_404(
        PieceJointeContactEntrant.objects.select_related("contact_entrant__domaine"),
        id=piece_id
    )

    contact = pj.contact_entrant
    if not user_has_domaine(request.user, contact.domaine):
        return HttpResponse("Accès interdit à ce domaine", status=403)

    # réponse binaire
    resp = HttpResponse(pj.contenu, content_type=pj.content_type or "application/octet-stream")
    filename = pj.nom_original or f"piece_jointe_{pj.id}"
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
