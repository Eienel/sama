# agentaudit

Test suite for onchain agent execution. Point it at your execution layer, find out
which guarantees actually hold.

```bash
python3 -m agentaudit.cli --adapter local-evm     # real EVM, in-process, no setup
python3 -m agentaudit.cli --adapter keeperhub     # live, needs KEEPERHUB_API_KEY
python3 -m agentaudit.cli --compare local-evm keeperhub
```

## The comparison is the point

The question a builder actually has is not "is this provider perfect". It is "what does
using it buy me over signing transactions myself".

```
COMPARISON           local-evm     keeperhub
amount_formatting    FINDING/M     FINDING/M
concurrent_same_key  FINDING/H     PASS
omitted_key          FINDING/M     FINDING/M
premise_staleness    FINDING/M     FINDING/M
prose_drift          FINDING/H     FINDING/H
revert_reporting     PASS          PASS
semantic_key_fix     FINDING/H     PASS
passed               1/7           3/7

Guarantees keeperhub provides that a raw signer does not:
  concurrent_same_key, semantic_key_fix
```

A raw signer has no idempotency layer at all: it signs and sends, and nothing else
happens for you. That is the honest baseline, and it is what makes the provider's
guarantees measurable rather than asserted.

Note what does **not** improve: prose drift, amount formatting and premise staleness
are the caller's problem on both, because they are properties of how an agent derives
keys and reads state, not of who submits the transaction.

## Why this exists as a framework rather than an audit

The first version of this project audited one platform. That is a consulting engagement
with a market of one. The scenarios turned out not to be about that platform at all:
`prose_drift` is about any agent deriving idempotency keys by hashing an LLM-authored
payload, and staleness hits any read-then-act loop. Only the transport was specific.

So the suite runs against an `ExecutionAdapter`. KeeperHub is the first one.

## Writing an adapter

```python
class MyAdapter:
    name = "mine"
    chain_id = "8453"

    def transfer(self, to, amount, *, token=None, idempotency_key=None) -> Execution: ...
    def contract_call(self, address, function, *, args=None, abi=None,
                      idempotency_key=None) -> Execution: ...
    def status(self, execution_id) -> Execution: ...
    def block_number(self) -> int: ...
```

Raise `Conflict("in_progress"|"reused")` when the provider correctly refuses a
duplicate. Without that distinction a provider that dedupes properly gets scored as if
it had crashed.

## The Mock adapter is the important one

`MockAdapter` is an in-memory execution layer with switchable guarantees, and it is
what keeps this a test suite rather than a hit piece:

```
--adapter mock          guarantees hold   -> 5 of 7 pass
--adapter mock-broken   guarantees do not -> 7 of 7 findings
```

`tests/` asserts that **every scenario can reach both verdicts**. A scenario that can
only report failure is a demo, and this catches it before it ships. Building this found
a real modelling error: `omitted_key` could never pass, because the Mock only deduped
when handed a key. A correct provider can protect the default path by deriving one
server-side from the payload, which is exactly the fix we recommend, so the Mock was
wrong rather than the scenario.

Tests need no key, no funds and no network:

```bash
python3 -m pytest tests/ -q
```

## Scenarios

| scenario | tests |
|---|---|
| `prose_drift` | payload-hash key survives an LLM rewriting its own prose |
| `semantic_key_fix` | hashing only the semantic surface survives that |
| `omitted_key` | the no-key default path is safe |
| `concurrent_same_key` | dedupe is atomic under a race |
| `amount_formatting` | equivalent amounts yield one key |
| `premise_staleness` | the premise still holds when the tx lands |
| `revert_reporting` | a revert is reported as failure, not success |

Two are client-side: `prose_drift` and `amount_formatting` find the same bug against a
perfect provider, because the bug is in how the caller derives its key.

## Relationship to `chaos/`

`chaos/` is the original KeeperHub-specific harness and still holds five scenarios that
have not been made portable, because they probe surfaces not every execution layer has:
`conditional_staleness` (a provider-side conditional primitive), `silent_noop_node`
(workflow nodes), `cross_chain_key_scope`, `overdraft_transfer` and
`parallel_distinct_transfers`. Those stay there until a second adapter shows what the
right abstraction is. Guessing it from one implementation is how you get an abstraction
that fits nothing.
