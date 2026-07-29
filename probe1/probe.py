"""
Probe 1 — Does content-addressed idempotency survive an LLM agent's context loss?

THE CLAIM UNDER TEST
--------------------
Stripe-style idempotency assumes a deterministic client: the caller retries with a
byte-identical body, so hashing the body yields a stable key and the duplicate is
suppressed. LLM agents are not deterministic clients. If an agent loses context and
regenerates its intent, it may produce a payload that is *semantically identical but
textually different*. The hash differs, the idempotency key misses, the dedupe never
fires, and the action executes twice.

Onchain, "executes twice" is an irreversible duplicate transfer.

WHAT KILLS THE IDEA
-------------------
If regenerated payloads are canonically identical every time, hashing works, Stripe's
model is sufficient, and there is nothing here. That is a real and welcome outcome:
it costs half a day instead of two weeks.

THE TWO ARMS
------------
  A. cold_restart  — identical prompt, fresh context, N times.
                     Tests raw sampling nondeterminism. The weak arm.
  B. log_replay    — the Lobstar Wilde case: the agent's context is gone, so it
                     reconstructs its intent from a log summary rather than the
                     original instruction. Same meaning, different words in.
                     The realistic arm, and where divergence is expected.

THREE COMPARISON LEVELS
-----------------------
  exact      — raw bytes. Naive hashing.
  canonical  — sorted keys, normalized whitespace/number formatting.
               This is what a *competently* implemented content-hash key uses.
  semantic   — only the fields that determine what happens onchain.

The finding that matters is the gap between `canonical` and `semantic`.
canonical < semantic means: the action was the same, the key was not, dedupe failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

# Fields that actually determine what happens onchain. Everything else -- notably
# `reason`, which is free prose -- can vary without changing the effect. That is
# precisely the trap: hashing the whole body folds prose drift into the key.
SEMANTIC_FIELDS = ("action", "chain", "token", "to", "amount")

SYSTEM = """You are the execution planner for an autonomous onchain agent.
Emit exactly one JSON object describing the single transaction to submit. No prose,
no markdown fences, no commentary.

Schema:
  action  string  one of: transfer, contract_call
  chain   string  e.g. base, ethereum
  token   string  token symbol
  to      string  0x-prefixed recipient address
  amount  string  decimal amount as a string
  reason  string  one short sentence explaining why this transaction is correct
"""


@dataclass
class Scenario:
    """One onchain intent, expressed two ways: as an original instruction (arm A)
    and as a log summary the agent would rebuild from after a context wipe (arm B).
    Both must denote the *same* transaction for the probe to mean anything."""

    name: str
    original: str
    log_summary: str


SCENARIOS = [
    Scenario(
        name="aave_repay",
        original=(
            "Your Aave position on Base has a health factor of 1.04, below your 1.10 "
            "floor. Your mandate is to repay USDC debt to restore it. Repaying 250 USDC "
            "brings it to 1.19. Treasury is 0x8Ba1f109551bD432803012645Ac136ddd64DBA72. "
            "Submit the repayment."
        ),
        log_summary=(
            "[recovered log] agent=keeper-01 mandate=maintain_health_factor floor=1.10\n"
            "[recovered log] observed hf=1.04 on aave/base -> breach\n"
            "[recovered log] computed remedy: repay 250 USDC restores hf to 1.19\n"
            "[recovered log] counterparty 0x8Ba1f109551bD432803012645Ac136ddd64DBA72\n"
            "[recovered log] -- context lost before submission --\n"
            "Reconstruct the transaction you were about to submit."
        ),
    ),
    Scenario(
        name="payroll_chunk",
        original=(
            "It is the 1st of the month. Contributor payroll for wallet "
            "0x2170Ed0880ac9A755fd29B2688956BD959F933F8 is due: 90 USDC on Base. "
            "Submit the payment."
        ),
        log_summary=(
            "[recovered log] agent=payroll-runner schedule=monthly day=1\n"
            "[recovered log] due: contributor 0x2170Ed0880ac9A755fd29B2688956BD959F933F8\n"
            "[recovered log] amount=90 token=USDC chain=base status=NOT_CONFIRMED\n"
            "[recovered log] -- context lost before submission --\n"
            "Reconstruct the transaction you were about to submit."
        ),
    ),
    Scenario(
        name="fee_sweep",
        original=(
            "Accrued protocol fees of 42.5 USDC on Base exceed your 40 USDC sweep "
            "threshold. Sweep them to the treasury at "
            "0xdAC17F958D2ee523a2206206994597C13D831ec7."
        ),
        log_summary=(
            "[recovered log] agent=fee-sweeper threshold=40 USDC\n"
            "[recovered log] accrued=42.5 USDC chain=base -> threshold crossed\n"
            "[recovered log] destination treasury 0xdAC17F958D2ee523a2206206994597C13D831ec7\n"
            "[recovered log] -- context lost before submission --\n"
            "Reconstruct the transaction you were about to submit."
        ),
    ),
]


def extract_json(raw: str) -> dict:
    """Models wrap JSON in fences or preamble regardless of instructions."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object found in: {raw[:200]!r}")
    return json.loads(raw[start : end + 1])


def canonical(payload: dict) -> str:
    """What a competent content-addressed idempotency key would hash: sorted keys,
    no incidental whitespace, normalized numeric formatting so "90" and "90.0" agree.
    Deliberately generous -- we want to beat the *strongest* reasonable
    implementation, not a strawman."""

    def norm(k: str, v):
        if not isinstance(v, str):
            return v
        s = " ".join(v.split())
        if k == "amount":
            try:
                return f"{float(s):.8f}".rstrip("0").rstrip(".")
            except ValueError:
                return s
        return s.lower() if k in ("action", "chain", "token", "to") else s

    return json.dumps(
        {k: norm(k, v) for k, v in sorted(payload.items())},
        separators=(",", ":"),
        sort_keys=True,
    )


def semantic(payload: dict) -> str:
    """Only what changes the onchain effect. `reason` is excluded by design."""
    return canonical({k: payload.get(k, "") for k in SEMANTIC_FIELDS})


def h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


@dataclass
class ArmResult:
    scenario: str
    arm: str
    payloads: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def _rate(self, fn) -> float:
        """Fraction of trials landing in the single most common bucket -- i.e. the
        share of retries a hash-based dedupe would actually catch."""
        if not self.payloads:
            return 0.0
        keys = [h(fn(p)) for p in self.payloads]
        return Counter(keys).most_common(1)[0][1] / len(keys)

    def exact(self) -> float:
        return self._rate(lambda p: json.dumps(p, sort_keys=False))

    def canonical(self) -> float:
        return self._rate(canonical)

    def semantic(self) -> float:
        return self._rate(semantic)


def make_generator(provider: str, model: str, temp: float):
    """Return a callable(prompt) -> raw text.

    Provider-pluggable on purpose: if the mechanism is real it should show up on any
    model, not just one vendor's sampler. A gap that appears on Gemini and Claude
    alike is structural; one that appears on only one is an implementation quirk.
    """
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise SystemExit("error: set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey)")
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise SystemExit("error: pip install google-genai")
        client = genai.Client(api_key=key)
        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM, temperature=temp, max_output_tokens=512
        )
        return lambda prompt: client.models.generate_content(
            model=model, contents=prompt, config=cfg
        ).text

    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("error: set ANTHROPIC_API_KEY")
        try:
            from anthropic import Anthropic
        except ImportError:
            raise SystemExit("error: pip install anthropic")
        client = Anthropic()
        return lambda prompt: client.messages.create(
            model=model, max_tokens=512, temperature=temp, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        ).content[0].text

    raise SystemExit(f"error: unknown provider {provider!r}")


def run_arm(generate, sc: Scenario, arm: str, n: int) -> ArmResult:
    prompt = sc.original if arm == "cold_restart" else sc.log_summary
    res = ArmResult(scenario=sc.name, arm=arm)
    for i in range(n):
        try:
            # Each call is a fresh request with no shared history. That IS the
            # context wipe -- there is nothing to carry over between trials.
            res.payloads.append(extract_json(generate(prompt)))
        except Exception as e:  # noqa: BLE001 - a failed trial is data, not a crash
            res.errors.append(f"trial {i}: {type(e).__name__}: {e}")
    return res


def report(results: list[ArmResult]) -> int:
    print("\n" + "=" * 74)
    print("PROBE 1 — content-addressed idempotency under LLM context loss")
    print("=" * 74)
    print("\nMatch rate = share of retries a hash-based dedupe would collapse.")
    print("Lower is worse. The number that matters is canonical vs semantic.\n")
    print(f"{'scenario':<16} {'arm':<14} {'exact':>8} {'canonical':>11} {'semantic':>10}")
    print("-" * 74)

    leaks = []
    for r in results:
        if not r.payloads:
            print(f"{r.scenario:<16} {r.arm:<14} {'NO DATA':>8}")
            continue
        print(
            f"{r.scenario:<16} {r.arm:<14} "
            f"{r.exact():>8.0%} {r.canonical():>11.0%} {r.semantic():>10.0%}"
        )
        # The failure we are hunting: same onchain effect, different hash.
        if r.canonical() < r.semantic():
            leaks.append(r)

    print("\n" + "=" * 74)
    if leaks:
        print("RESULT: MECHANISM CONFIRMED — idea #2 survives.\n")
        print("In these cases the agent regenerated the SAME onchain action with a")
        print("DIFFERENT canonical payload. A content-hash idempotency key would have")
        print("missed, dedupe would not have fired, and the transaction would have")
        print("executed twice:\n")
        for r in leaks:
            gap = (r.semantic() - r.canonical()) * 100
            print(f"  - {r.scenario}/{r.arm}: {gap:.0f} pt gap (canonical misses, semantic agrees)")
        print("\nThis is the gap Stripe-style idempotency cannot see.")
        print("Next: keep the semantic key, drop prose from the hashed surface.")
    else:
        print("RESULT: NOT CONFIRMED — idea #2 is dead, and that is worth knowing.\n")
        print("Canonical payloads were as stable as semantic ones. A well-implemented")
        print("content-hash key is sufficient; there is no gap to sell. Fall back to")
        print("idea #1 (premise invariants), which survived interrogation independently.")
    print("=" * 74 + "\n")

    for r in results:
        for e in r.errors:
            print(f"[warn] {r.scenario}/{r.arm}: {e}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", default="gemini", choices=("gemini", "anthropic"))
    ap.add_argument("--model", default=None, help="default: gemini-2.5-flash / claude-sonnet-5")
    ap.add_argument("--trials", type=int, default=8, help="trials per scenario per arm")
    ap.add_argument("--temperature", type=float, default=1.0,
                    help="1.0 = realistic agent default; 0.0 = best case for hashing")
    ap.add_argument("--dump", metavar="PATH", help="write raw payloads as JSON")
    args = ap.parse_args()

    model = args.model or {"gemini": "gemini-2.5-flash",
                           "anthropic": "claude-sonnet-5"}[args.provider]
    generate = make_generator(args.provider, model, args.temperature)
    print(f"provider={args.provider} model={model} "
          f"trials={args.trials} temperature={args.temperature}")

    results = []
    for sc in SCENARIOS:
        for arm in ("cold_restart", "log_replay"):
            print(f"  running {sc.name}/{arm} ...", flush=True)
            results.append(run_arm(generate, sc, arm, args.trials))

    if args.dump:
        with open(args.dump, "w") as f:
            json.dump(
                [{"scenario": r.scenario, "arm": r.arm, "payloads": r.payloads,
                  "errors": r.errors} for r in results],
                f, indent=2,
            )
        print(f"\nraw payloads -> {args.dump}")

    return report(results)


if __name__ == "__main__":
    sys.exit(main())
