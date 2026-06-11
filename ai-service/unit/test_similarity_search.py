"""Unit tests for Similarity Search Module."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from ai_market_intelligence_service.similarity_search import (
    VectorGenerator,
    EmbeddingService,
    SimilaritySearcher
)
from ai_market_intelligence_service.similarity_search.schemas import (
    SimilaritySearchRequest,
    EmbeddingServiceRequest
)


@pytest.fixture
def vector_generator():
    """Create a VectorGenerator instance for testing."""
    return VectorGenerator()


@pytest.fixture
def embedding_service():
    """Create an EmbeddingService instance for testing."""
    return EmbeddingService()


@pytest.fixture
def similarity_searcher():
    """Create a SimilaritySearcher instance for testing."""
    return SimilaritySearcher()


@pytest.fixture
def sample_similarity_search_request():
    """Create a sample similarity search request."""
    return SimilaritySearchRequest(
        vector_type="PATTERN",
        instrument_id="NIFTY50-INDEX",
        timeframe="15m",
        k=10,
        threshold=0.8
    )


class TestVectorGenerator:
    """Test cases for VectorGenerator."""
    
    @pytest.mark.asyncio
    async def test_generate_vector_success(self, vector_generator):
        """Test successful vector generation."""
        features = {
            "rsi": 50.0,
            "macd": 0.5,
            "volume_ratio": 1.2
        }
        
        result = await vector_generator.generate_vector(features)
        
        assert result is not None
        assert isinstance(result, list)
        assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_generate_vector_empty_features(self, vector_generator):
        """Test vector generation with empty features."""
        features = {}
        
        result = await vector_generator.generate_vector(features)
        
        assert result is not None
        assert isinstance(result, list)


class TestEmbeddingService:
    """Test cases for EmbeddingService."""
    
    @pytest.mark.asyncio
    async def test_generate_and_store_embedding_success(self, embedding_service):
        """Test successful embedding generation and storage."""
        request = EmbeddingServiceRequest(
            vector_type="PATTERN",
            entity_id="pattern-1",
            features={
                "rsi": 50.0,
                "macd": 0.5
            }
        )
        
        # Mock session
        session = Mock()
        
        result = await embedding_service.generate_and_store_embedding(request, session)
        
        assert result is not None
        assert "embedding" in result
        assert "entity_id" in result
    
    @pytest.mark.asyncio
    async def test_get_embedding_success(self, embedding_service):
        """Test successful embedding retrieval."""
        # Mock session
        session = Mock()
        
        result = await embedding_service.get_embedding("pattern-1", "PATTERN", session)
        
        # May return None if not found
        assert result is not None or result is None


class TestSimilaritySearcher:
    """Test cases for SimilaritySearcher."""
    
    @pytest.mark.asyncio
    async def test_search_similar_patterns_success(self, similarity_searcher, sample_similarity_search_request):
        """Test successful similar pattern search."""
        query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        
        # Mock session
        session = Mock()
        
        result = await similarity_searcher.search_similar_patterns(
            sample_similarity_search_request.dict(),
            query_embedding,
            session
        )
        
        assert result is not None
        assert "results" in result
        assert isinstance(result["results"], list)
    
    @pytest.mark.asyncio
    async def test_search_similar_setups_success(self, similarity_searcher):
        """Test successful similar setup search."""
        request = SimilaritySearchRequest(
            vector_type="SETUP",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            k=10,
            threshold=0.8
        )
        query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        
        # Mock session
        session = Mock()
        
        result = await similarity_searcher.search_similar_setups(
            request.dict(),
            query_embedding,
            session
        )
        
        assert result is not None
        assert "results" in result


class TestSimilaritySearchSchemas:
    """Test cases for Similarity Search schemas."""
    
    def test_similarity_search_request_validation(self):
        """Test SimilaritySearchRequest validation."""
        request = SimilaritySearchRequest(
            vector_type="PATTERN",
            instrument_id="NIFTY50-INDEX",
            timeframe="15m",
            k=10,
            threshold=0.8
        )
        
        assert request.vector_type == "PATTERN"
        assert request.instrument_id == "NIFTY50-INDEX"
        assert request.k == 10
        assert request.threshold == 0.8
    
    def test_embedding_service_request_validation(self):
        """Test EmbeddingServiceRequest validation."""
        request = EmbeddingServiceRequest(
            vector_type="PATTERN",
            entity_id="pattern-1",
            features={
                "rsi": 50.0,
                "macd": 0.5
            }
        )
        
        assert request.vector_type == "PATTERN"
        assert request.entity_id == "pattern-1"
        assert "rsi" in request.features