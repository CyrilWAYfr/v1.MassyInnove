from django.urls import path
from . import views
from . import views_admin


app_name = "logement"   # important pour le namespace

urlpatterns = [
    
    # Administration métier
    path("admin/canaux/", views_admin.canal_list, name="canal_list"),
    path("admin/canaux/ajout/", views_admin.canal_create, name="canal_create"),
    path("admin/canaux/<int:pk>/edit/", views_admin.canal_edit, name="canal_edit"),
    path("admin/canaux/<int:pk>/delete/", views_admin.canal_delete, name="canal_delete"),

    # --- Gestion des thématiques ---
    path("admin/thematiques/", views_admin.thematiques_list, name="thematique_list"),
    path("admin/thematiques/ajout/", views_admin.thematique_create, name="thematique_create"),
    path("admin/thematiques/<int:pk>/edit/", views_admin.thematique_edit, name="thematique_edit"),
    path("admin/thematiques/<int:pk>/delete/", views_admin.thematique_delete, name="thematique_delete"),
    
    # --- Gestion des groupes ---
    path("admin/groupes/", views_admin.groupes_list, name="groupes_list"),
    path("admin/groupes/nouveau/", views_admin.groupe_create, name="groupe_create"),
    path("admin/groupes/<int:groupe_id>/edit/", views_admin.groupe_edit, name="groupe_edit"),
    path("admin/groupes/<int:groupe_id>/delete/", views_admin.groupe_delete, name="groupe_delete"),

    # --- Gestion des domaines ---
    path("admin/domaines/", views_admin.domaines_list, name="domaines_list"),
    path("admin/domaines/nouveau/", views_admin.domaine_create, name="domaine_create"),
    path("admin/domaines/<int:domaine_id>/edit/", views_admin.domaine_edit, name="domaine_edit"),
    path("admin/domaines/<int:domaine_id>/delete/", views_admin.domaine_delete, name="domaine_delete"),

    # --- Gestion des salutations ---
    path("admin/salutations/", views_admin.salutation_list, name="salutation_list"),
    path("admin/salutations/nouveau/", views_admin.salutation_create, name="salutation_create"),
    path("admin/salutations/<int:pk>/modifier/", views_admin.salutation_update, name="salutation_update"),
    path("admin/salutations/<int:pk>/supprimer/", views_admin.salutation_delete, name="salutation_delete"),
    
    # Accueil et vues générales
    path("", views.logement_dashboard, name="dashboard"),
    path("demo", views.home_demo, name="home_demo"),
    path("home_vincent", views.home_vincent, name="home_vincent"),
    
    # Gestion des contacts
    path("<int:domaine_id>/contacts/", views.contact_list, name="contact_list"),
    path("contacts/", views.contact_list, name="contact_list"),
    path("<int:domaine_id>/contacts/<int:contact_id>/delete/", views.contact_delete, name="contact_delete"),
    
    # Gestion des demandeurs
    path("demandeurs/", views.demandeurs_list, name="demandeurs_list"),
    path("demandeurs/<int:demandeur_id>/", views.demandeur_detail, name="demandeur_detail"),
    path("demandeurs/<int:demandeur_id>/edit/", views.demandeur_edit, name="demandeur_edit"),
    path("demandeurs/<int:demandeur_id>/delete/", views.demandeur_delete, name="demandeur_delete"),
    path("<int:domaine_id>/demandeur/", views.demandeur_entry_point, name="demandeur_entry_point"),
    path("<int:domaine_id>/blacklist/", views.blacklist_manage, name="blacklist_manage"),
    path("<int:domaine_id>/blacklist/<int:entry_id>/delete/", views.blacklist_delete, name="blacklist_delete"),

    # Traitement des emails entrants
    path("check-demandeur/", views.check_demandeur, name="check_demandeur"),
    path("<int:domaine_id>/emails/nouveau/", views.email_create_step1, name="email_create_step1"),
    path("<int:domaine_id>/emails/nouveau/<int:demandeur_id>/", views.email_create_step1, name="email_create_step1"),
    path("emails/<int:contact_id>/caracteriser/", views.email_create_step2, name="email_create_step2"),
    path("emails/<int:contact_id>/proposer-reponse/", views.proposer_reponse, name="proposer_reponse"),
    path("pieces-jointes/<int:piece_id>/download/", views.piece_jointe_contact_download, name="piece_jointe_contact_download"),


    ]
