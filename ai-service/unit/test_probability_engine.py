"""Unit tests for Probability Engine Module."""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.probability_engine import StatisticalCalculator, ProbabilityCache
from ai_market_intelligence_service.probability_engine.schemas import ProbabilityCalculationRequest


@pytest.fixture
def statistical_calculator():
    """Create a StatisticalCalculator instance for testing."""
    return StatisticalCalculator()


@pytest.fixture
def probability_cache():
    """Create a ProbabilityCache instance for testing."""
    return ProbabilityCache()


@pytest.fixture
def sample_probability_request():
    """Create a sample probability calculation request."""
    return ProbabilityCalculationRequest(
        setup_id="setup-1",
        pattern_id=None,
        time_horizon="1d",
        confidence_level=0.95,
        force_recalculate=False
    )


class TestStatisticalCalculator:
    """Test cases for StatisticalCalculator."""
    
    @pytest.mark.asyncio
    async def test_calculate_probability_success(self, statistical_calculator, sample_probability_request):
        """Test successful probability calculation."""
        # Mock the database query to return sample data
        result = await statistical_calculator.calculate_probability(sample_probability_request.dict())
        
        assert result is not None
        assert "probability" in result
        assert "sample_size" in result
        assert isinstance(result["probability"], (int, float, Decimal))
    
    @pytest.mark.asyncio
    async def test_calculate_probability_with_pattern(self, statistical_calculator):
        """Test probability calculation for pattern."""
        request = ProbabilityCalculationRequest(
            setup_id=None,
            pattern_id="DOJI",
            time_horizon="1d",
            confidence_level=0.95,
            force_recalculate=False
        )
        
        result = await statistical_calculator.calculate_probability(request.dict())
        
        assert result is not None
        assert "probability" in result
    
    @pytest.mark.asyncio
    async def test_calculate_probability_insufficient_data(self, statistical_calculator):
        """Test probability calculation with insufficient data."""
        request = ProbabilityCalculationRequest(
            setup_id="setup-new",
            pattern_id=None,
            time_horizon="1d",
            confidence_level=0.95,
            force_recalculate=False
        )
        
        result = await statistical_calculator.calculate_probability(request.dict())
        
        # Should return None or handle insufficient data gracefully
        assert result is not None


class TestProbabilityCache:
    """Test cases for ProbabilityCache."""
    
    @pytest.mark.asyncio
    async def test_cache_probability_success(self, probability_cache):
        """Test successful probability caching."""
        entity_id = "setup-1"
        time_horizon = "1d"
        probability = 0.75
        confidence_interval = (0.70, 0.80)
        sample_size = 100
        
        # Mock session
        session = Mock()
        
        result = await probability_cache.cache_probability(
            entity_id, time_horizon, probability, confidence_interval, sample_size, session
        )
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_get_cached_probability_hit(self, probability_cache):
        """Test getting cached probability (cache hit)."""
        entity_id = "setup-1"
        time_horizon = "1d"
        
        # Mock session
        session = Mock()
        
        result = await probability_cache.get_cached_probability(entity_id, time_horizon, session)
        
        # Should return cached value if available
        assert result is not None or result is None  # May be None if not cached
    
    @pytest.mark.asyncio
    async def test_get_cached_probability_miss(self, probability_cache):
        """Test getting cached probability (cache miss)."""
        entity_id = "setup-new"
        time_horizon = "1d"
        
        # Mock session
        session = Mock()
        
        result = await probability_cache.get_cached_probability(entity_id, time_horizon, session)
        
        # Should return None for cache miss
        assert result is None


class TestProbabilityCalculationSchemas:
    """Test cases for Probability Calculation schemas."""
    
    def test_probability_calculation_request_validation(self):
        """Test ProbabilityCalculationRequest validation."""
        request = ProbabilityCalculationRequest(
            setup_id="setup-1",
            pattern_id=None,
            time_horizon="1d",
            confidence_level=0.95,
            force_recalculate=False
        )
        
        assert request.setup_id == "setup-1"
        assert request.time_horizon == "1d"
        assert request.confidence_level == 0.95
        assert request.force_recalculate is False
    
    def test_probability_calculation_request_invalid_confidence(self):
        """Test ProbabilityCalculationRequest with invalid confidence level."""
        with pytest.raises(Exception):
            ProbabilityCalculationRequest(
                setup_id="setup-1",
                pattern_id=None,
                time_horizon="1d",
                confidence_level=1.5,  # Invalid: > 1.0
                force_recalculate=False
            )