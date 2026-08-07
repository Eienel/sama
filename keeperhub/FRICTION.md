# Getting to a first KeeperHub call from a headless environment

Notes taken live while going from a fresh account to a working onchain call from a
remote container with no browser. Written for the onboarding-UX bounty: every item is
something that cost real time, with the fix that would have saved it.

Context: the environment is a cloud container. No browser, no GUI, no localhost the
user can reach. This is not an exotic setup: it is where autonomous agents actually
run (CI, servers, sandboxes).

## 1. Onboarding dead-ends at step 3/3 for anyone without a local browser

Step 3 of the `/welcome` wizard ("Connect your AI agent") offers exactly one path:

```
claude mcp add --transport http keeperhub https://app.keeperhub.com/mcp
# then: run /mcp and complete the browser sign-in
```

That OAuth handshake needs a browser on the same machine as the agent. In a container
it cannot complete. The wizard has no skip, and offers no alternative.

The official Claude plugin (`KeeperHub/claude-plugins`) is the same story:
`/keeperhub:login` is documented as OAuth-browser-only, with no `KEEPERHUB_API_KEY`
support.

**A headless path does exist**: an organisation API key passed as a bearer token,
documented under `ai-tools/mcp-server`. It works perfectly. It is simply absent from
onboarding and from the plugin, which are the two places a new user actually looks.

> **Fix:** add "no browser? use an API key" to step 3, and support
> `KEEPERHUB_API_KEY` in the plugin.

**Update, 7 August 2026:** KeeperHub shipped `docs/api/headless-onboarding.md`
(PR #1908, released in v2.88.0) covering SIWE sign-in without a browser, creating an
organization API key programmatically, funding the right wallet, and gas. That closes the
documentation half of this item. Authored 4 August, before our PR merged, so this is
KeeperHub's own work and not a result of this write-up. The wizard itself still offers
only OAuth at step 3/3, so the in-product half stands.

## 2. The API-keys page has no discoverable URL

Docs say "Settings > API Keys > Organisation tab". From a fresh account stuck in the
wizard, that page is hard to reach, and every guessable URL 404s:

```
/settings  /settings/api-keys  /settings/api_keys  /account/api-keys
/organisation/api-keys  /org/api-keys  /profile/api-keys  /api-keys
/developers  /settings/keys  /settings/tokens  /settings/developer   -> all 404
```

The only `/settings/*` route in the client bundle is `/settings/mcp/reauthorize`. The
backing endpoint `/api/api-keys` returns **401** (not 404), so the feature is live -
its UI just isn't linkable. `https://app.keeperhub.com/workflows` (200) is the usable
way past the wizard.

> **Fix:** give the API-keys page a stable deep link and put it in the docs.

## 3. The edge 403s the default Python user-agent

A bare `urllib` request with a valid API key returns **403 Forbidden**, no body:

```
urllib.error.HTTPError: HTTP Error 403: Forbidden
```

The key is fine. The `User-Agent` is the problem: reproducible with
`curl -A "Python-urllib/3.11"`, which also 403s, while the same request with curl's
default agent succeeds. Any conventional UA string passes.

This is a nasty one: a 403 next to a fresh API key reads unmistakably as "bad key",
and sends you back to re-issue credentials that were never wrong.

> **Fix:** allow the default agent of common HTTP clients, or return a body saying
> the user-agent was rejected.

## 4. Session ID is required but undocumented in the API-key flow

After `initialize`, every subsequent call must carry the `Mcp-Session-Id` returned in
the initialize **response header**. Omit it and you get a bare `400 Bad Request` with
no explanation. Standard MCP, but invisible if you're driving the endpoint directly
rather than through an SDK: which is exactly what the headless path forces you to do.

> **Fix:** one curl example in the API-key docs showing the two-step handshake.

## 5. Tool parameters are snake_case; the docs read camelCase

`chainId` / `contractAddress` are rejected; the schema wants `chain_id` /
`contract_address`. The validation error is clear once you hit it, but the surrounding
docs and workflow JSON use camelCase, so the first attempt reliably fails.

## 6. Filling in more fields makes workflow creation fail

Not a blocker to a first call, but the sharpest footgun found, and it belongs here
rather than in a bug report because it is about what the platform teaches a newcomer.

An action node without `actionType` is accepted. Add `actionType` and creation rejects
the workflow for a missing `abi`, even though `execute_contract_call` auto-fetches an
ABI perfectly well (see "What went right" below). The vaguer definition is the one that
validates.

A newcomer who fills in more fields gets an error, backs off to the version that was
accepted, and ships a workflow that reports success forever without ever running its
action. The tooling rewarded being less specific, and the reward was silent.

**Fix:** require `actionType` at creation and auto-fetch the `abi` in the workflow
validator, so the more complete definition is also the accepted one.

## What went right

- The API key worked instantly once obtained, with `mcp:read mcp:write mcp:admin`.
- **ABI auto-fetch is excellent.** A read call against verified USDC on Base needed
  only address, chain and function name: no ABI:

  ```
  execute_contract_call {"chain_id":"8453",
    "contract_address":"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "function_name":"totalSupply"}
  -> {"result": "4145349003927320"}
  ```

- `list_action_schemas` returns the full chain catalogue with testnet flags and
  explorer URLs in one call: genuinely well designed.
- 35 tools, clearly named and described.

## Cumulative cost

Roughly two hours from verified account to first successful call, essentially all of
it spent on items 1-4, none of which are about blockchain. A user without an existing
reason to believe the headless path exists would likely have stopped at item 1.
