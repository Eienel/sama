# ERC-8004 Validator

Publishes the harness's verdicts to the **ERC-8004 Validation Registry**, so other
agents can read an independent assessment of an execution layer before trusting it.

## Why this registry

ERC-8004 defines three registries. KeeperHub uses two:

| registry | purpose | KeeperHub |
|---|---|---|
| Identity | ERC-721 agent identity | in use, agent 31875 on mainnet |
| Reputation | feedback from counterparties | in use, via `giveFeedback` |
| **Validation** | validators publishing verification results | **unused** |

`grep -rl "ValidationRegistry"` across their repo returns nothing.

The distinction matters. **Reputation is subjective**: a payer rating 4/5. **Validation
is objective**: an independent checker publishing a verdict and the evidence behind it.
Their reputation path is also closed to us by design, since `giveFeedback` requires
having paid for the execution, requires mainnet gas, and the contract blocks
self-feedback.

A validator needs none of that, because its standing comes from published evidence.

## What this record is, and is not

**The agentId on our validation record is 9139, an identity we minted ourselves. It is
not KeeperHub's agent.** KeeperHub's identity is 31875 on Ethereum mainnet, and it does
not exist on Sepolia:

```
ownerOf(31875) on Sepolia IdentityRegistry -> revert ERC721NonexistentToken(31875)
```

So this is not a third-party rating of KeeperHub's registered agent, and describing it
as one would be false. What it is: a working demonstration of the publication
mechanism, and a hash-committed, timestamped publication of our verdict by a known
validator address. The subject of the audit is named inside the record; the registry
entry proves when we said it and that we have not restated it since.

Validating KeeperHub's actual agent means publishing against 31875 on mainnet, which
needs mainnet gas and is a decision to make deliberately rather than by default.

## Live onchain record

Every transaction below was executed **through KeeperHub**, which is the point: the
execution layer was used to publish an independent assessment of itself.

```
chain                Ethereum Sepolia (11155111)
IdentityRegistry     0x8004A818BFB912233c491871b3d84c89A494BD9e
ValidationRegistry   0x8004Cb1BF31DAf7788923b405b754f57acEB4272
agentId              9139
validator            0x22eC6D712F60Fb032b307D98E1c245af8401d950
```

| step | transaction |
|---|---|
| `register` | [`0x02130b6f…eac22c`](https://sepolia.etherscan.io/tx/0x02130b6f04edb232f73a8826fb47e5e26a9186e0c286be61022e757606eac22c) |
| `validationRequest` | [`0x49dd9836…98f696`](https://sepolia.etherscan.io/tx/0x49dd98362217f794ae03956de5328585440c9d585bac25b6852f8da24198f696) |
| `validationResponse` | [`0x52a568af…0aa478`](https://sepolia.etherscan.io/tx/0x52a568aff9d960854da832769d36b10d83646cd4fb33fee3654de546820aa478) |

Read it back the way any other agent would, via `getValidationStatus`:

```json
{"validatorAddress":"0x22eC6D712F60Fb032b307D98E1c245af8401d950",
 "agentId":"9139","response":"38",
 "responseHash":"0xc04b861f555a9989ef6a92e471784a475c7217a66aabeb98be58b8c4290b902e",
 "tag":"execution-reliability","lastUpdate":"1785545196"}
```

## What the score means

**38 / 100**, tag `execution-reliability`, from 13 scenarios with 6 findings, 4 of them
HIGH.

The formula is stated so the number is auditable rather than a vibe: the share of
tested guarantees that held, with HIGH findings weighted double.

```
score = 100 * (1 - (findings + high) / (scenarios + high))
      = 100 * (1 - (6 + 4) / (12 + 4))  =  38
```

`responseHash` is the keccak256 of the full verdict record, so the onchain number is
bound to a specific set of results and cannot be quietly restated later.

## Running

```bash
export KEEPERHUB_API_KEY=kh_...
python3 validator/publish.py --register   # once, mints the identity
python3 validator/publish.py --publish    # score the latest harness run
```

`--register` mints an ERC-721 identity; read the `agentId` from the `Transfer` event in
the receipt and record it in `state.json`.

## Honest limits

- Sepolia, not mainnet. The registries are the same code at the canonical testnet proxy
  addresses, but a mainnet verdict would carry more weight and cost real gas.
- The subject is an agent identity we minted ourselves. Validating a third party's
  agentId is the same call with a different id, but publishing verdicts about other
  people's agents is a decision to make deliberately rather than by default.
- keccak256 requires `pycryptodome` or `eth-hash`; `hashlib.sha3_256` is a different
  function and will produce the wrong hash.
