# Submission: Reliability Auditor

Everything needed for the DoraHacks BUIDL entry, plus the demo script.

## The one-liner

KeeperHub says 76% of 2025 DeFi losses came from infrastructure rather than code. We
built the agent that checks whether their infrastructure holds, found four HIGH issues
including one in their own conditional-execution primitive, and published the verdict
onchain to the ERC-8004 registry they left empty.

## Required fields

| requirement | value |
|---|---|
| Source code | `https://github.com/eienel/sama` (branch `claude/relaxed-ride-a9py6j`) |
| Demo video | see script below, not yet recorded |
| Transaction executed by the agent | [`0x2241db71…2401e4`](https://sepolia.etherscan.io/tx/0x2241db718b260ae0d7850060ce77f39275e7dfc5c55b6f5a3c7e59a1d42401e4) (ERC-8004 `validationResponse`) |
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

**Reliability and observability.** This is the whole project. 12 scenarios, 6 findings,
4 HIGH, 6 passes, every claim carrying a transaction hash.

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

**1:00 to 2:00, the headline finding.** `conditional_staleness`. Show on screen:

```
condition "block <= 11394644"  TRUE  at block 11394644
action                          included at block 11394645, condition FALSE
```

Say: this is KeeperHub's own `execute_check_and_execute`, the primitive you use so you
do not hand-roll read-then-act. The gate promises "only act while true" and delivers
"act if it was true a moment ago". Open the transaction on Etherscan.

**2:00 to 2:30, the passes.** Scroll the scoreboard. Six of twelve passed, and most
were written expecting failure. Dedupe is atomic under races, keys are bound to
payloads, reverts report honestly. Say: this is a test suite, not a hit piece, which is
why the findings are worth believing.

**2:30 to 3:00, onchain.** Show `validationResponse` on Etherscan, then
`getValidationStatus` returning `response: 38`, `tag: execution-reliability`. Say:
ERC-8004 defines three registries. KeeperHub uses identity and reputation and left
validation empty. Reputation is what a payer felt; validation is what an independent
checker verified. Any agent can now read this score before trusting an execution layer.

## What we would say if asked what is weak

- Sepolia, not mainnet. The registries are the same code at canonical testnet proxies.
- We are the seller side of x402. The buyer half needs USDC on Base, which we did not
  fund.
- The agent reasons over a fixed probe set. It chooses and interprets, it does not
  invent new probes.
- The validated subject is an identity we minted. Validating third parties is the same
  call with a different id, held back deliberately rather than technically.

## Contribution to KeeperHub

Beyond the audit, ready to file as issues or PRs:

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
