"""Pytest configuration and fixtures for AI Service E2E tests."""

import pytest
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from uuid import uuid4

# Add the ai-service source to the path so tests can import from it
ai_service_path = Path(__file__).parent.parent.parent.parent / "ai-service" / "src"
if str(ai_service_path) not in sys.path:
    sys.path.insert(0, str(ai_service_path))

# Add the smarttrade-tests directory to path to import e2e as a module
smarttrade_tests_path = Path(__file__).parent.parent.parent.parent
if str(smarttrade_tests_path) not in sys.path:
    sys.path.insert(0, str(smarttrade_tests_path))

# Load .env file for JWT_SECRET_KEY
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv not available, rely on environment


@pytest.fixture
async def ai_service_client():
    """Create an AI Service client for E2E testing."""
    try:
        from e2e.clients.ai_service_client import AIServiceClient
        
        client = AIServiceClient(base_url="http://localhost:8014", timeout=30)
        
        yield client
        
        await client.close()
    except Exception as e:
        pytest.skip(f"AI service client not available: {e}")


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


# Mock fixtures for cross-service tests (these would be replaced with real clients in actual E2E tests)
@pytest.fixture
async def mds_client():
    """Mock Market Data Service client for testing."""
    class MockMDSClient:
        async def get_quote(self, instrument_id):
            return {"ltp": "18500.00", "volume": 1000000}
        
        async def get_historical_candles(self, instrument_id, timeframe, limit):
            return [
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "open": "18500.00",
                    "high": "18550.00",
                    "low": "18480.00",
                    "close": "18520.00",
                    "volume": 1000000
                }
            ]
    
    return MockMDSClient()


@pytest.fixture
async def journal_client():
    """Mock Journal Service client for testing."""
    class MockJournalClient:
        async def get_trades(self, limit):
            return []
    
    return MockJournalClient()


@pytest.fixture
async def portfolio_client():
    """Mock Portfolio Service client for testing."""
    class MockPortfolioClient:
        async def get_holdings(self, account_id):
            return []
    
    return MockPortfolioClient()


@pytest.fixture
async def strategy_client():
    """Mock Strategy Service client for testing."""
    class MockStrategyClient:
        async def get_strategies(self, limit):
            return []
    
    return MockStrategyClient()


@pytest.fixture
async def auth_client():
    """Mock Authentication Service client for testing."""
    class MockAuthClient:
        async def login(self, username, password):
            return {"access_token": "mock-jwt-token"}
    
    return MockAuthClient()


# Test markers
pytestmark = [
    pytest.mark.e2e,
]