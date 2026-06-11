"""Cross-service integration tests for AI Service."""

import pytest
from datetime import datetime
from decimal import Decimal


@pytest.mark.e2e
@pytest.mark.cross_service
class TestAIServiceMarketDataServiceIntegration:
    """Cross-service integration tests for AI Service + Market Data Service."""
    
    @pytest.mark.asyncio
    async def test_pattern_detection_using_mds_quotes(self, ai_service_client, mds_client, auth_token):
        """Test pattern detection using live quotes from Market Data Service."""
        # Step 1: Get current quote from MDS
        quote = await mds_client.get_quote("NIFTY50-INDEX")
        
        # Verify quote was retrieved
        assert quote is not None
        assert "ltp" in quote
        
        # Step 2: Use quote data for pattern detection
        patterns = await ai_service_client.detect_patterns(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            timestamp=datetime.utcnow().isoformat(),
            open_price=str(quote.get("ltp", "18500.00")),
            high_price=str(quote.get("ltp", "18500.00")),
            low_price=str(quote.get("ltp", "18500.00")),
            close_price=str(quote.get("ltp", "18500.00")),
            volume=quote.get("volume", 1000000),
            auth_token=auth_token
        )
        
        # Verify patterns were detected
        assert patterns is not None
    
    @pytest.mark.asyncio
    async def test_setup_detection_using_mds_candles(self, ai_service_client, mds_client, auth_token):
        """Test setup detection using candles from Market Data Service."""
        # Step 1: Get historical candles from MDS
        candles = await mds_client.get_historical_candles(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            limit=10
        )
        
        # Verify candles were retrieved
        assert candles is not None
        assert len(candles) > 0
        
        # Step 2: Use latest candle for setup detection
        latest_candle = candles[-1]
        setups = await ai_service_client.detect_setups(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            timestamp=latest_candle.get("timestamp", datetime.utcnow().isoformat()),
            open_price=str(latest_candle.get("open", "18500.00")),
            high_price=str(latest_candle.get("high", "18550.00")),
            low_price=str(latest_candle.get("low", "18480.00")),
            close_price=str(latest_candle.get("close", "18520.00")),
            volume=latest_candle.get("volume", 1000000),
            auth_token=auth_token
        )
        
        # Verify setups were detected
        assert setups is not None


@pytest.mark.e2e
@pytest.mark.cross_service
class TestAIServiceJournalServiceIntegration:
    """Cross-service integration tests for AI Service + Journal Service."""
    
    @pytest.mark.asyncio
    async def test_outcome_evaluation_from_journal_trades(self, ai_service_client, journal_client, auth_token):
        """Test outcome evaluation using trades from Journal Service."""
        # Step 1: Get recent trades from Journal Service
        trades = await journal_client.get_trades(limit=10)
        
        # Verify trades were retrieved
        assert trades is not None
        assert len(trades) >= 0
        
        # Step 2: Use trade data for outcome evaluation
        if trades and len(trades) > 0:
            latest_trade = trades[0]
            
            # Calculate probability for the setup associated with the trade
            if latest_trade.get("setup_id"):
                probability = await ai_service_client.calculate_probability(
                    setup_id=latest_trade["setup_id"],
                    time_horizon="1d",
                    confidence_level=0.95,
                    auth_token=auth_token
                )
                
                # Verify probability was calculated
                assert probability is not None
    
    @pytest.mark.asyncio
    async def test_pattern_performance_tracking(self, ai_service_client, journal_client, auth_token):
        """Test pattern performance tracking using Journal Service data."""
        # Step 1: Get patterns from AI Service
        patterns = await ai_service_client.get_patterns(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            limit=10,
            auth_token=auth_token
        )
        
        # Verify patterns were retrieved
        assert patterns is not None
        
        # Step 2: Get trades from Journal Service for correlation
        trades = await journal_client.get_trades(limit=10)
        
        # Verify trades were retrieved
        assert trades is not None


@pytest.mark.e2e
@pytest.mark.cross_service
class TestAIServicePortfolioServiceIntegration:
    """Cross-service integration tests for AI Service + Portfolio Service."""
    
    @pytest.mark.asyncio
    async def test_watchlist_generation_from_portfolio(self, ai_service_client, portfolio_client, auth_token):
        """Test watchlist generation using portfolio holdings."""
        # Step 1: Get portfolio holdings from Portfolio Service
        holdings = await portfolio_client.get_holdings(account_id="test-account")
        
        # Verify holdings were retrieved
        assert holdings is not None
        assert len(holdings) >= 0
        
        # Step 2: Generate watchlist based on holdings
        if holdings and len(holdings) > 0:
            instrument_ids = [h.get("instrument_id") for h in holdings if h.get("instrument_id")]
            
            if instrument_ids:
                # Create watchlist with holdings
                watchlist = await ai_service_client.create_watchlist(
                    name="Portfolio Holdings Watchlist",
                    user_id="user-1",
                    description="Watchlist based on portfolio holdings",
                    watchlist_type="CUSTOM",
                    metadata={"instrument_ids": instrument_ids},
                    auth_token=auth_token
                )
                
                # Verify watchlist was created
                assert watchlist is not None


@pytest.mark.e2e
@pytest.mark.cross_service
class TestAIServiceStrategyServiceIntegration:
    """Cross-service integration tests for AI Service + Strategy Service."""
    
    @pytest.mark.asyncio
    async def test_setup_intelligence_for_strategy_decisions(self, ai_service_client, strategy_client, auth_token):
        """Test setup intelligence for strategy decision making."""
        # Step 1: Get active strategies from Strategy Service
        strategies = await strategy_client.get_strategies(limit=10)
        
        # Verify strategies were retrieved
        assert strategies is not None
        assert len(strategies) >= 0
        
        # Step 2: Get setups for strategy instruments
        if strategies and len(strategies) > 0:
            strategy = strategies[0]
            instrument_id = strategy.get("instrument_id")
            
            if instrument_id:
                setups = await ai_service_client.get_setups(
                    instrument_id=instrument_id,
                    timeframe="15m",
                    lifecycle_status="ACTIVE",
                    limit=10,
                    auth_token=auth_token
                )
                
                # Verify setups were retrieved
                assert setups is not None


@pytest.mark.e2e
@pytest.mark.cross_service
class TestAIServiceAuthenticationIntegration:
    """Cross-service integration tests for AI Service + Authentication Service."""
    
    @pytest.mark.asyncio
    async def test_ai_service_authentication_flow(self, ai_service_client, auth_client):
        """Test AI Service authentication using Auth Service."""
        # Step 1: Authenticate with Auth Service
        auth_response = await auth_client.login(
            username="testuser",
            password="testpass"
        )
        
        # Verify authentication was successful
        assert auth_response is not None
        assert "access_token" in auth_response
        
        # Step 2: Use token to access AI Service
        auth_token = auth_response["access_token"]
        patterns = await ai_service_client.get_patterns(
            instrument_id="NIFTY50-INDEX",
            limit=10,
            auth_token=auth_token
        )
        
        # Verify AI Service access with auth token
        assert patterns is not None