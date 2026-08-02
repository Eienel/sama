# Finding testers

The ask that works is **"break my thing"**, not "try my tool". Builders enjoy the first
and resist the second. Everything below is written that way.

Keep it short. A DM that needs scrolling does not get read.

---

## X / Twitter DM (the main one)

Short enough to read in the notification preview.

> hey, saw your KeeperHub hackathon submission. built a test suite for onchain agent
> execution and I want to know if it's wrong before I ship it.
>
> it reads your agent's code for 3 specific bugs: idempotency keys hashed from
> LLM-written text, unnormalized amounts in those keys, read-then-act with no re-check.
>
> one paste into Claude Code, ~2 min, no signup:
> github.com/eienel/sama/blob/main/TESTERS.md
>
> mainly want to hear if it flags something that isn't actually a problem for you.

Why this works: it names their submission (not a blast), says what it looks for
concretely, states the time cost, and the ask is criticism rather than adoption.

**If you only have one line**, use this:

> built a thing that finds double-spend bugs in onchain agents. one paste, 2 min, no
> signup. want to tell me if it's wrong? github.com/eienel/sama/blob/main/TESTERS.md

---

## Hackathon Discord (`#general` or `#help`)

Post once, do not spam channels.

> Been auditing KeeperHub's execution layer for this hackathon and turned it into a
> test suite anyone can run against their own agent.
>
> It checks three things that bite agents specifically:
> • idempotency keys built by hashing a payload that contains model-written text. We
>   measured two model families at temperature 0 rewording the same transaction. The
>   hash changes, dedupe misses, you send twice.
> • "0.001" vs "0.0010" hashing differently, which defeats the fix for the above
> • read-then-act where nothing re-checks the state at submission
>
> One paste into whatever coding agent you have open, ~2 min, no signup:
> github.com/eienel/sama/blob/main/TESTERS.md
>
> Genuinely want false positives. If it flags something that isn't a problem in your
> code, that's more useful to me than a hit.

---

## DoraHacks comment on their BUIDL

Public, so lead with something useful to them rather than to you.

> Nice submission. I built a test suite for onchain agent execution while auditing
> KeeperHub for this hackathon (found a reproducible double-spend and a workflow that
> reported success while its action node never ran).
>
> It runs against your own agent in about 2 min with no signup, if it's useful:
> github.com/eienel/sama/blob/main/TESTERS.md

---

## Follow-up, only once, after ~3 days

> no worries if not, just checking, did it run? happy to hear it was useless, that's
> data too

Do not follow up twice.

---

## Handling replies

**"It found something."**
Ask for the file and line, and whether they had already fixed it or knew about it. A
bug they already knew about is much weaker evidence than one they did not.

**"It flagged X but that's fine because Y."**
This is the best outcome. Thank them properly, get the detail, open an issue. It means
a scenario is overfitted to how we build things.

**"Didn't install."**
Get the exact error and their Python version. Install failures are the single biggest
reason a tester silently disappears, and we cannot see them from here.

**No reply.**
Normal. Expect maybe 1 in 4 to respond, fewer to run it. Ten conversations is a
realistic target for three or four real data points.

---

## What we are actually trying to learn

Not "do people like it". These three:

1. Does it find real bugs in code we did not write?
2. Does it report things that are not bugs?
3. Where does setup break on a machine that is not ours?

Three honest answers beat thirty installs.

---

## Do not

- Send a wall of links. One link.
- Say "revolutionary", "game-changing", or describe it as a product.
- Follow up more than once.
- Argue when someone says a finding is wrong. Write it down, that is the point.
- Message people who have not submitted anything. They have no agent to test.
