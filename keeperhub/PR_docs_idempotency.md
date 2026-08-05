# PR: document how to choose an idempotency key when the caller is an LLM

**Filed:** [KeeperHub/keeperhub#1877](https://github.com/KeeperHub/keeperhub/pull/1877)
**File:** `docs/api/direct-execution.md`, base `staging`, head `Eienel:docs-idempotency-llm-agents`
**Final section:** `PR_SECTION.md` in this directory, kept in sync with the PR branch.

## Why this is a good first PR

Their idempotency implementation is correct and already well documented: replay,
conflict, in-progress, scope and window are all there. Nothing in this PR says otherwise.

The gap is one step earlier. The docs say the key is "any client-chosen string (for
example an agent-side transaction id, ideally a UUID)". That is right for a
deterministic client and misleading for a caller that reconstructs its request rather
than replaying buffered bytes, because the reconstruction produces a *new* UUID, so the
retry does not dedupe at all.

Additive, one file, no behaviour change, no criticism of their implementation.

## What review changed

Reviewer **suisuss** requested changes. Five items, all addressed across commits
`5483a55`, `eec1586`, `6d12814`, `6c03911`:

1. **Regenerated `specs/api-coverage.json`** via `npx tsx scripts/check-api-docs-routes.ts`.
   The repo has a `check:api-docs` gate that fails on a stale spec.
2. **Relocated the section** below the curl block and the workflow-webhook sentence,
   and added an anchor link from the `## Idempotency` intro so the pointer is not lost.
3. **Dropped the Python helper** for a language-neutral canonical form. A Python
   snippet in a docs page aimed at HTTP callers implies a reference implementation we
   were not shipping; the `chainId`/`network` alias also had to be resolved as an
   explicit canonicalization rule rather than assumed away.
4. **Made `taskId` lead the canonical form.** The original draft hashed only the effect
   fields and treated a task identifier as an add-on for payroll. That is backwards:
   effect-only hashing silently swallows a legitimate repeat payment, which is worse
   than a duplicate because nothing is left onchain to notice.
5. **Dropped the temperature-0 measurement claim.** Our own probe results do not support
   a general cross-model claim (qwen3.6-27b was perfectly stable), and the reviewer's
   framing, "not guaranteed byte-identical between calls even at temperature 0", is both
   stronger and true without measurement.

## Second review round

All five above accepted. One blocking gap left, and it was the outcome the section is
about. Verified against source before acting on it, all three claims correct:

- `lib/idempotency.ts:200` takes the `existing.requestHash !== requestHash` branch, and
  `stableStringify` (`:45-57`) normalizes JSON key order only, never values. So a stable
  key plus a byte-different body returns `409 idempotency_conflict`, **not** a replay.
  The section was written for exactly that case and never named its outcome, so a reader
  would treat the 409 as a broken key derivation and reach for a fresh key, which is the
  one response that does double-execute.
- `annotateReplay` (`:354-358`, applied `:370`) adds `idempotentReplay: true` to every
  replayed object body. Our "no error, nothing to alert on" wording was wrong: the
  replay is flagged, just easy to miss.
- Our branch was 68 merges behind upstream `staging`, which is why neither
  `annotateReplay` nor the `Recognising a replay` docs section existed in our base.
  Merged `staging` in, resolved the two conflicts, and regenerated the coverage spec.

The fix reframes the section honestly: a stable key does not buy you a replay, it buys
you a fail-closed 409 instead of a double-spend, and the 409 carries
`originalExecutionId` so it can be resolved by polling rather than retried around. Plus
the mechanical items: literal separator stated, `taskId` escaping rule added, the full
amount grammar spelled out so two implementations cannot disagree, UTF-8 bytes and
lowercase hex named, per-endpoint key scope noted, "unique `Idempotency-Key`" dropped
from the first-write sequence, and the canonical form moved to a fenced `text` block.

Two corrections we made to ourselves during the first revision, worth recording:

- We initially told the user the reviewer was wrong about the `chainId`/`network` alias.
  Wrong on the doc detail, right on the substance: `body.chainId ?? body.network` is
  confirmed at `transfer:108`, `check-and-execute:256` and `[...slug]:123`.
- We claimed the section "leads with" the byte-identical argument when that sentence was
  not in the section at all. It is now.

## Evidence behind the claim

The double-spend reproduced through KeeperHub on Sepolia, two transactions for one
intended payment, differing only in a free-text `reason` field:

- https://sepolia.etherscan.io/tx/0x63502437bb5d3d33223423ae529136fdb468bc1d6ad2818a3a41749e21f430ed
- https://sepolia.etherscan.io/tx/0x634ff5ca5de4ef620000889fc74a52ef2d386e4b3fef24be370be470d5b07cc6

This is not a bug in KeeperHub. Dedupe behaves correctly given a stable key: the
byte-identical retry returned the original `executionId` and did not execute again,
concurrent reuse was rejected `409 idempotency_in_progress`, and reuse with a changed
payload was rejected `409 idempotency_conflict` rather than answered from cache. The gap
is only that nothing tells the caller how to derive a key that stays stable.

Method and full results: `DOUBLE_SPEND.md`, `../probe1/RESULTS.md`.
