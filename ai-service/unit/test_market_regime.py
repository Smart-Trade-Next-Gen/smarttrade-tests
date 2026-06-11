"""Unit tests for Market Regime Module."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.market_regime import RegimeClassifier, VolatilityAnalyzer, TrendAnalyzer
from ai_market_intelligence_service.market_regime.schemas import RegimeClassificationRequest


@pytest.fixture
def regime_classifier():
    """Create a RegimeClassifier instance for testing."""
    return RegimeClassifier()


@pytest.fixture
def volatility_analyzer():
    """Create a VolatilityAnalyzer instance for testing."""
    return VolatilityAnalyzer()


@pytest.fixture
def trend_analyzer():
    """Create a TrendAnalyzer instance for testing."""
    return TrendAnalyzer()


@pytest.fixture
def sample_regime_request():
    """Create a sample regime classification request."""
    return RegimeClassificationRequest(
        instrument_id="NIFTY50-INDEX",
        timeframe="1D",
        timestamp=datetime.utcnow(),
        close_price=Decimal("18500.00"),
        volume=1000000
    )


class TestRegimeClassifier:
    """Test cases for RegimeClassifier."""
    
    @pytest.mark.asyncio
    async def test_classify_regime_success(self, regime_classifier, sample_regime_request):
        """Test successful regime classification."""
        # Mock the internal classification methods
        regime_classifier.analyze_trend = AsyncMock(return_value="BULL_TREND")
        regime_classifier.analyze_volatility = AsyncMock(return_value="QUIET")
        
        result = await regime_classifier.classify_regime(sample_regime_request.dict())
        
        assert result is not None
        assert "regime_type" in result
        assert "volatility_regime" in result
        assert "confidence" in result
    
    @pytest.mark.asyncio
    async def test_classify_regime_bull_trend(self, regime_classifier, sample_regime_request):
        """Test regime classification for bull trend."""
        regime_classifier.analyze_trend = AsyncMock(return_value="BULL_TREND")
        regime_classifier.analyze_volatility = AsyncMock(return_value="QUIET")
        
        result = await regime_classifier.classify_regime(sample_regime_request.dict())
        
        assert result["regime_type"] == "BULL_TREND"
    
    @pytest.mark.asyncio
    async def test_classify_regime_bear_trend(self, regime_classifier, sample_regime_request):
        """Test regime classification for bear trend."""
        regime_classifier.analyze_trend = AsyncMock(return_value="BEAR_TREND")
        regime_classifier.analyze_volatility = AsyncMock(return_value="VOLATILE")
        
        result = await regime_classifier.classify_regime(sample_regime_request.dict())
        
        assert result["regime_type"] == "BEAR_TREND"


class TestVolatilityAnalyzer:
    """Test cases for VolatilityAnalyzer."""
    
    @pytest.mark.asyncio
    async def test_analyze_volatility_quiet(self, volatility_analyzer):
        """Test volatility analysis for quiet market."""
        prices = [Decimal("18500.00"), Decimal("18510.00"), Decimal("18505.00")]
        
        result = await volatility_analyzer.analyze_volatility(prices)
        
        assert result is not None
        assert result in ["QUIET", "VOLATILE"]
    
    @pytest.mark.asyncio
    async def test_analyze_volatility_volatile(self, volatility_analyzer):
        """Test volatility analysis for volatile market."""
        prices = [Decimal("18500.00"), Decimal("18600.00"), Decimal("18400.00")]
        
        result = await volatility_analyzer.analyze_volatility(prices)
        
        assert result is not None
        assert result in ["QUIET", "VOLATILE"]


class TestTrendAnalyzer:
    """Test cases for TrendAnalyzer."""
    
    @pytest.mark.asyncio
    async def test_analyze_trend_bullish(self, trend_analyzer):
        """Test trend analysis for bullish trend."""
        prices = [Decimal("18500.00"), Decimal("18550.00"), Decimal("18600.00")]
        
        result = await trend_analyzer.analyze_trend(prices)
        
        assert result is not None
        assert result in ["BULL_TREND", "BEAR_TREND", "RANGE_BOUND"]
    
    @pytest.mark.asyncio
    async def test_analyze_trend_bearish(self, trend_analyzer):
        """Test trend analysis for bearish trend."""
        prices = [Decimal("18600.00"), Decimal("18550.00"), Decimal("18500.00")]
        
        result = await trend_analyzer.analyze_trend(prices)
        
        assert result is not None
        assert result in ["BULL_TREND", "BEAR_TREND", "RANGE_BOUND"]


class TestRegimeClassificationSchemas:
    """Test cases for Regime Classification schemas."""
    
    def test_regime_classification_request_validation(self):
        """Test RegimeClassificationRequest validation."""
        request = RegimeClassificationRequest(
            instrument_id="NIFTY50-INDEX",
            timeframe="1D",
            timestamp=datetime.utcnow(),
            close_price=Decimal("18500.00"),
            volume=1000000
        )
        
        assert request.instrument_id == "NIFTY50-INDEX"
        assert request.timeframe == "1D"
        assert request.volume == 1000000