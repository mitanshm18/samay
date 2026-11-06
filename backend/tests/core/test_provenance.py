"""Provenance and synthetic status travel with every value."""

from decimal import Decimal

import pytest

from samay.core import (
    DataStatus,
    Energy,
    MissingValueError,
    Money,
    Provenance,
    ProvenanceError,
    Rate,
    RoundingRule,
    Traced,
    Unit,
    combine_status,
)

SYN = DataStatus.SYNTHETIC
VER = DataStatus.VERIFIED


def add(a: Money, b: Money) -> Money:
    return a + b


def test_leaf_constructors() -> None:
    e = Traced.entered(Money(100), by="plant manager", status=VER)
    x = Traced.extracted(Energy("10"), source="Bill Oct 2026 p.1 'Units'", status=VER)
    s = Traced.estimated(Money(5), basis="average of last 3 months", status=SYN)
    assert (e.provenance, x.provenance, s.provenance) == (
        Provenance.ENTERED,
        Provenance.EXTRACTED,
        Provenance.ESTIMATED,
    )
    assert e.value == Money(100)
    assert x.note == "Bill Oct 2026 p.1 'Units'"
    assert s.is_synthetic
    assert not e.is_synthetic
    assert not e.is_missing


@pytest.mark.parametrize("blank", ["", "   "])
def test_notes_are_required(blank: str) -> None:
    with pytest.raises(ProvenanceError):
        Traced.estimated(Money(5), basis=blank, status=VER)
    with pytest.raises(ProvenanceError):
        Traced.extracted(Money(5), source=blank, status=VER)
    with pytest.raises(ProvenanceError):
        Traced.entered(Money(5), by=blank, status=VER)
    with pytest.raises(ProvenanceError):
        Traced.missing(reason=blank, status=VER)


def test_derive_is_calculated_and_links_inputs() -> None:
    a = Traced.entered(Money(100), by="user", status=VER)
    b = Traced.entered(Money(50), by="user", status=VER)
    total = Traced.derive(add, a, b, description="a + b")
    assert total.value == Money(150)
    assert total.provenance is Provenance.CALCULATED
    assert total.status is VER
    assert total.inputs == (a, b)
    assert total.note == "a + b"


def test_synthetic_spreads_through_a_chain_of_five() -> None:
    rate = Traced.extracted(
        Rate.rupees_per("7", Unit.KWH), source="SAMAY-DEMO-1 (SYNTHETIC)", status=SYN
    )
    units = Traced.extracted(Energy("100"), source="Bill p.1", status=VER)
    fixed = Traced.entered(Money(10000), by="user", status=VER)

    step1 = Traced.derive(lambda r, q: r * q, rate, units, description="energy charge")
    step2 = Traced.derive(lambda x: x.round(RoundingRule.HALF_UP_PAISA), step1, description="round")
    step3 = Traced.derive(add, step2, fixed, description="+ fixed charge")
    step4 = Traced.derive(
        lambda m: m.apply_percent("5", rule=RoundingRule.HALF_UP_PAISA), step3, description="duty"
    )
    step5 = Traced.derive(add, step3, step4, description="total")

    assert step5.value == Money(84000)  # (70000 + 10000) x 1.05
    for step in (step1, step2, step3, step4, step5):
        assert step.status is SYN
    assert set(map(id, step5.leaves())) == {id(rate), id(units), id(fixed)}


def test_all_verified_inputs_give_verified() -> None:
    a = Traced.entered(Money(1), by="u", status=VER)
    assert Traced.derive(add, a, a, description="2a").status is VER


def test_cannot_launder_synthetic_into_verified() -> None:
    syn = Traced.entered(Money(1), by="u", status=SYN)
    with pytest.raises(ProvenanceError, match="synthetic"):
        Traced(Money(1), Provenance.CALCULATED, VER, "x", (syn,))
    ver = Traced.entered(Money(1), by="u", status=VER)
    with pytest.raises(ProvenanceError, match="verified"):
        Traced(Money(1), Provenance.CALCULATED, SYN, "x", (ver,))


def test_missing_blocks_reading_and_spreads() -> None:
    gap = Traced.missing(reason="kVAh not printed on bill", status=VER)
    other = Traced.entered(Money(10), by="u", status=SYN)
    assert gap.is_missing
    with pytest.raises(MissingValueError, match="kVAh not printed"):
        _ = gap.value

    calls: list[object] = []

    def spy(a: Money, b: Money) -> Money:
        calls.append(a)
        return a + b

    result = Traced.derive(spy, other, gap, description="total")
    assert result.is_missing
    assert result.status is SYN  # synthetic still spreads
    assert "kVAh not printed" in result.note
    assert calls == []  # the function is never called with a missing input
    with pytest.raises(MissingValueError):
        _ = result.value
    assert Traced.derive(spy, result, other, description="again").is_missing


def test_structural_rules() -> None:
    leaf = Traced.entered(Money(1), by="u", status=VER)
    gap = Traced.missing(reason="none", status=VER)
    with pytest.raises(ProvenanceError, match="inputs"):
        Traced(Money(1), Provenance.CALCULATED, VER, "x")
    with pytest.raises(ProvenanceError, match="cannot have inputs"):
        Traced(Money(1), Provenance.ENTERED, VER, "x", (leaf,))
    with pytest.raises(ProvenanceError, match="MISSING exactly"):
        Traced(None, Provenance.ENTERED, VER, "x")
    with pytest.raises(ProvenanceError, match="MISSING exactly"):
        Traced(Money(1), Provenance.MISSING, VER, "x")
    with pytest.raises(ProvenanceError, match="must be MISSING"):
        Traced(Money(1), Provenance.CALCULATED, VER, "x", (gap,))
    with pytest.raises(ProvenanceError, match="at least one"):
        Traced.derive(add, description="nothing")


def test_type_checks() -> None:
    with pytest.raises(TypeError, match="float"):
        Traced.entered(1.5, by="u", status=VER)
    with pytest.raises(TypeError, match="Provenance"):
        Traced(Money(1), "entered", VER, "x")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="DataStatus"):
        Traced(Money(1), Provenance.ENTERED, "verified", "x")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tuple"):
        Traced(Money(1), Provenance.CALCULATED, VER, "x", [1])  # type: ignore[arg-type]
    with pytest.raises(ProvenanceError):
        Traced(Money(1), Provenance.ENTERED, VER, None)  # type: ignore[arg-type]


def test_combine_status() -> None:
    assert combine_status([VER, VER]) is VER
    assert combine_status([VER, SYN, VER]) is SYN
    with pytest.raises(ProvenanceError):
        combine_status([])


def test_traced_decimal_values_allowed() -> None:
    t = Traced.entered(Decimal("0.95"), by="u", status=VER)
    assert t.value == Decimal("0.95")


def test_leaves_of_a_leaf_and_shared_inputs() -> None:
    a = Traced.entered(Money(1), by="u", status=VER)
    assert a.leaves() == (a,)
    doubled = Traced.derive(add, a, a, description="a + a")
    assert doubled.leaves() == (a,)
