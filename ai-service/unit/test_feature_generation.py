"""Unit tests for Feature Generation Module."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.feature_generation import (
    FeatureGenerator,
    TechnicalIndicatorCalculator,
    MarketStructureAnalyzer
)


@pytest.fixture
def feature_generator():
    """Create a FeatureGenerator instance for testing."""
    return FeatureGenerator()


@pytest.fixture
def technical_indicator_calculator():
    """Create a TechnicalIndicatorCalculator instance for testing."""
    return TechnicalIndicatorCalculator()


@pytest.fixture
def market_structure_analyzer():
    """Create a MarketStructureAnalyzer instance for testing."""
    return MarketStructureAnalyzer()


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    return {
        "open": Decimal("18500.00"),
        "high": Decimal("18550.00"),
        "low": Decimal("18480.00"),
        "close": Decimal("18520.00"),
        "volume": 1000000,
        "timestamp": datetime.utcnow()
    }


class TestFeatureGenerator:
    """Test cases for FeatureGenerator."""
    
    @pytest.mark.asyncio
    async def test_generate_features_success(self, feature_generator, sample_ohlcv_data):
        """Test successful feature generation."""
        result = await feature_generator.generate_features(sample_ohlcv_data)
        
        assert result is not None
        assert isinstance(result, dict)
        # Check that common features are present
        assert "rsi" in result or "macd" in result or "volume_ratio" in result
    
    @pytest.mark.asyncio
    async def test_generate_features_with_history(self, feature_generator):
        """Test feature generation with historical data."""
        historical_data = [
            {
                "open": Decimal("18500.00"),
                "high": Decimal("18550.00"),
                "low": Decimal("18480.00"),
                "close": Decimal("18520.00"),
                "volume": 1000000,
                "timestamp": datetime.utcnow() - timedelta(minutes=i)
            }
            for i in range(20)
        ]
        
        result = await feature_generator.generate_features(historical_data[-1], historical_data)
        
        assert result is not None
        assert isinstance(result, dict)


class TestTechnicalIndicatorCalculator:
    """Test cases for TechnicalIndicatorCalculator."""
    
    @pytest.mark.asyncio
    async def test_calculate_rsi_success(self, technical_indicator_calculator):
        """Test successful RSI calculation."""
        prices = [Decimal("18500.00") + i * 10 for i in range(20)]
        
        result = await technical_indicator_calculator.calculate_rsi(prices, period=14)
        
        assert result is not None
        assert isinstance(result, (int, float, Decimal))
        assert 0 <= result <= 100  # RSI should be between 0 and 100
    
    @pytest.mark.asyncio
    async def test_calculate_macd_success(self, technical_indicator_calculator):
        """Test successful MACD calculation."""
        prices = [Decimal("18500.00") + i * 10 for i in range(30)]
        
        result = await technical_indicator_calculator.calculate_macd(prices)
        
        assert result is not None
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result
    
    @pytest.mark.asyncio
    async def test_calculate_bollinger_bands_success(self, technical_indicator_calculator):
        """Test successful Bollinger Bands calculation."""
        prices = [Decimal("18500.00") + i * 10 for i in range(20)]
        
        result = await technical_indicator_calculator.calculate_bollinger_bands(prices, period=20)
        
        assert result is not None
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
    
    @pytest.mark.asyncio
    async def test_calculate_volume_ratio_success(self, technical_indicator_calculator):
        """Test successful volume ratio calculation."""
        current_volume = 1000000
        average_volume = 800000
        
        result = await technical_indicator_calculator.calculate_volume_ratio(current_volume, average_volume)
        
        assert result is not None
        assert result == 1.25  # 1000000 / 800000


class TestMarketStructureAnalyzer:
    """Test cases for MarketStructureAnalyzer."""
    
    @pytest.mark.asyncio
    async def test_identify_support_resistance_success(self, market_structure_analyzer):
        """Test successful support/resistance identification."""
        prices = [Decimal("18500.00") + i * 10 for i in range(50)]
        
        result = await market_structure_analyzer.identify_support_resistance(prices)
        
        assert result is not None
        assert "support" in result
        assert "resistance" in result
    
    @pytest.mark.asyncio
    async def test_identify_trend_success(self, market_structure_analyzer):
        """Test successful trend identification."""
        prices = [Decimal("18500.00") + i * 10 for i in range(50)]
        
        result = await market_structure_analyzer.identify_trend(prices)
        
        assert result is not None
        assert result in ["UPTREND", "DOWNTREND", "SIDEWAYS"]
    
    @pytest.mark.asyncio
    async def test_identify_uptrend(self, market_structure_analyzer):
        """Test uptrend identification."""
        prices = [Decimal("18500.00") + i * 10 for i in range(50)]
        
        result = await market_structure_analyzer.identify_trend(prices)
        
        assert result == "UPTREND"
    
    @pytest.mark.asyncio
    async def test_identify_downtrend(self, market_structure_analyzer):
        """Test downtrend identification."""
        prices = [Decimal("19000.00") - i * 10 for i in range(50)]
        
        result = await market_structure_analyzer.identify_trend(prices)
        
        assert result == "DOWNTREND"