# sama vs pay-kit Conformance Harness: Gap Analysis

> **Provenance and caveats.** This document was produced by a subagent (Haiku) doing a
> read-only comparison, and has been spot-checked rather than fully verified. Two
> reservations worth carrying:
>
> 1. The headline count of **0 COVERED / 13 NOT APPLICABLE** is too clean. The table
>    itself twice compares our scenarios against a pay-kit case named
>    `idempotent-resubmit`, which is partial coverage under a different model, not
>    inapplicability. Read the per-row reasoning, not the tally.
> 2. Individual case keys and file paths below have not been re-verified against the
>    repo by hand.
>
> The conclusion we acted on is the coarse one, and it is unaffected by either
> reservation: pay-kit tests cross-language protocol interop on Solana, sama tests
> execution reliability on EVM, and there is nothing cheap for us to contribute.
> Recorded so the reasoning is not repeated, not as a finding.

## Overview

The pay-kit conformance harness is organized in three tiers:

1. **Structural interop tier** (`test/e2e.test.ts`, `test/cross-server-scenarios.test.ts`, `test/x402-exact.e2e.test.ts`): Tests cross-language protocol agreement (encoding/parsing challenges, credentials, receipts), transaction byte-shape, and balance deltas across TypeScript, Rust, Go, Python, PHP, Ruby, and Lua implementations. The harness uses a hub-and-spoke matrix (Rust as reference) to validate interop in both directions. This tier does not execute the on-chain program.

2. **Protocol conformance tier** (`test/protocol-conformance.test.ts`, `test/conformance.test.ts`): Low-level vector tests for base64url encoding/decoding (20 cases), challenge parsing/formatting (26 cases), credential parsing/formatting (10 cases), receipt parsing/formatting (9 cases), and challenge ID computation (25 cases across 90 total caseMeta entries in `divergence-raw.json`). These test byte-level compatibility across SDKs.

3. **On-chain settlement tier** (`test/onchain.e2e.test.ts`): Runs a mainnet-forking Surfpool that executes the real payment-channels program, verifying that successful settlements confirm on-chain (returning HTTP 200) and failures surface as 402 responses. This catches settlement-class regressions (treasury account mismatches, voucher expiry, malformed ALT references) that the structural tier cannot detect.

The harness emphasizes protocol **interop and settlement correctness**. It does not test execution-layer semantics like idempotency key durability, deduplication under concurrency, or transaction retry resilience.

---

## Gap Analysis Table

| Scenario | Classification | Evidence / Reasoning |
|----------|------------------|----------------------|
| prose_drift | NOT APPLICABLE | sama tests LLM payload instability causing idempotency key divergence (Ethereum/KeeperHub concept). pay-kit uses cryptographic authorization headers, not payload hashing for idempotency keys. |
| semantic_key_fix | NOT APPLICABLE | Tests semantic-field-only idempotency key derivation (KeeperHub pattern). pay-kit lacks this; credentials are HMAC-verified, not key-derived from semantic fields. |
| body_drift_conflict | NOT APPLICABLE | Tests payload-based idempotency key + stable key with drifting payload. pay-kit doesn't use payload-keyed idempotency; settlement is signature-based replay detection. |
| omitted_key | NOT APPLICABLE | Tests opt-in idempotency key protection on unaffordable transfers. pay-kit's equivalent (`idempotent-resubmit` scenario) tests authorization replay, which is always required, not opt-in. |
| concurrent_same_key | NOT APPLICABLE | Tests 4 concurrent calls with one key deduplicate to 1 execution (race serialization). pay-kit's architecture doesn't deduplicate concurrent submissions; idempotent-resubmit tests sequential replay to the same server. |
| amount_formatting | NOT APPLICABLE | Tests numeric normalization in idempotency key (e.g., "0.001" vs "0.0010"). pay-kit uses cryptographic HMAC verification; field normalization is implicit in the protocol, not tested via key derivation. |
| cross_chain_key_scope | NOT APPLICABLE | Tests key scoping to prevent cross-chain suppression of legitimate transfers. pay-kit uses Solana exclusively; challenges embed network context implicitly. No cross-EVM-chain scenarios in harness. |
| premise_staleness | NOT APPLICABLE | Tests read-then-act staleness on chain height (decision @ block N, inclusion @ N+1, premise false). pay-kit has no check-and-execute pattern; settlement is direct signature-based, not gated on chain state at submission time. |
| conditional_staleness | NOT APPLICABLE | Tests KeeperHub's `execute_check_and_execute` primitive (reads condition @ block M, executes @ M+1). pay-kit has no equivalent; authorization/settlement flow does not re-check conditions between signature and on-chain execution. |
| revert_reporting | NOT APPLICABLE | Tests ERC20 transfer revert reporting (Ethereum-specific failure mode). pay-kit uses Solana SPL transfers and program-based settlement; revert semantics differ. On-chain tier verifies settlement confirmation, implying failure detection, but doesn't explicitly test a reverting instruction scenario. |
| overdraft_transfer | NOT APPLICABLE | Tests Ethereum nonce-blocking on unaffordable sends. Solana has no nonce model for SPL transfers; parallel sends from one pubkey execute in parallel, not serially. Architectural difference makes scenario inapplicable. |
| silent_noop_node | NOT APPLICABLE | Tests KeeperHub workflow execution nodes (action node missing `actionType` reports success). pay-kit is a payment protocol, not a workflow engine; no action node concept. |
| parallel_distinct_transfers | NOT APPLICABLE | Tests head-of-line blocking avoidance on Ethereum nonces under concurrent load. Solana's Sealevel runtime executes in parallel by design; no serial nonce queue from one wallet. Fundamental architectural difference. |

---

## Analysis by Category

### Idempotency and Deduplication (5 scenarios)

**prose_drift, semantic_key_fix, body_drift_conflict, omitted_key, amount_formatting**

**Classification:** NOT APPLICABLE (all 5)

**Reasoning:** sama tests KeeperHub's idempotency-key model where a single request submission can be retried and must deduplicate based on a derived key. This is an **execution-layer semantics** problem (agent retry resilience). pay-kit uses **cryptographic authorization headers** with HMAC verification, where the client provides a signed credential that the server verifies; there is no re-execution deduplication at the API layer. The scenario `charge-idempotent-resubmit` tests that a replayed authorization is rejected (`signature_consumed`), not that concurrent duplicate requests deduplicate to one execution.

---

### Concurrency and Atomicity (2 scenarios)

**concurrent_same_key, parallel_distinct_transfers**

**Classification:** NOT APPLICABLE (both)

**Reasoning:** 
- **concurrent_same_key**: Tests atomic deduplication under a race (4 concurrent calls → 1 execution). pay-kit's architecture does not deduplicate concurrent submissions; the `idempotent-resubmit` test is sequential replay detection on the same authorization.
- **parallel_distinct_transfers**: Tests Ethereum nonce serialization (concurrent distinct transfers must all land despite serial nonce ordering). Solana's Sealevel VM executes transactions in parallel by default; there is no serial nonce queue per wallet that can head-of-line block. Architectural difference makes the property inapplicable.

---

### Staleness and Conditional Execution (3 scenarios)

**premise_staleness, conditional_staleness, cross_chain_key_scope**

**Classification:** NOT APPLICABLE (all 3)

**Reasoning:**
- **premise_staleness / conditional_staleness**: sama tests KeeperHub primitives (`execute_transfer` with premise check, `execute_check_and_execute`) where a condition is evaluated off-chain and then the action is submitted on-chain. The gap is that the condition may become false between evaluation and inclusion. pay-kit has no equivalent off-chain-then-on-chain gatekeeping; settlement is direct (client signs, server broadcasts/confirms). No "check then execute" flow exists.
- **cross_chain_key_scope**: Tests Ethereum idempotency-key scoping across EVM chains. pay-kit is Solana-only in the harness; no cross-chain scenarios exist. The property (key scoping to prevent cross-chain payment suppression) is architecture-specific to multi-EVM systems.

---

### Failure Reporting and Blockchain-Specific Semantics (3 scenarios)

**revert_reporting, overdraft_transfer, silent_noop_node**

**Classification:** NOT APPLICABLE (all 3)

**Reasoning:**
- **revert_reporting**: Tests Ethereum ERC20 transfer revert reporting. Solana SPL transfers have different failure modes (account-not-found, insufficient balance). On-chain tests verify settlement confirmation (200 on success, 402 on any error), implying failure surfaces correctly, but don't explicitly test a "guaranteed-to-revert" instruction like sama's huge ERC20 transfer.
- **overdraft_transfer**: Tests Ethereum nonce management (unaffordable send blocks later sends). Solana's parallel execution model has no equivalent nonce blocking; architectural difference makes the property inapplicable.
- **silent_noop_node**: Tests KeeperHub workflow engine (action node validation). pay-kit is a payment protocol, not a workflow system; no such nodes exist.

---

## Summary

| Classification | Count | Scenario IDs |
|---|---|---|
| COVERED | 0 | — |
| NOT APPLICABLE | 13 | all 13 scenarios |
| GAP | 0 | — |
| UNSURE | 0 | — |

**Conclusion:** No gaps exist. All 13 of sama's scenarios test properties that are either:
1. **Architecture-specific to KeeperHub's EVM execution layer** (idempotency keys, nonce management, conditional execution), or
2. **Blockchain-specific to Ethereum** (ERC20 transfers, Solana has parallel execution), or
3. **Inapplicable to a payment protocol** (workflow nodes; pay-kit is protocol-focused, not orchestration-focused).

pay-kit's harness solves a different problem set: **cross-language protocol interop and on-chain settlement confirmation** on Solana. Overlapping property: both harnesses test some form of failure reporting (sama: explicit reverting-call tests; pay-kit: on-chain tier confirms failures surface as 402), but the underlying architectures and test domains are orthogonal.
