# Probe 1 — Does content-addressed idempotency survive LLM context loss?

A half-day scouting probe. It exists to **kill an idea cheaply**, not to validate one.

## The question

Stripe-style idempotency assumes a **deterministic client**: you retry with a
byte-identical body, the server hashes it, the duplicate is suppressed. Coinbase's
CLI docs give agents the same advice — use idempotent order IDs so retries don't
duplicate.

LLM agents are not deterministic clients.

If an agent loses context and regenerates its intent, it may produce a payload that is
**semantically identical but textually different**. The hash differs. The idempotency
key misses. Dedupe never fires. The action executes twice.

Over HTTP that's a duplicate API call. Onchain it's an irreversible duplicate transfer.

This isn't hypothetical. In February 2026 **Lobstar Wilde**, an agent built on the
OpenClaw framework, hit a tool error that forced a session restart and wiped its
context. It reconstructed its *persona* from logs but failed to reconstruct its
*wallet state*, miscalculated its disposable balance, and sent ~$250K of tokens to a
stranger.

## What kills the idea

If regenerated payloads come out canonically identical every time, hashing works,
Stripe's model is sufficient, and there is nothing here. **That is a good outcome** —
it costs half a day instead of two weeks. The probe is built to reach that verdict
honestly; it reports `NOT CONFIRMED` when payloads agree.

## Design

**Two arms:**

| arm | what it does | why |
|---|---|---|
| `cold_restart` | identical prompt, fresh context, N times | raw sampling nondeterminism — the weak arm |
| `log_replay` | agent rebuilds intent from a **log summary** instead of the original instruction | the Lobstar case. Same meaning, different words in. The realistic arm |

**Three comparison levels:**

- `exact` — raw bytes. Naive hashing.
- `canonical` — sorted keys, normalized whitespace, case-folded identifiers, numeric
  normalization so `90` and `90.0` agree. This is what a *competent* content-hash
  implementation uses. Deliberately generous: the point is to beat the strongest
  reasonable implementation, not a strawman.
- `semantic` — only the fields that determine the onchain effect
  (`action`, `chain`, `token`, `to`, `amount`). `reason` is excluded by design.

**The finding that matters is the gap between `canonical` and `semantic`.**
`canonical < semantic` means the action was the same but the key was not — dedupe
failed, and the transaction would have gone out twice.

Each trial is a fresh conversation with no shared history. That *is* the context wipe.

## Running it

Default provider is **Gemini** (free key at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey)):

```bash
pip install google-genai
export GEMINI_API_KEY=...

python3 probe1/probe.py                          # 3 scenarios x 2 arms x 8 trials
python3 probe1/probe.py --temperature 0.0        # best case for hashing
python3 probe1/probe.py --dump raw.json          # keep payloads for inspection
```

48 calls to `gemini-2.5-flash`, comfortably inside the free tier. Pass `--model` for a
newer model (e.g. `gemini-3.5-flash`) if your key has access.

Anthropic is also supported, which is worth using **as a second run, not a
replacement**:

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python3 probe1/probe.py --provider anthropic
```

A gap that shows up on Gemini *and* Claude is structural — a property of LLM
regeneration itself. A gap on only one vendor is a sampler quirk and much weaker
evidence. Cross-vendor agreement is the version of this result worth putting in a
pitch.

Run at `--temperature 1.0` first (the realistic agent default), then `0.0`. If the gap
persists at temperature 0, the mechanism isn't a sampling artifact either — that's the
strong result.

## Reading the output

```
scenario         arm               exact   canonical   semantic
aave_repay       log_replay          25%         50%       100%
```

Every trial produced the *same transaction* (semantic 100%) but only half shared a
canonical hash. A content-addressed idempotency key would have caught 50% of retries
and let the rest through as duplicate onchain transfers.

## Interpreting the verdict

- **CONFIRMED** → the mechanism is real and personally witnessed rather than borrowed.
  The fix is to hash the semantic surface and keep free prose out of the key.
- **NOT CONFIRMED** → the idea is dead. Fall back to premise invariants, which
  survived interrogation on independent grounds.

## Offline check

The analysis logic is verifiable without an API key:

```bash
python3 -c "
import probe1.probe as p
a={'action':'transfer','chain':'base','token':'USDC','to':'0xAbC','amount':'250','reason':'Health factor below floor.'}
b={'chain':'Base','action':'transfer','token':'usdc','to':'0xabc','amount':'250.00','reason':'Restoring health factor.'}
print('canonical equal:', p.canonical(a)==p.canonical(b))  # False
print('semantic  equal:', p.semantic(a)==p.semantic(b))    # True
"
```

Same transaction, different key. That's the whole thesis in six lines.
