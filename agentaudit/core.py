"""Core types for auditing an onchain agent's execution behaviour.

A scenario states a guarantee a builder would reasonably assume, then tries to break it
against a real execution layer. It knows nothing about which layer: everything it needs
goes through an `ExecutionAdapter`, so the same suite runs against KeeperHub, a raw
signer, or anything else that can send a transaction.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

# Fields that determine the onchain effect. Anything else, above all model-authored
# prose, must stay out of an idempotency key.
SEMANTIC_FIELDS = ("action", "chain_id", "to_address", "amount", "token_address")

MIN_EVIDENCE = 1


@dataclass
class Execution:
    """One submitted action, normalized across providers."""
    id: str
    status: str = "unknown"          # completed | failed | pending | unknown
    tx_hash: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "completed"


class Conflict(Exception):
    """The provider refused a duplicate. `kind` is 'in_progress' or 'reused'.

    Both are correct behaviour and must be distinguished from a transport error, or a
    provider that dedupes properly gets scored as if it had crashed.
    """

    def __init__(self, kind: str, raw: str = ""):
        self.kind, self.raw = kind, raw
        super().__init__(f"{kind}: {raw[:120]}")


@runtime_checkable
class ExecutionAdapter(Protocol):
    """What a scenario needs from an execution layer. Implement this to audit yours."""

    name: str
    chain_id: str

    def transfer(self, to: str, amount: str, *, token: str | None = None,
                 idempotency_key: str | None = None) -> Execution: ...

    def contract_call(self, address: str, function: str, *, args: list | None = None,
                      abi: str | None = None,
                      idempotency_key: str | None = None) -> Execution: ...

    def status(self, execution_id: str) -> Execution: ...

    def block_number(self) -> int: ...


@dataclass
class Result:
    name: str
    claim: str
    verdict: str                     # PASS | FINDING | ERROR
    detail: str = ""
    evidence: list = field(default_factory=list)
    severity: str = "-"
    adapter: str = ""

    def validate(self) -> list[str]:
        """A finding without evidence is an assertion. Refuse to ship those."""
        problems = []
        if self.verdict == "FINDING" and len(self.evidence) < MIN_EVIDENCE:
            problems.append(f"{self.name}: FINDING with no evidence")
        if self.verdict == "FINDING" and self.severity == "-":
            problems.append(f"{self.name}: FINDING with no severity")
        return problems


REGISTRY: dict[str, Callable] = {}


def scenario(fn: Callable) -> Callable:
    """Register a scenario. Signature: fn(adapter) -> Result."""
    REGISTRY[fn.__name__] = fn
    return fn


def key(payload: dict, fields=None) -> str:
    """Derive an idempotency key by hashing `fields` of `payload` (all if None)."""
    src = payload if fields is None else {k: payload.get(k, "") for k in fields}
    return "aa-" + hashlib.sha256(json.dumps(src, sort_keys=True).encode()).hexdigest()[:24]


def run(adapter: ExecutionAdapter, only: list[str] | None = None,
        on_result: Callable[[Result], None] | None = None) -> list[Result]:
    out = []
    for nm, fn in REGISTRY.items():
        if only and nm not in only:
            continue
        t0 = time.time()
        try:
            r = fn(adapter)
        except Exception as e:  # a scenario blowing up is data, not a crash
            r = Result(nm, "", "ERROR", f"{type(e).__name__}: {e}"[:300])
        r.adapter = getattr(adapter, "name", "?")
        for p in r.validate():
            r.verdict, r.detail = "ERROR", f"invalid result: {p}"
        out.append(r)
        if on_result:
            on_result(r)
        else:
            print(f"  {r.name:<28} {r.verdict:<8} ({time.time()-t0:.0f}s)", flush=True)
    return out
