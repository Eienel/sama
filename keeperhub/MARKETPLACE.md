# Listing a workflow on the KeeperHub marketplace

**Correction.** An earlier version of this file claimed the marketplace was empty and
that ours was the first listing. That was wrong. `search_workflows` returned 0 items
when 19 listings already existed, some dating to 2026-07-12, and the conclusion drawn
from that single reading was not re-checked before being written down. A later call
with identical arguments returned all 20.

Ours is the newest listing, not the first. The empty result was bad data, and treating
one API call as ground truth was the mistake.

That the search silently returned zero rather than erroring is itself worth reporting:
an agent using `search_workflows` for discovery would have concluded there was nothing
to call.

## `premise-freshness-check`

A read workflow that returns the chain height a read was observed at, so an agent can
re-verify the premise behind a pending action immediately before submitting it. It
exists because of `conditional_staleness`: KeeperHub's own read-condition-act primitive
evaluates its gate at one block and lands the action at a later one.

```
workflowId  6ke4mwpf39d9wn5elnxnj
slug        premise-freshness-check
type        read      chain 11155111 (Sepolia)      category monitoring
```

Called the way an external agent would:

```
call_workflow {"slug":"premise-freshness-check","inputs":{}}
-> {"status":"success","output":{"result":{"blockNumber":"11392743"},"success":true}}
```

## The competitive picture

20 listings, priced $0.01-$0.05 per call (ours is currently free). Several are directly
adjacent to this project's findings:

- **`assay-verify`** — "given an intent hash, reports whether the agent committed to
  that action onchain BEFORE it executed". This is intent-commitment verification, very
  close to the premise-invariants direction. Someone else reached a neighbouring idea.
- **`checked-transfer-*`** (three listings) — "checks your source wallet balance and
  sends a transfer only if the balance exceeds a threshold". This is exactly the
  read-then-act pattern that `conditional_staleness` shows is not atomic.
- **`position-health-check`** — reads a lending position's health factor and danger band.

## What listing taught us

**The documented creation path does not work on a new account.** `tools_documentation`
prescribes: `list_action_schemas` → `ai_generate_workflow` → `create_workflow`. Step 2
returns `503 {"error":"AI Prompt is disabled"}`, and no node schema is documented
anywhere, so there is no supported way to author a workflow headlessly. We recovered
the node shape by reading a public template (`get_template`) and copying it.

> **Fix:** document the node/edge shape, or ship one worked `create_workflow` example.

**A node missing `actionType` is accepted and silently skipped** — see the
`silent_noop_node` finding in `../chaos/README.md`. Worse, the *more* complete
definition is the one that gets rejected: adding `actionType` triggers validation that
demands an `abi`, while omitting it passes and does nothing.

**ABI handling is inconsistent across surfaces.** `execute_contract_call` auto-fetches
the ABI for verified contracts and worked with no `abi` at all. The `web3/read-contract`
workflow node hard-requires one, despite its own schema describing the field as
"auto-fetched for verified contracts".

> **Fix:** make the workflow node auto-fetch too, or correct the schema description.

## Worth noting: ERC-8004 reputation

`call_workflow` returns a feedback prompt inviting the caller to rate the workflow on
an **ERC-8004 ReputationRegistry**, signed by the caller's wallet and submitted onchain.

That is an onchain reputation surface for agent-to-agent workflow calls, and it is
currently attached to a marketplace with one listing. It is the natural place for the
reliability evidence this harness produces to land — scores backed by executed
transactions rather than self-reported claims.
