# Ready to file on KeeperHub/keeperhub

**Status:** item 6 is filed as a PR rather than an issue:
[KeeperHub/keeperhub#1877](https://github.com/KeeperHub/keeperhub/pull/1877).
Items 1 to 5 remain to be filed.

Each is written as a maintainer would want to receive it: what happened, how to
reproduce, why it matters, and a proposed fix. Reproductions are real, from going from
a fresh account to a working call in a container.

File them separately, not as one mega-issue. Small, specific issues get fixed.

---

## 1. Onboarding step 3/3 has no path for environments without a browser

**Title:** `Onboarding offers only browser OAuth, which cannot complete headlessly`

Step 3 of `/welcome` ("Connect your AI agent") offers exactly one option:

```
claude mcp add --transport http keeperhub https://app.keeperhub.com/mcp
# then run /mcp and complete the browser sign-in
```

That handshake needs a browser on the same machine as the agent. In a container, a CI
runner, or a remote dev box there is none, so it cannot complete. The wizard has no
skip. The official Claude plugin is the same: `/keeperhub:login` is OAuth-only with no
`KEEPERHUB_API_KEY` support.

The headless path exists and works perfectly (organisation API key as a bearer token,
documented under `ai-tools/mcp-server`). It just is not mentioned in either place a new
user looks.

This matters because containers and CI are where autonomous agents actually run.

**Proposed fix:** add a "no browser?" line to step 3 pointing at the API key, and
support `KEEPERHUB_API_KEY` in the plugin.

---

## 2. The edge returns a bare 403 for the default Python user-agent

**Title:** `403 with no body for Python-urllib user-agent reads as an invalid API key`

A valid `kh_` key over plain `urllib` returns:

```
urllib.error.HTTPError: HTTP Error 403: Forbidden
```

No body, no reason. The key is fine. Reproduce:

```bash
curl -A "Python-urllib/3.11" -H "Authorization: Bearer kh_..." \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -X POST https://app.keeperhub.com/mcp -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
# -> 403

# identical request with curl's default agent -> 200
```

A 403 next to a freshly created API key reads unmistakably as "bad key", so the user
goes and re-issues credentials that were never wrong. This cost about 40 minutes.

**Proposed fix:** allow the default agent of common HTTP clients, or return a body
naming the user-agent as the reason.

---

## 3. A workflow node without `actionType` is accepted and silently skipped

**Title:** `Workflow reports status=success while its action node never ran`

Create a workflow whose action node omits `actionType`. Creation succeeds with no
validation complaint. Execute it:

```json
{"status": "success", "error": null, "executionTrace": ["trigger-1"]}
```

The action node is absent from the trace. It never ran. The run reports success.

The incentive runs backwards: adding `actionType` makes creation reject the workflow
for a missing `abi`, so the *less* complete definition passes and does nothing while
the more complete one is caught.

For a platform whose value is reliability, a green run for an automation that never
executed is worse than an error: an agent polling status sees success, the audit trail
records success, and nothing alerts.

**Proposed fix:** reject a node without `actionType` at creation, or mark the execution
`partial`/`failed` when a node in the graph is skipped.

---

## 4. `web3/read-contract` requires an `abi` its own schema calls auto-fetched

**Title:** `web3/read-contract requires abi, but execute_contract_call auto-fetches it`

`list_action_schemas` describes the field as:

```
abi: "string (JSON ABI - auto-fetched for verified contracts)"
```

But creating a workflow without it fails:

```
422 INVALID_ACTION_CONFIG
MISSING_REQUIRED_FIELD nodes[1].data.config.abi
```

Meanwhile `execute_contract_call` auto-fetches correctly against the same verified
contract:

```json
{"chain_id":"8453","contract_address":"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
 "function_name":"totalSupply"}
-> {"result": "4145349003927320"}
```

Same capability, two surfaces, opposite behaviour, and the schema documents the one
that does not apply.

**Proposed fix:** auto-fetch in the workflow node too, or correct the schema text.

---

## 5. `ai_generate_workflow` returns 503, and it is the documented path

**Title:** `tools_documentation prescribes ai_generate_workflow, which returns 503`

`tools_documentation` gives this as the way to create a workflow:

```
1. list_action_schemas
2. ai_generate_workflow      <- 503 {"error":"AI Prompt is disabled"}
3. create_workflow
```

With step 2 unavailable and no node/edge schema documented anywhere, there is no
supported way to author a workflow headlessly. We recovered the shape by reading a
public template via `get_template` and copying it.

**Proposed fix:** document the node and edge shape, or ship one worked
`create_workflow` example.

---

## 6. Recommend a semantic idempotency-key derivation in the docs

**Title:** `Docs should warn against hashing a whole request body into idempotency_key`

`idempotency_key` is optional and agent-supplied, so its correctness depends entirely
on how the caller derives it. The obvious derivation, and the one an LLM agent will
reach for, is to hash the request body.

That breaks when the caller is a model. We measured `llama-3.3-70b` and
`gpt-oss-120b` at **temperature 0** regenerating the same transaction with reworded
prose after a context loss, then reproduced the resulting double-spend on Sepolia:

- [`0x63502437…f430ed`](https://sepolia.etherscan.io/tx/0x63502437bb5d3d33223423ae529136fdb468bc1d6ad2818a3a41749e21f430ed)
- [`0x634ff5ca…b07cc6`](https://sepolia.etherscan.io/tx/0x634ff5ca5de4ef620000889fc74a52ef2d386e4b3fef24be370be470d5b07cc6)

Two transactions, one intended payment, no error. Only the free-text `reason` field
differed.

To be clear, **KeeperHub's dedupe is correct**: given a stable key it does exactly the
right thing, rejects concurrent reuse with `409`, and binds keys to payloads. The gap
is that nothing tells the caller how to derive one safely.

**Proposed fix:** document deriving the key from the semantic surface only
(`chain_id`, `to_address`, `amount`, `token_address`, function, args), with values
normalized first, and warn explicitly against hashing model-authored text. Optionally,
derive server-side from those fields when `idempotency_key` is absent, so the safe path
is the default.

Full writeup: https://github.com/Eienel/sama/blob/main/keeperhub/DOUBLE_SPEND.md
