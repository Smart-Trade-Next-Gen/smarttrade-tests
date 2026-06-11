"""Unit tests for Setup Intelligence Module."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.setup_intelligence import SetupDetector, SetupScorer
from ai_market_intelligence_service.setup_intelligence.schemas import SetupDetectionRequest


@pytest.fixture
def setup_detector():
    """Create a SetupDetector instance for testing."""
    return SetupDetector()


@pytest.fixture
def setup_scorer():
    """Create a SetupScorer instance for testing."""
    return SetupScorer()


@pytest.fixture
def sample_setup_request():
    """Create a sample setup detection request."""
    return SetupDetectionRequest(
        instrument_id="NIFTY50-INDEX",
        timeframe="15m",
        timestamp=datetime.utcnow(),
        open_price=Decimal("18500.00"),
        high_price=Decimal("18550.00"),
        low_price=Decimal("18480.00"),
        close_price=Decimal("18520.00"),
        volume=1000000
    )


class TestSetupDetector:
    """Test cases for SetupDetector."""
    
    @pytest.mark.asyncio
    async def test_detect_setups_success(self, setup_detector, sample_setup_request):
        """Test successful setup detection."""
        # Mock the internal setup detection methods
        setup_detector.detect_bullish_setups = AsyncMock(return_value=[])
        setup_detector.detect_bearish_setups = AsyncMock(return_value=[])
        
        result = await setup_detector.detect_setups(sample_setup_request.dict())
        
        assert result is not None
        assert "setups" in result
        assert isinstance(result["setups"], list)
    
    @pytest.mark.asyncio
    async def test_detect_setups_with_bullish_setup(self, setup_detector, sample_setup_request):
        """Test setup detection with bullish setup."""
        # Mock bullish setup detection to return a setup
        setup_detector.detect_bullish_setups = AsyncMock(return_value=[
            {
                "setup_id": "setup-1",
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
                "market_regime": "BULL_TREND",
                "volatility_regime": "QUIET",
                "metadata": {}
            }
        ])
        setup_detector.detect_bearish_setups = AsyncMock(return_value=[])
        
        result = await setup_detector.detect_setups(sample_setup_request.dict())
        
        assert len(result["setups"]) == 1
        assert result["setups"][0]["setup_type"] == "BULLISH_CONTINUATION"


class TestSetupScorer:
    """Test cases for SetupScorer."""
    
    @pytest.mark.asyncio
    async def test_score_setup_success(self, setup_scorer):
        """Test successful setup scoring."""
        setup_data = {
            "setup_type": "BULLISH_CONTINUATION",
            "pattern_quality": 0.85,
            "structure_quality": 0.90,
            "volume_quality": 0.80,
            "trend_quality": 0.85,
            "context_quality": 0.88
        }
        
        result = await setup_scorer.score_setup(setup_data)
        
        assert result is not None
        assert "setup_score" in result
        assert "confidence_level" in result
        assert "ranking_score" in result
    
    @pytest.mark.asyncio
    async def test_score_setup_invalid_input(self, setup_scorer):
        """Test setup scoring with invalid input."""
        with pytest.raises(Exception):
            await setup_scorer.score_setup({})


class TestSetupDetectionSchemas:
    """Test cases for Setup Detection schemas."""
    
    def test_setup_detection_request_validation(self):
        """Test SetupDetectionRequest validation."""
        request = SetupDetectionRequest(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            timestamp=datetime.utcnow(),
            open_price=Decimal("18500.00"),
            high_price=Decimal("18550.00"),
            low_price=Decimal("18480.00"),
            close_price=Decimal("18520.00"),
            volume=1000000
        )
        
        assert request.instrument_id == "NIFTY50-INDEX"
        assert request.timeframe == "15m"
        assert request.volume == 1000000