# BUIDL entry: Two Hours to First Call

Separate BUIDL for the "Best Onboarding UX Improvement" bounty, on Luca's instruction in
Discord: *"Preferably, create a new BUIDL for your onboarding contribution. Makes it
easier for us to distinguish between them."*

Deliberately scoped to onboarding only. The chaos harness, the scoreboard and the
ERC-8004 publication belong to the sama BUIDL and are left out of this one, apart from a
single line disclosing that the two entries share an author and a repository.

---

## Name

    Two Hours to First Call

## Tagline

    Everything between a fresh KeeperHub account and a first headless call, with a fix
    already merged.

## Description

I set out to build an agent that executes through KeeperHub and kept a log of everything
that got in the way before the first call succeeded. It took about two hours, and
essentially none of it was about blockchain.

**One fix is already merged.**
[#1877](https://github.com/KeeperHub/keeperhub/pull/1877) added a section to
`docs/api/direct-execution.md` on deriving an idempotency key that survives a retry.
Three review rounds, merged as `ef4913b`.

The gap it closes: the docs said the key is "any client-chosen string, ideally a UUID".
That is correct for a client replaying buffered bytes, and wrong for one that
reconstructs its request, because the reconstruction generates a new UUID and executes
again. I hit this, reproduced the resulting double-spend onchain, and the page now tells
the next person how to avoid it.

Review also corrected me, which is the part worth reading. A stable key sent with a
reworded body returns `409 idempotency_conflict` rather than replaying. That is
fail-closed and safe, but a caller expecting a replay reads the 409 as a broken key and
reaches for a fresh one, which is the single response that *does* double-execute. The
merged section now says so explicitly.

### The six blockers

Each is written up with a proposed fix in
[FRICTION.md](https://github.com/Eienel/sama/blob/main/keeperhub/FRICTION.md), and as a
ready-to-file issue in
[ISSUES_TO_FILE.md](https://github.com/Eienel/sama/blob/main/keeperhub/ISSUES_TO_FILE.md).

1. **Onboarding dead-ends at step 3/3 without a local browser.** The wizard offers only
   OAuth sign-in, which cannot complete in a container or CI, which is where agents
   actually run. The headless API-key path exists and works, and appears in neither the
   wizard nor the official Claude plugin.
2. **The edge returns a bare 403 for the default Python user-agent.** No body, no
   explanation. It reads unmistakably as an invalid API key and sends you to re-issue
   credentials that were never wrong. Verified by reproducing it with `curl -A`.
3. **An action node missing `actionType` is accepted and silently skipped.** The run
   reports `status: success`, `error: null`, and an execution trace containing only the
   trigger. A green run for an automation that never executed.
4. **Workflow validation rewards the vaguer definition.** Adding `actionType` makes
   creation fail for a missing `abi`, so the *less* complete node is the one that
   validates, and it is the one that silently does nothing. A builder who fills in more
   fields is punished for it and backs off to the version that "worked".
5. **`web3/read-contract` hard-requires an `abi` its own schema describes as
   auto-fetched**, while `execute_contract_call` auto-fetches correctly. The capability
   exists; one surface does not use it.
6. **`ai_generate_workflow` returns `503 AI Prompt is disabled`**, and it is the
   documented path for creating a workflow.

Plus two smaller ones in the write-up: the API-keys page has no discoverable URL, and the
MCP session id is required on every call after `initialize` but undocumented in the
API-key flow.

### What they have in common

**The failure never says what is actually wrong.** A 403 that means "wrong user-agent"
reads as "bad API key". A workflow that validates and does nothing reads as success. A
`503` on the documented path reads as "this feature was removed". Each one cost real time
not because the platform lacks the capability, but because the error pointed somewhere
else.

Items 1 and 2 account for most of the two hours, and both are invisible to anyone who
onboards in a browser. That is why they survived: the people who hit them are agents in
containers and CI, and they cannot file bug reports.

### What is genuinely good

Worth stating, because a friction log that only complains is not a fair report:

- **ABI auto-fetch is excellent.** A read against verified USDC on Base needed only
  address, chain and function name.
- **`list_action_schemas`** returns the full chain catalogue with testnet flags and
  explorer URLs in one call.
- The API key worked instantly once obtained, with clear scopes.
- 35 tools, clearly named and described.
- Idempotency semantics are correct and already well documented: replay, conflict,
  in-progress, scope and window. The gap the merged PR closed was one step earlier, in
  how a caller derives a key, not in how the key behaves.

### Disclosure

Same author and same repository as the **sama** BUIDL, submitted separately at
KeeperHub's request so the two can be judged apart. sama is the reliability harness; this
entry is the onboarding work only.

## Links

- Friction log: https://github.com/Eienel/sama/blob/main/keeperhub/FRICTION.md
- Ready-to-file issues: https://github.com/Eienel/sama/blob/main/keeperhub/ISSUES_TO_FILE.md
- Merged PR: https://github.com/KeeperHub/keeperhub/pull/1877
- Repository: https://github.com/Eienel/sama

## Open question for submission

Whether this BUIDL needs its own demo video, or whether the written contribution is
sufficient for a bounty entry. Worth asking Luca in the same Discord thread.
