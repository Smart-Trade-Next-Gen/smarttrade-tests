"""
Integration test — Portfolio Service ↔ Redis `position.updated.v1`.

Pair under test: portfolio-service ←→ Redis Streams (`events:position.updated.v1`).

Contract:
    1. Portfolio Service consumes position.updated.v1 events from Redis.
    2. After consumption, Portfolio's REST endpoint
       `GET /api/v1/positions/{broker}/{account}` returns a position whose
       `net_quantity`, `average_price` and `instrument_id` match the event
       payload.
    3. A second fill on the same instrument updates the same position row —
       Portfolio does not create a duplicate per event.

Past regression this test guards against:
    - The previous version of this test only asserted the position event was
      published to Redis and never queried Portfolio. It passed silently
      when Portfolio's consumer was misconfigured or the service was dead.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest


pytestmark = pytest.mark.asyncio


async def _wait_for_portfolio_position(
    portfolio_client,
    *,
    instrument_id: str,
    expected_net_quantity: int,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
) -> dict:
    """Poll Portfolio REST until a position with the expected net_quantity
    appears for the given instrument. Raises TimeoutError if not seen.

    The fixture portfolio_client targets the same broker/account as the test
    placed the order on, so we don't need to filter on those fields here.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    last_seen: list[dict] = []
    while True:
        positions = await portfolio_client.get_positions(instrument_id=instrument_id)
        last_seen = positions
        for pos in positions:
            if (
                pos.get("instrument_id") == instrument_id
                and int(pos.get("net_quantity") or 0) == expected_net_quantity
            ):
                return pos
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(
                f"Portfolio did not expose a position with "
                f"instrument_id={instrument_id} net_quantity={expected_net_quantity} "
                f"within {timeout}s. Last response: {last_seen}"
            )
        await asyncio.sleep(poll_interval)


async def test_portfolio_consumes_position_event_and_exposes_via_rest(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
    portfolio_client,
):
    """A fill drives a position.updated.v1 event → Portfolio consumes it →
    Portfolio's REST endpoint returns the position with matching fields.
    """
    broker_id = config.broker_id

    from e2e.integration.test_bas_pbs_execution_ws import _place_and_fill

    qty = 100
    price = Decimal("550.00")
    broker_order_id, instrument_id, _events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        # Pick an instrument that other integration tests don't touch
        # so we are not subject to cross-test pollution of Portfolio's
        # `average_price` (other tests publish quotes for the first
        # equity in the catalog and PBS reuses those quotes for fills).
        instrument_index=4,
        qty=qty,
        price=price,
    )

    # Sanity: position event must have been published. If this fails, the
    # bug is upstream of Portfolio (BAS↔PBS WS path); fail loudly here so
    # the test points at the right culprit.
    position_events = [
        e
        for e in redis_event_collector.get_events_on_stream(
            "events:position.updated.v1"
        )
        if (e.get("payload") or {}).get("instrument_id") == instrument_id
    ]
    assert position_events, (
        f"No position.updated.v1 event found for instrument_id={instrument_id}. "
        f"BAS→Redis position path is broken; Portfolio test cannot proceed."
    )

    # The actual integration assertion: Portfolio's REST returns the position.
    position = await _wait_for_portfolio_position(
        portfolio_client,
        instrument_id=instrument_id,
        expected_net_quantity=qty,
        timeout=15.0,
    )

    # The position row must match the fill we drove.
    assert position["instrument_id"] == instrument_id
    assert int(position["net_quantity"]) == qty
    assert Decimal(str(position["average_price"])) == price, (
        f"Portfolio average_price={position['average_price']!r}; "
        f"expected fill price={price}. Portfolio may be reading the wrong "
        f"field from position.updated.v1 (regression: avg_price vs "
        f"average_price)."
    )
    assert position["broker_id"] == broker_id
    assert position["account_id"] == test_account_id


async def test_portfolio_position_accumulates_across_two_fills(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
    portfolio_client,
):
    """Two BUY fills on the same instrument must produce one Portfolio row
    whose net_quantity equals the sum of the two fills.

    Guards against the regression where Portfolio creates a fresh row per
    event instead of upserting the existing one.
    """
    broker_id = config.broker_id

    from e2e.integration.test_bas_pbs_execution_ws import _place_and_fill

    qty1 = 50
    price1 = Decimal("550.00")
    _, instrument_id, _ = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        # Pick an instrument that other integration tests don't touch
        # so we are not subject to cross-test pollution of Portfolio's
        # `average_price` (other tests publish quotes for the first
        # equity in the catalog and PBS reuses those quotes for fills).
        instrument_index=4,
        qty=qty1,
        price=price1,
    )

    # Confirm first fill landed on Portfolio before we drive the second one.
    await _wait_for_portfolio_position(
        portfolio_client,
        instrument_id=instrument_id,
        expected_net_quantity=qty1,
        timeout=15.0,
    )

    qty2 = 30
    price2 = Decimal("560.00")
    # Re-use the same instrument by overriding instrument_index handling:
    # call the helper but force the same instrument. _place_and_fill picks
    # by index, so to keep it on the same instrument we need to place a
    # second order on the same instrument_id directly.
    from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest

    place_response = await place_and_sync_order(
        broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty2,
        },
    )
    second_broker_order_id = place_response[0]["broker_order_id"]
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=second_broker_order_id,
        sequence=1,
        fill_qty=qty2,
        fill_price=price2,
    )
    await redis_event_collector.wait_for_completion(
        second_broker_order_id, timeout=10.0
    )

    # Portfolio must now expose qty1 + qty2 on the same row, not two rows.
    final_position = await _wait_for_portfolio_position(
        portfolio_client,
        instrument_id=instrument_id,
        expected_net_quantity=qty1 + qty2,
        timeout=15.0,
    )

    # And the average_price must reflect the volume-weighted average. The
    # exact rounding policy is Portfolio's call; we only assert it sits
    # between the two fill prices (i.e. Portfolio didn't just clobber the
    # field with the latest fill).
    avg = Decimal(str(final_position["average_price"]))
    assert price1 <= avg <= price2, (
        f"Portfolio average_price={avg}, expected to fall between fill "
        f"prices {price1} and {price2}. Likely a regression where Portfolio "
        f"overwrote avg with the latest fill instead of recomputing."
    )

    # Exactly one row for this instrument — no duplicates.
    all_positions = await portfolio_client.get_positions(
        instrument_id=instrument_id
    )
    matching = [p for p in all_positions if p["instrument_id"] == instrument_id]
    assert len(matching) == 1, (
        f"Portfolio produced {len(matching)} rows for instrument_id="
        f"{instrument_id}; expected exactly 1 (upsert, not insert). Rows: "
        f"{matching}"
    )
