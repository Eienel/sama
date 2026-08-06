# Submission: Reliability Auditor

Everything needed for the DoraHacks BUIDL entry, plus the demo script.

## The one-liner

KeeperHub says 76% of 2025 DeFi losses came from infrastructure rather than code. We
built the agent that checks whether their infrastructure holds, found six issues including a
reproducible double-spend and a workflow that reports success while doing nothing, and
published the verdict onchain to the ERC-8004 registry they left empty.

## Required fields

| requirement | value |
|---|---|
| Source code | https://github.com/Eienel/sama |
| Demo video | see script below, not yet recorded |
| Transaction executed by the agent | [`0x9378fa1b…5a4e75`](https://sepolia.etherscan.io/tx/0x9378fa1bcc730bf664a07617d06c91dd54a9f873676b4c6a3f4b4317415a4e75) (ERC-8004 `validationResponse`) |
| Agent framework | custom, model served via Groq (`llama-3.3-70b-versatile`) |
| Used KeeperHub before | no |

Backup transaction links, all executed through KeeperHub:

- first transfer: [`0x6d449684…827f51`](https://sepolia.etherscan.io/tx/0x6d449684081d196d207b430629e1c2916a567e994422788e5a94f59403827f51)
- the double-spend pair: [`0x63502437…f430ed`](https://sepolia.etherscan.io/tx/0x63502437bb5d3d33223423ae529136fdb468bc1d6ad2818a3a41749e21f430ed) and [`0x634ff5ca…b07cc6`](https://sepolia.etherscan.io/tx/0x634ff5ca5de4ef620000889fc74a52ef2d386e4b3fef24be370be470d5b07cc6)
- ERC-8004 identity mint: [`0x02130b6f…eac22c`](https://sepolia.etherscan.io/tx/0x02130b6f04edb232f73a8826fb47e5e26a9186e0c286be61022e757606eac22c)

## Judging criteria, answered directly

**Does it execute onchain via KeeperHub?** Every scenario is real transactions on
Sepolia. A full pipeline run executes dozens. The ERC-8004 publication itself runs
through `execute_contract_call`, so we use the execution layer to publish an
assessment of the execution layer.

**Use of KeeperHub surfaces.** MCP server (headless, API key, no OAuth),
`execute_transfer`, `execute_contract_call`, `execute_check_and_execute`, workflow
create/update/execute, `get_execution`, the audit trail, the marketplace
(`list_workflow`, `call_workflow`), and x402 as a seller with a listing priced at 0.01
USDC on Base.

**Reliability and observability.** This is the whole project. 13 scenarios, 6 findings
(2 HIGH, 4 MEDIUM), 7 passes, every claim carrying a transaction hash.

**Originality.** The findings are not reproductions of known issues. The staleness gap
in `execute_check_and_execute` and the silent no-op on a workflow node were both found
here. The ERC-8004 Validation Registry is unused by KeeperHub and, as far as we can
tell, by everyone else.

**Integration quality and DX.** One command runs the whole pipeline. The scoreboard is
generated from run output so it cannot drift. `keeperhub/FRICTION.md` documents five
onboarding blockers with fixes, which is also the bounty submission.

## Demo video script (about 3 minutes)

**0:00 to 0:20, the claim.** Show KeeperHub's own line: 76% of DeFi losses came from
infrastructure, not code. Say: nothing lets you check whether an execution layer
actually holds. We built the agent that does.

**0:20 to 1:00, the agent runs.** Terminal, `python3 run_pipeline.py`. Show the agent
picking probes, then real transactions landing. Point out one rejected report: the
agent tried to cite evidence it had not observed and the harness refused it. Say: an
auditor that can assert what it did not check is worthless.

**1:00 to 2:00, the headline finding.** `silent_noop_node`, because it is the one that
survives a rebuttal. Show on screen:

```
status = 'success'      error = None
executionTrace = ['trigger-1']      <- the action node never ran
```

Say: a workflow whose action node is missing `actionType` is accepted at creation,
silently skipped at execution, and reports success. Worse, the incentive runs backwards:
add `actionType` and creation rejects you for a missing `abi`, so the less complete
definition passes and does nothing. For a reliability layer, a green run for an
automation that never ran is worse than an error.

Then, briefly, `conditional_staleness` as the honest secondary: the condition is checked
at one block and the action lands at the next. Say plainly that off-chain check-then-act
cannot be atomic, so this is a documentation gap rather than a bug, and that is exactly
why we rate it MEDIUM.

**2:00 to 2:30, the passes.** Scroll the scoreboard. Seven of thirteen passed, and most
were written expecting failure. Dedupe is atomic under races, keys are bound to
payloads, reverts report honestly. Say: this is a test suite, not a hit piece, which is
why the findings are worth believing.

**2:30 to 3:00, onchain.** Show `validationResponse` on Etherscan, then
`getValidationStatus` returning `response: 43`, `tag: execution-reliability`. Say:
ERC-8004 defines three registries. KeeperHub uses identity and reputation and left
validation empty. Reputation is what a payer felt; validation is what an independent
checker verified.

Say the limitation out loud rather than waiting to be asked: the agentId on this record
is one we minted, not KeeperHub's, because theirs is mainnet-only. This proves the
mechanism and timestamps the verdict; it is not yet a third-party score.

## What we would say if asked what is weak

- **The ERC-8004 record is attached to agent 9139, an identity we minted ourselves.**
  It is not a rating of KeeperHub's agent, which is 31875 on mainnet and does not exist
  on Sepolia. It demonstrates the mechanism and timestamps our verdict; it is not a
  third-party score, and we will not present it as one.
- **Both staleness findings are inherent, not defects.** Off-chain check-then-act cannot
  be atomic. The defensible claim is that it is undocumented and the primitive's name
  implies a guarantee it cannot give. We rated these HIGH initially and that was wrong;
  they are MEDIUM documentation gaps.
- **The marketplace listing is thin.** It returns a block height for 0.01 USDC. It
  proves the x402 plumbing works, not that anyone would buy it.
- Sepolia, not mainnet. The registries are the same code at canonical testnet proxies.
- We are the seller side of x402. The buyer half needs USDC on Base, which we did not
  fund.
- The agent reasons over a fixed probe set. It chooses and interprets, it does not
  invent new probes.
- The validated subject is an identity we minted. Validating third parties is the same
  call with a different id, held back deliberately rather than technically.

## Contribution to KeeperHub

**Merged: [KeeperHub/keeperhub#1877](https://github.com/KeeperHub/keeperhub/pull/1877)**, a docs
PR adding a section on deriving an idempotency key that survives a retry. Additive, one
file, +103 lines, no behaviour change. It establishes that KeeperHub's dedupe is correct
given a stable key, because it is: the gap is that nothing tells the caller how to
derive one that stays stable. Three review rounds, all addressed, merged as `ef4913b`
(`keeperhub/PR_docs_idempotency.md` records what changed and why). The second round
changed our own understanding: a stable key with a reworded body returns
`409 idempotency_conflict` rather than replaying, which is the safe direction and is now
what the section teaches. `body_drift_conflict` verifies it against live infrastructure.

The remainder, ready to file as issues:

1. Onboarding offers only browser OAuth, which cannot complete in a container, and the
   headless API-key path is absent from both the wizard and the official plugin.
2. The edge returns a bare 403 for the default Python user-agent, which reads as a bad
   API key.
3. An action node missing `actionType` is accepted and silently skipped while the run
   reports success.
4. `web3/read-contract` hard-requires an `abi` its own schema describes as
   auto-fetched, while `execute_contract_call` auto-fetches correctly.
5. `ai_generate_workflow` returns `503 AI Prompt is disabled`, and it is the documented
   path for creating a workflow.
6. Recommend a semantic idempotency-key derivation in the docs, and warn against
   hashing a whole request body when the caller is an LLM.
