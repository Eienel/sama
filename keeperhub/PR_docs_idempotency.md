# PR: document how to choose an idempotency key when the caller is an LLM

**File:** `docs/api/direct-execution.md`
**Where:** insert after the existing `## Idempotency` bullet list, before the
`curl` example (currently after line 60).

## Why this is a good first PR

Their idempotency implementation is correct and already well documented: replay,
conflict, in-progress, scope and window are all there. Nothing in this PR says otherwise.

The gap is one step earlier. The docs say the key is "any client-chosen string (for
example an agent-side transaction id, ideally a UUID)". That is right for a
deterministic client and misleading for an LLM agent, because an agent that loses
context and regenerates its request generates a *new* UUID, so the retry does not
dedupe at all.

Additive, no behaviour change, no criticism of their implementation, and backed by
transactions anyone can verify. That is the kind of PR that gets merged.

---

## The patch

Insert this section:

```markdown
### Choosing a key when the caller is an AI agent

The guidance above assumes the retry sends the same key. That assumption breaks when
an LLM agent loses context and regenerates its request, which is the common case after
a crash, a restart, or a compacted conversation.

Two derivations that look reasonable and are not:

**A fresh UUID per attempt.** The regenerated request gets a new key, so it reads as a
new request and executes again. A UUID only works if the agent persists it *before*
the first attempt and can recover it afterwards.

**A hash of the request body.** This is the textbook derivation, and it is safe only
while the body is byte-stable. If the body carries any model-authored text (a `reason`,
`memo`, `description` or `note`), the model rewords it on regeneration, the hash
changes, and the duplicate is not caught. This was measured on two model families at
temperature 0, where sampling nondeterminism is off: the same transaction was emitted
with reworded prose, producing different keys and two onchain transfers for one
intended payment.

**Derive the key from the fields that determine the onchain effect**, and normalize
them first:

```python
SEMANTIC = ("chainId", "recipientAddress", "amount", "tokenAddress")

def idempotency_key(req: dict) -> str:
    parts = {
        "chainId": str(req["chainId"]),
        "recipientAddress": req["recipientAddress"].lower(),
        "amount": f"{float(req['amount']):.18f}".rstrip("0").rstrip("."),
        "tokenAddress": (req.get("tokenAddress") or "").lower(),
    }
    return sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
```

Normalization matters on its own: `"0.001"` and `"0.0010"` are the same transfer and
hash differently, as do a checksummed and a lowercase address.

Add a task or period identifier to the hashed fields when the same transfer is
legitimately repeated, for example a monthly payroll run:

```python
parts["period"] = "2026-08"
```

Note the limit of any idempotency key: it makes a *repeated* intent safe. It does not
help when the agent regenerates a genuinely *different* action, or when the state that
justified the transaction has changed by the time it lands. Those need a re-check
before submission, not deduplication.
```

---

## Suggested PR title

```
docs: how to derive an idempotency key when the caller is an LLM agent
```

## Suggested PR description

```markdown
The idempotency docs are clear on how the key behaves once chosen (replay, conflict,
in-progress, scope, window). This adds the step before that: how to derive one when
the caller is an LLM agent.

The current suggestion, "an agent-side transaction id, ideally a UUID", is correct for
a deterministic client. It breaks for an agent that loses context and regenerates its
request, because the regenerated request carries a new UUID and executes again.

The other obvious derivation, hashing the request body, breaks for a subtler reason:
if the body contains model-authored text, the model rewords it on regeneration and the
hash changes. I measured this on llama-3.3-70b and gpt-oss-120b at temperature 0, then
reproduced the resulting double-spend through KeeperHub on Sepolia:

- https://sepolia.etherscan.io/tx/0x63502437bb5d3d33223423ae529136fdb468bc1d6ad2818a3a41749e21f430ed
- https://sepolia.etherscan.io/tx/0x634ff5ca5de4ef620000889fc74a52ef2d386e4b3fef24be370be470d5b07cc6

Two transactions, one intended payment, no error. Only the free-text `reason` field
differed between them.

To be clear, this is not a bug in KeeperHub. Dedupe behaves correctly given a stable
key: the byte-identical retry returned the original `executionId` and did not execute
again, concurrent reuse was rejected `409 idempotency_in_progress`, and reuse with a
changed payload was rejected `409 idempotency_conflict` rather than silently answered
from cache. The gap is only that nothing tells the caller how to derive a key that
stays stable.

The section is additive and changes no behaviour. Method and full results:
https://github.com/Eienel/sama/blob/main/keeperhub/DOUBLE_SPEND.md

Happy to adjust the tone or trim it if you would rather this were shorter.
```

---

## How to open it

You do not need to clone or fork manually. GitHub forks for you:

1. Open
   https://github.com/KeeperHub/keeperhub/blob/staging/docs/api/direct-execution.md
2. Click the pencil (Edit). GitHub creates a fork automatically.
3. Paste the section after the bullet list, before the `curl` example.
4. "Commit changes", choose "Create a new branch and start a pull request".
5. Use the title and description above.

**Note their default branch is `staging`, not `main`.** Target the PR at `staging` or
it will be closed for the wrong base.
