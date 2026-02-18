# logement/stats.py


from datetime import date
from django.shortcuts import render, get_object_or_404
from django.utils.timezone import now
from django.db.models import Count, Value, F
from django.db.models import Func
from django.db.models.functions import Coalesce



from .models import ContactEntrant, Domaine



from datetime import datetime, time, timedelta
from django.utils.timezone import now, make_aware, get_current_timezone

def _get_date_bounds():
    tz = get_current_timezone()
    today_local = now().astimezone(tz).date()

    start_year_local = datetime(today_local.year, 1, 1)
    start_month_local = datetime(today_local.year, today_local.month, 1)

    return {
        "start_year": make_aware(start_year_local, tz),
        "start_month": make_aware(start_month_local, tz),
    }





from collections import defaultdict
from django.utils.timezone import now

def stats_by_statut(domaine):
    """
    Statistiques globales / YTD / MTD par statut
    CALCULÉES À PARTIR DE LA RÉPARTITION MENSUELLE (source fiable)
    """

    today = now().date()
    current_year = today.year
    current_month = today.month

    data = repartition_statut_par_mois_ytd(domaine)

    global_counts = defaultdict(int)
    ytd_counts = defaultdict(int)
    mtd_counts = defaultdict(int)

    for row in data:
        statut = row["statut_libelle"] or "Non défini"
        total = row["total"]

        global_counts[statut] += total

        if row["year"] == current_year:
            ytd_counts[statut] += total

            if row["month"] == current_month:
                mtd_counts[statut] += total

    def as_list(d):
        return [
            {"statut_libelle": k, "total": v}
            for k, v in d.items()
        ]

    return {
        "global": as_list(global_counts),
        "ytd": as_list(ytd_counts),
        "mtd": as_list(mtd_counts),
    }




from collections import defaultdict
from django.utils.timezone import localtime

def evolution_ytd(domaine):
    dates = _get_date_bounds()

    qs = (
        ContactEntrant.objects
        .filter(
            domaine=domaine,
            date__gte=dates["start_year"]
        )
        .values("date")
    )

    data = defaultdict(int)

    for row in qs:
        dt = localtime(row["date"])
        data[(dt.year, dt.month)] += 1

    return [
        {"year": y, "month": m, "total": t}
        for (y, m), t in sorted(data.items())
    ]





def top_thematiques_mtd(domaine, limit=8):
    dates = _get_date_bounds()

    return (
        ContactEntrant.objects
        .filter(
            domaine=domaine,
            date__gte=dates["start_month"],
            thematiques__isnull=False
        )
        .values("thematiques__libelle_thematique")
        .annotate(total=Count("id", distinct=True))
        .order_by("-total")[:limit]
    )





from collections import defaultdict
from django.utils.timezone import localtime

def repartition_statut_par_mois_ytd(domaine):
    dates = _get_date_bounds()

    qs = (
        ContactEntrant.objects
        .filter(
            domaine=domaine,
            date__gte=dates["start_year"]
        )
        .values(
            "date",
            "statut__libelle",
        )
    )

    data = defaultdict(int)

    for row in qs:
        dt = localtime(row["date"])
        statut = row["statut__libelle"] or "Non défini"
        key = (dt.year, dt.month, statut)
        data[key] += 1

    result = []
    for (year, month, statut), total in sorted(data.items()):
        result.append({
            "year": year,
            "month": month,
            "statut_libelle": statut,
            "total": total,
        })

    return result






