"""
Integration test — Journal Service ↔ Redis `order.updated` / `trade.executed`.

Pair under test: journal-service ←→ Redis Streams.

Contract:
    1. Journal consumes `order.updated` and persists the order. After a
       fill, `GET /api/v1/orders/{broker}/{account}` returns the order with
       status FILLED, the broker_order_id, and the correct instrument_id.
    2. Journal consumes `trade.executed` and persists the trade. After a
       fill, `GET /api/v1/trades/{broker}/{account}` returns a trade for that
       order with quantity and price matching the fill.

Past regression this test guards against:
    - The previous version wrapped every Journal call in `try/except: pass`,
      so it passed silently when Journal didn't consume events at all (e.g.
      the smarttrade-common SchemaRegistry.get_event_schema bug — see
      [[journal-trade-consumer-validate-schema]]).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest


pytestmark = pytest.mark.asyncio


async def _wait_for_journal_order(
    journal_client,
    *,
    broker_order_id: str,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
) -> dict:
    """Poll Journal /orders until an entry with the given broker_order_id is
    present.  Journal stores the broker order id under `order_id` in its
    response (see journal-service router for /orders)."""
    deadline = asyncio.get_event_loop().time() + timeout
    last_seen: list[dict] = []
    while True:
        # journal_client.get_orders paginates via (page, page_size). A
        # single page of 200 is large enough for any single test run.
        orders = await journal_client.get_orders(page_size=200)
        last_seen = orders
        for order in orders:
            # Journal exposes the canonical broker order id as `broker_order_id`
            if order.get("broker_order_id") == broker_order_id:
                return order
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(
                f"Journal did not expose an order with broker_order_id="
                f"{broker_order_id} within {timeout}s. Last response (first "
                f"3 of {len(last_seen)}): {last_seen[:3]}"
            )
        await asyncio.sleep(poll_interval)


async def _wait_for_journal_trade(
    journal_client,
    *,
    broker_order_id: str,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
) -> dict:
    """Poll Journal /trades until a trade for the given broker_order_id is
    present."""
    deadline = asyncio.get_event_loop().time() + timeout
    last_seen: list[dict] = []
    while True:
        trades = await journal_client.get_trades(limit=200)
        last_seen = trades
        for trade in trades:
            if trade.get("broker_order_id") == broker_order_id:
                return trade
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(
                f"Journal did not expose a trade for broker_order_id="
                f"{broker_order_id} within {timeout}s. Last response (first "
                f"3 of {len(last_seen)}): {last_seen[:3]}"
            )
        await asyncio.sleep(poll_interval)


async def test_journal_consumes_order_event_and_exposes_via_rest(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
    journal_client,
):
    """A fill drives `order.updated` events → Journal consumes them →
    Journal's REST returns the order with status=FILLED.
    """
    broker_id = config.broker_id

    from e2e.integration.bas.test_bas_pbs_execution_ws import _place_and_fill

    qty = 100
    price = Decimal("550.00")
    broker_order_id, instrument_id, _events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
        qty=qty,
        price=price,
    )

    order = await _wait_for_journal_order(
        journal_client, broker_order_id=broker_order_id
    )

    assert order.get("instrument_id") == instrument_id, (
        f"Journal order has instrument_id={order.get('instrument_id')}; "
        f"expected {instrument_id}"
    )
    status = (order.get("status") or "").upper()
    assert status == "FILLED", (
        f"Journal order status={status!r}; expected FILLED. Full row: {order}"
    )


async def test_journal_consumes_trade_event_and_exposes_via_rest(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
    journal_client,
):
    """A fill drives a `trade.executed` event → Journal consumes it →
    Journal's REST returns the trade with quantity and price matching the fill.
    """
    broker_id = config.broker_id

    from e2e.integration.bas.test_bas_pbs_execution_ws import _place_and_fill

    qty = 100
    price = Decimal("550.00")
    broker_order_id, instrument_id, _events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
        qty=qty,
        price=price,
    )

    trade = await _wait_for_journal_trade(
        journal_client, broker_order_id=broker_order_id
    )

    assert trade.get("instrument_id") == instrument_id
    assert int(trade.get("quantity") or 0) == qty, (
        f"Journal trade quantity={trade.get('quantity')!r}; expected {qty}"
    )
    assert Decimal(str(trade.get("price"))) == price, (
        f"Journal trade price={trade.get('price')!r}; expected {price}"
    )
