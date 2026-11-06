"""Test configuration: Hypothesis profiles.

CI sets HYPOTHESIS_PROFILE=ci: a fixed derandomised seed, so runs repeat exactly.
"""

import os

from hypothesis import HealthCheck, settings

settings.register_profile("ci", derandomize=True, max_examples=300, database=None, deadline=None)
settings.register_profile("dev", max_examples=200, deadline=None)
settings.register_profile(
    "thorough", max_examples=5000, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


# ---- decimal context leak guard ---------------------------------------------
# Some tests deliberately change Python's shared decimal context. This hook
# fails any test that leaves the context different from how it found it, so
# one test can never change the arithmetic seen by another.

from collections.abc import Generator  # noqa: E402
from decimal import Context, getcontext  # noqa: E402

import pytest  # noqa: E402


def _snapshot(ctx: Context) -> tuple[object, ...]:
    traps = tuple(sorted(signal.__name__ for signal, on in ctx.traps.items() if on))
    return (ctx.prec, ctx.rounding, ctx.Emin, ctx.Emax, ctx.capitals, ctx.clamp, traps)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, object, object]:
    before = _snapshot(getcontext())
    result = yield
    after = _snapshot(getcontext())
    if after != before:
        pytest.fail(f"{item.nodeid} leaked a modified decimal context: {before} -> {after}")
    return result
