from collections import defaultdict
from datetime import datetime

from django.db.models import Count
from django.utils.timezone import get_current_timezone, localtime, make_aware, now

from .models import ContactEntrant, StatutContact


MOIS_FR = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def _normalize_status_label(label):
    if not label:
        return "Non défini"
    if label == "Repondu":
        return "Répondu"
    return label


def _get_date_bounds():
    tz = get_current_timezone()
    today_local = now().astimezone(tz).date()
    start_year_local = datetime(today_local.year, 1, 1)
    start_month_local = datetime(today_local.year, today_local.month, 1)
    if today_local.month == 12:
        start_next_month_local = datetime(today_local.year + 1, 1, 1)
    else:
        start_next_month_local = datetime(today_local.year, today_local.month + 1, 1)

    return {
        "start_year": make_aware(start_year_local, tz),
        "start_month": make_aware(start_month_local, tz),
        "start_next_month": make_aware(start_next_month_local, tz),
        "current_year": today_local.year,
        "current_month": today_local.month,
    }


def _month_key(year, month):
    return f"{year}-{month:02d}"


def _month_label(year, month):
    return f"{MOIS_FR[month - 1]} {year}"


def _month_options_current_year():
    dates = _get_date_bounds()
    year = dates["current_year"]
    month_options = []
    for month in range(1, dates["current_month"] + 1):
        month_options.append(
            {
                "value": _month_key(year, month),
                "label": _month_label(year, month),
                "year": year,
                "month": month,
            }
        )
    return month_options


def contacts_par_statut_par_mois(domaine):
    dates = _get_date_bounds()
    qs = (
        ContactEntrant.objects
        .filter(domaine=domaine, date__gte=dates["start_year"])
        .values("date", "statut__libelle")
    )

    counts = defaultdict(int)
    for row in qs:
        dt = localtime(row["date"])
        if dt.year != dates["current_year"] or dt.month > dates["current_month"]:
            continue
        statut = _normalize_status_label(row["statut__libelle"])
        counts[(dt.year, dt.month, statut)] += 1

    month_options = _month_options_current_year()
    data_by_month = {}
    for m in month_options:
        rows = []
        for (year, month, statut), total in counts.items():
            if year == m["year"] and month == m["month"]:
                rows.append({"statut_libelle": statut, "total": total})
        data_by_month[m["value"]] = sorted(rows, key=lambda x: (-x["total"], x["statut_libelle"]))

    default_month_value = _month_key(dates["current_year"], dates["current_month"])
    default_month_label = _month_label(dates["current_year"], dates["current_month"])
    return {
        "month_options": month_options,
        "default_month_value": default_month_value,
        "default_month_label": default_month_label,
        "data_by_month": data_by_month,
    }


def evolution_par_statut_mensuelle_ytd(domaine):
    dates = _get_date_bounds()
    year = dates["current_year"]
    month_labels = [_month_label(year, m) for m in range(1, dates["current_month"] + 1)]

    qs = (
        ContactEntrant.objects
        .filter(domaine=domaine, date__gte=dates["start_year"])
        .values("date", "statut__libelle")
    )
    counts = defaultdict(int)
    for row in qs:
        dt = localtime(row["date"])
        if dt.year != year or dt.month > dates["current_month"]:
            continue
        statut = _normalize_status_label(row["statut__libelle"])
        counts[(statut, dt.month)] += 1

    status_options = [
        _normalize_status_label(s.libelle) for s in StatutContact.objects.all().order_by("id")
    ]
    seen = set(status_options)
    for statut, _month in counts.keys():
        if statut not in seen:
            status_options.append(statut)
            seen.add(statut)

    data_by_status = {}
    for statut in status_options:
        data_by_status[statut] = [
            counts.get((statut, month), 0)
            for month in range(1, dates["current_month"] + 1)
        ]

    default_status = "Répondu" if "Répondu" in status_options else (status_options[0] if status_options else "")
    return {
        "month_labels": month_labels,
        "status_options": status_options,
        "default_status": default_status,
        "data_by_status": data_by_status,
    }


def _top_thematiques_from_queryset(base_qs, limit):
    rows = (
        base_qs
        .filter(thematiques__isnull=False)
        .values("thematiques__libelle_thematique")
        .annotate(total=Count("id", distinct=True))
        .order_by("-total", "thematiques__libelle_thematique")[:limit]
    )
    return [
        {
            "libelle": row["thematiques__libelle_thematique"],
            "total": row["total"],
        }
        for row in rows
    ]


def top_thematiques_par_periode(domaine, limit=5):
    dates = _get_date_bounds()
    base = ContactEntrant.objects.filter(domaine=domaine)
    return {
        "month": _top_thematiques_from_queryset(base.filter(date__gte=dates["start_month"]), limit),
        "ytd": _top_thematiques_from_queryset(base.filter(date__gte=dates["start_year"]), limit),
        "all": _top_thematiques_from_queryset(base, limit),
    }
