# logement/decorators.py

from functools import wraps

from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from django.http import Http404



from django.http import HttpResponseForbidden
from functools import wraps
from django.shortcuts import get_object_or_404

from .models import Domaine
from .security import user_has_domaine


def domaine_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        domaine_id = kwargs.get("domaine_id")

        if not domaine_id:
            return HttpResponseForbidden("Domaine non spécifié")

        domaine = get_object_or_404(Domaine, pk=domaine_id)

        if not user_has_domaine(request.user, domaine):
            return HttpResponseForbidden("Accès interdit à ce domaine")

        # 🔑 injection standardisée
        request.domaine = domaine

        return view_func(request, *args, **kwargs)

    return _wrapped_view




from django.core.exceptions import PermissionDenied
from .models import Domaine

def domaine_admin_required(view_func):
    def _wrapped(request, *args, **kwargs):
        # 1️⃣ Domaine explicitement fourni (URL / GET / POST)
        domaine_id = (
            kwargs.get("domaine_id")
            or request.GET.get("domaine")
            or request.POST.get("domaine")
        )

        if domaine_id:
            if not Domaine.objects.filter(
                id=domaine_id,
                user_links__user=request.user,
                user_links__is_admin=True,
            ).exists():
                raise PermissionDenied("Vous n’êtes pas administrateur de ce domaine.")
            return view_func(request, *args, **kwargs)

        # 2️⃣ AUCUN domaine précisé → vue globale admin domaine
        if Domaine.objects.filter(
            user_links__user=request.user,
            user_links__is_admin=True,
        ).exists():
            return view_func(request, *args, **kwargs)

        raise PermissionDenied("Vous n’êtes administrateur d’aucun domaine.")
    return _wrapped




from django.core.exceptions import PermissionDenied

def plateforme_admin_required(view_func):
    def _wrapped(request, *args, **kwargs):
        if not hasattr(request.user, "profile") or not request.user.profile.is_plateforme_admin:
            raise PermissionDenied("Accès réservé à l’administrateur de la plateforme.")
        return view_func(request, *args, **kwargs)
    return _wrapped

# logement/decorators.py

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Domaine
from .security import user_is_domaine_admin


def domaine_edit_required(view_func):
    """
    Autorise :
    - plateforme admin
    - OU admin du domaine concerné
    Interdit :
    - domaine public pour les admins métier
    """
    def _wrapped(request, *args, **kwargs):
        domaine_id = kwargs.get("domaine_id")
        if not domaine_id:
            raise PermissionDenied("Domaine non spécifié.")

        domaine = get_object_or_404(Domaine, pk=domaine_id)

        # Plateforme admin → toujours OK
        if (
            hasattr(request.user, "profile")
            and request.user.profile.is_plateforme_admin
        ):
            request.domaine = domaine
            return view_func(request, *args, **kwargs)

        # Domaine public → jamais modifiable par admin métier
        if domaine.is_public:
            raise PermissionDenied("Ce domaine est public et ne peut pas être modifié.")

        # Admin métier du domaine
        if user_is_domaine_admin(request.user, domaine):
            request.domaine = domaine
            return view_func(request, *args, **kwargs)

        raise PermissionDenied("Vous n’êtes pas autorisé à modifier ce domaine.")

    return _wrapped
