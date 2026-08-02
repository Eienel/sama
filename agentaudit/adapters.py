"""Execution adapters. Implement one to audit a different execution layer.

Two ship here: KeeperHub, and an in-memory Mock whose behaviour is configurable so the
scenarios can be exercised with no API key, no funds, and no network. The Mock is not a
toy: it is how you check that a scenario can actually come back clean, which is the
difference between a test suite and a hit piece.
"""

from __future__ import annotations

import json
import os
import sys
import time

from .core import Conflict, Execution

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "keeperhub"))


class KeeperHubAdapter:
    """Drives KeeperHub over its MCP endpoint with an organisation API key."""

    name = "keeperhub"

    def __init__(self, chain_id: str = "11155111", wallet: str | None = None):
        from kh import call_tool  # imported late so the Mock needs no dependency
        self._call = call_tool
        self.chain_id = chain_id
        self.wallet = wallet or os.environ.get(
            "AUDIT_WALLET", "0x22eC6D712F60Fb032b307D98E1c245af8401d950")

    def _exec(self, tool: str, args: dict) -> Execution:
        try:
            out = json.loads(self._call(tool, args))
        except RuntimeError as e:
            m = str(e)
            if "409" in m:
                raise Conflict(
                    "in_progress" if "already being processed" in m else "reused", m)
            raise
        return Execution(id=out.get("executionId", ""),
                         status=out.get("status", "unknown"), raw=out)

    def transfer(self, to, amount, *, token=None, idempotency_key=None) -> Execution:
        a = {"chain_id": self.chain_id, "to_address": to, "amount": amount}
        if token:
            a["token_address"] = token
        if idempotency_key:
            a["idempotency_key"] = idempotency_key
        return self._exec("execute_transfer", a)

    def contract_call(self, address, function, *, args=None, abi=None,
                      idempotency_key=None) -> Execution:
        a = {"chain_id": self.chain_id, "contract_address": address,
             "function_name": function}
        if args is not None:
            a["function_args"] = json.dumps(args)
        if abi:
            a["abi"] = abi
        if idempotency_key:
            a["idempotency_key"] = idempotency_key
        return self._exec("execute_contract_call", a)

    def status(self, execution_id: str) -> Execution:
        d = json.loads(self._call("get_direct_execution_status",
                                  {"execution_id": execution_id}))
        return Execution(id=execution_id, status=d.get("status", "unknown"),
                         tx_hash=d.get("transactionHash"),
                         error=d.get("error"), raw=d)

    def block_number(self) -> int:
        MC3 = "0xcA11bde05977b3631167028862bE2a173976CA11"
        out = json.loads(self._call("execute_contract_call", {
            "chain_id": self.chain_id, "contract_address": MC3,
            "function_name": "getBlockNumber"}))["result"]
        return int(out["blockNumber"] if isinstance(out, dict) else out)


class MockAdapter:
    """In-memory execution layer with switchable guarantees.

    Lets a scenario be checked in both directions offline: with `dedupe=True` it must
    PASS, with `dedupe=False` it must FIND. A scenario that cannot come back clean is a
    demo, and this is how you catch that before shipping it.
    """

    name = "mock"

    def __init__(self, *, dedupe: bool = True, honest_errors: bool = True,
                 block_lag: int = 1, chain_id: str = "31337"):
        self.chain_id = chain_id
        self.dedupe, self.honest_errors, self.block_lag = dedupe, honest_errors, block_lag
        self._keys: dict[str, str] = {}
        self._execs: dict[str, Execution] = {}
        self._block = 1_000_000
        self._n = 0

    def _new(self, ok=True, err=None) -> Execution:
        self._n += 1
        self._block += self.block_lag
        e = Execution(id=f"mock-{self._n}", status="completed" if ok else "failed",
                      tx_hash=f"0x{self._n:064x}" if ok else None, error=err)
        self._execs[e.id] = e
        return e

    def _dedupe(self, idempotency_key, payload) -> Execution | None:
        if not self.dedupe:
            return None
        # A correct provider can protect the default path by deriving a key from the
        # semantic payload when the caller supplies none. Modelling that is what lets
        # omitted_key come back clean, which it must be able to do.
        idempotency_key = idempotency_key or f"auto:{json.dumps(payload, sort_keys=True)}"
        prev = self._keys.get(idempotency_key)
        if prev is None:
            return None
        if self._execs[prev].raw.get("payload") != payload:
            raise Conflict("reused", "key reused with a different payload")
        return self._execs[prev]

    def _record(self, key, e, payload):
        e.raw["payload"] = payload
        if self.dedupe:
            key = key or f"auto:{json.dumps(payload, sort_keys=True)}"
        if key:
            self._keys[key] = e.id

    def transfer(self, to, amount, *, token=None, idempotency_key=None) -> Execution:
        payload = {"to": to, "amount": str(float(amount)), "token": token}
        hit = self._dedupe(idempotency_key, payload)
        if hit:
            return hit
        e = self._new()
        self._record(idempotency_key, e, payload)
        return e

    def contract_call(self, address, function, *, args=None, abi=None,
                      idempotency_key=None) -> Execution:
        payload = {"address": address, "function": function, "args": args}
        hit = self._dedupe(idempotency_key, payload)
        if hit:
            return hit
        bad = function == "transfer" and args and str(args[-1]).isdigit() and int(args[-1]) > 10**24
        e = self._new(ok=not bad,
                      err="mock revert: insufficient balance" if bad and self.honest_errors else None)
        if bad and not self.honest_errors:
            e.status = "completed"  # the dangerous case: failure reported as success
        self._record(idempotency_key, e, payload)
        return e

    def status(self, execution_id: str) -> Execution:
        return self._execs.get(execution_id, Execution(id=execution_id))

    def block_number(self) -> int:
        return self._block


class LocalEVMAdapter:
    """A real in-process EVM (eth-tester / py-evm) driven by a raw signer.

    This is what an agent gets with no execution layer at all: it signs and sends, and
    nothing else happens for it. Deliberately the opposite end of the spectrum from a
    managed provider, which is what makes it useful as a second implementation. If a
    scenario only works against KeeperHub, running it here exposes that.

    It needs no account, no funds and no network, so the whole suite is reproducible by
    anyone in seconds.
    """

    name = "local-evm"

    # Minimal contract whose runtime is PUSH1 0 PUSH1 0 REVERT: it always reverts.
    ALWAYS_REVERT = "0x600580600b6000396000f360006000fd"

    def __init__(self, chain_id: str = "131277322940537"):
        from web3 import Web3, EthereumTesterProvider
        self.w3 = Web3(EthereumTesterProvider())
        self.chain_id = str(self.w3.eth.chain_id)
        self.wallet = self.w3.eth.accounts[0]
        self._peer = self.w3.eth.accounts[1]
        self._execs: dict[str, Execution] = {}
        self._n = 0
        self._revert_addr = None

    def _record(self, tx_hash, ok: bool, err: str | None = None) -> Execution:
        self._n += 1
        e = Execution(id=f"evm-{self._n}",
                      status="completed" if ok else "failed",
                      tx_hash=tx_hash.hex() if hasattr(tx_hash, "hex") else tx_hash,
                      error=err)
        self._execs[e.id] = e
        return e

    def transfer(self, to, amount, *, token=None, idempotency_key=None) -> Execution:
        # A raw signer has no idempotency layer at all. The key is accepted and
        # ignored, which is exactly the point: nothing dedupes for you.
        try:
            h = self.w3.eth.send_transaction({
                "from": self.wallet, "to": self.w3.to_checksum_address(to),
                "value": self.w3.to_wei(float(amount), "ether")})
            r = self.w3.eth.wait_for_transaction_receipt(h)
            return self._record(h, r.status == 1,
                                None if r.status == 1 else "reverted")
        except Exception as ex:
            return self._record("0x", False, str(ex)[:160])

    def _deploy_reverter(self) -> str:
        if self._revert_addr is None:
            h = self.w3.eth.send_transaction(
                {"from": self.wallet, "data": self.ALWAYS_REVERT})
            self._revert_addr = self.w3.eth.wait_for_transaction_receipt(h).contractAddress
        return self._revert_addr

    def contract_call(self, address, function, *, args=None, abi=None,
                      idempotency_key=None) -> Execution:
        # The scenarios pass a mainnet token address that does not exist here, so a
        # call meant to revert is routed at a contract that genuinely does.
        target = self._deploy_reverter()
        try:
            h = self.w3.eth.send_transaction(
                {"from": self.wallet, "to": target, "data": "0x"})
            r = self.w3.eth.wait_for_transaction_receipt(h)
            return self._record(h, r.status == 1,
                                None if r.status == 1 else "execution reverted")
        except Exception as ex:
            return self._record("0x", False, str(ex)[:160])

    def status(self, execution_id: str) -> Execution:
        return self._execs.get(execution_id, Execution(id=execution_id))

    def block_number(self) -> int:
        return self.w3.eth.block_number
