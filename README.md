# Does the execution layer actually hold?

KeeperHub is the execution and reliability layer for onchain agents. Nothing currently
lets anyone *check* that reliability claim: the audit trail records every trigger,
simulation, transaction and outcome, and nobody reads it back.

This is a chaos harness that deliberately breaks agent execution through KeeperHub and
reports what survives: with transaction hashes for every claim.

**13 scenarios · 6 findings · 2 HIGH · 4 MEDIUM · 7 passes.** Every run executes real transactions
on Ethereum Sepolia. Gas is sponsored and transfers are self-directed, so a full pass
costs nothing and is repeatable indefinitely.

```
scenario                    verdict   sev
prose_drift                 FINDING   HIGH    payload-hash idempotency key drifts
premise_staleness           FINDING   HIGH    premise false by the time tx lands
conditional_staleness       FINDING   HIGH    KeeperHub's own guard is not atomic
silent_noop_node            FINDING   HIGH    skipped action node reports success
omitted_key                 FINDING   MEDIUM  duplicate protection is opt-in
amount_formatting           FINDING   MEDIUM  our own fix needs value normalization
semantic_key_fix            PASS      -       proposed fix survives prose drift
concurrent_same_key         PASS      -       dedupe is atomic under races
cross_chain_key_scope       PASS      -       key<->payload binding enforced
revert_reporting            PASS      -       reverts reported honestly
overdraft_transfer          PASS      -       no stuck nonce on unaffordable send
parallel_distinct_transfers PASS      -       nonce ordering holds under load
```

## The four HIGH findings

**1. `conditional_staleness` (MEDIUM).** `execute_check_and_execute` is KeeperHub's own
read-condition-act primitive. The condition is evaluated at one block and the action
lands at a later one:

```
condition "block <= 11392654"  TRUE at block 11392654
action                          included at 11392655: condition FALSE
```

**Stated fairly: off-chain check-then-act cannot be atomic, so this is inherent rather
than a defect.** The issue is that nothing says so. The primitive's name and shape imply
the condition gates the action, and an agent handed it reasonably assumes enforcement at
execution. Documented, this is a caveat; undocumented, it is a trap. A real fix needs an
on-chain guard that re-checks in the same transaction. We originally rated this HIGH and
that overstated it.

**2. `silent_noop_node`: a green run for an automation that never ran.** An action node
missing `actionType` is accepted at creation and silently skipped at execution:
`status='success'`, `error=None`, `executionTrace=['trigger-1']`. The incentive runs
backwards: adding `actionType` triggers validation demanding an `abi`, so the *less*
complete definition passes and does nothing while the more complete one is rejected.

**3. `prose_drift`: a reproducible double-spend.** `idempotency_key` is optional and
agent-supplied. The textbook derivation is to hash the request body, but when the caller
is an LLM that body contains model-authored prose which is not stable across a context
loss. Two payloads differing only in a `reason` field produced two keys, two executions,
two transactions onchain for one intended payment. The prose variants are verbatim
output from `llama-3.3-70b` and `gpt-oss-120b` **at temperature 0**.

**4. `premise_staleness`**: the same staleness gap in hand-rolled read-then-act.

Findings 1/2/4 and 3 are *different mechanisms*: one is the world moving underneath the
agent, the other is the agent forgetting its own words. Neither fix addresses the other.

## What KeeperHub gets right

Six scenarios pass, and five were written expecting a failure. That ratio is the point -
this is a test suite, not a hit piece.

Dedupe is atomic under concurrency (parallel calls are rejected `409`, not raced
through). Keys are bound to payloads, so reuse with a changed payload is refused rather
than silently returning a stale result. Reverts report `status='failed'` with a reason.
Unaffordable sends are refused before submission with no nonce consumed. Five concurrent
transfers all land, so a busy agent does not head-of-line block itself.

## Layout

| path | what |
|---|---|
| `chaos/` | the harness: scenarios, runner, scoreboard |
| `probe1/` | the offline experiment behind `prose_drift`, cross-model at temperature 0 |
| `keeperhub/` | headless MCP client, double-spend writeup, marketplace notes, friction log |

## Try it on your own agent

If you have a coding agent open in your project, `TESTERS.md` has a prompt you can
paste that installs this, runs it, then reads your code for the three failure patterns
it measures and writes up what it finds. Two minutes, no account needed.

Or directly:

```bash
pip install -e .
agentaudit --adapter local-evm        # real EVM in-process, no setup at all
```

## Running

```bash
export KEEPERHUB_API_KEY=kh_...          # Settings > API Keys > Organisation
cd chaos && python3 run.py               # full pass
cd chaos && python3 run.py prose_drift   # one scenario
```

## Also shipped

- **`premise-freshness-check`**, listed on the KeeperHub marketplace and callable by any
  agent via `call_workflow`. It returns the block height a read was observed at: the
  re-check `conditional_staleness` shows is missing.
- **`keeperhub/FRICTION.md`**: every blocker hit going from a fresh account to a working
  headless call, each with the fix that would have prevented it.

## Honesty notes

Kept deliberately, because a reliability project that hides its own errors is worthless:

- `amount_formatting` is a finding against **our own proposed fix**, not KeeperHub.
- Probe 1's cross-model claim was **withdrawn** when `qwen3.6-27b` proved perfectly
  stable: the effect is model-dependent, not universal.
- An earlier claim that the marketplace was empty was **wrong**; `search_workflows`
  returned 0 while 19 listings existed, and one API call was treated as fact.
