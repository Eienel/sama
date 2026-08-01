"""Publish harness verdicts to the ERC-8004 Validation Registry.

ERC-8004 defines three registries: Identity, Reputation and Validation. KeeperHub
uses the first two (agent 31875 on mainnet, feedback via giveFeedback) and leaves
Validation entirely unused: `grep -rl ValidationRegistry` over their repo returns
nothing.

That is the registry this project belongs in. Reputation is subjective, a payer saying
"4/5". Validation is objective, an independent checker publishing a verdict and the
evidence behind it. The chaos harness produces the second kind.

Every transaction here is executed *through KeeperHub*, which is the point: we use the
execution layer to publish an independent assessment of the execution layer.

Flow:
  1. register()          IdentityRegistry  -> an agentId for the audited subject
  2. validationRequest() ValidationRegistry -> subject owner asks us to validate
  3. validationResponse() ValidationRegistry -> we publish score 0-100 plus evidence

Run:
    export KEEPERHUB_API_KEY=kh_...
    python3 validator/publish.py --register     # once, mints the agent identity
    python3 validator/publish.py --publish      # score the latest harness run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "keeperhub"))
from kh import call_tool  # noqa: E402

SEPOLIA = "11155111"
IDENTITY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
VALIDATION = "0x8004Cb1BF31DAf7788923b405b754f57acEB4272"
STATE = os.path.join(os.path.dirname(__file__), "state.json")

# Minimal ABIs. The registries are proxies, so auto-fetch resolves the proxy rather
# than the implementation; supplying the exact fragment avoids that entirely.
ABI_REGISTER = json.dumps([{
    "inputs": [{"internalType": "string", "name": "agentURI", "type": "string"}],
    "name": "register",
    "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
    "stateMutability": "nonpayable", "type": "function"}])

ABI_REQUEST = json.dumps([{
    "inputs": [
        {"internalType": "address", "name": "validatorAddress", "type": "address"},
        {"internalType": "uint256", "name": "agentId", "type": "uint256"},
        {"internalType": "string", "name": "requestURI", "type": "string"},
        {"internalType": "bytes32", "name": "requestHash", "type": "bytes32"}],
    "name": "validationRequest", "outputs": [],
    "stateMutability": "nonpayable", "type": "function"}])

ABI_RESPONSE = json.dumps([{
    "inputs": [
        {"internalType": "bytes32", "name": "requestHash", "type": "bytes32"},
        {"internalType": "uint8", "name": "response", "type": "uint8"},
        {"internalType": "string", "name": "responseURI", "type": "string"},
        {"internalType": "bytes32", "name": "responseHash", "type": "bytes32"},
        {"internalType": "string", "name": "tag", "type": "string"}],
    "name": "validationResponse", "outputs": [],
    "stateMutability": "nonpayable", "type": "function"}])


def load_state() -> dict:
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(d: dict) -> None:
    json.dump(d, open(STATE, "w"), indent=2)


def call(contract: str, fn: str, abi: str, args: list, key: str) -> dict:
    out = json.loads(call_tool("execute_contract_call", {
        "chain_id": SEPOLIA, "contract_address": contract, "function_name": fn,
        "abi": abi, "function_args": json.dumps(args), "idempotency_key": key}))
    eid = out.get("executionId")
    for _ in range(10):
        d = json.loads(call_tool("get_direct_execution_status", {"execution_id": eid}))
        if d.get("status") in ("completed", "failed", "error"):
            return d
        time.sleep(3)
    return {"status": "timeout", "executionId": eid}


def keccak(data: bytes) -> str:
    """keccak256, the hash ERC-8004 commits to. Not sha3-256; Ethereum uses the
    original Keccak padding, so hashlib's sha3_256 is the wrong function here."""
    try:
        from Crypto.Hash import keccak as _k
        h = _k.new(digest_bits=256)
        h.update(data)
        return "0x" + h.hexdigest()
    except ImportError:
        from eth_hash.auto import keccak as _kk
        return "0x" + _kk(data).hex()


def summarize_run() -> dict:
    """Turn the latest harness run into a 0-100 score plus a citable record."""
    path = os.path.join(os.path.dirname(__file__), "..", "chaos", "last_run.json")
    run = json.load(open(path))
    total = len(run)
    findings = [r for r in run if r["verdict"] == "FINDING"]
    high = [r for r in findings if r.get("severity") == "HIGH"]
    passes = total - len(findings)

    # Score is the share of tested guarantees that held, with HIGH findings weighted
    # double. Stated explicitly so the number is auditable rather than a vibe.
    penalty = len(findings) + len(high)
    score = max(0, min(100, round(100 * (1 - penalty / (total + len(high))))))

    return {
        "score": score,
        "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "subject": "KeeperHub execution layer",
        "method": "chaos harness, live transactions on Ethereum Sepolia",
        "scoring": "share of tested guarantees that held; HIGH findings weighted double",
        "totals": {"scenarios": total, "passed": passes,
                   "findings": len(findings), "high": len(high)},
        "results": [{"scenario": r["name"], "verdict": r["verdict"],
                     "severity": r.get("severity", "-"), "claim": r.get("claim", ""),
                     "evidence": r.get("evidence", [])} for r in run],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true", help="mint the agent identity")
    ap.add_argument("--publish", action="store_true", help="request + respond with a verdict")
    ap.add_argument("--agent-uri", default="https://github.com/eienel/sama")
    a = ap.parse_args()
    if not os.environ.get("KEEPERHUB_API_KEY"):
        raise SystemExit("error: set KEEPERHUB_API_KEY")

    st = load_state()
    wallet = st.get("wallet", "0x22eC6D712F60Fb032b307D98E1c245af8401d950")

    if a.register:
        print("registering agent identity on IdentityRegistry (Sepolia)")
        d = call(IDENTITY, "register", ABI_REGISTER, [a.agent_uri],
                 f"erc8004-register-{int(time.time())}")
        print("  status:", d.get("status"), "tx:", d.get("transactionHash"))
        st["register_tx"] = d.get("transactionHash")
        st["register_status"] = d.get("status")
        save_state(st)
        print("  note: read agentId from the Registered event in the receipt")
        return 0 if d.get("status") == "completed" else 1

    if a.publish:
        rec = summarize_run()
        blob = json.dumps(rec, sort_keys=True).encode()
        h = keccak(blob)
        print(f"score {rec['score']}/100 from {rec['totals']['scenarios']} scenarios "
              f"({rec['totals']['high']} HIGH)")
        print("  evidence hash:", h)

        agent_id = st.get("agent_id")
        if agent_id is None:
            print("  no agent_id in state.json; run --register first and record the id")
            return 1

        uri = a.agent_uri + "/blob/main/chaos/last_run.json"
        print("1/2 validationRequest")
        d1 = call(VALIDATION, "validationRequest", ABI_REQUEST,
                  [wallet, str(agent_id), uri, h], f"erc8004-req-{h[:18]}")
        print("   ", d1.get("status"), d1.get("transactionHash"))
        if d1.get("status") != "completed":
            print("    error:", str(d1.get("error"))[:200])
            return 1

        print("2/2 validationResponse")
        d2 = call(VALIDATION, "validationResponse", ABI_RESPONSE,
                  [h, str(rec["score"]), uri, h, "execution-reliability"],
                  f"erc8004-res-{h[:18]}")
        print("   ", d2.get("status"), d2.get("transactionHash"))
        st["last_publish"] = {"hash": h, "score": rec["score"],
                              "request_tx": d1.get("transactionHash"),
                              "response_tx": d2.get("transactionHash")}
        save_state(st)
        json.dump(rec, open(os.path.join(os.path.dirname(__file__),
                                         "last_verdict.json"), "w"), indent=2)
        return 0 if d2.get("status") == "completed" else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
