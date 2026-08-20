# Target: routeweiler-python-sdk

Second target for the harness, chosen after KeeperHub. An async HTTP client that
transparently pays `402 Payment Required` across x402, L402 and MPP, with budget
envelopes and an audit trace.

- repo: https://github.com/nikoSchoinas/routeweiler-python-sdk
- commit examined: `809bc69`
- ~24k lines of Python, 65 test files, no CONTRIBUTING, **zero PRs ever**

Why this target: it is a library, so scenarios run locally with no account, no API
key and no funds. The maintainer has clearly thought about idempotency, which means
a careful finding lands rather than annoys.

## Finding: the durable draw dedupe cannot fire across a restart

`budgets/_draw.py:75-79` short-circuits on `(envelope_id, idempotency_key)` against
SQLite. The dedupe is durable by construction, which is the right design.

The key it matches on is built in `_auth.py:567-573`:

```python
return hashlib.sha256(f"{request_id}:{attempt}".encode()).hexdigest()
```

and `request_id` is minted fresh at every 402 interception (`_auth.py:197`):

```python
request_id = _uuid7()
```

So two attempts at the same piece of work never present the same key unless they
share a single 402 interception. The short-circuit fires for the rail-failover path
its docstring describes, and cannot fire for a caller-level retry or a process
restart. **The persistence is real and unreachable.**

`test_idempotency_across_restart.py` pins both cases. Both tests pass against
`809bc69`, so they document current behaviour rather than asserting a fix.

## Relationship to the KeeperHub work

This is the same mechanism as `prose_drift`: a key minted per attempt does not
survive the loss of the process that minted it. KeeperHub's docs now say so, in a
section we wrote and they merged
([#1877](https://github.com/KeeperHub/keeperhub/pull/1877)).

The correction we took there applies here too. Deriving the key from the request's
*effect* alone looks like the obvious fix and is wrong: it silently collapses a
legitimate repeat purchase into a cache hit, which is worse than a duplicate because
nothing is left to notice. The key needs a caller-supplied identifier for the work.
