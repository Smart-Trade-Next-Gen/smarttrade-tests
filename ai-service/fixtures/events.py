"""Event fixtures for AI Market Intelligence Service tests."""

import pytest
from datetime import datetime
from decimal import Decimal


@pytest.fixture
def mock_market_quote_event():
    """Create a mock market quote event for testing."""
    return {
        "event_id": "event-1",
        "event_type": "market.quote",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "instrument_id": "NIFTY50-INDEX",
            "ltp": "18500.00",
            "volume": "1000000",
            "change": "50.00",
            "change_percent": "0.27"
        }
    }


@pytest.fixture
def mock_market_candle_event():
    """Create a mock market candle event for testing."""
    return {
        "event_id": "event-2",
        "event_type": "market.candle",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "15m",
            "open": "18500.00",
            "high": "18550.00",
            "low": "18480.00",
            "close": "18520.00",
            "volume": "1000000"
        }
    }


@pytest.fixture
def mock_trade_event():
    """Create a mock trade event for testing."""
    return {
        "event_id": "event-3",
        "event_type": "trade.executed",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "trade_id": "trade-1",
            "instrument_id": "NIFTY50-INDEX",
            "quantity": "100",
            "price": "18500.00",
            "side": "BUY",
            "user_id": "user-1",
            "account_id": "account-1"
        }
    }


@pytest.fixture
def mock_order_event():
    """Create a mock order event for testing."""
    return {
        "event_id": "event-4",
        "event_type": "order.updated",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "order_id": "order-1",
            "instrument_id": "NIFTY50-INDEX",
            "quantity": "100",
            "price": "18500.00",
            "side": "BUY",
            "status": "FILLED",
            "user_id": "user-1",
            "account_id": "account-1"
        }
    }


@pytest.fixture
def mock_pattern_detected_event():
    """Create a mock pattern detected event for testing."""
    return {
        "event_id": "event-5",
        "event_type": "ai.pattern.detected",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "pattern_id": "pattern-1",
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "15m",
            "pattern_type": "DOJI",
            "pattern_direction": "NEUTRAL",
            "confidence_score": 0.85,
            "quality_score": 0.90
        }
    }


@pytest.fixture
def mock_setup_detected_event():
    """Create a mock setup detected event for testing."""
    return {
        "event_id": "event-6",
        "event_type": "ai.setup.detected",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "setup_id": "setup-1",
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "15m",
            "setup_type": "BULLISH_CONTINUATION",
            "setup_direction": "BULLISH",
            "setup_score": 0.85,
            "confidence_level": 0.90
        }
    }


@pytest.fixture
def mock_regime_changed_event():
    """Create a mock regime changed event for testing."""
    return {
        "event_id": "event-7",
        "event_type": "ai.regime.changed",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "instrument_id": "NIFTY50-INDEX",
            "timeframe": "1D",
            "regime_type": "BULL_TREND",
            "volatility_regime": "QUIET",
            "confidence": 0.85
        }
    }


@pytest.fixture
def mock_outcome_evaluated_event():
    """Create a mock outcome evaluated event for testing."""
    return {
        "event_id": "event-8",
        "event_type": "ai.outcome.evaluated",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "setup_id": "setup-1",
            "pattern_id": "pattern-1",
            "outcome_type": "SUCCESS",
            "future_return_1d": 2.5,
            "confidence": 0.85
        }
    }