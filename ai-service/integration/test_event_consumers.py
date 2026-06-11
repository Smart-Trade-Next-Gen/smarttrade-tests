"""Integration tests for AI Market Intelligence Service event consumers."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock


@pytest.mark.integration
class TestMarketDataConsumer:
    """Integration tests for Market Data Consumer."""
    
    @pytest.mark.asyncio
    async def test_process_quote_message_success(self):
        """Test processing of market quote message."""
        from ai_market_intelligence_service.events.market_data_consumer import MarketDataConsumer
        
        consumer = MarketDataConsumer()
        msg_id = "msg-1"
        fields = {
            "instrument_id": "NIFTY50-INDEX",
            "ltp": "18500.00",
            "volume": "1000000",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock the pattern detection and feature generation
        consumer.process_pattern_detection = AsyncMock()
        consumer.generate_features = AsyncMock()
        
        await consumer.process_message(msg_id, fields)
        
        # Verify that pattern detection was called
        consumer.process_pattern_detection.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_quote_with_pattern_detection(self):
        """Test quote processing with pattern detection."""
        from ai_market_intelligence_service.events.market_data_consumer import MarketDataConsumer
        
        consumer = MarketDataConsumer()
        msg_id = "msg-1"
        fields = {
            "instrument_id": "NIFTY50-INDEX",
            "ltp": "18500.00",
            "volume": "1000000",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock pattern detection to return a pattern
        consumer.process_pattern_detection = AsyncMock(return_value={
            "pattern_type": "DOJI",
            "confidence": 0.85
        })
        
        await consumer.process_message(msg_id, fields)
        
        consumer.process_pattern_detection.assert_called_once()


@pytest.mark.integration
class TestMarketCandleConsumer:
    """Integration tests for Market Candle Consumer."""
    
    @pytest.mark.asyncio
    async def test_process_candle_message_success(self):
        """Test processing of market candle message."""
        from ai_market_intelligence_service.events.market_candle_consumer import MarketCandleConsumer
        
        consumer = MarketCandleConsumer()
        msg_id = "msg-1"
        fields = {
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "15m",
            "open": "18500.00",
            "high": "18550.00",
            "low": "18480.00",
            "close": "18520.00",
            "volume": "1000000",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock the regime analysis and setup detection
        consumer.analyze_regime = AsyncMock()
        consumer.detect_setups = AsyncMock()
        
        await consumer.process_message(msg_id, fields)
        
        # Verify that regime analysis was called
        consumer.analyze_regime.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_candle_with_setup_detection(self):
        """Test candle processing with setup detection."""
        from ai_market_intelligence_service.events.market_candle_consumer import MarketCandleConsumer
        
        consumer = MarketCandleConsumer()
        msg_id = "msg-1"
        fields = {
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "15m",
            "open": "18500.00",
            "high": "18550.00",
            "low": "18480.00",
            "close": "18520.00",
            "volume": "1000000",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock setup detection to return a setup
        consumer.detect_setups = AsyncMock(return_value={
            "setup_type": "BULLISH_CONTINUATION",
            "setup_score": 0.85
        })
        
        await consumer.process_message(msg_id, fields)
        
        consumer.detect_setups.assert_called_once()


@pytest.mark.integration
class TestTradeConsumer:
    """Integration tests for Trade Consumer."""
    
    @pytest.mark.asyncio
    async def test_process_trade_message_success(self):
        """Test processing of trade message."""
        from ai_market_intelligence_service.events.trade_consumer import TradeConsumer
        
        consumer = TradeConsumer()
        msg_id = "msg-1"
        fields = {
            "trade_id": "trade-1",
            "instrument_id": "NIFTY50-INDEX",
            "quantity": "100",
            "price": "18500.00",
            "side": "BUY",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock the outcome evaluation
        consumer.evaluate_outcome = AsyncMock()
        
        await consumer.process_message(msg_id, fields)
        
        # Verify that outcome evaluation was called
        consumer.evaluate_outcome.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_trade_with_outcome_evaluation(self):
        """Test trade processing with outcome evaluation."""
        from ai_market_intelligence_service.events.trade_consumer import TradeConsumer
        
        consumer = TradeConsumer()
        msg_id = "msg-1"
        fields = {
            "trade_id": "trade-1",
            "instrument_id": "NIFTY50-INDEX",
            "quantity": "100",
            "price": "18500.00",
            "side": "BUY",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock outcome evaluation to return a result
        consumer.evaluate_outcome = AsyncMock(return_value={
            "outcome_type": "SUCCESS",
            "future_return": 2.5
        })
        
        await consumer.process_message(msg_id, fields)
        
        consumer.evaluate_outcome.assert_called_once()


@pytest.mark.integration
class TestOrderConsumer:
    """Integration tests for Order Consumer."""
    
    @pytest.mark.asyncio
    async def test_process_order_message_success(self):
        """Test processing of order message."""
        from ai_market_intelligence_service.events.order_consumer import OrderConsumer
        
        consumer = OrderConsumer()
        msg_id = "msg-1"
        fields = {
            "order_id": "order-1",
            "instrument_id": "NIFTY50-INDEX",
            "quantity": "100",
            "price": "18500.00",
            "side": "BUY",
            "status": "FILLED",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock the setup lifecycle management
        consumer.update_setup_lifecycle = AsyncMock()
        
        await consumer.process_message(msg_id, fields)
        
        # Verify that setup lifecycle was called
        consumer.update_setup_lifecycle.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_order_with_lifecycle_update(self):
        """Test order processing with lifecycle update."""
        from ai_market_intelligence_service.events.order_consumer import OrderConsumer
        
        consumer = OrderConsumer()
        msg_id = "msg-1"
        fields = {
            "order_id": "order-1",
            "instrument_id": "NIFTY50-INDEX",
            "quantity": "100",
            "price": "18500.00",
            "side": "BUY",
            "status": "FILLED",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock lifecycle update to return a result
        consumer.update_setup_lifecycle = AsyncMock(return_value={
            "setup_id": "setup-1",
            "lifecycle_status": "IN_PROGRESS"
        })
        
        await consumer.process_message(msg_id, fields)
        
        consumer.update_setup_lifecycle.assert_called_once()


@pytest.mark.integration
class TestHistoricalDataConsumer:
    """Integration tests for Historical Data Consumer."""
    
    @pytest.mark.asyncio
    async def test_process_historical_candle_message_success(self):
        """Test processing of historical candle message."""
        from ai_market_intelligence_service.events.historical_data_consumer import HistoricalDataConsumer
        
        consumer = HistoricalDataConsumer()
        msg_id = "msg-1"
        fields = {
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "1d",
            "open": "18500.00",
            "high": "18550.00",
            "low": "18480.00",
            "close": "18520.00",
            "volume": "1000000",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock the data validation and storage
        consumer.validate_candle_data = AsyncMock()
        consumer.store_historical_candle = AsyncMock()
        
        await consumer.process_message(msg_id, fields)
        
        # Verify that data validation was called
        consumer.validate_candle_data.assert_called_once()


@pytest.mark.integration
class TestReplayEventConsumer:
    """Integration tests for Replay Event Consumer."""
    
    @pytest.mark.asyncio
    async def test_process_replay_event_message_success(self):
        """Test processing of replay event message."""
        from ai_market_intelligence_service.events.replay_event_consumer import ReplayEventConsumer
        
        consumer = ReplayEventConsumer()
        msg_id = "msg-1"
        fields = {
            "replay_job_id": "job-1",
            "event_type": "candle",
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "1d",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {}
        }
        
        # Mock the event processing
        consumer.process_replay_event = AsyncMock()
        
        await consumer.process_message(msg_id, fields)
        
        # Verify that event processing was called
        consumer.process_replay_event.assert_called_once()


@pytest.mark.integration
class TestOutcomeGenerationConsumer:
    """Integration tests for Outcome Generation Consumer."""
    
    @pytest.mark.asyncio
    async def test_process_outcome_generation_message_success(self):
        """Test processing of outcome generation message."""
        from ai_market_intelligence_service.events.outcome_generation_consumer import OutcomeGenerationConsumer
        
        consumer = OutcomeGenerationConsumer()
        msg_id = "msg-1"
        fields = {
            "outcome_generation_job_id": "job-1",
            "setup_id": "setup-1",
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "1d",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock the outcome generation
        consumer.generate_outcome = AsyncMock()
        
        await consumer.process_message(msg_id, fields)
        
        # Verify that outcome generation was called
        consumer.generate_outcome.assert_called_once()


@pytest.mark.integration
class TestValidationExecutionConsumer:
    """Integration tests for Validation Execution Consumer."""
    
    @pytest.mark.asyncio
    async def test_process_validation_message_success(self):
        """Test processing of validation execution message."""
        from ai_market_intelligence_service.events.validation_execution_consumer import ValidationExecutionConsumer
        
        consumer = ValidationExecutionConsumer()
        msg_id = "msg-1"
        fields = {
            "validation_job_id": "job-1",
            "validation_type": "setup_validation",
            "parameters": {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Mock the validation execution
        consumer.execute_validation = AsyncMock()
        
        await consumer.process_message(msg_id, fields)
        
        # Verify that validation execution was called
        consumer.execute_validation.assert_called_once()