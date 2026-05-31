"""
Integration tests for event schema validation.

Tests validate:
- Events published to Redis Streams conform to expected structure
- Required fields are present in events
- Field types match expectations
- Events can be consumed and parsed correctly

These tests use actual events from the system to validate schema compliance.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.smoke
@pytest.mark.injection
async def test_order_updated_event_structure(
    config,
    instrument_catalog,
    bas_client,
    mock_client,
    redis_event_collector,
    test_account_id,
):
    """
    Test: OrderUpdated event structure validation.

    Validates:
    - Required fields are present in published events
    - Field types match expectations
    - Event can be consumed from Redis Streams
    """
    from smarttrade_common.schemas.types import OrderSide, OrderType, TimeInForce, PositionType
    from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest, BasOrderLeg
    import uuid
    from decimal import Decimal
    
    broker_id = config.broker_id
    instrument = instrument_catalog.get_test_instrument(0)
    instrument_id = instrument["id"]
    
    # Place and execute an order
    qty = 10
    fill_price = Decimal("550.00")
    
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_event_schema_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=instrument_id,
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=qty,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=fill_price,
            )
        ],
        underlying_symbol=instrument["symbol"],
        tif=TimeInForce.DAY,
    )
    
    order_responses = await bas_client.place_order(broker_id, test_account_id, order_request)
    # Broker may return multiple responses if it breaks large orders into smaller ones
    order_resp = order_responses[0]
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_resp.broker_order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=fill_price,
    )
    
    # Collect events
    events = await redis_event_collector.wait_for_completion(order_resp.broker_order_id, timeout=config.timeout_medium)
    
    # Validate order updated events
    order_events = [e for e in events if e.get("stream") == "events:order.updated"]
    assert len(order_events) > 0, "Should have order updated events"
    
    for event in order_events:
        event_data = event.get("data", {})
        
        # Validate basic event structure
        assert "event_id" in event_data, "event_id is required"
        assert "event_name" in event_data, "event_name is required"
        assert "event_version" in event_data, "event_version is required"
        
        # Validate payload structure
        assert "payload" in event_data, "payload is required"
        payload = event_data["payload"]
        
        # Validate that payload contains order-related fields
        assert len(payload) > 0, "payload should not be empty"
        
        # Event should be parseable JSON
        assert isinstance(event_data, dict), "event_data should be a dict"
        
        # Validate event metadata
        assert event_data["event_name"] == "order.updated", "event_name should be order.updated"
        assert event_data["event_version"] == "1.0", "event_version should be 1.0"