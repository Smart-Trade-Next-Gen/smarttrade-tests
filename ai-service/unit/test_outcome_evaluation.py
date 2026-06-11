"""Unit tests for Outcome Evaluation Module."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.outcome_evaluation import ReturnCalculator, OutcomeClassifier
from ai_market_intelligence_service.outcome_evaluation.schemas import (
    ReturnCalculationRequest,
    OutcomeClassificationRequest
)


@pytest.fixture
def return_calculator():
    """Create a ReturnCalculator instance for testing."""
    return ReturnCalculator()


@pytest.fixture
def outcome_classifier():
    """Create an OutcomeClassifier instance for testing."""
    return OutcomeClassifier()


@pytest.fixture
def sample_return_request():
    """Create a sample return calculation request."""
    return ReturnCalculationRequest(
        setup_id="setup-1",
        entry_price=Decimal("18500.00"),
        exit_price=Decimal("18600.00"),
        time_horizons=["1h", "4h", "1d", "1w", "1m"]
    )


class TestReturnCalculator:
    """Test cases for ReturnCalculator."""
    
    @pytest.mark.asyncio
    async def test_calculate_returns_success(self, return_calculator, sample_return_request):
        """Test successful return calculation."""
        result = await return_calculator.calculate_returns(sample_return_request)
        
        assert result is not None
        assert isinstance(result, dict)
        # Check that time horizons are present
        for horizon in sample_return_request.time_horizons:
            assert horizon in result
    
    @pytest.mark.asyncio
    async def test_calculate_returns_profitable(self, return_calculator):
        """Test return calculation for profitable trade."""
        request = ReturnCalculationRequest(
            setup_id="setup-1",
            entry_price=Decimal("18500.00"),
            exit_price=Decimal("18600.00"),
            time_horizons=["1d"]
        )
        
        result = await return_calculator.calculate_returns(request)
        
        assert result["1d"] > 0  # Profitable trade
    
    @pytest.mark.asyncio
    async def test_calculate_returns_loss(self, return_calculator):
        """Test return calculation for losing trade."""
        request = ReturnCalculationRequest(
            setup_id="setup-1",
            entry_price=Decimal("18600.00"),
            exit_price=Decimal("18500.00"),
            time_horizons=["1d"]
        )
        
        result = await return_calculator.calculate_returns(request)
        
        assert result["1d"] < 0  # Losing trade


class TestOutcomeClassifier:
    """Test cases for OutcomeClassifier."""
    
    @pytest.mark.asyncio
    async def test_classify_outcome_success(self, outcome_classifier):
        """Test successful outcome classification."""
        future_returns = {
            "1h": 0.5,
            "4h": 1.0,
            "1d": 2.0,
            "1w": 3.0,
            "1m": 5.0
        }
        
        request = OutcomeClassificationRequest(
            setup_id="setup-1",
            future_returns=future_returns,
            holding_period=1440  # 1 day in minutes
        )
        
        result = await outcome_classifier.classify_outcome(request)
        
        assert result is not None
        assert "outcome_type" in result
        assert "confidence" in result
    
    @pytest.mark.asyncio
    async def test_classify_outcome_profitable(self, outcome_classifier):
        """Test outcome classification for profitable trade."""
        future_returns = {
            "1d": 2.0  # 2% profit
        }
        
        request = OutcomeClassificationRequest(
            setup_id="setup-1",
            future_returns=future_returns,
            holding_period=1440
        )
        
        result = await outcome_classifier.classify_outcome(request)
        
        assert result["outcome_type"] == "SUCCESS"
    
    @pytest.mark.asyncio
    async def test_classify_outcome_loss(self, outcome_classifier):
        """Test outcome classification for losing trade."""
        future_returns = {
            "1d": -2.0  # 2% loss
        }
        
        request = OutcomeClassificationRequest(
            setup_id="setup-1",
            future_returns=future_returns,
            holding_period=1440
        )
        
        result = await outcome_classifier.classify_outcome(request)
        
        assert result["outcome_type"] == "FAILURE"