"""Database fixtures for AI Market Intelligence Service tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    # Use an in-memory SQLite database for testing
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )
    
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
    
    await engine.dispose()


@pytest.fixture
def mock_pattern_data():
    """Create mock pattern data for testing."""
    from datetime import datetime
    from decimal import Decimal
    
    return {
        "pattern_id": "pattern-1",
        "instrument_id": "NIFTY50-INDEX",
        "timeframe": "15m",
        "pattern_type": "DOJI",
        "pattern_direction": "NEUTRAL",
        "pattern_category": "CANDLESTICK",
        "confidence_score": Decimal("0.85"),
        "quality_score": Decimal("0.90"),
        "parameters": {},
        "candle_timestamp": datetime.utcnow(),
        "close_price": Decimal("18500.00"),
        "volume": 1000000,
        "detection_method": "STATISTICAL",
        "metadata": {}
    }


@pytest.fixture
def mock_setup_data():
    """Create mock setup data for testing."""
    from datetime import datetime
    from decimal import Decimal
    
    return {
        "setup_id": "setup-1",
        "instrument_id": "NIFTY50-INDEX",
        "timeframe": "15m",
        "setup_type": "BULLISH_CONTINUATION",
        "setup_direction": "BULLISH",
        "setup_score": Decimal("0.85"),
        "confidence_level": Decimal("0.90"),
        "ranking_score": Decimal("0.88"),
        "pattern_quality_score": Decimal("0.85"),
        "structure_quality_score": Decimal("0.90"),
        "volume_quality_score": Decimal("0.80"),
        "trend_quality_score": Decimal("0.85"),
        "context_quality_score": Decimal("0.88"),
        "components": [],
        "candle_timestamp": datetime.utcnow(),
        "close_price": Decimal("18500.00"),
        "volume": 1000000,
        "market_regime": "BULL_TREND",
        "volatility_regime": "QUIET",
        "detection_method": "STATISTICAL",
        "metadata": {}
    }


@pytest.fixture
def mock_regime_data():
    """Create mock regime data for testing."""
    from datetime import datetime
    from decimal import Decimal
    
    return {
        "instrument_id": "NIFTY50-INDEX",
        "timeframe": "1D",
        "regime_type": "BULL_TREND",
        "volatility_regime": "QUIET",
        "trend_strength": Decimal("0.75"),
        "volatility_level": Decimal("0.30"),
        "regime_timestamp": datetime.utcnow(),
        "confidence_score": Decimal("0.85"),
        "metadata": {}
    }