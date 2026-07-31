# First workflow on the KeeperHub marketplace

`search_workflows` returned **0 listed workflows**. The marketplace surface is fully
built — search, listing, slugs, input/output schemas, per-call pricing, and agent-to-
agent invocation via `call_workflow` — and empty.

We listed the first one.

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
