# logement/security.py

from django.contrib.auth.models import AnonymousUser
from django.shortcuts import get_object_or_404
from django.http import Http404

from .models import Domaine, DomaineUser


def get_user_domaines(user):
    """
    Retourne le queryset des domaines accessibles à l'utilisateur.
    """
    if not user or isinstance(user, AnonymousUser):
        return Domaine.objects.none()

    return Domaine.objects.filter(
        user_links__user=user
    ).distinct()


def user_has_domaine(user, domaine: Domaine) -> bool:
    """
    Indique si l'utilisateur a accès à ce domaine.
    """
    if not user or isinstance(user, AnonymousUser):
        return False

    # Domaine public → accès lecture accordé à tous les users authentifiés
    if domaine.is_public:
        return True

    return DomaineUser.objects.filter(
        user=user,
        domaine=domaine
    ).exists()


def user_is_domaine_admin(user, domaine: Domaine) -> bool:
    """
    Indique si l'utilisateur est administrateur de ce domaine.
    """
    if not user or isinstance(user, AnonymousUser):
        return False

    return DomaineUser.objects.filter(
        user=user,
        domaine=domaine,
        is_admin=True
    ).exists()


from .models import ContactEntrant
from django.db.models import Q

def get_contacts_for_user(user):
    """
    Retourne le queryset des contacts accessibles à l'utilisateur,
    tous domaines confondus.
    """
    if not user or not user.is_authenticated:
        return ContactEntrant.objects.none()

    return (
        ContactEntrant.objects
        .filter(
            Q(domaine__is_public=True)
            | Q(domaine__user_links__user=user)
        )
        .distinct()
    )
