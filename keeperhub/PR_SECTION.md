### Choosing a stable key

*Merged into KeeperHub `staging` in [#1877](https://github.com/KeeperHub/keeperhub/pull/1877). This is the final text,
including the two commits suisuss pushed to the branch. See `PR_docs_idempotency.md`
for the full history.*

A UUID generated per attempt does not survive a retry: the second attempt generates a
different UUID, so the request is treated as new and executes again. A UUID works only
when it is persisted before the first attempt and recovered afterwards.

A caller that cannot persist a key must derive one that is reproducible from the work
itself. Derive it from a canonical form of the caller's own stable identifier for the
piece of work, joined with the fields that determine the onchain effect:

```text
taskId|chainId|recipientAddress|amount|tokenAddress
```

The separator is a single ASCII vertical bar, `U+007C`, with no surrounding whitespace.

`taskId` is whatever the caller already uses to name the work: an invoice number, a
payroll period, a job id. It must be stable across a retry of the same work and
different for different work.

Canonicalize each part before joining:

- **`taskId`**: trim surrounding whitespace, and percent-encode any `%` as `%25` and any
  `|` as `%7C`. Without this a `taskId` of `8453|0xabc` on chain `1` joins to the same
  string as a different intent on chain `8453`. Do not case-fold it; task identifiers
  are opaque to this endpoint.
- **Resolve the chain to one spelling.** These endpoints accept `chainId` and also the
  deprecated `network` alias, so `{"network": "base"}` and `{"chainId": 8453}` are the
  same transfer. Resolve the alias to a numeric chain id first, then use its decimal
  integer form with no leading zeros, so `8453`, `"8453"` and `"base"` all agree.
- **Lowercase addresses**, so a checksummed and an unchecksummed address agree.
- **Canonicalize `amount` as a decimal string**, not a binary float, under all of the
  following rules, so that two conforming implementations cannot disagree:
  - trim surrounding whitespace, and reject a leading `+` or `-`
  - use no exponent notation
  - require at least one digit before the decimal point, so `.5` becomes `0.5`
  - strip leading zeros, except the single `0` before a decimal point, so `01.5`
    becomes `1.5` and `007` becomes `7`
  - strip trailing zeros after the decimal point, then strip a trailing decimal point,
    so `0.0010` becomes `0.001` and `1.000` becomes `1`
  - if the rules above leave an empty string, use `0`, so `0`, `0.0` and `0.000` all
    agree regardless of the order the rules are applied in

  Specifying the string form rather than a numeric type is deliberate: a caller parsing
  `"0.1"` as a 64-bit float gets `0.100000000000000006`, and binary floats also collapse
  distinct 18-decimal amounts onto the same value.
- **Represent omitted optional fields as an empty string**, so the separator positions
  stay fixed.

Hash the joined string's UTF-8 bytes with SHA-256 and send the digest as lowercase hex
in the `Idempotency-Key` header.

#### A stable key does not by itself produce a replay

Deriving a stable key is necessary but not sufficient, and it is worth being precise
about what it buys, because the difference decides how a caller should handle the
response.

The stored record is keyed on `(organization, scope, key)`, but the **request body is
hashed too**, and only a value-equal body replays. The body is hashed after it is parsed,
so formatting is normalized — whitespace, key order, and the spelling of JSON *numbers*
all stop mattering, and `{"chainId": 8453}` and `{"chainId": 8.453e3}` are the same body.
What is not normalized is the value itself, so anything carried as a string keeps its
exact spelling. `{"network": "base"}` and `{"chainId": 8453}` are different bodies, as are
the strings `"0.001"` and `"0.0010"`, and so is a `reason`, `memo` or `note` field that
the caller reworded between attempts.

So a retry that reuses a stable key with a reconstructed, value-different body returns
`409 idempotency_conflict`, not a replay. **That is the outcome to design for**, and it
is the safe one: the fail-closed `409` is precisely what stops the reconstructed retry
from executing a second time. A caller that expects a replay will read it as a bug in
its key derivation and reach for a fresh key, which is the one response that does cause
a double-execution.

Handle it as an answer rather than an error. When the `409` body carries a non-null
`originalExecutionId`, poll `GET /api/execute/{executionId}/status` with it to learn the
outcome of the work you were retrying.

`originalExecutionId` is nullable, and it is null in the two cases you are most likely to
hit here: the first attempt reached the broadcast path and failed, and the first attempt
is still in flight. Neither is a reason to rotate the key. Instead, canonicalize the body
with the rules above so it matches the original and re-send under the same key. A record
that has settled — whether it succeeded or failed — replays its stored response, so that
re-send returns the original outcome rather than executing again; a record still in
flight returns `409 idempotency_in_progress`, which is the retryable code, so back off
and re-send.

To get an actual replay instead, the retry must reproduce every value in the body, though
not its formatting. Canonicalize the body with the same rules used for the key, and omit
free-text fields whose wording is not reproducible, rather than regenerating them.

A stable key makes a **repeated** submission of the same work safe. It does not help
with three other cases:

- the caller submits genuinely different work, which needs a different key rather than
  deduplication
- the state that justified the request has changed by the time the transaction lands,
  which needs a check before submission
- the same work is legitimately repeated but the key cannot tell it apart from a retry

The last case is why `taskId` belongs in the key by default. **Omit it only when
repeating the transfer would genuinely be a mistake.** Hashing the effect fields alone
makes every identical transfer the same request, so an agent that legitimately pays the
same recipient the same amount twice inside the 24 hour window gets the second call
answered from the first one's cached response: the original `executionId`,
`status: completed`, and no second transfer. That outcome is flagged only by
`idempotentReplay: true` in the body, which is easy to miss if the caller does not check
that field, so the second payment can go missing while the response reads as success.
