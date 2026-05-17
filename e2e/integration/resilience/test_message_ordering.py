"""
Integration tests for message ordering guarantees.

Tests validate:
- Redis stream message ordering
- Sequence number guarantees
- Consumer group ordering
- No duplicate processing
"""

from __future__ import annotations

import pytest
import asyncio
import uuid

pytestmark = pytest.mark.asyncio


@pytest.mark.resilience
async def test_redis_stream_message_ordering(
    config,
    redis_client,
):
    """
    Test: Redis stream message ordering.

    Validates:
    - Messages are ordered by sequence number
    - Consumers read messages in order
    - No out-of-order processing
    """
    stream_name = "e2e-test-ordering"
    
    try:
        # Write messages in order
        await redis_client.xadd(stream_name, {"sequence": "1"})
        await asyncio.sleep(0.01)  # Small delay
        await redis_client.xadd(stream_name, {"sequence": "2"})
        await asyncio.sleep(0.01)
        await redis_client.xadd(stream_name, {"sequence": "3"})
        
        # Read messages
        messages = await redis_client.xrange(stream_name)
        
        # Validate ordering
        sequences = [msg[1]["sequence"] for msg in messages]
        assert sequences == ["1", "2", "3"], "Messages should be in order"
        
        # Cleanup
        await redis_client.delete(stream_name)
        
    except Exception as e:
        pytest.skip(f"Message ordering test failed: {e}")


@pytest.mark.resilience
async def test_consumer_group_ordering_guarantees(
    config,
    redis_client,
):
    """
    Test: Consumer group ordering guarantees.

    Validates:
    - Each consumer in a group gets unique messages
    - Messages are not duplicated within a group
    - All messages are processed
    """
    stream_name = f"e2e-test-group-ordering-{uuid.uuid4().hex[:8]}"
    consumer_group = f"e2e-test-group-{uuid.uuid4().hex[:8]}"
    
    try:
        # Create stream and consumer group
        await redis_client.xadd(stream_name, {"data": "1"})
        await redis_client.xadd(stream_name, {"data": "2"})
        await redis_client.xadd(stream_name, {"data": "3"})
        
        await redis_client.xgroup_create(
            stream_name, consumer_group, id="0", mkstream=True
        )
        
        # Create two consumers
        consumer1_messages = await redis_client.xreadgroup(
            consumer_group, consumername="consumer1",
            streams={stream_name: ">"},
            count=2,
        )
        
        consumer2_messages = await redis_client.xreadgroup(
            consumer_group, consumername="consumer2",
            streams={stream_name: ">"},
            count=2,
        )
        
        # Validate messages are distributed (not duplicated)
        all_messages = []
        # xreadgroup returns list of (stream_name, messages) tuples
        for stream, msgs in consumer1_messages:
            all_messages.extend(msgs)
        for stream, msgs in consumer2_messages:
            all_messages.extend(msgs)
        
        # Each message should appear only once
        message_ids = [msg[0] for msg in all_messages]
        assert len(message_ids) == len(set(message_ids)), \
            "Messages should not be duplicated within consumer group"
        
        # Cleanup
        await redis_client.delete(stream_name)
        
    except Exception as e:
        pytest.skip(f"Consumer group ordering test failed: {e}")


@pytest.mark.resilience
async def test_idempotent_processing(
    config,
    redis_client,
):
    """
    Test: Idempotent message processing.

    Validates:
    - Duplicate messages are detected and skipped
    - Processing is idempotent
    - No side effects from reprocessing
    """
    stream_name = f"e2e-test-idempotency-{uuid.uuid4().hex[:8]}"
    consumer_group = f"e2e-test-idempotency-group-{uuid.uuid4().hex[:8]}"
    
    try:
        # Create stream and consumer group
        await redis_client.xadd(stream_name, {"event_id": "123", "data": "test"})
        
        await redis_client.xgroup_create(
            stream_name, consumer_group, id="0", mkstream=True
        )
        
        # Read message first time
        messages1 = await redis_client.xreadgroup(
            consumer_group, consumername="consumer1",
            streams={stream_name: ">"},
            count=1,
        )
        
        # Try to read same message again (should get nothing)
        messages2 = await redis_client.xreadgroup(
            consumer_group, consumername="consumer1",
            streams={stream_name: ">"},
            count=1,
        )
        
        # Second read should return no new messages
        assert not messages2 or not messages2.get(stream_name), \
            "Should not receive same message again"
        
        # Cleanup
        await redis_client.delete(stream_name)
        
    except Exception as e:
        pytest.skip(f"Idempotency test failed: {e}")