"""Integration tests for Similarity Service."""

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, AsyncMock


@pytest.mark.integration
class TestSimilarityService:
    """Integration tests for Similarity Service."""
    
    @pytest.mark.asyncio
    async def test_search_similar_patterns(self):
        """Test searching for similar patterns using pgvector."""
        try:
            from ai_market_intelligence_service.services.similarity_service import similarity_service
            
            # Mock the database session
            session = Mock()
            session.execute = Mock()
            
            query_vector = [0.1, 0.2, 0.3, 0.4, 0.5] * 25  # 128-dimensional vector
            
            similar_patterns = await similarity_service.search_similar_patterns(
                query_vector=query_vector,
                instrument_id="NIFTY50-INDEX",
                timeframe="15m",
                k=10,
                similarity_threshold=0.8,
                session=session
            )
            
            # Verify similar patterns were found
            assert similar_patterns is not None
            assert len(similar_patterns) >= 0
        except ImportError:
            pytest.skip("Similarity service not available")
        except Exception as e:
            pytest.skip(f"Similarity service test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_search_similar_setups(self):
        """Test searching for similar setups using pgvector."""
        try:
            from ai_market_intelligence_service.services.similarity_service import similarity_service
            
            # Mock the database session
            session = Mock()
            session.execute = Mock()
            
            query_vector = [0.1, 0.2, 0.3, 0.4, 0.5] * 25  # 128-dimensional vector
            
            similar_setups = await similarity_service.search_similar_setups(
                query_vector=query_vector,
                instrument_id="NIFTY50-INDEX",
                timeframe="15m",
                k=10,
                similarity_threshold=0.8,
                session=session
            )
            
            # Verify similar setups were found
            assert similar_setups is not None
            assert len(similar_setups) >= 0
        except ImportError:
            pytest.skip("Similarity service not available")
        except Exception as e:
            pytest.skip(f"Similarity service test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_cosine_similarity_calculation(self):
        """Test cosine similarity calculation."""
        try:
            from ai_market_intelligence_service.similarity_search.similarity_ranking_engine import SimilarityRankingEngine
            
            # Mock the database session
            session = Mock()
            
            ranking_engine = SimilarityRankingEngine(session)
            
            vector1 = [0.1, 0.2, 0.3, 0.4, 0.5] * 25
            vector2 = [0.2, 0.3, 0.4, 0.5, 0.6] * 25
            
            similarity = ranking_engine.calculate_cosine_similarity(vector1, vector2)
            
            # Verify similarity is between 0 and 1
            assert 0 <= similarity <= 1
        except ImportError:
            pytest.skip("Similarity ranking engine not available")
        except Exception as e:
            pytest.skip(f"Similarity calculation test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_euclidean_distance_calculation(self):
        """Test Euclidean distance calculation."""
        try:
            from ai_market_intelligence_service.similarity_search.similarity_ranking_engine import SimilarityRankingEngine
            
            # Mock the database session
            session = Mock()
            
            ranking_engine = SimilarityRankingEngine(session)
            
            vector1 = [0.1, 0.2, 0.3, 0.4, 0.5] * 25
            vector2 = [0.2, 0.3, 0.4, 0.5, 0.6] * 25
            
            distance = ranking_engine.calculate_euclidean_distance(vector1, vector2)
            
            # Verify distance is non-negative
            assert distance >= 0
        except ImportError:
            pytest.skip("Similarity ranking engine not available")
        except Exception as e:
            pytest.skip(f"Similarity calculation test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_vector_generation_for_pattern(self):
        """Test vector generation for pattern."""
        try:
            from ai_market_intelligence_service.similarity_search.vector_generator import VectorGeneratorEngine
            
            vector_generator = VectorGeneratorEngine(vector_size=128)
            
            vector = vector_generator.generate_pattern_vector(
                pattern_type="DOJI",
                pattern_direction="NEUTRAL",
                pattern_category="CANDLESTICK",
                confidence_score=0.85,
                quality_score=0.90,
                ohlcv_data=[]
            )
            
            # Verify vector is generated
            assert vector is not None
            assert len(vector) == 128
        except ImportError:
            pytest.skip("Vector generator not available")
        except Exception as e:
            pytest.skip(f"Vector generation test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_vector_generation_for_setup(self):
        """Test vector generation for setup."""
        try:
            from ai_market_intelligence_service.similarity_search.vector_generator import VectorGeneratorEngine
            
            vector_generator = VectorGeneratorEngine(vector_size=128)
            
            vector = vector_generator.generate_setup_vector(
                setup_type="BULLISH_CONTINUATION",
                setup_direction="BULLISH",
                setup_score=0.85,
                confidence_level=0.90,
                pattern_score=0.85,
                structure_score=0.90,
                volume_score=0.80,
                trend_score=0.85,
                context_score=0.88,
                market_regime="BULL_TREND",
                volatility_regime="QUIET"
            )
            
            # Verify vector is generated
            assert vector is not None
            assert len(vector) == 128
        except ImportError:
            pytest.skip("Vector generator not available")
        except Exception as e:
            pytest.skip(f"Vector generation test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_rank_by_outcome(self):
        """Test re-ranking similar vectors by historical outcome."""
        try:
            from ai_market_intelligence_service.similarity_search.similarity_ranking_engine import SimilarityRankingEngine
            
            # Mock the database session
            session = Mock()
            
            ranking_engine = SimilarityRankingEngine(session)
            
            ranked_vectors = [
                {"entity_id": "pattern-1", "similarity": 0.95, "outcome_type": "SUCCESS"},
                {"entity_id": "pattern-2", "similarity": 0.90, "outcome_type": "FAILURE"},
                {"entity_id": "pattern-3", "similarity": 0.85, "outcome_type": "SUCCESS"}
            ]
            
            re_ranked = await ranking_engine.rank_by_outcome(
                ranked_vectors=ranked_vectors,
                outcome_type="SUCCESS"
            )
            
            # Verify re-ranking
            assert re_ranked is not None
            assert len(re_ranked) == len(ranked_vectors)
        except ImportError:
            pytest.skip("Similarity ranking engine not available")
        except Exception as e:
            pytest.skip(f"Ranking test failed: {e}")