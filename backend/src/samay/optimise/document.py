"""The optimisation report as JSON-ready data (samay.optimisation/1).

Money is a string of paise plus its display text, never a JSON number; a value
that is not available is null with the reason alongside.
"""

from __future__ import annotations

from typing import Any

from samay.core import Money

from .engine import Kind, OptimisationReport, Recommendation, Saving

FORMAT = "samay.optimisation/1"


def _money(value: Money | None) -> dict[str, str] | None:
    return None if value is None else {"paise": str(value.paise), "inr": value.format_inr()}


def _quantity(value: Any) -> str | None:
    return None if value is None else str(value.value)


def _saving(saving: Saving) -> dict[str, Any]:
    return {
        "status": saving.status.value,
        "note": saving.note,
        "scenario": saving.scenario,
        "current_total": _money(saving.current_total),
        "scenario_total": _money(saving.scenario_total),
        "amount": _money(saving.amount),
    }


def _recommendation(item: Recommendation) -> dict[str, Any]:
    return {
        "key": item.key,
        "category": item.category.value,
        "kind": item.kind.value,
        "title": item.title,
        "finding": item.finding,
        "action": item.action,
        "confidence": item.confidence.value,
        "confidence_reason": item.confidence_reason,
        "saving": _saving(item.saving),
        "metrics": [{"label": m.label, "value": m.value} for m in item.metrics],
        "basis": list(item.basis),
        "assumptions": list(item.assumptions),
        "missing_data": list(item.missing_data),
    }


def optimisation_document(report: OptimisationReport) -> dict[str, Any]:
    profile = report.profile
    return {
        "format": FORMAT,
        "bill_id": report.bill_id,
        "tariff": {"id": report.tariff_id, "status": report.tariff_status.value},
        "synthetic": report.synthetic,
        "banner": report.banner,
        "current_total": _money(report.current_total),
        "profile": {
            "contract_demand_kva": _quantity(profile.contract_demand_kva),
            "recorded_md_kva": _quantity(profile.recorded_md_kva),
            "demand_floor_kva": profile.demand_floor_kva,
            "billing_demand_kva": profile.billing_demand_kva,
            "kwh": _quantity(profile.kwh),
            "kvah": _quantity(profile.kvah),
            "power_factor": profile.power_factor,
            "period_hours": profile.period_hours,
            "load_factor_percent": profile.load_factor_percent,
            "zones": [
                {
                    "zone": z.zone.value,
                    "hours": z.hours,
                    "kvah": _quantity(z.kvah),
                    "percent": z.percent,
                }
                for z in profile.zones
            ],
        },
        "counts": {kind.value: str(report.count(kind)) for kind in Kind},
        "recommendations": [_recommendation(r) for r in report.recommendations],
    }
