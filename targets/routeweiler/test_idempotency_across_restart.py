"""The durable draw dedupe cannot fire across a process restart.

``_draw.py`` short-circuits on ``(envelope_id, idempotency_key)`` against SQLite,
so the dedupe is durable by construction. The key it matches on is
``sha256(f"{request_id}:{attempt}")`` where ``request_id = _uuid7()`` is minted
fresh at every 402 interception (``_auth.py:197``), so two attempts at the same
piece of work never present the same key unless they share one interception.

These tests pin the current behaviour.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from eth_account.signers.local import LocalAccount

from routeweiler import BudgetEnvelope, Funding, Routeweiler
from routeweiler.trace.sink_sqlite import TraceSink

_URL = "http://testserver/protected"

_SPEC = BudgetEnvelope(
    id="restart-envelope",
    cap_minor_units=10_000,
    cap_currency="usd",
    allowed_rails=["x402"],
    ttl_seconds=3_600,
)


def _draws(db_path: Path) -> list[dict]:  # type: ignore[type-arg]
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM draws ORDER BY issued_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _make_client(
    test_account: LocalAccount,
    transport: httpx.ASGITransport,
    db_path: Path,
    keystore_root: Path,
) -> Routeweiler:
    """A client sharing one envelope, trace DB and keystore across sessions."""
    sink = TraceSink.sqlite(db_path, url_mode="raw")
    with patch("routeweiler.rails.x402.x402Client") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.create_payment_payload = AsyncMock(
            return_value={
                "x402Version": 2,
                "payload": {
                    "authorization": {
                        "from": test_account.address,
                        "to": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
                        "value": "1000",
                        "validAfter": "0",
                        "validBefore": "9999999999",
                        "nonce": "0xdeadbeef",
                    },
                    "signature": "0x" + "ab" * 65,
                },
            }
        )
        mock_cls.return_value = mock_instance
        client = Routeweiler(
            funding=[Funding.base_sepolia_usdc(wallet=test_account)],
            trace_sink=sink,
            budget_envelope=_SPEC,
            keystore_root=keystore_root,
        )
        client._http = httpx.AsyncClient(
            auth=client._http.auth,
            event_hooks=client._http.event_hooks,
            transport=transport,
        )
    return client


async def test_same_work_after_restart_draws_twice(
    test_account: LocalAccount,
    mock_x402_app: httpx.ASGITransport,
    tmp_trace_db_path: Path,
    tmp_path: Path,
) -> None:
    """One piece of work, paid for twice, because the key did not survive."""
    ks = tmp_path / "keys"

    # Session one: the agent pays for the resource.
    async with _make_client(test_account, mock_x402_app, tmp_trace_db_path, ks) as c1:
        r1 = await c1.get(_URL)
    assert r1.status_code == 200

    # Session two: same process image restarted, same envelope, same URL. The
    # agent has no memory of session one beyond the shared SQLite state, which
    # is exactly the state the dedupe was built to consult.
    async with _make_client(test_account, mock_x402_app, tmp_trace_db_path, ks) as c2:
        r2 = await c2.get(_URL)
    assert r2.status_code == 200

    draws = _draws(tmp_trace_db_path)
    keys = {d["idempotency_key"] for d in draws}

    # The durable short-circuit never fires: two draws, two distinct keys, and
    # the envelope is debited twice for one intended purchase.
    assert len(draws) == 2, f"expected 2 draws, got {len(draws)}"
    assert len(keys) == 2, "keys collided, dedupe would have fired"
    # Both draws reserve against the same envelope, so the cap is consumed twice
    # for one intended purchase.
    assert draws[0]["amount_reserved_minor_units"] == draws[1]["amount_reserved_minor_units"]
    assert {d["envelope_id"] for d in draws} == {"restart-envelope"}


async def test_repeat_call_in_one_session_also_draws_twice(
    test_account: LocalAccount,
    mock_x402_app: httpx.ASGITransport,
    tmp_trace_db_path: Path,
    tmp_path: Path,
) -> None:
    """No restart needed: a caller-level retry inside one session pays twice too."""
    ks = tmp_path / "keys"
    async with _make_client(test_account, mock_x402_app, tmp_trace_db_path, ks) as c:
        await c.get(_URL)
        await c.get(_URL)

    draws = _draws(tmp_trace_db_path)
    assert len(draws) == 2
    assert len({d["idempotency_key"] for d in draws}) == 2
