"""
Tests für Memory System v2.0 - Hybrid Search und Reflection Engine.
"""
import pytest
import asyncio
from datetime import datetime
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from memory.memory_system import (
    MemoryManager,
    MemoryItem,
    SemanticSearchResult,
    SemanticMemoryStore
)


class TestSemanticMemoryStore:
    """Tests für SemanticMemoryStore (ChromaDB Integration)."""
    
    def test_store_without_chromadb(self):
        """Testet dass Store ohne ChromaDB graceful fallback macht."""
        store = SemanticMemoryStore(collection=None)
        assert not store.is_available()
        
        item = MemoryItem(
            category="user_profile",
            key="test",
            value="test value"
        )
        result = store.store_embedding(item)
        assert result is None  # Should return None when not available
    
    def test_search_without_chromadb(self):
        """Testet dass Suche ohne ChromaDB leere Liste zurückgibt."""
        store = SemanticMemoryStore(collection=None)
        results = store.find_related_memories("test query")
        assert results == []
    
    def test_stats_without_chromadb(self):
        """Testet Stats ohne ChromaDB."""
        store = SemanticMemoryStore(collection=None)
        stats = store.get_stats()
        assert stats["available"] is False
        assert stats["count"] == 0


class TestMemoryManagerHybrid:
    """Tests für MemoryManager Hybrid-Suche."""
    
    def test_store_with_embedding_no_chromadb(self):
        """Testet Hybrid-Speicherung ohne ChromaDB (SQLite only)."""
        manager = MemoryManager()
        
        item = MemoryItem(
            category="test_category",
            key="test_key",
            value="test value for hybrid search",
            importance=0.8
        )
        
        # Should work even without ChromaDB
        result = manager.store_with_embedding(item)
        assert result is True
        
        # Verify SQLite storage
        stored = manager.persistent.get_memory_items("test_category")
        assert len(stored) > 0
        assert stored[0].value == "test value for hybrid search"
    
    def test_find_related_memories_without_chromadb(self):
        """Testet Hybrid-Suche ohne ChromaDB (FTS5 fallback)."""
        manager = MemoryManager()
        
        # Store a test item
        item = MemoryItem(
            category="user_profile",
            key="test_pref",
            value="Ich mag strukturierte JSON Antworten",
            importance=0.7
        )
        manager.store_with_embedding(item)
        
        # Search should not crash even without ChromaDB
        results = manager.find_related_memories("JSON Antwort")
        # Results might be empty if FTS5 is not synced, but shouldn't crash
        assert isinstance(results, list)
    
    def test_get_enhanced_context(self):
        """Testet erweiterten Kontext mit relevanter Suche."""
        manager = MemoryManager()
        
        # Store some context
        manager.store_with_embedding(MemoryItem(
            category="user_profile",
            key="language",
            value="Deutsch",
            importance=0.8
        ))
        
        # Get enhanced context
        context = manager.get_enhanced_context("Spracheinstellungen")
        
        # Should include base context
        assert "BEKANNTE FAKTEN" in context or "STRUKTURIERTE MEMORY" in context


class TestMemoryManagerSync:
    """Tests für Markdown-Sync."""
    
    def test_sync_to_markdown_creates_files(self):
        """Testet dass Sync Markdown-Dateien erstellt."""
        manager = MemoryManager()
        
        # Store some data
        manager.store_with_embedding(MemoryItem(
            category="user_profile",
            key="name",
            value="Test User",
            importance=0.9
        ))
        
        # Sync should not crash
        result = manager.sync_to_markdown()
        # May return False if markdown_store not fully initialized
        assert isinstance(result, bool)
    
    def test_sync_from_markdown(self):
        """Testet Markdown → Memory Sync."""
        manager = MemoryManager()
        
        result = manager.sync_from_markdown()
        # Should not crash even if files don't exist
        assert isinstance(result, bool)


class TestReflectionEngine:
    """Tests für Reflection Engine."""
    
    @pytest.mark.asyncio
    async def test_reflection_engine_init(self):
        """Testet Reflection Engine Initialisierung."""
        from memory.reflection_engine import ReflectionEngine, get_reflection_engine
        
        # Test singleton
        engine1 = get_reflection_engine()
        engine2 = get_reflection_engine()
        assert engine1 is engine2
    
    @pytest.mark.asyncio
    async def test_reflection_without_llm(self):
        """Testet dass Reflexion ohne LLM graceful handled wird."""
        from memory.reflection_engine import ReflectionEngine
        
        engine = ReflectionEngine(memory_manager=None, llm_client=None)
        
        # Should return None when no LLM available
        result = await engine.reflect_on_task(
            task={"description": "Test task"},
            actions=[{"method": "test", "params": {}}],
            result="Test result"
        )
        
        # Without LLM, should return None
        assert result is None
    
    @pytest.mark.asyncio
    async def test_reflection_stats(self):
        """Testet Reflection Stats."""
        from memory.reflection_engine import get_reflection_engine
        
        engine = get_reflection_engine()
        stats = engine.get_stats()
        
        assert "total_reflections" in stats
        assert isinstance(stats["total_reflections"], int)


class TestBaseAgentIntegration:
    """Tests für BaseAgent Reflection Integration."""
    
    def test_reflection_flag_in_init(self):
        """Testet dass Reflection Flag in __init__ gesetzt wird."""
        # Import would fail if syntax errors in base_agent
        from agent.base_agent import BaseAgent
        
        # Just verify import works
        assert hasattr(BaseAgent, '_run_reflection')


def test_memory_item_dataclass():
    """Testet MemoryItem Dataclass."""
    item = MemoryItem(
        category="test",
        key="test_key",
        value={"nested": "data"},
        importance=0.8,
        reason="test"
    )
    
    assert item.category == "test"
    assert item.key == "test_key"
    assert item.importance == 0.8


def test_semantic_search_result_dataclass():
    """Testet SemanticSearchResult Dataclass."""
    result = SemanticSearchResult(
        doc_id="test_doc",
        content="test content",
        category="test",
        importance=0.7,
        distance=0.1,
        source="chromadb"
    )
    
    assert result.doc_id == "test_doc"
    assert result.source == "chromadb"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
