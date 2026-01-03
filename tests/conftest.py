"""Pytest configuration and shared fixtures"""
import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import patch, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.database import Base
from app.core.mod_manager import ModManager
from app.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temp_db() -> AsyncGenerator[AsyncSession, None]:
    """Create a temporary in-memory database for testing"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
    
    await engine.dispose()


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for test files"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def game_path(temp_dir: Path) -> Path:
    """Create a mock game directory structure with all expected directories"""
    game_dir = temp_dir / "game"
    game_dir.mkdir()
    
    # Create expected game directories
    (game_dir / "r6" / "scripts").mkdir(parents=True)
    (game_dir / "r6" / "tweaks").mkdir(parents=True)
    (game_dir / "red4ext" / "plugins").mkdir(parents=True)
    (game_dir / "archive" / "pc" / "mod").mkdir(parents=True)
    (game_dir / "bin" / "x64").mkdir(parents=True)
    
    # Create mock Cyberpunk2077.app bundle to pass pre-flight validation
    app_bundle = game_dir / "Cyberpunk2077.app"
    app_bundle.mkdir()
    (app_bundle / "Contents").mkdir()
    # Create minimal Info.plist
    (app_bundle / "Contents" / "Info.plist").write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        b'<plist version="1.0"><dict>'
        b'<key>CFBundleShortVersionString</key><string>2.13</string>'
        b'</dict></plist>'
    )
    
    return game_dir


@pytest.fixture
def mod_manager(temp_db: AsyncSession, game_path: Path) -> ModManager:
    """Create a ModManager instance for testing"""
    return ModManager(temp_db, game_path)


@pytest.fixture
def staging_dir(temp_dir: Path) -> Path:
    """Create a staging directory"""
    staging = temp_dir / "staging"
    staging.mkdir()
    return staging


@pytest.fixture
def backup_dir(temp_dir: Path) -> Path:
    """Create a backup directory"""
    backup = temp_dir / "backups"
    backup.mkdir()
    return backup


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch, temp_dir: Path):
    """Mock settings to use temp directories"""
    monkeypatch.setattr(settings, "staging_dir", temp_dir / "staging")
    monkeypatch.setattr(settings, "backups_dir", temp_dir / "backups")
    monkeypatch.setattr(settings, "cache_dir", temp_dir / "cache")
    monkeypatch.setattr(settings, "default_mod_path", "r6/scripts")
    monkeypatch.setattr(settings, "game_id", "cyberpunk2077")
    monkeypatch.setattr(settings, "game_domain", "cyberpunk2077")
    monkeypatch.setattr(settings, "strict_compatibility", False)  # Disable for most tests
    monkeypatch.setattr(settings, "backup_before_install", True)
    monkeypatch.setattr(settings, "auto_remove_quarantine", False)  # Disable for tests
    settings.staging_dir.mkdir(parents=True, exist_ok=True)
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def mock_process_check(monkeypatch):
    """Mock psutil.process_iter to avoid 'game running' check during tests"""
    import psutil
    
    def mock_process_iter(attrs=None):
        """Return empty iterator - no game processes running"""
        return iter([])
    
    monkeypatch.setattr(psutil, "process_iter", mock_process_iter)
