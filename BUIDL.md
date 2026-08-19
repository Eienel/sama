KeeperHub's own research says **76% of 2025 DeFi losses came from infrastructure, not code.** Nothing lets you check whether an execution layer actually holds up. sama is that check, plus an audit of KeeperHub run with it.

**13 scenarios against live infrastructure. 6 findings, 7 passes, every claim carrying a transaction hash.**

The passes matter as much as the findings: most were written expecting a failure. That is the only reason the findings are worth believing.

## What we found

**A workflow that reports success while doing nothing.** An action node missing `actionType` is accepted at creation, silently skipped at execution, and the run returns `status: "success"`, `error: None`, with `executionTrace: ["trigger-1"]`. The action node never ran.

The incentive runs backwards: adding `actionType` makes creation reject the workflow for a missing `abi`, so the *less* complete definition passes validation and does nothing. For a platform whose value is reliability, a green run for an automation that never executed is worse than an error.

**A reproducible double-spend.** `idempotency_key` is optional and agent-supplied. The textbook derivation is to hash the request body, but when the caller is an LLM that body contains model-authored prose. We measured `llama-3.3-70b` and `gpt-oss-120b` at **temperature 0** regenerating the same transaction with reworded text, then reproduced it onchain:

- [0x63502437…f430ed](https://sepolia.etherscan.io/tx/0x63502437bb5d3d33223423ae529136fdb468bc1d6ad2818a3a41749e21f430ed)
- [0x634ff5ca…b07cc6](https://sepolia.etherscan.io/tx/0x634ff5ca5de4ef620000889fc74a52ef2d386e4b3fef24be370be470d5b07cc6)

Two transactions, one intended payment, no error. Only the free-text `reason` field differed.

Not a universal claim: `qwen3.6-27b` was perfectly stable across the same arms, so this is a property of particular models rather than of LLMs in general.

**Staleness in read-then-act**, including in `execute_check_and_execute`: the condition is evaluated at one block and the action lands at the next. We rate this MEDIUM, not HIGH, because off-chain check-then-act cannot be atomic. It is inherent. The issue is that nothing says so.

## What KeeperHub gets right

Stated first because most of these scenarios were written expecting a failure:

- Dedupe is **atomic under concurrency**: parallel calls with one key are rejected 409, not raced through
- Keys are **bound to payloads**: reuse with a changed payload is refused, not silently answered from cache
- Reverts report `status: failed` **with the reason attached**
- Unaffordable sends are refused before submission with **no nonce consumed**, so one bad send cannot head-of-line block the wallet
- A stable key sent with a **reworded body fails closed**: refused `409 idempotency_conflict` with no second transfer, rather than quietly executing twice

## Published onchain

Verdicts go to the **ERC-8004 Validation Registry**, which KeeperHub leaves unused: they use Identity (agent 31875) and Reputation, and `grep -rl ValidationRegistry` across their repo returns nothing.

Reputation is what a payer felt. Validation is what an independent checker verified.

- [validationResponse](https://sepolia.etherscan.io/tx/0x9378fa1bcc730bf664a07617d06c91dd54a9f873676b4c6a3f4b4317415a4e75) — score 43/100, tag `execution-reliability`
- Readable by any agent via `getValidationStatus`

Every transaction, including the publication itself, runs **through KeeperHub**.

## Onboarding UX

Submitted separately as its own BUIDL, **Two Hours to First Call**, at KeeperHub's
request so the two entries can be judged apart. It covers six blockers between a fresh
account and a first headless call, each with a proposed fix, and one fix already merged
into KeeperHub ([#1877](https://github.com/KeeperHub/keeperhub/pull/1877), `ef4913b`).

That PR is worth naming here for one reason: review corrected *us*. A stable idempotency
key sent with a reworded body returns `409 idempotency_conflict` rather than replaying.
Fail-closed and safe, but a caller expecting a replay reads the 409 as a broken key and
reaches for a fresh one, which is the single response that does double-execute.
`body_drift_conflict` verifies this against live infrastructure, and is one of the passes
in the scoreboard above.

## Try it in 60 seconds

    git clone https://github.com/Eienel/sama && cd sama
    pip install -e .
    agentaudit --adapter local-evm

No account, no key, no funds. It runs a real EVM in-process.

The comparison is the interesting part, since the question a builder has is not "is this provider perfect" but "what does it buy me over signing transactions myself":

    COMPARISON           local-evm     keeperhub
    concurrent_same_key  FINDING/H     PASS
    semantic_key_fix     FINDING/H     PASS
    prose_drift          FINDING/H     FINDING/H
    premise_staleness    FINDING/M     FINDING/M
    revert_reporting     PASS          PASS
    passed               1/7           3/7

That is a separate, smaller scenario set from the 13 above, because it has to run against providers other than KeeperHub.

Note what does **not** improve. Prose drift and staleness are findings on both, because they are properties of how the caller derives keys and reads state, not of who submits the transaction.

## Honest limitations

- The ERC-8004 record is attached to agent 9139, **an identity we minted ourselves**. It is not a third-party rating of KeeperHub's agent, which is 31875 on mainnet and does not exist on Sepolia. It demonstrates the mechanism and timestamps our verdict.
- We are the **seller** side of x402 (a listing on Base at 0.01 USDC), and it has taken two paid invocations from an external caller, settled on Base. We have not driven a payment outward as a buyer.
- The agent chooses among a fixed probe set. It selects and interprets; it does not invent new probes.
- Sepolia, not mainnet.
