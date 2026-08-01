"""Portable scenarios. Each takes an ExecutionAdapter and knows nothing about it.

Every scenario states a guarantee a builder would reasonably assume, then tries to
break it. Two rules, both learned by getting them wrong:

  1. It must be able to come back clean. A scenario that can only find problems is a
     demo, not a test. `tests/` runs each one against a Mock configured both ways to
     prove it can reach either verdict.
  2. Every FINDING carries evidence a third party can check.
"""

from __future__ import annotations

import concurrent.futures
import time

from .core import Conflict, Result, key, scenario, SEMANTIC_FIELDS


def _me(a):
    return getattr(a, "wallet", "0x0000000000000000000000000000000000000001")


@scenario
def prose_drift(a) -> Result:
    """Does a payload-hash idempotency key survive an LLM rewriting its own prose?"""
    w = _me(a)
    before = {"action": "transfer", "chain_id": a.chain_id, "to_address": w,
              "amount": "0.001", "token_address": "",
              "reason": "Accrued fees exceeded the threshold of 40 USDC"}
    after = dict(before, reason="Accrued fees exceed threshold")

    x = a.transfer(w, "0.001", idempotency_key=key(before))
    y = a.transfer(w, "0.001", idempotency_key=key(after))
    same = x.id == y.id
    return Result(
        "prose_drift",
        "Hashing the whole payload gives a stable idempotency key across a retry",
        "PASS" if same else "FINDING",
        ("Deduplicated correctly." if same else
         "Same transaction, two executions. The payloads differ only in a free-text "
         "`reason` field the model rewrote: observed verbatim from llama-3.3-70b and "
         "gpt-oss-120b at temperature 0."),
        [] if same else [x.id, y.id],
        "-" if same else "HIGH")


@scenario
def semantic_key_fix(a) -> Result:
    """The proposed fix must hold on the same inputs that broke prose_drift."""
    w = _me(a)
    p = {"action": "transfer", "chain_id": a.chain_id, "to_address": w,
         "amount": "0.001", "token_address": ""}
    k = key(p, SEMANTIC_FIELDS)
    x = a.transfer(w, "0.001", idempotency_key=k)
    y = a.transfer(w, "0.001", idempotency_key=k)
    same = x.id == y.id
    return Result(
        "semantic_key_fix",
        "Hashing only the semantic surface survives prose drift",
        "PASS" if same else "FINDING",
        "Both retries collapsed to one execution." if same else
        "The proposed fix did not dedupe: the recommendation is wrong.",
        [x.id] if same else [x.id, y.id],
        "-" if same else "HIGH")


@scenario
def omitted_key(a) -> Result:
    """What does the default path cost when no idempotency key is supplied?"""
    w = _me(a)
    x, y = a.transfer(w, "0.001"), a.transfer(w, "0.001")
    same = x.id == y.id
    return Result(
        "omitted_key",
        "Retrying an identical transfer without a key is safe by default",
        "PASS" if same else "FINDING",
        ("Server-side dedupe caught it." if same else
         "Two identical transfers, two executions. Duplicate protection is opt-in: an "
         "agent that never sets an idempotency key has none, and nothing warns it."),
        [] if same else [x.id, y.id],
        "-" if same else "MEDIUM")


@scenario
def concurrent_same_key(a, n=4) -> Result:
    """Dedupe under a race. Agents retry in parallel; check-then-insert can slip."""
    w = _me(a)
    k = key({"s": "concurrent", "n": time.time()})
    ids, blocked = set(), 0

    def one():
        try:
            return a.transfer(w, "0.001", idempotency_key=k).id
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
        (f"{n} concurrent calls -> {len(ids)} execution, {blocked} rejected 409. The "
         "race is serialised rather than slipping through a check-then-insert."
         if ok else
         f"{n} concurrent calls with one key produced {len(ids)} executions, so "
         "parallel retries defeat the dedupe."),
        sorted(ids), "-" if ok else "HIGH")


@scenario
def amount_formatting(a) -> Result:
    """'0.001' and '0.0010' are one transfer. Does the key survive re-formatting?"""
    w = _me(a)
    p1 = {"action": "transfer", "chain_id": a.chain_id, "to_address": w,
          "amount": "0.001", "token_address": ""}
    p2 = dict(p1, amount="0.0010")
    x = a.transfer(w, "0.001", idempotency_key=key(p1, SEMANTIC_FIELDS))
    y = a.transfer(w, "0.0010", idempotency_key=key(p2, SEMANTIC_FIELDS))
    same = x.id == y.id
    return Result(
        "amount_formatting",
        "Equivalent amount strings yield the same semantic key",
        "PASS" if same else "FINDING",
        ("Numeric normalization held." if same else
         "'0.001' and '0.0010' are the same transfer but hash differently, so even a "
         "semantic key double-spends unless values are normalized before hashing. "
         "This is a finding against the fix, not against the provider."),
        [] if same else [x.id, y.id],
        "-" if same else "MEDIUM")


@scenario
def premise_staleness(a) -> Result:
    """Read-then-act with a premise that provably expires: chain height."""
    w = _me(a)
    n0 = a.block_number()
    e = a.transfer(w, "0.001", idempotency_key=key({"s": "stale", "n": time.time()}))
    st = a.status(e.id)
    n1 = a.block_number()
    stale = n1 > n0
    return Result(
        "premise_staleness",
        "The premise an agent decided on still holds when its tx is included",
        "FINDING" if stale else "PASS",
        (f"Decided at block {n0} on the premise 'block <= {n0}'; the transaction "
         f"landed at or after block {n1}, where it is false. Nothing re-checks the "
         "premise in that window. Off-chain read-then-act cannot be atomic, so this "
         "is inherent: the issue is that nothing says so."
         if stale else f"Same block ({n1}); premise held."),
        [st.tx_hash or e.id, f"decided@{n0}", f"observed@{n1}"],
        "MEDIUM" if stale else "-")


@scenario
def revert_reporting(a) -> Result:
    """A call that reverts must be reported as failed, with a reason."""
    w = _me(a)
    token = getattr(a, "weth", "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14")
    try:
        e = a.contract_call(token, "transfer", args=[w, str(10 ** 30)],
                            idempotency_key=key({"s": "revert", "n": time.time()}))
    except Exception as ex:
        return Result("revert_reporting",
                      "A call that will revert is reported as failed, not completed",
                      "PASS", f"Rejected before submission: {str(ex)[:140]}", [])
    st = a.status(e.id)
    honest = st.status != "completed" or bool(st.error)
    return Result(
        "revert_reporting",
        "A call that will revert is reported as failed, not completed",
        "PASS" if honest else "FINDING",
        (f"Reported status={st.status!r}, error={str(st.error)[:70]!r}."
         if honest else
         "A guaranteed-to-fail call reported success with no error, so any agent "
         "trusting the status field acts on a lie."),
        [e.id], "-" if honest else "HIGH")
