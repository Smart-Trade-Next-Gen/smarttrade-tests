"""Unit tests for Historical Learning Module."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.historical_learning import (
    SetupCollector,
    PerformanceCalculator,
    LearningScheduler,
    PatternPerformanceTracker
)
from ai_market_intelligence_service.historical_learning.schemas import (
    LearningBatchRequest,
    SetupCollectionRequest,
    PerformanceCalculationRequest
)


@pytest.fixture
def setup_collector():
    """Create a SetupCollector instance for testing."""
    return SetupCollector()


@pytest.fixture
def performance_calculator():
    """Create a PerformanceCalculator instance for testing."""
    return PerformanceCalculator()


@pytest.fixture
def learning_scheduler():
    """Create a LearningScheduler instance for testing."""
    return LearningScheduler()


@pytest.fixture
def pattern_performance_tracker():
    """Create a PatternPerformanceTracker instance for testing."""
    return PatternPerformanceTracker()


@pytest.fixture
def sample_setup_collection_request():
    """Create a sample setup collection request."""
    return SetupCollectionRequest(
        setup_id="setup-1",
        instrument_id="NIFTY50-INDEX",
        timeframe="15m",
        setup_type="BULLISH_CONTINUATION",
        detection_timestamp=datetime.utcnow()
    )


class TestSetupCollector:
    """Test cases for SetupCollector."""
    
    @pytest.mark.asyncio
    async def test_collect_setup_success(self, setup_collector, sample_setup_collection_request):
        """Test successful setup collection."""
        # Mock session
        session = Mock()
        
        result = await setup_collector.collect_setup(sample_setup_collection_request, session)
        
        assert result is not None
        assert "setup_id" in result
        assert "collected_at" in result
    
    @pytest.mark.asyncio
    async def test_collect_setup_with_outcome(self, setup_collector):
        """Test setup collection with outcome data."""
        request = SetupCollectionRequest(
            setup_id="setup-1",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            setup_type="BULLISH_CONTINUATION",
            detection_timestamp=datetime.utcnow(),
            outcome_type="SUCCESS",
            future_return=Decimal("2.5")
        )
        
        # Mock session
        session = Mock()
        
        result = await setup_collector.collect_setup(request, session)
        
        assert result is not None


class TestPerformanceCalculator:
    """Test cases for PerformanceCalculator."""
    
    @pytest.mark.asyncio
    async def test_calculate_setup_performance_success(self, performance_calculator):
        """Test successful setup performance calculation."""
        request = PerformanceCalculationRequest(
            setup_type="BULLISH_CONTINUATION",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            time_horizon="1d"
        )
        
        # Mock session
        session = Mock()
        
        result = await performance_calculator.calculate_setup_performance(request, session)
        
        assert result is not None
        assert "success_rate" in result
        assert "average_return" in result
    
    @pytest.mark.asyncio
    async def test_calculate_pattern_performance_success(self, performance_calculator):
        """Test successful pattern performance calculation."""
        request = PerformanceCalculationRequest(
            pattern_type="DOJI",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            time_horizon="1d"
        )
        
        # Mock session
        session = Mock()
        
        result = await performance_calculator.calculate_pattern_performance(request, session)
        
        assert result is not None
        assert "success_rate" in result


class TestLearningScheduler:
    """Test cases for LearningScheduler."""
    
    @pytest.mark.asyncio
    async def test_execute_batch_success(self, learning_scheduler):
        """Test successful batch execution."""
        request = LearningBatchRequest(
            batch_type="SETUP_PERFORMANCE",
            date_range_start=datetime.utcnow() - timedelta(days=30),
            date_range_end=datetime.utcnow()
        )
        
        result = await learning_scheduler.execute_batch(request)
        
        assert result is not None
        assert "batch_id" in result
        assert "status" in result
    
    @pytest.mark.asyncio
    async def test_start_scheduler_success(self, learning_scheduler):
        """Test successful scheduler start."""
        result = await learning_scheduler.start_scheduler()
        
        assert result is None  # Start may not return anything
    
    @pytest.mark.asyncio
    async def test_stop_scheduler_success(self, learning_scheduler):
        """Test successful scheduler stop."""
        result = await learning_scheduler.stop_scheduler()
        
        assert result is None  # Stop may not return anything


class TestPatternPerformanceTracker:
    """Test cases for PatternPerformanceTracker."""
    
    @pytest.mark.asyncio
    async def test_track_pattern_performance_success(self, pattern_performance_tracker):
        """Test successful pattern performance tracking."""
        pattern_type = "DOJI"
        instrument_id = "NIFTY50-INDEX"
        timeframe = "15m"
        
        # Mock session
        session = Mock()
        
        result = await pattern_performance_tracker.track_pattern_performance(
            pattern_type, instrument_id, timeframe, session
        )
        
        assert result is not None
        assert "pattern_type" in result
        assert "success_rate" in result


class TestHistoricalLearningSchemas:
    """Test cases for Historical Learning schemas."""
    
    def test_learning_batch_request_validation(self):
        """Test LearningBatchRequest validation."""
        request = LearningBatchRequest(
            batch_type="SETUP_PERFORMANCE",
            date_range_start=datetime.utcnow() - timedelta(days=30),
            date_range_end=datetime.utcnow()
        )
        
        assert request.batch_type == "SETUP_PERFORMANCE"
    
    def test_setup_collection_request_validation(self):
        """Test SetupCollectionRequest validation."""
        request = SetupCollectionRequest(
            setup_id="setup-1",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            setup_type="BULLISH_CONTINUATION",
            detection_timestamp=datetime.utcnow()
        )
        
        assert request.setup_id == "setup-1"
        assert request.setup_type == "BULLISH_CONTINUATION"