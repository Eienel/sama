"""Every scenario must be able to come back clean AND to find a real problem.

A scenario that can only report failure is a demo, not a test, and it is the single
easiest way for an audit tool to become dishonest. These run entirely against the Mock
adapter: no API key, no funds, no network.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentaudit import scenarios  # noqa: F401  (registers them)
from agentaudit.core import REGISTRY, run
from agentaudit.adapters import MockAdapter

# Adapter configured so each scenario's guarantee HOLDS.
GOOD = dict(dedupe=True, honest_errors=True, block_lag=0)
# Adapter configured so it does NOT.
BAD = dict(dedupe=False, honest_errors=False, block_lag=1)

# Scenarios whose subject is the client's key derivation rather than the provider:
# the Mock cannot make these pass, and that is correct.
CLIENT_SIDE = {"prose_drift", "amount_formatting"}


def test_all_scenarios_pass_against_a_correct_provider():
    res = {r.name: r for r in run(MockAdapter(**GOOD), on_result=lambda r: None)}
    bad = [r.name for r in res.values()
           if r.verdict != "PASS" and r.name not in CLIENT_SIDE]
    assert not bad, f"should have passed against a correct provider: {bad}"


def test_scenarios_detect_a_broken_provider():
    res = {r.name: r for r in run(MockAdapter(**BAD), on_result=lambda r: None)}
    for n in ("omitted_key", "premise_staleness", "revert_reporting"):
        assert res[n].verdict == "FINDING", f"{n} missed a broken provider"


def test_client_side_scenarios_are_provider_independent():
    """prose_drift finds the same bug no matter how good the provider is, because the
    bug is in how the caller derives its key."""
    for cfg in (GOOD, BAD):
        res = {r.name: r for r in run(MockAdapter(**cfg), on_result=lambda r: None)}
        assert res["prose_drift"].verdict == "FINDING"
        assert res["semantic_key_fix"].verdict == "PASS" if cfg is GOOD else True


def test_no_finding_ships_without_evidence():
    for cfg in (GOOD, BAD):
        for r in run(MockAdapter(**cfg), on_result=lambda r: None):
            assert not r.validate(), r.validate()


def test_every_scenario_is_registered_and_callable():
    assert len(REGISTRY) >= 7
    for n, fn in REGISTRY.items():
        assert callable(fn), n
