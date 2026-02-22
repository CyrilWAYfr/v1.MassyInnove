from collections import defaultdict
from datetime import datetime

from django.db.models import Count
from django.utils.timezone import get_current_timezone, localtime, make_aware, now

from .models import ContactEntrant


def _get_date_bounds():
    tz = get_current_timezone()
    today_local = now().astimezone(tz).date()
    start_year_local = datetime(today_local.year, 1, 1)
    start_month_local = datetime(today_local.year, today_local.month, 1)
    return {
        "start_year": make_aware(start_year_local, tz),
        "start_month": make_aware(start_month_local, tz),
        "current_year": today_local.year,
        "current_month": today_local.month,
    }


def contacts_par_statut(domaine):
    rows = (
        ContactEntrant.objects
        .filter(domaine=domaine)
        .values("statut__libelle")
        .annotate(total=Count("id"))
        .order_by("-total", "statut__libelle")
    )
    return [
        {"statut_libelle": row["statut__libelle"] or "Non défini", "total": row["total"]}
        for row in rows
    ]


def evolution_statut_3_par_mois_ytd(domaine):
    dates = _get_date_bounds()
    qs = (
        ContactEntrant.objects
        .filter(
            domaine=domaine,
            statut_id=3,
            date__gte=dates["start_year"],
        )
        .values("date")
    )
    counts = defaultdict(int)
    for row in qs:
        dt = localtime(row["date"])
        counts[(dt.year, dt.month)] += 1

    year = dates["current_year"]
    return [
        {
            "year": year,
            "month": month,
            "label": f"{month:02d}/{year}",
            "total": counts.get((year, month), 0),
        }
        for month in range(1, dates["current_month"] + 1)
    ]


def top_thematiques_ytd(domaine, limit=5):
    dates = _get_date_bounds()
    rows = (
        ContactEntrant.objects
        .filter(
            domaine=domaine,
            date__gte=dates["start_year"],
            thematiques__isnull=False,
        )
        .values("thematiques__libelle_thematique")
        .annotate(total=Count("id", distinct=True))
        .order_by("-total", "thematiques__libelle_thematique")[:limit]
    )
    return list(rows)


def top_thematiques_mtd(domaine, limit=8):
    dates = _get_date_bounds()
    return (
        ContactEntrant.objects
        .filter(
            domaine=domaine,
            date__gte=dates["start_month"],
            thematiques__isnull=False,
        )
        .values("thematiques__libelle_thematique")
        .annotate(total=Count("id", distinct=True))
        .order_by("-total", "thematiques__libelle_thematique")[:limit]
    )


def repartition_statut_par_mois_ytd(domaine):
    dates = _get_date_bounds()
    qs = (
        ContactEntrant.objects
        .filter(domaine=domaine, date__gte=dates["start_year"])
        .values("date", "statut__libelle")
    )
    data = defaultdict(int)
    for row in qs:
        dt = localtime(row["date"])
        statut = row["statut__libelle"] or "Non défini"
        data[(dt.year, dt.month, statut)] += 1

    return [
        {"year": year, "month": month, "statut_libelle": statut, "total": total}
        for (year, month, statut), total in sorted(data.items())
    ]
