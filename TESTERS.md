# Test your onchain agent in one paste

If you have Claude Code, Cursor, or any coding agent open in your project, paste the
block below. It installs the suite, runs it, then reads **your** code for the failure
patterns we measured, and writes up what it found.

Takes about two minutes. Needs no account, no API key and no funds for the first half.

---

```
Audit this project's onchain agent for execution safety bugs, using the agentaudit
suite plus a review of our own code. Be skeptical and concrete: I want real problems
or a clean bill of health, not reassurance.

STEP 1. Install and run the baseline (no credentials needed):

    git clone https://github.com/eienel/sama /tmp/agentaudit-src
    pip install -e /tmp/agentaudit-src
    agentaudit --adapter local-evm --json /tmp/aa-baseline.json

This runs a real EVM in-process. Expect findings: a raw signer has no duplicate
protection at all. That is the baseline, not a bug in my code.

STEP 2. If this project has a KEEPERHUB_API_KEY (or you can find one in .env),
also run the comparison so we can see what our execution layer actually gives us:

    agentaudit --compare local-evm keeperhub --json /tmp/aa-compare.json

STEP 3. Now the part that matters. Search THIS repository for the three failure
patterns below. For each, quote the actual file and line if you find it, and say
plainly if you do not.

  (a) IDEMPOTENCY KEY DERIVED FROM MODEL-WRITTEN TEXT.
      Look for an idempotency key, request id, nonce or dedupe key built by hashing a
      whole request body, payload dict, or JSON blob. Then check whether that body can
      contain any LLM-generated field: a reason, explanation, rationale, memo, note,
      description, comment or message.
      Why it matters: we measured two model families at temperature 0 regenerating the
      same transaction with reworded prose. The hash changes, the dedupe misses, and
      the transaction is sent twice. Fix: hash only the fields that determine the
      onchain effect (chain, recipient, amount, token, function, args).

  (b) UNNORMALIZED VALUES IN THAT KEY.
      Even hashing only the right fields breaks if "0.001" and "0.0010", or a
      checksummed and lowercase address, reach the hash as raw strings. Look for
      amounts and addresses being hashed without being parsed or case-folded first.

  (c) READ-THEN-ACT WITH NO RE-CHECK.
      Look for a read of onchain state (balance, price, health factor, allowance,
      block number) followed by a transaction whose correctness depends on that value,
      with nothing re-verifying it at submission time. Off-chain check-then-act cannot
      be atomic, so the question is not whether a gap exists but whether the code
      acknowledges it and bounds it (a deadline, a slippage limit, an on-chain require,
      an abort path).

STEP 4. Also check: does this project retry failed onchain calls? If so, does it
distinguish retryable failures from permanent ones, and does it cap attempts?

STEP 5. Write /tmp/agentaudit-feedback.md containing:

  1. What the suite reported (paste the summary table).
  2. For each of (a), (b), (c), (4): FOUND with file:line and a one-line explanation,
     or NOT PRESENT. Do not soften a real finding and do not invent one.
  3. FALSE POSITIVES: any scenario whose finding does not actually apply to this
     project, and why. This is the most useful section, so think about it properly.
  4. Anything that broke during install or running, with the exact error.
  5. One line: was this worth two minutes, yes or no.

Then show me the file.
```

---

## What to send back

The `/tmp/agentaudit-feedback.md` file, or just paste it into an issue at
`https://github.com/eienel/sama/issues`.

**We especially want the false positives and the install failures.** A scenario that
fires on code where it does not apply means the scenario is overfitted to how we happen
to build things, and that is worth more to us than a confirmed hit.

## What this is

`agentaudit` is a test suite for onchain agent execution. It came out of auditing
KeeperHub for the Agents Onchain hackathon, where it found a reproducible double-spend
and a workflow that reported success while its action node never ran. Seven of thirteen
scenarios pass, and most were written expecting a failure, which is the only reason the
findings are worth anything.

Full writeup: `README.md`. No account needed to try it.
