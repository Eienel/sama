# KeeperHub Chaos Harness

Deliberately breaks agent execution through KeeperHub and reports what survives.

KeeperHub's pitch is reliability. Nothing currently lets you *check* that claim — the
audit trail records every trigger, simulation, transaction and outcome, and nobody
reads it back. This runs the failure modes that are documented in the wild against
live infrastructure and publishes a scoreboard.

Every run costs nothing: self-transfers on Sepolia, gas sponsored, funds return to the
sender. A full pass is repeatable indefinitely.

## Latest run

```
scenario                verdict   sev     claim
prose_drift             FINDING   HIGH    payload-hash key is stable across a retry
semantic_key_fix        PASS      -       semantic-surface key survives prose drift
omitted_key             FINDING   MEDIUM  retry without a key is safe by default
concurrent_same_key     PASS      -       simultaneous retries -> one execution
amount_formatting       FINDING   MEDIUM  equivalent amounts yield the same key
cross_chain_key_scope   PASS      -       key reuse w/ different payload is caught
premise_staleness       FINDING   MEDIUM  decided state still current when tx lands
```

**4 findings / 7 scenarios.**

## What KeeperHub got right

Worth stating first, because two of these were scenarios written expecting a failure:

- **Dedupe is atomic under concurrency.** Four simultaneous calls with one key produce
  one execution; the rest are rejected `409 already being processed`. The race is
  serialised server-side rather than slipping through a check-then-insert.
- **Keys are bound to payloads.** Reusing a key with a different payload returns
  `409 Idempotency-Key was reused with a different request payload` instead of
  silently applying the old result. That is the Stripe semantic done correctly, and it
  rules out a whole class of silent-lost-payment bugs.
- Given a stable key, dedupe is exactly right.

## The findings

### HIGH — `prose_drift`

Hashing the request body is the textbook idempotency-key derivation. When the caller
is an LLM, the body contains model-authored prose, and that prose is not stable across
a context loss. Two payloads differing only in a `reason` field produced two keys, two
executions, and two transactions onchain for one intended payment.

The prose variants are not invented — they are verbatim output from `llama-3.3-70b`
and `gpt-oss-120b` at **temperature 0** (see `../probe1/RESULTS.md`). Evidence and
transaction hashes: `../keeperhub/DOUBLE_SPEND.md`.

### MEDIUM — `omitted_key`

`idempotency_key` is optional. Two identical transfers with no key produce two
executions. Duplicate protection is opt-in and nothing warns an agent that it is
running without it — so the default path is the unsafe one.

### MEDIUM — `amount_formatting`

**This is a finding against our own proposed fix, not against KeeperHub.** `"0.001"`
and `"0.0010"` are the same transfer, but hashing the semantic fields *as raw strings*
yields different keys, and both executed. A semantic key is necessary but not
sufficient: values must be normalized (numbers parsed, addresses case-folded) before
hashing. A model re-emitting a number in another format is enough to defeat a
half-implemented fix.

### MEDIUM — `premise_staleness`

11.6s elapsed between the agent observing state and its transaction being included.
Nothing re-checks the premise in that window. Simulation verifies the transaction
*can* execute, never that the reason for it still holds.

Stated honestly: this scenario **measures the window, it does not yet prove harm.**
Proving it requires mutating the observed state mid-window. That is the natural next
scenario, and it is the failure a semantic key provably cannot catch.

## Running

```bash
export KEEPERHUB_API_KEY=kh_...
cd chaos && python3 run.py                    # all scenarios
cd chaos && python3 run.py prose_drift        # one scenario
```

Results land in `chaos/last_run.json`.

## Adding a scenario

A scenario states a claim a builder would reasonably assume, then tries to break it:

```python
def my_scenario(w: str) -> Result:
    return Result(name, claim, "PASS"|"FINDING", detail, evidence, severity)
```

Two rules, both learned from getting them wrong:

1. **It must be able to come back clean.** A scenario that can only find problems is a
   demo, not a test. Three of seven currently pass, and two of those were written
   expecting a failure.
2. **Every FINDING carries verifiable evidence** — execution ids or transaction
   hashes a third party can check.
