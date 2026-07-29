# Probe 1 — Results

**Verdict: MECHANISM CONFIRMED.** Content-addressed idempotency does not survive an
LLM agent's context loss. Idea #2 lives.

Run on `llama-3.3-70b-versatile` via Groq, 8 trials per scenario per arm, 3 scenarios,
2 arms. Raw payloads in `results/`; re-analyse with
`python3 probe1/probe.py --report-from probe1/results/groq_t0.json`.

## Temperature 1.0 — realistic agent default

```
scenario         arm               exact   canonical   semantic
aave_repay       cold_restart        38%         38%       100%
aave_repay       log_replay          25%         25%        62%
payroll_chunk    cold_restart        50%         50%       100%
payroll_chunk    log_replay          38%         38%       100%
fee_sweep        cold_restart        50%         50%       100%
fee_sweep        log_replay          25%         25%       100%
```

Every arm shows a gap. At worst (`fee_sweep/log_replay`) a content-hash idempotency
key would have caught **25%** of retries and let **75%** through as duplicate onchain
transfers — while the transaction being sent was identical every time.

## Temperature 0.0 — the decisive run

The obvious objection to the above is "that's just sampling noise, turn the temperature
down." So we did.

```
scenario         arm               exact   canonical   semantic
aave_repay       cold_restart        62%         62%       100%
aave_repay       log_replay          75%         75%        88%
payroll_chunk    cold_restart       100%        100%       100%
payroll_chunk    log_replay          88%         88%       100%
fee_sweep        cold_restart       100%        100%       100%
fee_sweep        log_replay          50%         50%       100%
```

Distinct canonical keys produced across 8 identical retries:

| scenario | cold_restart | log_replay |
|---|---|---|
| aave_repay | 2 | 3 |
| payroll_chunk | **1** | 2 |
| fee_sweep | **1** | **4** |

**This is the finding.** At temperature 0 the `cold_restart` arm mostly collapses to a
single key — deterministic prompt, deterministic output, hashing works. The
`log_replay` arm **does not**: 2, 3, and 4 distinct keys for the same transaction.

The divergence is not sampling noise. It is caused by **reconstructing intent from a
log after context loss** — precisely the Lobstar Wilde scenario. Turning temperature
down does not fix it, because the input itself changed.

## What actually differs

`fee_sweep/log_replay` at temperature 0 — the `reason` field across 8 trials:

```
Accrued fees exceeded the threshold of 40 USDC
Accrued fees exceed threshold of 40 USDC
Accrued fees exceeded threshold of 40 USDC
Accrued fees exceeded the threshold of 40 USDC
Accrued fees exceeded the threshold of 40 USDC
Accrued fees exceeded the threshold of 40 USDC
Accrued fees exceed threshold of 40 USDC
Accrued fees exceed threshold
```

Tense, articles, truncation. Nothing else. `action`, `chain`, `token`, `to` and
`amount` were **identical in all 8**. Four different hashes, one transaction.

That is the entire thesis in one field: **prose the model writes about the action gets
folded into the key that is supposed to identify the action.**

Note the canonicalizer already sorts keys, folds case, normalizes whitespace and
number formats. This is not a strawman implementation failing — it is a competent one
failing, because no amount of canonicalization fixes a field whose content legitimately
varies.

## The second finding (unplanned, arguably worse)

`aave_repay/log_replay` is the only arm where **semantic** dropped below 100% (88% at
t=0, 62% at t=1). Inspecting the payloads:

```
[0] contract_call 250 USDC -> 0x8Ba1...
...
[5] transfer      250 USDC -> 0x8Ba1...      <-- different action
```

After context loss the agent did not merely re-word its intent — in one trial it chose
a **different transaction type** for the same situation. A semantic idempotency key
would not save you here, because the semantics genuinely changed.

This is not an idempotency problem. It is the agent disagreeing with itself about what
it was doing, and it needs a different mechanism: **premise invariants** (idea #1) —
re-checking at submission that the justification still holds.

**The two ideas are separately confirmed by this one run, which is direct evidence they
should not be merged.** #2 = the agent forgot the exact words. #1 = the agent forgot
the plan.

## Implications

1. **Do not hash free-text fields into an idempotency key.** Hash the semantic surface
   only: `action`, `chain`, `token`, `to`, `amount`.
2. **A semantic key is necessary but not sufficient.** It closes the prose-drift gap
   and does nothing for the changed-action case.
3. **Lower temperature is not a fix.** The `log_replay` divergence survives temperature
   0 because the input changed, not the sampling.

## Cross-model confirmation

The single most important objection is "this is one model's quirk." Re-ran the
decisive temperature-0 condition on a second, unrelated family — `openai/gpt-oss-120b`:

```
scenario         arm               exact   canonical   semantic
aave_repay       cold_restart        88%         88%        88%
aave_repay       log_replay          88%         88%       100%
payroll_chunk    cold_restart        62%         62%       100%
payroll_chunk    log_replay          50%         50%       100%
fee_sweep        cold_restart        88%         88%       100%
fee_sweep        log_replay          25%         25%       100%
```

Same signature, independently: `fee_sweep/log_replay` at **25% canonical vs 100%
semantic** — a 75-point gap at temperature 0. `payroll_chunk/log_replay` at 50 vs 100.

Note `aave_repay/cold_restart` also shows semantic at 88% here: gpt-oss, like Llama,
sometimes picks a different action type. The second finding replicates too.

### The third family falsifies the strong claim

`qwen/qwen3.6-27b`, same conditions, after fixing a bug in our JSON extractor that had
previously written its output off as unparseable:

```
scenario         arm               exact   canonical   semantic
aave_repay       cold_restart       100%        100%       100%
aave_repay       log_replay         100%        100%       100%
payroll_chunk    cold_restart       100%        100%       100%
payroll_chunk    log_replay         100%        100%       100%
fee_sweep        cold_restart       100%        100%       100%
fee_sweep        log_replay         100%        100%       100%
```

**One distinct canonical key per arm, across every arm.** Perfectly stable, including
`log_replay`. Content-hash idempotency would work flawlessly against this model.

The `fee_sweep/log_replay` reason field across 8 trials, by model:

| model | distinct reasons / 8 | mean length |
|---|---|---|
| qwen3.6-27b | **1** | 93 chars |
| llama-3.3-70b | 4 | 41 chars |
| gpt-oss-120b | **7** | 64 chars |

Not a length effect — qwen writes the *longest* reason and still never varies it.
It is a per-model property of how deterministically the model regenerates prose.

### What this actually licenses us to claim

An earlier draft of this document said the effect is "a property of LLM regeneration,
not of one vendor's sampler." **Qwen falsifies that, and the claim is withdrawn.**

The defensible claim is narrower and still useful:

> Content-addressed idempotency is **model-dependent and silently unsafe**. Two of
> three model families break it at temperature 0 — including gpt-oss-120b, a large
> capable model, which was the *worst* at 7 distinct keys out of 8 retries. One family
> does not break it at all.

Why that still matters:

1. **You do not control the model.** An agent system correct under qwen silently
   double-executes when someone swaps in gpt-oss. Nothing warns you.
2. **The failure is invisible.** There is no error — dedupe simply does not fire.
3. **Model choice is not a safety mechanism.** "Use qwen" is not an argument anyone
   can make to a treasury.

What it costs us: the primitive is no longer justified by "LLMs are nondeterministic,
therefore hashing is broken." It is justified by "hashing's correctness depends on an
uncontrolled, unstated property of whichever model is deployed." That is a weaker but
honest pitch, and one a judge cannot puncture with a single counterexample.

## Caveats

- Two model families confirmed, both open-weights served by one provider (Groq). A
  run against a closed frontier model (`--provider gemini` / `anthropic`) would
  strengthen it further; blocked today only by Gemini free-tier quota.
- 8 trials per arm — enough to show the effect, not to put confidence intervals on it.
- `log_summary` inputs are hand-written approximations of what a real agent's recovered
  log looks like. A recovered log from an actual framework crash would be stronger
  evidence.
