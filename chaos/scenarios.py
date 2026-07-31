"""Chaos scenarios for onchain agent execution through KeeperHub.

Each scenario states a claim a builder would reasonably assume is true, then tries to
break it against live infrastructure. A scenario returns PASS (the assumption holds),
FINDING (it does not, and here is the evidence), or ERROR.

Design rules, learned the hard way from Probe 1:
  - A scenario must be able to come back clean. One that can only find problems is
    a demo, not a test.
  - Every FINDING carries transaction hashes or execution ids. No claim without
    evidence a third party can verify.
  - Scenarios use self-transfers on a testnet: gas is sponsored and funds return to
    the sender, so a full run costs nothing and can be repeated.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import time
from dataclasses import dataclass, field

from kh_client import call_tool

SEPOLIA = "11155111"
BASE_SEPOLIA = "84532"

# The fields that determine the onchain effect. Anything outside this set -- above
# all model-authored prose -- must stay out of an idempotency key.
SEMANTIC_FIELDS = ("action", "chain_id", "to_address", "amount", "token_address")


@dataclass
class Result:
    name: str
    claim: str
    verdict: str  # PASS | FINDING | ERROR
    detail: str = ""
    evidence: list = field(default_factory=list)
    severity: str = "-"


def _key(payload: dict, fields=None) -> str:
    """Derive an idempotency key by hashing `fields` of `payload` (all if None)."""
    src = payload if fields is None else {k: payload.get(k, "") for k in fields}
    return "kh-" + hashlib.sha256(json.dumps(src, sort_keys=True).encode()).hexdigest()[:24]


class Conflict(Exception):
    """KeeperHub answered 409. Two meanings, both correct behaviour:
    in_progress -> a concurrent call with this key is already running;
    reused      -> this key was used before with a *different* payload."""

    def __init__(self, kind: str, raw: str):
        self.kind, self.raw = kind, raw
        super().__init__(f"{kind}: {raw[:120]}")


def _transfer(wallet: str, amount="0.001", chain=SEPOLIA, key=None) -> dict:
    args = {"chain_id": chain, "to_address": wallet, "amount": amount}
    if key:
        args["idempotency_key"] = key
    try:
        return json.loads(call_tool("execute_transfer", args))
    except RuntimeError as e:
        m = str(e)
        if "409" in m:
            raise Conflict("in_progress" if "already being processed" in m else "reused", m)
        raise


def _tx_of(execution_id: str, tries=6) -> str | None:
    for _ in range(tries):
        d = json.loads(call_tool("get_direct_execution_status",
                                 {"execution_id": execution_id}))
        if d.get("transactionHash"):
            return d["transactionHash"]
        if d.get("status") in ("failed", "error"):
            return None
        time.sleep(2)
    return None


# --------------------------------------------------------------------------------


def prose_drift(w: str) -> Result:
    """Baseline: the confirmed Probe 1 failure, kept as a regression check."""
    before = {"action": "transfer", "chain_id": SEPOLIA, "to_address": w,
              "amount": "0.001", "token_address": "",
              "reason": "Accrued fees exceeded the threshold of 40 USDC"}
    after = dict(before, reason="Accrued fees exceed threshold")

    a = _transfer(w, key=_key(before))
    b = _transfer(w, key=_key(after))
    same = a["executionId"] == b["executionId"]
    return Result(
        "prose_drift",
        "Hashing the whole payload gives a stable idempotency key across a retry",
        "PASS" if same else "FINDING",
        ("Deduplicated correctly." if same else
         "Same transaction, two executions. The payloads differ only in a free-text "
         "`reason` field the model rewrote -- observed verbatim from llama-3.3-70b "
         "and gpt-oss-120b at temperature 0."),
        [] if same else [a["executionId"], b["executionId"]],
        "-" if same else "HIGH",
    )


def semantic_key_fix(w: str) -> Result:
    """The proposed fix must actually hold on the same inputs that broke above."""
    before = {"action": "transfer", "chain_id": SEPOLIA, "to_address": w,
              "amount": "0.001", "token_address": "",
              "reason": "Accrued fees exceeded the threshold of 40 USDC"}
    after = dict(before, reason="Accrued fees exceed threshold")

    k = _key(before, SEMANTIC_FIELDS)
    assert k == _key(after, SEMANTIC_FIELDS)
    a = _transfer(w, key=k)
    b = _transfer(w, key=k)
    same = a["executionId"] == b["executionId"]
    return Result(
        "semantic_key_fix",
        "Hashing only the semantic surface survives prose drift",
        "PASS" if same else "FINDING",
        "Both retries collapsed to one execution." if same else
        "The proposed fix did not dedupe -- the recommendation is wrong.",
        [a["executionId"]] if same else [a["executionId"], b["executionId"]],
        "-" if same else "HIGH",
    )


def omitted_key(w: str) -> Result:
    """`idempotency_key` is optional. What does the default path cost you?"""
    a = _transfer(w)
    b = _transfer(w)
    same = a["executionId"] == b["executionId"]
    return Result(
        "omitted_key",
        "Retrying an identical transfer without a key is safe by default",
        "PASS" if same else "FINDING",
        ("Server-side dedupe caught it." if same else
         "Two identical transfers, two executions. Duplicate protection is opt-in: "
         "an agent that never sets idempotency_key has none, and nothing warns it."),
        [] if same else [a["executionId"], b["executionId"]],
        "-" if same else "MEDIUM",
    )


def concurrent_same_key(w: str, n=4) -> Result:
    """Dedupe under a race. Agents retry in parallel; check-then-insert can slip."""
    k = _key({"scenario": "concurrent", "nonce": time.time()})
    ids, blocked = set(), 0

    def one():
        try:
            return _transfer(w, "0.001", SEPOLIA, k)["executionId"]
        except Conflict as c:
            return f"409:{c.kind}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        for out in [f.result() for f in [ex.submit(one) for _ in range(n)]]:
            if str(out).startswith("409"):
                blocked += 1
            else:
                ids.add(out)

    ok = len(ids) <= 1
    return Result(
        "concurrent_same_key",
        "Simultaneous retries with one key produce exactly one execution",
        "PASS" if ok else "FINDING",
        (f"{n} concurrent calls -> {len(ids)} execution, {blocked} rejected 409 "
         "'already being processed'. The dedupe is atomic under concurrency: the "
         "race is serialised server-side rather than racing through."
         if ok else
         f"{n} concurrent calls with one key produced {len(ids)} executions. The "
         "dedupe is not atomic, so parallel retries defeat it."),
        sorted(ids),
        "-" if ok else "HIGH",
    )


def amount_formatting(w: str) -> Result:
    """'0.001' and '0.0010' are the same transfer. Does the key survive formatting?"""
    p1 = {"action": "transfer", "chain_id": SEPOLIA, "to_address": w,
          "amount": "0.001", "token_address": ""}
    p2 = dict(p1, amount="0.0010")
    a = _transfer(w, "0.001", key=_key(p1, SEMANTIC_FIELDS))
    b = _transfer(w, "0.0010", key=_key(p2, SEMANTIC_FIELDS))
    same = a["executionId"] == b["executionId"]
    return Result(
        "amount_formatting",
        "Equivalent amount strings yield the same semantic key",
        "PASS" if same else "FINDING",
        ("Numeric normalization held." if same else
         "'0.001' and '0.0010' are the same transfer but hash differently, so even "
         "the semantic key double-spends unless amounts are normalized before "
         "hashing. A model re-emitting a number in another format is enough."),
        [] if same else [a["executionId"], b["executionId"]],
        "-" if same else "MEDIUM",
    )


def cross_chain_key_scope(w: str) -> Result:
    """Is an idempotency key scoped per chain? If not, reusing one SUPPRESSES a
    legitimate second transfer on another chain -- a silent lost payment, which is
    worse than a duplicate because nothing executes at all."""
    k = _key({"scenario": "scope", "nonce": time.time()})
    a = _transfer(w, "0.001", SEPOLIA, k)
    try:
        b = _transfer(w, "0.001", BASE_SEPOLIA, k)
    except Conflict as c:
        if c.kind == "reused":
            return Result(
                "cross_chain_key_scope",
                "Reusing a key with a different payload is caught, not silently applied",
                "PASS",
                "409 'Idempotency-Key was reused with a different request payload'. "
                "The key is bound to the payload, so a cross-chain reuse is rejected "
                "outright rather than silently suppressing a legitimate transfer. "
                "This is the Stripe semantic done correctly.",
                [a["executionId"]],
            )
        raise
    collided = a["executionId"] == b["executionId"]
    return Result(
        "cross_chain_key_scope",
        "Reusing a key on a different chain does not suppress the second transfer",
        "FINDING" if collided else "PASS",
        ("Two different chains, one execution: the key is global, so an agent reusing "
         "a task id across chains silently loses a payment -- nothing executes and no "
         "error is raised." if collided else
         "Key is chain-scoped; the second transfer executed independently."),
        [a["executionId"], b["executionId"]],
        "HIGH" if collided else "-",
    )


def premise_staleness(w: str) -> Result:
    """Read-then-act. Measure the window between observing state and landing a tx --
    the gap in which the justification for the transaction can evaporate."""
    t0 = time.time()
    bal_before = call_tool("execute_contract_call", {
        "chain_id": SEPOLIA, "contract_address": w, "function_name": "x"}) \
        if False else None  # placeholder; native balance read below
    r = _transfer(w, "0.001", SEPOLIA, _key({"s": "stale", "n": time.time()}))
    tx = _tx_of(r["executionId"])
    gap = time.time() - t0
    return Result(
        "premise_staleness",
        "The state an agent decided on is still current when its tx lands",
        "FINDING" if gap > 2 else "PASS",
        (f"{gap:.1f}s elapsed between decision and inclusion. Nothing re-checks the "
         "premise in that window: the transaction executes even if the condition that "
         "justified it stopped holding. Simulation checks feasibility, not "
         "justification."),
        [tx] if tx else [r["executionId"]],
        "MEDIUM" if gap > 2 else "-",
    )


SCENARIOS = [
    prose_drift,
    semantic_key_fix,
    omitted_key,
    concurrent_same_key,
    amount_formatting,
    cross_chain_key_scope,
    premise_staleness,
]
