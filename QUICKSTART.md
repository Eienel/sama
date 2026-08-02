# Run it in 60 seconds

No account, no API key, no funds, no testnet. This runs a real EVM in-process.

```bash
git clone https://github.com/eienel/sama && cd sama
pip install -e .
agentaudit --adapter local-evm
```

That is the whole thing. You should see seven scenarios run and about six findings,
because a raw signer gives an agent no duplicate protection at all.

## Then point it at what you actually use

```bash
export KEEPERHUB_API_KEY=kh_...      # Settings > API Keys > Organisation
agentaudit --adapter keeperhub
```

And the question worth answering, which is what using an execution layer buys you over
signing transactions yourself:

```bash
agentaudit --compare local-evm keeperhub
```

```
COMPARISON           local-evm     keeperhub
concurrent_same_key  FINDING/H     PASS
semantic_key_fix     FINDING/H     PASS
prose_drift          FINDING/H     FINDING/H
omitted_key          FINDING/M     FINDING/M
premise_staleness    FINDING/M     FINDING/M
revert_reporting     PASS          PASS
passed               1/7           3/7
```

## What the findings mean for your agent

Three of them are **your** problem no matter which provider you use, because they are
about how your agent derives keys and reads state:

- **`prose_drift`** If your agent builds an idempotency key by hashing its request
  body, and that body contains any model-written text, the key changes when the model
  rewords itself. We measured this at temperature 0 on two model families. The retry
  does not dedupe and you send the transaction twice. Fix: hash only the fields that
  determine the onchain effect.
- **`amount_formatting`** `"0.001"` and `"0.0010"` are one transfer and two hashes.
  Normalize values before hashing or the fix above still breaks.
- **`premise_staleness`** You read state, then act. The transaction lands a block
  later. Nothing re-checks that the reason for acting still holds.

## Sending results back

```bash
agentaudit --compare local-evm keeperhub --json results.json
```

`results.json` has no keys or addresses beyond the wallet you audited. Send it over, or
open an issue. What is most useful to hear:

1. Did any scenario find something real in your agent?
2. Did any scenario report a finding that is wrong for your setup, i.e. a false
   positive? Those matter more than the hits.
3. What broke during setup?

## Testing your own execution layer

Implement four methods and the whole suite runs against it. See
`agentaudit/README.md`.
