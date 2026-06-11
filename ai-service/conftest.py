"""Pytest configuration and fixtures for AI Market Intelligence Service tests."""

import pytest
import sys
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta

# Add the ai-service source to the path so tests can import from it
ai_service_path = Path(__file__).parent.parent.parent / "ai-service" / "src"
if str(ai_service_path) not in sys.path:
    sys.path.insert(0, str(ai_service_path))

# Load .env file for JWT_SECRET_KEY
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv not available, rely on environment

# Register custom pytest marks
def pytest_configure(config):
    """Register custom pytest marks."""
    config.addinivalue_line(
        "markers", "integration: Integration tests for AI service"
    )
    config.addinivalue_line(
        "markers", "unit: Unit tests for AI service"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests"
    )
    config.addinivalue_line(
        "markers", "cross_service: Cross-service integration tests"
    )
    config.addinivalue_line(
        "markers", "smoke: Critical path tests"
    )


@pytest.fixture
def auth_token():
    """Provide a valid JWT auth token for testing."""
    try:
        from jose import jwt
        
        # Secret from environment (must match docker-compose JWT_SECRET_KEY)
        secret = os.getenv("JWT_SECRET_KEY")
        if not secret:
            pytest.skip("JWT_SECRET_KEY not found in environment")
        
        # Generate a test user ID
        test_user_id = str(uuid4())
        
        now = datetime.utcnow()
        payload = {
            "sub": test_user_id,
            "roles": ["user", "trader"],
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=24)).timestamp()),
            "iss": "auth-service",
            "aud": "smarttrade-services",
        }
        
        # Use python-jose (same as smarttrade-common)
        token = jwt.encode(payload, secret, algorithm="HS256")
        return token
    except Exception as e:
        pytest.skip(f"Failed to generate auth token: {e}")


@pytest.fixture
async def client():
    """Create an async HTTP client for API testing."""
    try:
        from httpx import AsyncClient, ASGITransport
        from ai_market_intelligence_service.main import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    except Exception as e:
        pytest.skip(f"AI service not available for testing: {e}")


@pytest.fixture
async def db_session():
    """Create a database session for integration tests."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from ai_market_intelligence_service.config import settings
        
        # Create async engine
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True
        )
        
        # Create async session factory
        async_session = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        async with async_session() as session:
            yield session
            
        await engine.dispose()
    except Exception as e:
        pytest.skip(f"Database session not available: {e}")


@pytest.fixture
async def mock_redis():
    """Create a mock Redis client for testing."""
    try:
        import redis.asyncio as redis
        from ai_market_intelligence_service.config import settings
        
        client = await redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        
        yield client
        
        await client.close()
    except Exception as e:
        pytest.skip(f"Redis client not available: {e}")


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    from datetime import datetime
    from decimal import Decimal
    
    return {
        "open": Decimal("18500.00"),
        "high": Decimal("18550.00"),
        "low": Decimal("18480.00"),
        "close": Decimal("18520.00"),
        "volume": 1000000,
        "timestamp": datetime.utcnow()
    }


@pytest.fixture
def sample_features():
    """Create sample features for testing."""
    return {
        "rsi": 50.0,
        "macd": 0.5,
        "signal": 0.3,
        "histogram": 0.2,
        "volume_ratio": 1.2,
        "price_change": 0.5,
        "volatility": 0.3
    }


@pytest.fixture
def sample_pattern():
    """Create a sample pattern for testing."""
    from datetime import datetime
    from decimal import Decimal
    
    return {
        "pattern_id": "pattern-1",
        "instrument_id": "NIFTY50-INDEX",
        "timeframe": "15m",
        "pattern_type": "DOJI",
        "pattern_direction": "NEUTRAL",
        "pattern_category": "CANDLESTICK",
        "confidence_score": 0.85,
        "quality_score": 0.90,
        "parameters": {},
        "candle_timestamp": datetime.utcnow(),
        "close_price": Decimal("18500.00"),
        "volume": 1000000,
        "detection_method": "STATISTICAL",
        "metadata": {}
    }


@pytest.fixture
def sample_setup():
    """Create a sample setup for testing."""
    from datetime import datetime
    from decimal import Decimal
    
    return {
        "setup_id": "setup-1",
        "instrument_id": "NIFTY50-INDEX",
        "timeframe": "15m",
        "setup_type": "BULLISH_CONTINUATION",
        "setup_direction": "BULLISH",
        "setup_score": 0.85,
        "confidence_level": 0.90,
        "ranking_score": 0.88,
        "pattern_quality_score": 0.85,
        "structure_quality_score": 0.90,
        "volume_quality_score": 0.80,
        "trend_quality_score": 0.85,
        "context_quality_score": 0.88,
        "components": [],
        "candle_timestamp": datetime.utcnow(),
        "close_price": Decimal("18500.00"),
        "volume": 1000000,
        "market_regime": "BULL_TREND",
        "volatility_regime": "QUIET",
        "detection_method": "STATISTICAL",
        "metadata": {}
    }