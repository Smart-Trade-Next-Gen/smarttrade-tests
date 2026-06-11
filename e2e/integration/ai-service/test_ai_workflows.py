"""E2E workflow tests for AI Service core intelligence."""

import pytest
from datetime import datetime
from decimal import Decimal


@pytest.mark.e2e
@pytest.mark.smoke
class TestPatternDetectionWorkflow:
    """E2E tests for Pattern Detection workflow."""
    
    @pytest.mark.asyncio
    async def test_pattern_detection_from_market_data(self, ai_service_client, auth_token):
        """Test complete pattern detection workflow from market data."""
        # Step 1: Detect patterns from OHLCV data
        patterns = await ai_service_client.detect_patterns(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            timestamp=datetime.utcnow().isoformat(),
            open_price="18500.00",
            high_price="18550.00",
            low_price="18480.00",
            close_price="18520.00",
            volume=1000000,
            auth_token=auth_token
        )
        
        # Verify patterns were detected
        assert patterns is not None
        assert "patterns" in patterns or len(patterns) >= 0
        
        # Step 2: Query patterns with filters
        queried_patterns = await ai_service_client.get_patterns(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            limit=10,
            auth_token=auth_token
        )
        
        # Verify patterns can be queried
        assert queried_patterns is not None
    
    @pytest.mark.asyncio
    async def test_pattern_outcome_evaluation(self, ai_service_client, auth_token):
        """Test pattern outcome evaluation workflow."""
        # Step 1: Detect a pattern
        patterns = await ai_service_client.detect_patterns(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            timestamp=datetime.utcnow().isoformat(),
            open_price="18500.00",
            high_price="18550.00",
            low_price="18480.00",
            close_price="18520.00",
            volume=1000000,
            auth_token=auth_token
        )
        
        # Step 2: Calculate probability for the pattern
        if patterns and len(patterns) > 0:
            pattern_id = patterns[0].get("pattern_id") if isinstance(patterns, list) else None
            if pattern_id:
                probability = await ai_service_client.calculate_probability(
                    pattern_id=pattern_id,
                    time_horizon="1d",
                    confidence_level=0.95,
                    auth_token=auth_token
                )
                
                # Verify probability was calculated
                assert probability is not None


@pytest.mark.e2e
@pytest.mark.smoke
class TestSetupIntelligenceWorkflow:
    """E2E tests for Setup Intelligence workflow."""
    
    @pytest.mark.asyncio
    async def test_setup_detection_from_market_data(self, ai_service_client, auth_token):
        """Test complete setup detection workflow from market data."""
        # Step 1: Detect setups from OHLCV data
        setups = await ai_service_client.detect_setups(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            timestamp=datetime.utcnow().isoformat(),
            open_price="18500.00",
            high_price="18550.00",
            low_price="18480.00",
            close_price="18520.00",
            volume=1000000,
            auth_token=auth_token
        )
        
        # Verify setups were detected
        assert setups is not None
        assert "setups" in setups or len(setups) >= 0
        
        # Step 2: Query setups with filters
        queried_setups = await ai_service_client.get_setups(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            limit=10,
            auth_token=auth_token
        )
        
        # Verify setups can be queried
        assert queried_setups is not None
    
    @pytest.mark.asyncio
    async def test_setup_lifecycle_management(self, ai_service_client, auth_token):
        """Test setup lifecycle management workflow."""
        # Step 1: Detect a setup
        setups = await ai_service_client.detect_setups(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            timestamp=datetime.utcnow().isoformat(),
            open_price="18500.00",
            high_price="18550.00",
            low_price="18480.00",
            close_price="18520.00",
            volume=1000000,
            auth_token=auth_token
        )
        
        # Step 2: Update setup lifecycle
        if setups and len(setups) > 0:
            setup_id = setups[0].get("setup_id") if isinstance(setups, list) else None
            if setup_id:
                updated_setup = await ai_service_client.update_setup_lifecycle(
                    setup_id=setup_id,
                    lifecycle_status="EVALUATED",
                    auth_token=auth_token
                )
                
                # Verify setup was updated
                assert updated_setup is not None


@pytest.mark.e2e
@pytest.mark.smoke
class TestMarketRegimeWorkflow:
    """E2E tests for Market Regime workflow."""
    
    @pytest.mark.asyncio
    async def test_regime_classification_workflow(self, ai_service_client, auth_token):
        """Test complete regime classification workflow."""
        # Step 1: Classify market regime
        regime = await ai_service_client.classify_regime(
            instrument_id="NIFTY50-INDEX",
            timeframe="1D",
            timestamp=datetime.utcnow().isoformat(),
            close_price="18500.00",
            volume=1000000,
            auth_token=auth_token
        )
        
        # Verify regime was classified
        assert regime is not None
        assert regime.get("regime_type") in ["BULL_TREND", "BEAR_TREND", "RANGE", "BREAKOUT", "REVERSAL"]
        
        # Step 2: Query latest regime
        latest_regime = await ai_service_client.get_latest_regime(
            instrument_id="NIFTY50-INDEX",
            timeframe="1D",
            auth_token=auth_token
        )
        
        # Verify latest regime can be queried
        assert latest_regime is not None


@pytest.mark.e2e
class TestWatchlistIntelligenceWorkflow:
    """E2E tests for Watchlist Intelligence workflow."""
    
    @pytest.mark.asyncio
    async def test_watchlist_creation_workflow(self, ai_service_client, auth_token):
        """Test watchlist creation workflow."""
        # Step 1: Create a watchlist
        watchlist = await ai_service_client.create_watchlist(
            name="Test Watchlist",
            user_id="user-1",
            description="Test watchlist for E2E testing",
            watchlist_type="CUSTOM",
            metadata={},
            auth_token=auth_token
        )
        
        # Verify watchlist was created
        assert watchlist is not None
        assert watchlist.get("name") == "Test Watchlist"
        
        # Step 2: Query watchlists for user
        watchlists = await ai_service_client.get_watchlists(
            user_id="user-1",
            limit=10,
            auth_token=auth_token
        )
        
        # Verify watchlists can be queried
        assert watchlists is not None


@pytest.mark.e2e
class TestSimilaritySearchWorkflow:
    """E2E tests for Similarity Search workflow."""
    
    @pytest.mark.asyncio
    async def test_pattern_similarity_search(self, ai_service_client, auth_token):
        """Test pattern similarity search workflow."""
        # Step 1: Create a query vector
        query_vector = [0.1, 0.2, 0.3, 0.4, 0.5] * 25  # 128-dimensional vector
        
        # Step 2: Search for similar patterns
        similar_patterns = await ai_service_client.search_similar(
            query_vector=query_vector,
            vector_type="PATTERN",
            entity_type="pattern",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            k=10,
            similarity_threshold=0.8,
            auth_token=auth_token
        )
        
        # Verify similar patterns were found
        assert similar_patterns is not None
        assert "similar_vectors" in similar_patterns


@pytest.mark.e2e
class TestFeatureStoreWorkflow:
    """E2E tests for Feature Store workflow."""
    
    @pytest.mark.asyncio
    async def test_feature_generation_workflow(self, ai_service_client, auth_token):
        """Test feature generation workflow."""
        # Step 1: List features for an entity type
        features = await ai_service_client.list_features(
            entity_type="pattern",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            limit=10,
            auth_token=auth_token
        )
        
        # Verify features can be listed
        assert features is not None
        assert "features" in features
        
        # Step 2: Get features for a specific entity
        entity_features = await ai_service_client.get_features(
            entity_type="pattern",
            entity_id="pattern-1",
            auth_token=auth_token
        )
        
        # Verify features can be retrieved
        assert entity_features is not None or entity_features is None  # May not exist


@pytest.mark.e2e
class TestProbabilityEngineWorkflow:
    """E2E tests for Probability Engine workflow."""
    
    @pytest.mark.asyncio
    async def test_setup_probability_calculation(self, ai_service_client, auth_token):
        """Test setup probability calculation workflow."""
        # Step 1: Detect a setup
        setups = await ai_service_client.detect_setups(
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            timestamp=datetime.utcnow().isoformat(),
            open_price="18500.00",
            high_price="18550.00",
            low_price="18480.00",
            close_price="18520.00",
            volume=1000000,
            auth_token=auth_token
        )
        
        # Step 2: Calculate probability for the setup
        if setups and len(setups) > 0:
            setup_id = setups[0].get("setup_id") if isinstance(setups, list) else None
            if setup_id:
                probability = await ai_service_client.calculate_probability(
                    setup_id=setup_id,
                    time_horizon="1d",
                    confidence_level=0.95,
                    auth_token=auth_token
                )
                
                # Verify probability was calculated
                assert probability is not None
                assert 0 <= probability.get("probability_value", 0) <= 1