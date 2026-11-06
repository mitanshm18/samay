"""SAMAY-DEMO-1: a SYNTHETIC tariff for development and tests.

Every number here is made up. None of it is a UP (UPERC) rate or rule, and a
bill computed with it is not a real bill. The structure is documented in
docs/tariffs/SAMAY-DEMO-1.md; a real tariff will replace it only after the
order is checked line by line.
"""

from decimal import Decimal

from samay.core import DataStatus, Rate, RateBasis, RoundingRule, Unit

from .model import Assumption, ComponentCode, ComponentTerms, Tariff, TodRate, TodZone

TARIFF_ID = "SAMAY-DEMO-1"

_SYNTHETIC = Assumption("synthetic", "All rates are synthetic placeholders, not UP tariff rates.")
_NO_PRORATION = Assumption(
    "no-proration",
    "Charges are per billing period and are not prorated by period length.",
)
_LINE_ROUNDING = Assumption(
    "line-rounding", "Each money line is rounded once, half-up to the paisa."
)


def _terms(code: ComponentCode, label: str, *extra: Assumption) -> ComponentTerms:
    return ComponentTerms(code, label, (_SYNTHETIC, *extra))


SAMAY_DEMO_1 = Tariff(
    tariff_id=TARIFF_ID,
    name="SAMAY demo HT industrial tariff (synthetic)",
    status=DataStatus.SYNTHETIC,
    demand_rate=Rate.rupees_per("400", Unit.KVA, RateBasis.PER_UNIT_PER_BILLING_PERIOD),
    demand_floor_percent=Decimal(75),
    excess_demand_multiplier=Decimal("1.5"),
    energy_rate=Rate.rupees_per("9", Unit.KVAH),
    tod_rates=(
        TodRate(TodZone.PEAK, "18:00-22:00", Rate.rupees_per("1.50", Unit.KVAH)),
        TodRate(TodZone.OFF_PEAK, "22:00-06:00", Rate.rupees_per("-1.00", Unit.KVAH)),
        TodRate(TodZone.NORMAL, "06:00-18:00", Rate.rupees_per("0", Unit.KVAH)),
    ),
    duty_percent=Decimal(5),
    line_rounding=RoundingRule.HALF_UP_PAISA,
    total_rounding=RoundingRule.HALF_UP_RUPEE,
    components=(
        _terms(
            ComponentCode.DEMAND_CHARGE,
            "Demand charge",
            Assumption(
                "demand-floor",
                "Billing demand is the higher of recorded MD and 75% of contract demand, "
                "kept exact (never rounded).",
            ),
            _NO_PRORATION,
            _LINE_ROUNDING,
        ),
        _terms(
            ComponentCode.EXCESS_DEMAND_CHARGE,
            "Excess demand charge",
            Assumption(
                "excess-demand",
                "Demand above contract demand pays 1.5 times the demand rate, "
                "in addition to the demand charge.",
            ),
            _LINE_ROUNDING,
        ),
        _terms(
            ComponentCode.ENERGY_CHARGE,
            "Energy charge",
            Assumption("kvah-billing", "Energy is billed on kVAh."),
            _LINE_ROUNDING,
        ),
        _terms(
            ComponentCode.TOD_ADJUSTMENT,
            "Time-of-day adjustment",
            Assumption(
                "tod-zones",
                "Zone kVAh comes from the meter; the three zones must add up to total kVAh. "
                "Without zone data the adjustment is MISSING, never zero.",
            ),
            Assumption("tod-rounding", "The zone amounts are added exactly and rounded once."),
        ),
        _terms(
            ComponentCode.ELECTRICITY_DUTY,
            "Electricity duty",
            Assumption(
                "duty-base",
                "Duty is 5% of the rounded demand, excess demand, energy and ToD lines; "
                "printed 'other' lines are not part of the base.",
            ),
            _LINE_ROUNDING,
        ),
        _terms(
            ComponentCode.ROUNDING_OFF,
            "Rounding off",
            Assumption(
                "total-rounding",
                "The payable total is rounded half-up to the rupee; the difference is "
                "shown as its own line.",
            ),
        ),
    ),
    assumptions=(
        _SYNTHETIC,
        Assumption(
            "power-factor",
            "Power factor is shown for information only; this tariff has no power factor "
            "charge or rebate.",
        ),
    ),
)
