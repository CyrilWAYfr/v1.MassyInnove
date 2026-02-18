from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .models import Canal, Thematique, Groupe, Domaine, Salutations
from .forms import CanalForm, ThematiqueForm, GroupeForm, DomaineForm, SalutationForm
from .decorators import (
    plateforme_admin_required,
    domaine_admin_required,
)

from django.contrib import messages


# ---------------- CANAL ----------------

@plateforme_admin_required
def canal_list(request):
    canaux = Canal.objects.all().order_by("libelle")
    return render(request, "logement/admin/canaux_list.html", {"canaux": canaux})


@plateforme_admin_required
def canal_create(request):
    if request.method == "POST":
        form = CanalForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("logement:canal_list")
    else:
        form = CanalForm()

    return render(request, "logement/admin/canaux_form.html", {"form": form})


@plateforme_admin_required
def canal_edit(request, pk):
    canal = get_object_or_404(Canal, pk=pk)

    if request.method == "POST":
        form = CanalForm(request.POST, instance=canal)
        if form.is_valid():
            form.save()
            return redirect("logement:canal_list")
    else:
        form = CanalForm(instance=canal)

    return render(request, "logement/admin/canaux_form.html", {"form": form, "canal": canal})


@plateforme_admin_required
def canal_delete(request, pk):
    canal = get_object_or_404(Canal, pk=pk)

    if request.method == "POST":
        canal.delete()
        return redirect("logement:canal_list")

    return render(request, "logement/admin/canaux_confirm_delete.html", {"canal": canal})



# ---------------- THEMATIQUE ----------------

@domaine_admin_required
def thematiques_list(request):
    domaines = Domaine.objects.filter(
        user_links__user=request.user,
        user_links__is_admin=True,
    ).order_by("ordre", "libelle").distinct()

    domaine_id = request.GET.get("domaine")

    thematiques = Thematique.objects.filter(
        groupe__domaine__in=domaines
    )

    if domaine_id:
        thematiques = thematiques.filter(groupe__domaine_id=domaine_id)

    return render(request, "logement/admin/thematiques_list.html", {
        "domaines": domaines,
        "thematiques": thematiques,
        "selected_domaine": domaine_id,
    })


@domaine_admin_required
def thematique_create(request):
    groupes_autorises = Groupe.objects.filter(
        domaine__user_links__user=request.user,
        domaine__user_links__is_admin=True,
    ).order_by("domaine__ordre", "ordre", "libelle")

    if request.method == "POST":
        form = ThematiqueForm(request.POST)
    else:
        initial = {}
        if groupes_autorises.count() == 1:
            initial["groupe"] = groupes_autorises.first()
        form = ThematiqueForm(initial=initial)

    # 🔒 restriction serveur
    form.fields["groupe"].queryset = groupes_autorises

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("logement:thematique_list")

    return render(request, "logement/admin/thematiques_form.html", {
        "form": form,
        "thematique": None,
    })




@domaine_admin_required
def thematique_edit(request, pk):
    thematique = get_object_or_404(Thematique, pk=pk)

    groupes_autorises = Groupe.objects.filter(
        domaine__user_links__user=request.user,
        domaine__user_links__is_admin=True,
    )

    if request.method == "POST":
        form = ThematiqueForm(request.POST, instance=thematique)
    else:
        form = ThematiqueForm(instance=thematique)

    form.fields["groupe"].queryset = groupes_autorises

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("logement:thematique_list")

    return render(request, "logement/admin/thematiques_form.html", {
        "form": form,
        "thematique": thematique,
    })




@domaine_admin_required
def thematique_delete(request, pk):
    thematique = get_object_or_404(Thematique, pk=pk)

    if request.method == "POST":
        thematique.delete()
        return redirect("logement:thematique_list")

    return render(request, "logement/admin/thematiques_confirm_delete.html", {"thematique": thematique})


# GROUPES ET DOMAINES
@domaine_admin_required
def groupes_list(request):
    domaines = Domaine.objects.filter(
        user_links__user=request.user,
        user_links__is_admin=True,
    ).order_by("ordre", "libelle").distinct()

    domaine_id = request.GET.get("domaine")

    groupes = Groupe.objects.filter(domaine__in=domaines)

    if domaine_id:
        groupes = groupes.filter(domaine_id=domaine_id)

    return render(request, "logement/admin/groupes_list.html", {
        "domaines": domaines,
        "groupes": groupes,
        "selected_domaine": domaine_id,
    })


@domaine_admin_required
def groupe_create(request):
    domaines_autorises = Domaine.objects.filter(
        user_links__user=request.user,
        user_links__is_admin=True,
    ).order_by("ordre", "libelle")

    if request.method == "POST":
        form = GroupeForm(request.POST)
    else:
        initial = {}
        if domaines_autorises.count() == 1:
            initial["domaine"] = domaines_autorises.first()
        form = GroupeForm(initial=initial)

    # 🔒 restriction serveur
    form.fields["domaine"].queryset = domaines_autorises

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("logement:groupes_list")

    return render(request, "logement/admin/groupe_form.html", {
        "form": form,
        "action": "Créer un groupe",
    })



@domaine_admin_required
def groupe_edit(request, groupe_id):
    groupe = get_object_or_404(Groupe, id=groupe_id)

    domaines_autorises = Domaine.objects.filter(
        user_links__user=request.user,
        user_links__is_admin=True,
    )

    if request.method == "POST":
        form = GroupeForm(request.POST, instance=groupe)
    else:
        form = GroupeForm(instance=groupe)

    form.fields["domaine"].queryset = domaines_autorises

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("logement:groupes_list")

    return render(request, "logement/admin/groupe_form.html", {
        "form": form,
        "action": "Modifier le groupe",
        "groupe": groupe,
    })



@domaine_admin_required
def groupe_delete(request, groupe_id):
    groupe = get_object_or_404(Groupe, id=groupe_id)

    if request.method == "POST":
        groupe.delete()
        return redirect("logement:groupes_list")

    return render(request, "logement/admin/groupe_confirm_delete.html", {
        "groupe": groupe
    })

@domaine_admin_required
def domaines_list(request):
    domaines = Domaine.objects.order_by("ordre", "libelle")
    return render(request, "logement/admin/domaines_list.html", {
        "domaines": domaines
    })

@plateforme_admin_required
def domaine_create(request):
    if request.method == "POST":
        form = DomaineForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("logement:domaines_list")
    else:
        form = DomaineForm()

    return render(request, "logement/admin/domaine_form.html", {
        "form": form,
        "action": "Créer un domaine"
    })

from .decorators import domaine_admin_required

@domaine_admin_required
def domaine_edit(request, domaine_id):
    domaine = get_object_or_404(Domaine, id=domaine_id)

    if request.method == "POST":
        form = DomaineForm(request.POST, instance=domaine)
        if form.is_valid():
            form.save()
            return redirect("logement:domaines_list")
    else:
        form = DomaineForm(instance=domaine)

    return render(request, "logement/admin/domaine_form.html", {
        "form": form,
        "action": "Modifier le domaine",
        "domaine": domaine,
    })

@plateforme_admin_required
def domaine_delete(request, domaine_id):
    domaine = get_object_or_404(Domaine, id=domaine_id)

    if request.method == "POST":
        domaine.delete()
        return redirect("logement:domaines_list")

    return render(request, "logement/admin/domaine_confirm_delete.html", {
        "domaine": domaine
    })


# SALUTATIONS


# -------------------------------------------------
# LISTE
# -------------------------------------------------
@plateforme_admin_required
def salutation_list(request):
    salutations = Salutations.objects.all()
    return render(request, "logement/admin/salutations_list.html", {
        "salutations": salutations,
    })


# -------------------------------------------------
# CRÉATION
# -------------------------------------------------
@plateforme_admin_required
def salutation_create(request):
    if request.method == "POST":
        form = SalutationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "La salutation a été créée avec succès.")
            return redirect("logement:salutation_list")
    else:
        form = SalutationForm()

    return render(request, "logement/admin/salutations_form.html", {
        "form": form,
        "title": "Nouvelle salutation",
        "submit_label": "Créer",
    })


# -------------------------------------------------
# MODIFICATION
# -------------------------------------------------
@plateforme_admin_required
def salutation_update(request, pk):
    salutation = get_object_or_404(Salutations, pk=pk)

    if request.method == "POST":
        form = SalutationForm(request.POST, instance=salutation)
        if form.is_valid():
            form.save()
            messages.success(request, "La salutation a été mise à jour avec succès.")
            return redirect("logement:salutation_list")
    else:
        form = SalutationForm(instance=salutation)

    return render(request, "logement/admin/salutations_form.html", {
        "form": form,
        "title": f"Modifier la salutation : {salutation.libelle}",
        "submit_label": "Enregistrer",
    })


# -------------------------------------------------
# SUPPRESSION
# -------------------------------------------------
@plateforme_admin_required
def salutation_delete(request, pk):
    salutation = get_object_or_404(Salutations, pk=pk)

    if request.method == "POST":
        salutation.delete()
        messages.success(request, "La salutation a été supprimée avec succès.")
        return redirect("logement:salutation_list")

    return render(request, "logement/admin/salutations_confirm_delete.html", {
        "salutation": salutation,
    })



