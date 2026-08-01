# What KeeperHub actually wants, from reading their code

Notes from their blog, docs, and a clone of `github.com/KeeperHub/keeperhub`. The point
was to find what they would genuinely value rather than guess.

## Their own thesis matches this project almost exactly

From their blog:

> "76% of DeFi losses in 2025 came from infrastructure, not code."

They cite the $25M Resolv compromise, and call out **oracle configuration drift** as a
preventable operational risk. They position themselves against payment protocols with:

> "x402 and MPP only address how agents pay, not how they act onchain."

So their stated worldview is: the losses come from infrastructure and operations, not
from clever contract bugs. A harness that measures whether execution guarantees hold
is not adjacent to their pitch, it is their pitch with evidence attached. Our
`conditional_staleness` finding is literally a drift problem in their own primitive.

## The gap: ERC-8004 Validation Registry is unused

ERC-8004 ("Trustless Agents") defines **three** registries:

| registry | purpose | KeeperHub uses it? |
|---|---|---|
| Identity | ERC-721 agent identity + agent card | **yes** |
| Reputation | feedback signals from counterparties | **yes** |
| Validation | hooks for validators to publish verification results | **no** |

Their identity is real and onchain:

```
agent_id  31875
registry  0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
chain     Ethereum mainnet (chain_id 1)
served at /.well-known/erc8004.json
```

`grep -rl "ValidationRegistry"` across the whole repo returns **nothing**. They built
identity and reputation and left validation untouched.

That matters because reputation and validation answer different questions:

- **Reputation** is subjective: "a payer rated this 4/5."
- **Validation** is objective: "an independent validator checked this and here is the
  evidence."

Our harness produces the second kind. Evidence-backed verdicts with transaction hashes
are validation results, not star ratings. **We are already a validator, we just have not
published as one.**

## Constraints on their reputation path (why we cannot just rate things)

From `app/api/agentic-wallet/feedback/route.ts`, `giveFeedback()` is gated:

- `403 NOT_PAYER` unless the caller's wallet paid for the execution being rated
- `402 INSUFFICIENT_GAS` unless the caller can cover **Ethereum mainnet** gas
- the ERC-8004 contract itself blocks self-feedback, so we cannot rate our own listing

So the reputation route is closed to us without mainnet funds and paid calls. The
validation route has no such gate, because a validator's authority comes from its
published evidence rather than from having paid.

## On running multiple agents

Worth separating two things that both get called "multi-agent":

- **A swarm of chatty LLMs** passing messages to each other. This adds surface area and
  demo risk without producing more evidence. Recommend against.
- **Agent-to-agent in the ERC-8004 sense**: our auditor is one agent, validating *other*
  agents' listed workflows, and publishing verdicts other agents can read before
  deciding whether to call something. That is genuinely multi-party and it is what the
  standard exists for.

The second is worth doing. It also makes the marketplace useful: there are 20 listings
priced at $0.01 to $0.05 and **nothing tells a paying agent whether any of them work**.

## Bounty surface

`CONTRIBUTING.md` exists, and the codebase uses `KEEP-###` ticket references. We already
have concrete, evidence-backed candidates from `chaos/` and `keeperhub/FRICTION.md`:

- headless API-key path missing from onboarding and from the official Claude plugin
- edge returns bare `403` for the default Python user-agent, which reads as a bad key
- action node without `actionType` is accepted and silently skipped while reporting
  success
- `web3/read-contract` hard-requires an `abi` its own schema calls "auto-fetched"
- `ai_generate_workflow` returns `503 AI Prompt is disabled`, which is the documented
  path for creating a workflow

## Recommendation

Build the auditor into an **ERC-8004 validator for onchain execution**: it selects
targets, runs evidence-producing probes through KeeperHub, and publishes verdicts to
the Validation Registry so other agents can read them before paying to call something.

That does four things at once: it fills a registry KeeperHub committed to and left
empty, it turns our findings into a live service instead of a report, it makes the
marketplace safer to buy from, and it lands squarely on their own stated thesis that
infrastructure is where the losses come from.
