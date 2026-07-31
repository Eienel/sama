# A reproducible double-spend through KeeperHub's idempotency key

Probe 1 showed that LLM agents regenerate semantically identical but textually
different payloads after context loss. This is that finding executed against live
infrastructure, on Ethereum Sepolia, with verifiable transaction hashes.

## The surface

Both `execute_transfer` and `execute_contract_call` accept:

```
idempotency_key   string   Optional Idempotency-Key (e.g. an agent-side transaction id)
```

Two properties matter, and they compound:

1. **Optional.** Omit it and there is no duplicate protection at all.
2. **Agent-supplied.** KeeperHub cannot compute it — correctness depends entirely on
   how the calling agent derives it.

The obvious derivation, and the one an agent will reach for, is to hash the payload.
That is what breaks.

## Control: the key works when it is stable

```
execute_transfer  chain 11155111  0.001 ETH  idempotency_key="probe1-demo-001"
  -> executionId 0vn804jzawlkj5c3u9k1c   status completed
     0x6d449684081d196d207b430629e1c2916a567e994422788e5a94f59403827f51
     gasUsed 74793, sponsored: true, completed in 7.8s

retry, byte-identical key
  -> executionId 0vn804jzawlkj5c3u9k1c   (same execution, no second transaction)
```

**KeeperHub's dedupe is correct.** Given a stable key it does exactly the right thing.
Nothing below is a bug in KeeperHub.

## The failure: a key derived from a regenerated payload

Two payloads in the shape Probe 1 actually produced at temperature 0 — same
transaction, only the free-text `reason` differing:

```python
before = {... "amount":"0.001", "reason":"Accrued fees exceeded the threshold of 40 USDC"}
after  = {... "amount":"0.001", "reason":"Accrued fees exceed threshold"}

key = "kh-" + sha256(json.dumps(payload, sort_keys=True)).hexdigest()[:24]
```

```
same transaction?    True
key before crash:    kh-24f6928b1d78a84528500477
key after  crash:    kh-55b48116cbb87c2d9b7482ac
keys match?          False
```

Both submitted:

| | executionId | transaction |
|---|---|---|
| pre-crash | `91wyxo6y9nzkz6e7s3fpi` | [`0x63502437…f430ed`](https://sepolia.etherscan.io/tx/0x63502437bb5d3d33223423ae529136fdb468bc1d6ad2818a3a41749e21f430ed) |
| post-crash regen | `7zl8b1j171o31bofdqqfk` | [`0x634ff5ca…b07cc6`](https://sepolia.etherscan.io/tx/0x634ff5ca5de4ef620000889fc74a52ef2d386e4b3fef24be370be470d5b07cc6) |

**Two distinct transactions onchain for one intended payment.** No error, no warning.
The dedupe simply never fired, because the two calls never looked like the same call.

## Why this is not a strawman

- The `reason` field drift is not invented — it is the exact output observed from
  `llama-3.3-70b` and `gpt-oss-120b` at **temperature 0**, where nondeterminism is
  supposed to be off (see `probe1/RESULTS.md`).
- Hashing the request body is the textbook derivation. It is what Stripe's model
  assumes and what Coinbase's CLI docs recommend to agents.
- Canonicalization does not save you. Sorting keys, folding case and normalizing
  numbers still leaves the prose field in the hash.
- The one model that would have survived this (`qwen3.6-27b`) is stable by accident,
  not by guarantee. Swap models and the bug appears with no code change.

## The fix

Derive the key from the **semantic surface only** — the fields that determine the
onchain effect — and keep model-authored prose out of it:

```python
SEMANTIC = ("action", "chain_id", "to_address", "amount", "token_address")
key = sha256(json.dumps({k: p[k] for k in SEMANTIC}, sort_keys=True)).hexdigest()
```

Both payloads above collapse to one key under this derivation, and the second call
dedupes.

Two things this does **not** fix, and which need separate mechanisms:

1. **A genuinely changed action.** Probe 1 also observed the agent choosing
   `transfer` where it previously chose `contract_call`. The semantics really did
   change, so a semantic key correctly treats them as different — and you double-spend
   anyway. That needs premise re-checking at submission, not idempotency.
2. **Agents that omit the key entirely.** It is optional, and nothing warns you.

## Suggested changes to KeeperHub

- Document a recommended key derivation, explicitly warning against hashing the whole
  request body when the caller is an LLM.
- Consider server-side derivation from the semantic fields as a default when
  `idempotency_key` is absent, so the safe path is the default path.
- Return a distinguishable response on a dedupe hit (e.g. `deduplicated: true`) so an
  agent can tell "your retry was absorbed" from "a new execution ran".

## Reproducing

```bash
export KEEPERHUB_API_KEY=kh_...
python3 keeperhub/kh.py call execute_transfer '{"chain_id":"11155111",
  "to_address":"0x...","amount":"0.001","idempotency_key":"<key>"}'
python3 keeperhub/kh.py call get_direct_execution_status '{"execution_id":"<id>"}'
```
