"""Unit tests for Watchlist Intelligence Module."""

import pytest
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.watchlist_intelligence import (
    PreMarketGenerator,
    OpportunityRanker,
    UnusualActivityDetector
)
from ai_market_intelligence_service.watchlist_intelligence.schemas import (
    PreMarketGenerationRequest,
    OpportunityRankingRequest,
    UnusualActivityDetectionRequest
)


@pytest.fixture
def pre_market_generator():
    """Create a PreMarketGenerator instance for testing."""
    return PreMarketGenerator()


@pytest.fixture
def opportunity_ranker():
    """Create an OpportunityRanker instance for testing."""
    return OpportunityRanker()


@pytest.fixture
def unusual_activity_detector():
    """Create an UnusualActivityDetector instance for testing."""
    return UnusualActivityDetector()


@pytest.fixture
def sample_pre_market_request():
    """Create a sample pre-market generation request."""
    return PreMarketGenerationRequest(
        user_id="user-1",
        date=date.today(),
        market="NSE"
    )


class TestPreMarketGenerator:
    """Test cases for PreMarketGenerator."""
    
    @pytest.mark.asyncio
    async def test_generate_watchlist_success(self, pre_market_generator, sample_pre_market_request):
        """Test successful pre-market watchlist generation."""
        result = await pre_market_generator.generate_watchlist(sample_pre_market_request.dict())
        
        assert result is not None
        assert "items" in result
        assert isinstance(result["items"], list)
    
    @pytest.mark.asyncio
    async def test_generate_watchlist_with_instruments(self, pre_market_generator):
        """Test pre-market watchlist generation with instruments."""
        request = PreMarketGenerationRequest(
            user_id="user-1",
            date=date.today(),
            market="NSE",
            instrument_ids=["NIFTY50-INDEX", "BANKNIFTY-INDEX"]
        )
        
        result = await pre_market_generator.generate_watchlist(request.dict())
        
        assert result is not None
        assert "items" in result


class TestOpportunityRanker:
    """Test cases for OpportunityRanker."""
    
    @pytest.mark.asyncio
    async def test_rank_opportunities_success(self, opportunity_ranker):
        """Test successful opportunity ranking."""
        opportunities = [
            {
                "instrument_id": "NIFTY50-INDEX",
                "setup_type": "BULLISH_CONTINUATION",
                "setup_score": 0.85
            },
            {
                "instrument_id": "BANKNIFTY-INDEX",
                "setup_type": "BULLISH_REVERSAL",
                "setup_score": 0.90
            }
        ]
        
        request = OpportunityRankingRequest(
            opportunities=opportunities,
            ranking_criteria="SETUP_SCORE"
        )
        
        result = await opportunity_ranker.rank_opportunities(request.dict())
        
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2


class TestUnusualActivityDetector:
    """Test cases for UnusualActivityDetector."""
    
    @pytest.mark.asyncio
    async def test_detect_activity_success(self, unusual_activity_detector):
        """Test successful unusual activity detection."""
        market_data = [
            {
                "instrument_id": "NIFTY50-INDEX",
                "volume": 2000000,  # Unusual volume
                "price_change": 2.5  # Unusual price change
            }
        ]
        
        request = UnusualActivityDetectionRequest(
            market_data=market_data,
            volume_threshold=1500000,
            price_change_threshold=2.0
        )
        
        result = await unusual_activity_detector.detect_activity(request.dict())
        
        assert result is not None
        assert "unusual_items" in result
        assert isinstance(result["unusual_items"], list)


class TestWatchlistIntelligenceSchemas:
    """Test cases for Watchlist Intelligence schemas."""
    
    def test_pre_market_generation_request_validation(self):
        """Test PreMarketGenerationRequest validation."""
        request = PreMarketGenerationRequest(
            user_id="user-1",
            date=date.today(),
            market="NSE"
        )
        
        assert request.user_id == "user-1"
        assert request.market == "NSE"
    
    def test_opportunity_ranking_request_validation(self):
        """Test OpportunityRankingRequest validation."""
        opportunities = [
            {
                "instrument_id": "NIFTY50-INDEX",
                "setup_type": "BULLISH_CONTINUATION",
                "setup_score": 0.85
            }
        ]
        
        request = OpportunityRankingRequest(
            opportunities=opportunities,
            ranking_criteria="SETUP_SCORE"
        )
        
        assert request.ranking_criteria == "SETUP_SCORE"
        assert len(request.opportunities) == 1