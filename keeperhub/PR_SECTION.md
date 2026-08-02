### Choosing a key when the caller is an AI agent

The guidance above assumes the retry sends the same key. That assumption breaks when an LLM agent loses context and regenerates its request, which is the common case after a crash, a restart, or a compacted conversation.

Two derivations that look reasonable and are not:

**A fresh UUID per attempt.** The regenerated request gets a new key, so it reads as a new request and executes again. A UUID only works if the agent persists it *before* the first attempt and can recover it afterwards.

**A hash of the request body.** This is the textbook derivation, and it is safe only while the body is byte-stable. If the body carries any model-authored text (a `reason`, `memo`, `description` or `note`), the model rewords it on regeneration, the hash changes, and the duplicate is not caught. This was measured on two model families at temperature 0, where sampling nondeterminism is off: the same transaction was emitted with reworded prose, producing different keys and two onchain transfers for one intended payment.

**Derive the key from the fields that determine the onchain effect**, and normalize them first:

```python
def idempotency_key(req: dict) -> str:
    parts = {
        "chainId": str(req["chainId"]),
        "recipientAddress": req["recipientAddress"].lower(),
        "amount": f"{float(req['amount']):.18f}".rstrip("0").rstrip("."),
        "tokenAddress": (req.get("tokenAddress") or "").lower(),
    }
    return sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
```

Normalization matters on its own: `"0.001"` and `"0.0010"` are the same transfer and hash differently, as do a checksummed and a lowercase address.

Add a task or period identifier to the hashed fields when the same transfer is legitimately repeated, for example a monthly payroll run:

```python
parts["period"] = "2026-08"
```

Note the limit of any idempotency key: it makes a *repeated* intent safe. It does not help when the agent regenerates a genuinely *different* action, or when the state that justified the transaction has changed by the time it lands. Those need a re-check before submission, not deduplication.
