# Who to contact

Found via GitHub search (`keeperhub in:name,description,readme pushed:>2026-07-01`,
102 repos). All public, all clearly building for this hackathon. Several map onto the
marketplace listings we already saw, which confirms they have something running.

Contact route: open a GitHub issue on their repo, or find them on X from their profile.
An issue is often better than a DM: it is public, it is on-topic, and it does not
require them to trust a stranger's link in a private message.

## Tier 1: their agent does the exact thing our scenarios test

These read onchain state and then act on it, which is `premise_staleness`, or move
money on a schedule, which is `prose_drift` and `omitted_key`.

| repo | why they are the best fit |
|---|---|
| [Risingtell/bulwark](https://github.com/Risingtell/bulwark) | Aave health-factor guardian that repays debt when it drops below a threshold. Textbook read-then-act: reads HF, then sends a repay. Our staleness scenario is written for exactly this shape. |
| [Assassin859/Nexus-Agent](https://github.com/Assassin859/Nexus-Agent) | "Autonomous DeFi Guardian", mined Base Sepolia repays, live deployment. Matches the `nexus-guardian-hf-read` marketplace listing, so it is running. |
| [Saber1Y/AutoKeep](https://github.com/Saber1Y/AutoKeep) | Treasury agent running **payroll on a schedule**. Recurring payments are where a duplicate is most expensive and where idempotency keys matter most. |
| [ephraimphrase/vigil](https://github.com/ephraimphrase/vigil) | Matches three marketplace listings (`vigil-risk-check`, `vigil-rescue-quote`, `vigil-aave-health-guard`). Solidity plus live listings means real execution. |
| [jackjosias/incomeshield-agent](https://github.com/jackjosias/incomeshield-agent) | Recurring stablecoin automation. Same duplicate-payment exposure as payroll. |

## Tier 2: adjacent to us, so they will have opinions

These people are already thinking about agent safety. They are the most likely to tell
us a scenario is wrong, which is what we actually want.

| repo | overlap |
|---|---|
| [emmanuelist/reckoner](https://github.com/emmanuelist/reckoner) | "Verifies its own execution against the chain, catching integration errors that report failure on success." Nearly our `silent_noop_node` finding, arrived at independently. Highest-value conversation on this list. |
| [Kelechikizito/Sentinel](https://github.com/Kelechikizito/Sentinel) | "Guardrail layer for autonomous onchain agents." Directly adjacent. |
| [HanzCEO/OathKeeper](https://github.com/HanzCEO/OathKeeper) | Agent-to-agent attestation. Overlaps our ERC-8004 validation work. |
| [Lukeknow0/keeperhub-agent-starter-doctor](https://github.com/Lukeknow0/keeperhub-agent-starter-doctor) | "Safety-first starter and Doctor." Same instinct as ours, different shape. |
| [bolajiev/khtop](https://github.com/bolajiev/khtop) | Terminal dashboard over the audit trail. We both concluded nobody reads it. |

## Tier 3: infrastructure and starters

| repo | note |
|---|---|
| [piiiico/keeperhub-headless-starter](https://github.com/piiiico/keeperhub-headless-starter) | "Zero to a verified transaction, headless." They hit the same onboarding wall we documented in `keeperhub/FRICTION.md`. Worth comparing notes. |
| [subheeksh5599/keepersense](https://github.com/subheeksh5599/keepersense) | Intent-to-execution bridge, 7 MCP tools. Matches `keepersense-demo-transfer`. |
| [CNWAOHIRI/handshake](https://github.com/CNWAOHIRI/handshake) | Conditional escrow, agent-to-agent, settled on Tempo. |
| [thisyearnofear/cognivern](https://github.com/thisyearnofear/cognivern) | Longest-running repo here (since Mar 2025), 3 stars, 12 open issues. |
| [zaikaman/ChronicleAI](https://github.com/zaikaman/ChronicleAI) · [Rolexcode/keepguard](https://github.com/Rolexcode/keepguard) · [AbiodunCreatives/KeeperPilot](https://github.com/AbiodunCreatives/KeeperPilot) · [Ashley-code396/Sentry](https://github.com/Ashley-code396/Sentry) | Active, less description to go on. |

## Suggested order

Message **Tier 1 first**: they get the most obvious value, since our scenarios are
written for the exact pattern their agents use. Then **Tier 2**, where you are asking
peers to critique rather than asking users to adopt, which is a different and easier
conversation.

Ten messages is enough. Three or four real responses answers the question.

## Opening line per tier

**Tier 1**, name the pattern in their code:

> saw bulwark reads the Aave health factor then repays. built a test suite that checks
> whether that premise still holds when the tx actually lands (it usually doesn't,
> ~1 block). one paste, 2 min, no signup: github.com/eienel/sama/blob/main/TESTERS.md
> would like to know if it flags something that isn't real for you

**Tier 2**, peer to peer:

> reckoner and what I built overlap a lot: I found a KeeperHub workflow that reports
> success while its action node never ran. curious whether your verifier catches that
> case. mine's here if useful: github.com/eienel/sama

## Also worth knowing

`KeeperHub/keeperhub` has **25 open issues** and `KeeperHub/cli` has 17. That is the
cheapest route to the $1,000 onboarding bounty, which asks for a merged PR. Our
`FRICTION.md` items are already written up and several are small fixes.
