"""Unit tests for Business Logic Services."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.services import (
    PatternService,
    SetupService,
    OutcomeService,
    ProbabilityService,
    RegimeService,
    WatchlistService,
    SimilarityService,
    LearningService
)


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


class TestPatternService:
    """Test cases for PatternService."""
    
    @pytest.mark.asyncio
    async def test_detect_patterns_success(self, mock_session):
        """Test successful pattern detection via service."""
        from ai_market_intelligence_service.pattern_detection.schemas import PatternDetectionRequest
        
        service = PatternService()
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
        
        # Mock the pattern detector
        service.pattern_detector.detect_patterns = AsyncMock(return_value={
            "total": 1,
            "patterns": [],
            "detection_timestamp": datetime.utcnow()
        })
        
        result = await service.detect_patterns(request, mock_session)
        
        assert result is not None
        assert "total" in result


class TestSetupService:
    """Test cases for SetupService."""
    
    @pytest.mark.asyncio
    async def test_detect_setups_success(self, mock_session):
        """Test successful setup detection via service."""
        from ai_market_intelligence_service.setup_intelligence.schemas import SetupDetectionRequest
        
        service = SetupService()
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
        
        # Mock the setup detector
        service.setup_detector.detect_setups = AsyncMock(return_value={
            "total": 1,
            "setups": [],
            "detection_timestamp": datetime.utcnow()
        })
        
        result = await service.detect_setups(request, mock_session)
        
        assert result is not None
        assert "total" in result


class TestOutcomeService:
    """Test cases for OutcomeService."""
    
    @pytest.mark.asyncio
    async def test_track_outcome_success(self, mock_session):
        """Test successful outcome tracking via service."""
        from ai_market_intelligence_service.outcome_evaluation.schemas import OutcomeTrackingRequest
        
        service = OutcomeService()
        request = OutcomeTrackingRequest(
            setup_id="setup-1",
            pattern_id="pattern-1",
            entry_price=Decimal("18500.00"),
            exit_price=Decimal("18600.00"),
            holding_period=1440,
            time_horizons=["1d"],
            exit_reason="TARGET_HIT"
        )
        
        # Mock the outcome tracker
        service.outcome_tracker.track_outcome = AsyncMock(return_value={
            "outcome_type": "SUCCESS",
            "confidence": 0.85
        })
        
        result = await service.track_outcome(request, mock_session)
        
        assert result is not None


class TestProbabilityService:
    """Test cases for ProbabilityService."""
    
    @pytest.mark.asyncio
    async def test_calculate_probability_success(self, mock_session):
        """Test successful probability calculation via service."""
        from ai_market_intelligence_service.probability_engine.schemas import ProbabilityCalculationRequest
        
        service = ProbabilityService()
        request = ProbabilityCalculationRequest(
            setup_id="setup-1",
            pattern_id=None,
            time_horizon="1d",
            confidence_level=0.95,
            force_recalculate=False
        )
        
        # Mock the statistical calculator
        service.statistical_calculator.calculate_probability = AsyncMock(return_value={
            "probability": 0.75,
            "sample_size": 100
        })
        
        result = await service.calculate_probability(request, mock_session)
        
        assert result is not None
        assert "probability" in result


class TestRegimeService:
    """Test cases for RegimeService."""
    
    @pytest.mark.asyncio
    async def test_classify_regime_success(self, mock_session):
        """Test successful regime classification via service."""
        from ai_market_intelligence_service.market_regime.schemas import RegimeClassificationRequest
        
        service = RegimeService()
        request = RegimeClassificationRequest(
            instrument_id="NIFTY50-INDEX",
            timeframe="1D",
            timestamp=datetime.utcnow(),
            close_price=Decimal("18500.00"),
            volume=1000000
        )
        
        # Mock the regime classifier
        service.regime_classifier.classify_regime = AsyncMock(return_value={
            "regime_type": "BULL_TREND",
            "volatility_regime": "QUIET",
            "confidence": 0.85
        })
        
        result = await service.classify_regime(request, mock_session)
        
        assert result is not None
        assert "regime_type" in result


class TestWatchlistService:
    """Test cases for WatchlistService."""
    
    @pytest.mark.asyncio
    async def test_generate_pre_market_watchlist_success(self, mock_session):
        """Test successful pre-market watchlist generation via service."""
        from ai_market_intelligence_service.watchlist_intelligence.schemas import PreMarketGenerationRequest
        from datetime import date
        
        service = WatchlistService()
        request = PreMarketGenerationRequest(
            user_id="user-1",
            date=date.today(),
            market="NSE"
        )
        
        # Mock the pre-market generator
        service.pre_market_generator.generate_watchlist = AsyncMock(return_value={
            "items": [],
            "generation_timestamp": datetime.utcnow()
        })
        
        result = await service.generate_pre_market_watchlist(request, mock_session)
        
        assert result is not None
        assert "items" in result


class TestSimilarityService:
    """Test cases for SimilarityService."""
    
    @pytest.mark.asyncio
    async def test_search_similar_success(self, mock_session):
        """Test successful similarity search via service."""
        from ai_market_intelligence_service.similarity_search.schemas import SimilaritySearchRequest
        
        service = SimilarityService()
        request = SimilaritySearchRequest(
            vector_type="PATTERN",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            k=10,
            threshold=0.8
        )
        
        # Mock the similarity searcher
        service.similarity_searcher.search_similar_patterns = AsyncMock(return_value={
            "total": 10,
            "results": [],
            "search_timestamp": datetime.utcnow()
        })
        
        result = await service.search_similar(request, mock_session)
        
        assert result is not None
        assert "total" in result


class TestLearningService:
    """Test cases for LearningService."""
    
    @pytest.mark.asyncio
    async def test_execute_learning_batch_success(self, mock_session):
        """Test successful learning batch execution via service."""
        from ai_market_intelligence_service.historical_learning.schemas import LearningBatchRequest
        
        service = LearningService()
        request = LearningBatchRequest(
            batch_type="SETUP_PERFORMANCE",
            date_range_start=datetime.utcnow(),
            date_range_end=datetime.utcnow()
        )
        
        # Mock the learning scheduler
        service.learning_scheduler.execute_batch = AsyncMock(return_value={
            "batch_id": "batch-1",
            "status": "COMPLETED",
            "records_processed": 100
        })
        
        result = await service.execute_learning_batch(request, mock_session)
        
        assert result is not None
        assert "batch_id" in result