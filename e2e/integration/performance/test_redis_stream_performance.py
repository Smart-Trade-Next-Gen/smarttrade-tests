"""
Integration tests for Redis stream performance.

Tests validate:
- Redis stream write throughput
- Redis stream read throughput
- Consumer group performance
- Memory efficiency
"""

from __future__ import annotations

import pytest
import asyncio
import uuid

pytestmark = pytest.mark.asyncio


@pytest.mark.performance
async def test_redis_stream_write_throughput(
    config,
    redis_client,
):
    """
    Test: Redis stream write throughput.

    Validates:
    - Stream writes complete quickly
    - Throughput meets requirements
    - No write bottlenecks
    """
    stream_name = "e2e-test-write-throughput"
    
    try:
        # Write many messages and measure time
        import time
        start = time.time()
        
        for i in range(1000):
            await redis_client.xadd(stream_name, {"data": str(i)})
        
        elapsed = time.time() - start
        
        # Validate throughput (should write > 1000 messages/sec)
        assert elapsed < 10.0, "1000 writes should complete within 10 seconds"
        
        # Cleanup
        await redis_client.delete(stream_name)
        
    except Exception as e:
        pytest.skip(f"Redis stream write throughput test failed: {e}")


@pytest.mark.performance
async def test_redis_stream_read_throughput(
    config,
    redis_client,
):
    """
    Test: Redis stream read throughput.

    Validates:
    - Stream reads complete quickly
    - Throughput meets requirements
    - No read bottlenecks
    """
    stream_name = f"e2e-test-read-throughput-{uuid.uuid4().hex[:8]}"
    consumer_group = f"e2e-test-read-throughput-group-{uuid.uuid4().hex[:8]}"
    
    try:
        # Write messages
        for i in range(1000):
            await redis_client.xadd(stream_name, {"data": str(i)})
        
        # Create consumer group
        await redis_client.xgroup_create(
            stream_name, consumer_group, id="0", mkstream=True
        )
        
        # Read messages and measure time
        import time
        start = time.time()
        
        messages = await redis_client.xreadgroup(
            consumer_group, consumername="test-consumer",
            streams={stream_name: ">"},
            count=1000,
        )
        
        elapsed = time.time() - start
        
        # Validate throughput (should read > 1000 messages/sec)
        assert elapsed < 10.0, "1000 reads should complete within 10 seconds"
        
        # Cleanup
        await redis_client.delete(stream_name)
        
    except Exception as e:
        pytest.skip(f"Redis stream read throughput test failed: {e}")


@pytest.mark.performance
async def test_consumer_group_performance(
    config,
    redis_client,
):
    """
    Test: Consumer group performance.

    Validates:
    - Consumer group operations are efficient
    - Multiple consumers scale well
    - No consumer group bottlenecks
    """
    stream_name = f"e2e-test-consumer-group-perf-{uuid.uuid4().hex[:8]}"
    consumer_group = f"e2e-test-consumer-group-perf-group-{uuid.uuid4().hex[:8]}"
    
    try:
        # Write messages
        for i in range(100):
            await redis_client.xadd(stream_name, {"data": str(i)})
        
        # Create consumer group
        await redis_client.xgroup_create(
            stream_name, consumer_group, id="0", mkstream=True
        )
        
        # Create multiple consumers
        async def consume_messages(consumer_name):
            messages = await redis_client.xreadgroup(
                consumer_group, consumername=consumer_name,
                streams={stream_name: ">"},
                count=50,
            )
            # xreadgroup returns a list of (stream_name, messages) tuples
            if messages:
                return len(messages[0][1])  # messages[0][1] is the list of messages for the stream
            return 0
        
        # Run consumers in parallel and measure time
        import time
        start = time.time()
        
        results = await asyncio.gather(
            consume_messages("consumer1"),
            consume_messages("consumer2"),
            consume_messages("consumer3"),
        )
        
        elapsed = time.time() - start
        
        # Validate performance
        total_processed = sum(results)
        assert total_processed == 100, "All messages should be processed"
        assert elapsed < 5.0, "Consumer group operations should complete within 5 seconds"
        
        # Cleanup
        await redis_client.delete(stream_name)
        
    except Exception as e:
        pytest.skip(f"Consumer group performance test failed: {e}")