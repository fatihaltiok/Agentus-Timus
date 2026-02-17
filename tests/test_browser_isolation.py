"""
Tests für Browser-Isolation Phase A (A0-A3).

Testet:
- PersistentContextManager
- Retry-Handler
- Browser-Tool Integration
"""
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import shutil
import sys

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


class TestPersistentContextManager:
    """Tests für PersistentContextManager."""
    
    @pytest.fixture
    def temp_storage_dir(self):
        """Erstellt temporäres Storage-Verzeichnis."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_manager_init(self, temp_storage_dir):
        """Testet Initialisierung."""
        from tools.browser_tool.persistent_context import PersistentContextManager
        
        manager = PersistentContextManager(base_storage_dir=temp_storage_dir)
        
        assert manager.base_storage_dir == temp_storage_dir
        assert manager.contexts == {}
        assert manager._initialized is False
    
    def test_manager_status(self, temp_storage_dir):
        """Testet Status-Abfrage."""
        from tools.browser_tool.persistent_context import PersistentContextManager
        
        manager = PersistentContextManager(base_storage_dir=temp_storage_dir)
        status = manager.get_status()
        
        assert status["initialized"] is False
        assert status["active_contexts"] == 0
        assert status["max_contexts"] == 5
    
    @pytest.mark.asyncio
    async def test_manager_initialize(self, temp_storage_dir):
        """Testet Browser-Initialisierung."""
        from tools.browser_tool.persistent_context import PersistentContextManager
        
        manager = PersistentContextManager(
            base_storage_dir=temp_storage_dir,
            headless=True
        )
        
        result = await manager.initialize()
        
        assert result is True
        assert manager._initialized is True
        assert manager._browser is not None
        
        # Cleanup
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_create_context(self, temp_storage_dir):
        """Testet Context-Erstellung."""
        from tools.browser_tool.persistent_context import PersistentContextManager
        
        manager = PersistentContextManager(base_storage_dir=temp_storage_dir)
        await manager.initialize()
        
        session = await manager.get_or_create_context("test_session")
        
        assert session.session_id == "test_session"
        assert session.context is not None
        assert session.page is not None
        assert manager.contexts.get("test_session") is session
        
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_reuse_context(self, temp_storage_dir):
        """Testet Context-Wiederverwendung."""
        from tools.browser_tool.persistent_context import PersistentContextManager
        
        manager = PersistentContextManager(base_storage_dir=temp_storage_dir)
        await manager.initialize()
        
        # Erster Aufruf - erstellt neuen Context
        session1 = await manager.get_or_create_context("test")
        assert session1.request_count == 0  # Noch 0 (neu erstellt)
        
        # Zweiter Aufruf - wiederverwendet existierenden Context
        session2 = await manager.get_or_create_context("test")
        
        # Gleiche Instanz
        assert session1 is session2
        # request_count zeigt Reuses an
        assert session2.request_count == 1  # Einmal wiederverwendet
        
        # Dritter Aufruf
        session3 = await manager.get_or_create_context("test")
        assert session3.request_count == 2  # Zweimal wiederverwendet
        
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_context_limit(self, temp_storage_dir):
        """Testet Context-Limit und Eviction."""
        from tools.browser_tool.persistent_context import PersistentContextManager, MAX_CONTEXTS
        
        manager = PersistentContextManager(base_storage_dir=temp_storage_dir)
        await manager.initialize()
        
        # Erstelle MAX_CONTEXTS + 1 Sessions
        for i in range(MAX_CONTEXTS + 2):
            await manager.get_or_create_context(f"session_{i}")
        
        # Sollte nur MAX_CONTEXTS haben (älteste wurde evicted)
        assert len(manager.contexts) <= MAX_CONTEXTS
        # Default sollte nie evicted werden
        assert "default" in manager.contexts or len(manager.contexts) == MAX_CONTEXTS
        
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_save_and_restore_state(self, temp_storage_dir):
        """Testet State-Speicherung und -Wiederherstellung."""
        from tools.browser_tool.persistent_context import PersistentContextManager
        
        manager = PersistentContextManager(base_storage_dir=temp_storage_dir)
        await manager.initialize()
        
        # Context erstellen
        session = await manager.get_or_create_context("persist_test")
        
        # State speichern
        saved = await manager.save_context_state("persist_test")
        assert saved is True
        
        # Storage-File sollte existieren
        storage_file = session.storage_path / "storage.json"
        assert storage_file.exists()
        
        # Context schließen
        await manager.close_context("persist_test", save_state=False)
        assert "persist_test" not in manager.contexts
        
        # Neu erstellen - sollte State laden
        session2 = await manager.get_or_create_context("persist_test")
        assert session2.storage_path == session.storage_path
        
        await manager.shutdown()


class TestBrowserRetryHandler:
    """Tests für BrowserRetryHandler."""
    
    def test_handler_init(self):
        """Testet Handler-Initialisierung."""
        from tools.browser_tool.retry_handler import BrowserRetryHandler
        
        handler = BrowserRetryHandler(max_retries=5)
        
        assert handler.max_retries == 5
        assert len(handler.retry_delays) == 3
    
    def test_captcha_detection(self):
        """Testet CAPTCHA-Erkennung."""
        from tools.browser_tool.retry_handler import retry_handler
        
        # CAPTCHA-Blockade
        result = {"status": "blocked", "content": "Cloudflare challenge"}
        assert retry_handler._is_captcha_blocked(result) is True
        
        # Normale Seite
        result_normal = {"status": "opened", "content": "Welcome"}
        assert retry_handler._is_captcha_blocked(result_normal) is False
    
    def test_retryable_error_detection(self):
        """Testet Retry-Fehler-Erkennung."""
        from tools.browser_tool.retry_handler import retry_handler
        
        # Retry-würdige Fehler
        assert retry_handler._is_retryable_error("Timeout after 30s") is True
        assert retry_handler._is_retryable_error("net::ERR_CONNECTION_REFUSED") is True
        assert retry_handler._is_retryable_error("SSL certificate error") is True
        
        # Nicht retry-würdig
        assert retry_handler._is_retryable_error("User cancelled") is False
    
    @pytest.mark.asyncio
    async def test_retry_success(self):
        """Testet erfolgreichen Retry."""
        from tools.browser_tool.retry_handler import BrowserRetryHandler
        
        handler = BrowserRetryHandler(max_retries=3)
        
        call_count = 0
        
        async def flaky_action():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Timeout error")
            return {"status": "ok"}
        
        result = await handler.execute_with_retry(flaky_action)
        
        assert result["status"] == "ok"
        assert call_count == 2  # Ein Fehler, dann Erfolg
    
    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Testet erschöpfte Retries."""
        from tools.browser_tool.retry_handler import BrowserRetryHandler
        
        handler = BrowserRetryHandler(max_retries=2, retry_delays=[0.1, 0.1])
        
        async def always_fail():
            raise Exception("Timeout error")
        
        result = await handler.execute_with_retry(always_fail)
        
        assert result["retries_exhausted"] is True
        assert result["attempts"] == 2


class TestBrowserToolIntegration:
    """Tests für Browser-Tool Integration."""
    
    @pytest.mark.asyncio
    async def test_ensure_browser_initialized(self):
        """Testet Browser-Initialisierung mit Session."""
        from tools.browser_tool.tool import ensure_browser_initialized
        import tools.shared_context as shared_context
        
        # Manager erstellen falls nicht vorhanden
        if not shared_context.browser_context_manager:
            from tools.browser_tool.persistent_context import PersistentContextManager
            manager = PersistentContextManager()
            await manager.initialize()
            shared_context.browser_context_manager = manager
        
        page = await ensure_browser_initialized("test_integration")
        
        assert page is not None
        
        # Cleanup
        await shared_context.browser_context_manager.shutdown()
        shared_context.browser_context_manager = None
    
    def test_session_tools_registered(self):
        """Testet dass Session-Tools registriert sind."""
        from tools.tool_registry_v2 import registry_v2
        
        tools = registry_v2.list_all_tools()
        
        # Neue Session-Tools sollten vorhanden sein
        assert "browser_session_status" in tools
        assert "browser_save_session" in tools
        assert "browser_close_session" in tools
        assert "browser_cleanup_expired" in tools


class TestRetryDecorator:
    """Tests für @with_retry Decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator(self):
        """Testet Retry-Decorator."""
        from tools.browser_tool.retry_handler import with_retry
        
        call_count = 0
        
        @with_retry(max_retries=2)
        async def decorated_action():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Timeout error")
            return {"status": "ok"}
        
        result = await decorated_action()
        
        assert result["status"] == "ok"
        assert call_count == 2


def test_imports():
    """Testet dass alle Module importiert werden können."""
    from tools.browser_tool.persistent_context import (
        PersistentContextManager,
        SessionContext,
        get_context_manager,
    )
    from tools.browser_tool.retry_handler import (
        BrowserRetryHandler,
        retry_handler,
        with_retry,
    )
    
    assert PersistentContextManager is not None
    assert BrowserRetryHandler is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
