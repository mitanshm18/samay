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
