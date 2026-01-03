"""Critical tests for enable_mod() - P0 Priority"""
import pytest
import os
from pathlib import Path
from app.core.mod_manager import ModManager, ModInstallationError
from app.models.mod import Mod, ModFile
from app.config import settings


class TestEnableMod:
    """Test suite for enable_mod() - Critical Priority"""
    
    @pytest.mark.asyncio
    async def test_enable_mod_creates_hardlinks(self, mod_manager: ModManager, temp_dir: Path):
        """Test that enable_mod creates hardlinks from staging to game directory"""
        # Create mod record
        mod = Mod(
            name="Test Mod",
            game_id="cyberpunk2077",
            install_path=str(mod_manager.mod_path),
            is_enabled=False,
            is_active=True
        )
        mod_manager.db.add(mod)
        await mod_manager.db.flush()
        
        # Create staging directory with files
        staging_dir = settings.staging_dir / f"mod_{mod.id}"
        staging_dir.mkdir(parents=True)
        (staging_dir / "test.reds").write_text("-- Test script")
        
        # Create mod file record
        mod_file = ModFile(
            mod_id=mod.id,
            file_path="test.reds",
            file_type=".reds",
            install_path=str(mod_manager.mod_path / "test.reds")
        )
        mod_manager.db.add(mod_file)
        await mod_manager.db.flush()
        
        # Enable mod
        await mod_manager.enable_mod(mod.id)
        
        # Verify file exists in game directory
        game_file = mod_manager.mod_path / "test.reds"
        assert game_file.exists()
        assert game_file.read_text() == "-- Test script"
        
        # Verify mod is enabled
        await mod_manager.db.refresh(mod)
        assert mod.is_enabled is True
    
    @pytest.mark.asyncio
    async def test_enable_mod_fallback_to_copy(self, mod_manager: ModManager, temp_dir: Path, monkeypatch):
        """Test fallback to copy when hardlink fails (cross-filesystem)"""
        # Create mod record
        mod = Mod(
            name="Test Mod",
            game_id="cyberpunk2077",
            install_path=str(mod_manager.mod_path),
            is_enabled=False,
            is_active=True
        )
        mod_manager.db.add(mod)
        await mod_manager.db.flush()
        
        # Create staging directory
        staging_dir = settings.staging_dir / f"mod_{mod.id}"
        staging_dir.mkdir(parents=True)
        (staging_dir / "test.reds").write_text("-- Test script")
        
        # Create mod file record
        mod_file = ModFile(
            mod_id=mod.id,
            file_path="test.reds",
            file_type=".reds",
            install_path=str(mod_manager.mod_path / "test.reds")
        )
        mod_manager.db.add(mod_file)
        await mod_manager.db.flush()
        
        # Mock os.link to raise OSError (simulating cross-filesystem)
        original_link = os.link
        
        def mock_link_fail(src: str, dst: str):
            raise OSError("Cross-device link not permitted")
        
        monkeypatch.setattr(os, "link", mock_link_fail)
        
        # Enable mod - should fallback to copy
        await mod_manager.enable_mod(mod.id)
        
        # Verify file was copied (not linked)
        game_file = mod_manager.mod_path / "test.reds"
        assert game_file.exists()
        assert game_file.read_text() == "-- Test script"
        
        # Restore original
        monkeypatch.setattr(os, "link", original_link)
    
    @pytest.mark.asyncio
    async def test_enable_mod_overwrites_existing(self, mod_manager: ModManager, temp_dir: Path):
        """Test that enable_mod overwrites existing files"""
        # Create existing file
        existing_file = mod_manager.mod_path / "existing.reds"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("-- Old content")
        
        # Create mod record
        mod = Mod(
            name="Test Mod",
            game_id="cyberpunk2077",
            install_path=str(mod_manager.mod_path),
            is_enabled=False,
            is_active=True
        )
        mod_manager.db.add(mod)
        await mod_manager.db.flush()
        
        # Create staging directory with new file
        staging_dir = settings.staging_dir / f"mod_{mod.id}"
        staging_dir.mkdir(parents=True)
        (staging_dir / "existing.reds").write_text("-- New content")
        
        # Create mod file record
        mod_file = ModFile(
            mod_id=mod.id,
            file_path="existing.reds",
            file_type=".reds",
            install_path=str(existing_file)
        )
        mod_manager.db.add(mod_file)
        await mod_manager.db.flush()
        
        # Enable mod
        await mod_manager.enable_mod(mod.id)
        
        # Verify file was overwritten
        assert existing_file.read_text() == "-- New content"
    
    @pytest.mark.asyncio
    async def test_enable_mod_creates_parent_directories(self, mod_manager: ModManager, temp_dir: Path):
        """Test that enable_mod creates parent directories as needed"""
        # Create mod record
        mod = Mod(
            name="Test Mod",
            game_id="cyberpunk2077",
            install_path=str(mod_manager.mod_path),
            is_enabled=False,
            is_active=True
        )
        mod_manager.db.add(mod)
        await mod_manager.db.flush()
        
        # Create staging directory with nested structure
        staging_dir = settings.staging_dir / f"mod_{mod.id}"
        (staging_dir / "nested" / "deep").mkdir(parents=True)
        (staging_dir / "nested" / "deep" / "script.reds").write_text("-- Deep script")
        
        # Create mod file record
        target_path = mod_manager.mod_path / "nested" / "deep" / "script.reds"
        mod_file = ModFile(
            mod_id=mod.id,
            file_path="nested/deep/script.reds",
            file_type=".reds",
            install_path=str(target_path)
        )
        mod_manager.db.add(mod_file)
        await mod_manager.db.flush()
        
        # Enable mod
        await mod_manager.enable_mod(mod.id)
        
        # Verify nested directories were created
        assert target_path.exists()
        assert target_path.read_text() == "-- Deep script"
    
    @pytest.mark.asyncio
    async def test_enable_mod_handles_missing_staging_file(self, mod_manager: ModManager, temp_dir: Path):
        """Test handling of missing staging files gracefully"""
        # Create mod record
        mod = Mod(
            name="Test Mod",
            game_id="cyberpunk2077",
            install_path=str(mod_manager.mod_path),
            is_enabled=False,
            is_active=True
        )
        mod_manager.db.add(mod)
        await mod_manager.db.flush()
        
        # Create mod file record but don't create staging file
        mod_file = ModFile(
            mod_id=mod.id,
            file_path="missing.reds",
            file_type=".reds",
            install_path=str(mod_manager.mod_path / "missing.reds")
        )
        mod_manager.db.add(mod_file)
        await mod_manager.db.flush()
        
        # Enable mod - should handle missing file gracefully
        await mod_manager.enable_mod(mod.id)
        
        # File should not exist in game directory
        assert not (mod_manager.mod_path / "missing.reds").exists()
    
    @pytest.mark.asyncio
    async def test_enable_mod_nonexistent_mod(self, mod_manager: ModManager):
        """Test enabling non-existent mod"""
        # Should handle gracefully without error
        await mod_manager.enable_mod(99999)
    
    @pytest.mark.asyncio
    async def test_enable_mod_multiple_files(self, mod_manager: ModManager, temp_dir: Path):
        """Test enabling mod with multiple files"""
        # Create mod record
        mod = Mod(
            name="Test Mod",
            game_id="cyberpunk2077",
            install_path=str(mod_manager.mod_path),
            is_enabled=False,
            is_active=True
        )
        mod_manager.db.add(mod)
        await mod_manager.db.flush()
        
        # Create staging directory with multiple files
        staging_dir = settings.staging_dir / f"mod_{mod.id}"
        (staging_dir / "subdir").mkdir(parents=True)
        (staging_dir / "file1.reds").write_text("-- File 1")
        (staging_dir / "file2.reds").write_text("-- File 2")
        (staging_dir / "subdir" / "file3.reds").write_text("-- File 3")
        
        # Create mod file records
        for i, file_path in enumerate(["file1.reds", "file2.reds", "subdir/file3.reds"]):
            mod_file = ModFile(
                mod_id=mod.id,
                file_path=file_path,
                file_type=".reds",
                install_path=str(mod_manager.mod_path / file_path)
            )
            mod_manager.db.add(mod_file)
        await mod_manager.db.flush()
        
        # Enable mod
        await mod_manager.enable_mod(mod.id)
        
        # Verify all files were enabled
        assert (mod_manager.mod_path / "file1.reds").exists()
        assert (mod_manager.mod_path / "file2.reds").exists()
        assert (mod_manager.mod_path / "subdir" / "file3.reds").exists()
        
        await mod_manager.db.refresh(mod)
        assert mod.is_enabled is True
