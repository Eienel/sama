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


MULTICALL3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
SEPOLIA_RPC = "https://ethereum-sepolia-rpc.publicnode.com"


def _rpc(method: str, params: list):
    import urllib.request
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    # Same trap as KeeperHub's edge: public RPCs 403 the default urllib user-agent.
    req = urllib.request.Request(SEPOLIA_RPC, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "chaos-harness/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("result")


def _block_now() -> int:
    """Read chain height through KeeperHub itself, so the premise is observed the
    same way an agent using KeeperHub would observe it."""
    out = call_tool("execute_contract_call", {
        "chain_id": SEPOLIA, "contract_address": MULTICALL3,
        "function_name": "getBlockNumber"})
    # Named single-output functions come back as {"result": {"blockNumber": "..."}};
    # unnamed ones as {"result": "..."}. Accept either.
    r = json.loads(out)["result"]
    return int(r["blockNumber"] if isinstance(r, dict) else r)


def premise_staleness(w: str) -> Result:
    """Read-then-act, with a premise that provably expires.

    The agent observes height N and acts on the premise "block <= N" -- true at the
    moment of decision. If the transaction is included at a height above N, the
    justification for it was false by the time it executed. Nothing anywhere in the
    pipeline notices: simulation checks that the transaction *can* run, never that
    the reason for running it still holds.
    """
    t0 = time.time()
    n_decide = _block_now()

    r = _transfer(w, "0.001", SEPOLIA, _key({"s": "stale", "n": time.time()}))
    tx = _tx_of(r["executionId"])
    if not tx:
        return Result("premise_staleness", "", "ERROR", "no transaction hash returned")

    rcpt = _rpc("eth_getTransactionReceipt", [tx])
    n_incl = int(rcpt["blockNumber"], 16) if rcpt else None
    gap = time.time() - t0
    if n_incl is None:
        return Result("premise_staleness", "", "ERROR", "no receipt")

    stale = n_incl > n_decide
    return Result(
        "premise_staleness",
        "The premise an agent decided on still holds when its tx is included",
        "FINDING" if stale else "PASS",
        (f"Decided at block {n_decide} on the premise 'block <= {n_decide}'. "
         f"Included at block {n_incl}, {n_incl - n_decide} block(s) later "
         f"({gap:.1f}s). The premise was FALSE at inclusion and the transaction "
         "executed anyway. Simulation verifies feasibility, never justification, so "
         "this is invisible: the transaction succeeds and reports success."
         if stale else
         f"Included in the same block ({n_incl}) it was decided on; premise held."),
        [tx, f"decided@{n_decide}", f"included@{n_incl}"],
        "HIGH" if stale else "-",
    )


WETH_SEPOLIA = "0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14"


def conditional_staleness(w: str) -> Result:
    """The same staleness question, aimed at KeeperHub's own primitive.

    `execute_check_and_execute` reads a contract value, evaluates a condition, and
    performs an action if it holds -- the read-then-act pattern, offered so agents do
    not hand-roll it. If the gate is evaluated at one block and the action lands at a
    later one, the guarantee it appears to offer ("only act while this is true") does
    not hold, and it fails in the same way as hand-rolled code while looking safer.

    The premise is chain height, which only ever advances, so a stale read is
    unambiguous rather than a matter of interpretation.
    """
    n = _block_now()
    out = json.loads(call_tool("execute_check_and_execute", {
        "chain_id": SEPOLIA,
        "contract_address": MULTICALL3,
        "function_name": "getBlockNumber",
        "condition": {"operator": "lte", "value": str(n)},
        # A zero-value approve: state-changing, always succeeds, costs nothing.
        "action": {"contract_address": WETH_SEPOLIA, "function_name": "approve",
                   "function_args": json.dumps([w, "0"])},
        "idempotency_key": _key({"s": "cae", "n": time.time()}),
    }))

    if not out.get("executed"):
        return Result("conditional_staleness",
                      "A met condition guarantees the action runs while it still holds",
                      "PASS", "Condition not met; nothing executed.", [])

    observed = int(out.get("conditionResult", {}).get("observedValue", n))
    tx = _tx_of(out["executionId"])
    if not tx:
        return Result("conditional_staleness", "", "ERROR", "no transaction hash")
    rcpt = _rpc("eth_getTransactionReceipt", [tx])
    if not rcpt:
        return Result("conditional_staleness", "", "ERROR", "no receipt")
    incl = int(rcpt["blockNumber"], 16)

    stale = incl > observed
    return Result(
        "conditional_staleness",
        "A met condition guarantees the action runs while it still holds",
        "FINDING" if stale else "PASS",
        (f"Condition 'block <= {observed}' evaluated true at block {observed}; the "
         f"action was included at block {incl}, {incl - observed} block(s) later, "
         "where it is false. KeeperHub's own read-condition-act primitive carries the "
         "gap it exists to remove: the check and the action are not atomic, so the "
         "gate says 'only act while true' and delivers 'act if it was true a moment "
         "ago'. An agent that hand-rolls this at least knows it is racing."
         if stale else
         f"Condition and action both at block {incl}; the gate held."),
        [tx, f"checked@{observed}", f"executed@{incl}"],
        "HIGH" if stale else "-",
    )


def revert_reporting(w: str) -> Result:
    """A reverting call must be reported as failed, with a reason.

    Reliability is only as good as its reporting. If a transaction that reverts is
    reported as completed, every downstream guard an agent builds -- retries, alerts,
    audit review -- is reading a lie.

    ERC20 transfer of a balance we do not have: reverts deterministically.
    """
    huge = str(10 ** 30)
    try:
        out = json.loads(call_tool("execute_contract_call", {
            "chain_id": SEPOLIA, "contract_address": WETH_SEPOLIA,
            "function_name": "transfer", "function_args": json.dumps([w, huge]),
            "idempotency_key": _key({"s": "revert", "n": time.time()})}))
    except RuntimeError as e:
        return Result(
            "revert_reporting",
            "A call that will revert is reported as failed, not completed",
            "PASS",
            f"Rejected before submission: {str(e)[:150]}",
            [])

    eid = out.get("executionId")
    d = json.loads(call_tool("get_direct_execution_status", {"execution_id": eid})) \
        if eid else out
    status = str(d.get("status", "?"))
    err = d.get("error")
    honest = status not in ("completed", "success") or bool(err)
    return Result(
        "revert_reporting",
        "A call that will revert is reported as failed, not completed",
        "PASS" if honest else "FINDING",
        (f"Reported status={status!r}, error={str(err)[:80]!r}. The failure surfaces."
         if honest else
         f"A transfer of 10^30 tokens from a wallet holding none reported "
         f"status={status!r} with no error. A guaranteed-to-fail call is reported as "
         "success, so any agent trusting the status field acts on a lie."),
        [eid or "-"],
        "-" if honest else "HIGH",
    )


def overdraft_transfer(w: str) -> Result:
    """Sending more than the balance: clean rejection, or a stuck nonce?

    A stuck transaction is the expensive failure -- it blocks every later transaction
    from the same account by head-of-line ordering, so one bad send freezes the agent.
    """
    try:
        out = json.loads(call_tool("execute_transfer", {
            "chain_id": SEPOLIA, "to_address": w, "amount": "1000000",
            "idempotency_key": _key({"s": "overdraft", "n": time.time()})}))
    except RuntimeError as e:
        return Result(
            "overdraft_transfer",
            "An unaffordable transfer is rejected cleanly, not left pending",
            "PASS", f"Rejected up front: {str(e)[:150]}", [])

    eid = out.get("executionId")
    d = json.loads(call_tool("get_direct_execution_status", {"execution_id": eid}))
    status = str(d.get("status", "?"))
    stuck = status in ("pending", "submitted", "processing")
    return Result(
        "overdraft_transfer",
        "An unaffordable transfer is rejected cleanly, not left pending",
        "FINDING" if stuck else "PASS",
        (f"status={status!r} -- left in flight. A transaction that can never succeed "
         "occupies a nonce, and nonce ordering means every later transaction from this "
         "wallet is blocked behind it."
         if stuck else
         f"status={status!r}, error={str(d.get('error'))[:70]!r}. Failed cleanly; "
         "no nonce consumed."),
        [eid],
        "HIGH" if stuck else "-",
    )


def silent_noop_node(w: str) -> Result:
    """A workflow whose action node never runs must not report success.

    For a reliability layer the worst outcome is not an error -- it is "your
    automation ran fine" while nothing happened. An agent polling status sees
    success, the audit trail records success, and no alert fires.
    """
    mc3, wid = MULTICALL3, None
    # A node with no actionType: accepted at creation, no validation complaint.
    nodes = [
        {"id": "trigger-1", "type": "trigger", "position": {"x": 0, "y": 0},
         "data": {"type": "trigger", "label": "Manual",
                  "config": {"triggerType": "Manual"}, "status": "idle"}},
        {"id": "read-1", "type": "action", "position": {"x": 300, "y": 0},
         "data": {"type": "action", "label": "Read Block", "status": "idle",
                  "config": {"network": SEPOLIA, "contractAddress": mc3,
                             "abiFunction": "getBlockNumber"}}},
    ]
    try:
        wf = json.loads(call_tool("create_workflow", {
            "name": f"chaos-silent-noop-{int(time.time())}",
            "description": "action node with no actionType",
            "nodes": nodes,
            "edges": [{"id": "e1", "source": "trigger-1", "target": "read-1"}],
            "enabled": True,
            "idempotency_key": _key({"s": "noop", "n": time.time()})}))
        wid = wf["id"]
        ex = json.loads(call_tool("execute_workflow", {"workflowId": wid}))
        time.sleep(6)
        e = json.loads(call_tool("get_execution",
                                 {"executionId": ex["executionId"]}))["logs"]["execution"]
    except RuntimeError as err:
        return Result(
            "silent_noop_node",
            "A workflow whose action node never runs does not report success",
            "PASS",
            f"Rejected at creation: {str(err)[:150]}", [])
    finally:
        if wid:
            try:
                call_tool("delete_workflow", {"workflowId": wid})
            except Exception:
                pass

    trace, status = e.get("executionTrace", []), e.get("status")
    ran = "read-1" in trace
    lied = (status == "success") and not ran
    return Result(
        "silent_noop_node",
        "A workflow whose action node never runs does not report success",
        "FINDING" if lied else "PASS",
        (f"status={status!r} but executionTrace={trace} -- the action node was "
         "skipped and the run still reported success, with error=None. The node was "
         "missing `actionType`; supplying it makes creation reject the workflow for a "
         "missing `abi`, so the *less* complete definition passes validation and "
         "silently does nothing, while the more complete one is caught. An agent sees "
         "a green run and an audit trail of success for an automation that never ran."
         if lied else
         f"status={status!r}, trace={trace}. No silent no-op."),
        [f"trace={trace}", f"status={status}"],
        "HIGH" if lied else "-",
    )


SCENARIOS = [
    prose_drift,
    semantic_key_fix,
    omitted_key,
    concurrent_same_key,
    amount_formatting,
    cross_chain_key_scope,
    premise_staleness,
    conditional_staleness,
    revert_reporting,
    overdraft_transfer,
    silent_noop_node,
]
