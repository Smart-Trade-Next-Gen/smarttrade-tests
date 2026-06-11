"""Unit tests for Pattern Detection Module."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.pattern_detection import PatternDetector
from ai_market_intelligence_service.pattern_detection.schemas import PatternDetectionRequest


@pytest.fixture
def pattern_detector():
    """Create a PatternDetector instance for testing."""
    return PatternDetector()


@pytest.fixture
def sample_pattern_request():
    """Create a sample pattern detection request."""
    return PatternDetectionRequest(
        instrument_id="NIFTY50-INDEX",
        timeframe="15m",
        timestamp=datetime.utcnow(),
        open_price=Decimal("18500.00"),
        high_price=Decimal("18550.00"),
        low_price=Decimal("18480.00"),
        close_price=Decimal("18520.00"),
        volume=1000000
    )


class TestPatternDetector:
    """Test cases for PatternDetector."""
    
    @pytest.mark.asyncio
    async def test_detect_patterns_success(self, pattern_detector, sample_pattern_request):
        """Test successful pattern detection."""
        # Mock the internal pattern detection methods
        pattern_detector.detect_candlestick_patterns = AsyncMock(return_value=[])
        pattern_detector.detect_price_action_patterns = AsyncMock(return_value=[])
        pattern_detector.detect_market_structure_patterns = AsyncMock(return_value=[])
        
        result = await pattern_detector.detect_patterns(sample_pattern_request.dict())
        
        assert result is not None
        assert "patterns" in result
        assert isinstance(result["patterns"], list)
    
    @pytest.mark.asyncio
    async def test_detect_patterns_with_candlestick(self, pattern_detector, sample_pattern_request):
        """Test pattern detection with candlestick patterns."""
        # Mock candlestick detection to return a pattern
        pattern_detector.detect_candlestick_patterns = AsyncMock(return_value=[
            {
                "pattern_id": "pattern-1",
                "pattern_type": "DOJI",
                "pattern_direction": "NEUTRAL",
                "pattern_category": "CANDLESTICK",
                "confidence_score": 0.85,
                "quality_score": 0.90,
                "parameters": {},
                "metadata": {}
            }
        ])
        pattern_detector.detect_price_action_patterns = AsyncMock(return_value=[])
        pattern_detector.detect_market_structure_patterns = AsyncMock(return_value=[])
        
        result = await pattern_detector.detect_patterns(sample_pattern_request.dict())
        
        assert len(result["patterns"]) == 1
        assert result["patterns"][0]["pattern_type"] == "DOJI"
    
    @pytest.mark.asyncio
    async def test_detect_patterns_invalid_input(self, pattern_detector):
        """Test pattern detection with invalid input."""
        with pytest.raises(Exception):
            await pattern_detector.detect_patterns({})


class TestPatternDetectionSchemas:
    """Test cases for Pattern Detection schemas."""
    
    def test_pattern_detection_request_validation(self):
        """Test PatternDetectionRequest validation."""
        request = PatternDetectionRequest(
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
    
    def test_pattern_detection_request_invalid_timeframe(self):
        """Test PatternDetectionRequest with invalid timeframe."""
        with pytest.raises(Exception):
            PatternDetectionRequest(
                instrument_id="NIFTY50-INDEX",
                timeframe="invalid",
                timestamp=datetime.utcnow(),
                open_price=Decimal("18500.00"),
                high_price=Decimal("18550.00"),
                low_price=Decimal("18480.00"),
                close_price=Decimal("18520.00"),
                volume=1000000
            )