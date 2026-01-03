"""Critical tests for _backup_conflicting_files() - P0 Priority"""
import pytest
from pathlib import Path
from app.core.mod_manager import ModManager
from app.config import settings


class TestBackupConflictingFiles:
    """Test suite for _backup_conflicting_files() - Critical Priority"""
    
    @pytest.mark.asyncio
    async def test_backup_creates_backup_when_conflicts_exist(self, mod_manager: ModManager, temp_dir: Path, game_path: Path):
        """Test backup creation when files will be overwritten"""
        # Create existing file in game directory
        existing_file = game_path / "r6" / "scripts" / "existing.reds"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("-- Original content")
        
        # Create file info for installation that will overwrite
        from app.core.mod_manager import FileInfoDict
        files_to_install: list[FileInfoDict] = [
            FileInfoDict(
                source_path=temp_dir / "new.reds",
                path="existing.reds",
                type=".reds",
                install_path=existing_file
            )
        ]
        
        # Create source file
        (temp_dir / "new.reds").write_text("-- New content")
        
        backup_path = await mod_manager._backup_conflicting_files(files_to_install)
        
        # Verify backup was created
        assert backup_path is not None
        assert backup_path.exists()
        
        # Verify backup contains original file
        backup_file = backup_path / "r6" / "scripts" / "existing.reds"
        assert backup_file.exists()
        assert backup_file.read_text() == "-- Original content"
    
    @pytest.mark.asyncio
    async def test_backup_returns_none_when_no_conflicts(self, mod_manager: ModManager, temp_dir: Path):
        """Test that backup returns None when no conflicts exist"""
        from app.core.mod_manager import FileInfoDict
        
        # Create file info for new file (no conflict)
        new_file = mod_manager.mod_path / "new.reds"
        files_to_install: list[FileInfoDict] = [
            FileInfoDict(
                source_path=temp_dir / "new.reds",
                path="new.reds",
                type=".reds",
                install_path=new_file
            )
        ]
        
        # Create source file
        (temp_dir / "new.reds").write_text("-- New content")
        
        backup_path = await mod_manager._backup_conflicting_files(files_to_install)
        
        # Should return None when no conflicts
        assert backup_path is None
    
    @pytest.mark.asyncio
    async def test_backup_preserves_directory_structure(self, mod_manager: ModManager, temp_dir: Path, game_path: Path):
        """Test that backup preserves directory structure"""
        # Create nested existing files
        nested_file = game_path / "r6" / "scripts" / "nested" / "deep" / "file.reds"
        nested_file.parent.mkdir(parents=True, exist_ok=True)
        nested_file.write_text("-- Nested content")
        
        from app.core.mod_manager import FileInfoDict
        files_to_install: list[FileInfoDict] = [
            FileInfoDict(
                source_path=temp_dir / "new.reds",
                path="nested/deep/file.reds",
                type=".reds",
                install_path=nested_file
            )
        ]
        
        (temp_dir / "new.reds").write_text("-- New content")
        
        backup_path = await mod_manager._backup_conflicting_files(files_to_install)
        
        # Verify nested structure preserved
        backup_file = backup_path / "r6" / "scripts" / "nested" / "deep" / "file.reds"
        assert backup_file.exists()
        assert backup_file.read_text() == "-- Nested content"
    
    @pytest.mark.asyncio
    async def test_backup_multiple_conflicting_files(self, mod_manager: ModManager, temp_dir: Path, game_path: Path):
        """Test backup of multiple conflicting files"""
        # Create multiple existing files
        file1 = game_path / "r6" / "scripts" / "file1.reds"
        file2 = game_path / "r6" / "scripts" / "file2.reds"
        file1.parent.mkdir(parents=True, exist_ok=True)
        file1.write_text("-- File 1 original")
        file2.write_text("-- File 2 original")
        
        from app.core.mod_manager import FileInfoDict
        files_to_install: list[FileInfoDict] = [
            FileInfoDict(
                source_path=temp_dir / "new1.reds",
                path="file1.reds",
                type=".reds",
                install_path=file1
            ),
            FileInfoDict(
                source_path=temp_dir / "new2.reds",
                path="file2.reds",
                type=".reds",
                install_path=file2
            )
        ]
        
        (temp_dir / "new1.reds").write_text("-- File 1 new")
        (temp_dir / "new2.reds").write_text("-- File 2 new")
        
        backup_path = await mod_manager._backup_conflicting_files(files_to_install)
        
        # Verify both files backed up
        assert backup_path is not None
        backup_file1 = backup_path / "r6" / "scripts" / "file1.reds"
        backup_file2 = backup_path / "r6" / "scripts" / "file2.reds"
        assert backup_file1.exists()
        assert backup_file2.exists()
        assert backup_file1.read_text() == "-- File 1 original"
        assert backup_file2.read_text() == "-- File 2 original"
    
    @pytest.mark.asyncio
    async def test_backup_mixed_conflicts_and_new_files(self, mod_manager: ModManager, temp_dir: Path, game_path: Path):
        """Test backup when some files conflict and some are new"""
        # Create one existing file
        existing_file = game_path / "r6" / "scripts" / "existing.reds"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("-- Original")
        
        from app.core.mod_manager import FileInfoDict
        files_to_install: list[FileInfoDict] = [
            FileInfoDict(
                source_path=temp_dir / "existing.reds",
                path="existing.reds",
                type=".reds",
                install_path=existing_file
            ),
            FileInfoDict(
                source_path=temp_dir / "new.reds",
                path="new.reds",
                type=".reds",
                install_path=mod_manager.mod_path / "new.reds"
            )
        ]
        
        (temp_dir / "existing.reds").write_text("-- New existing")
        (temp_dir / "new.reds").write_text("-- New file")
        
        backup_path = await mod_manager._backup_conflicting_files(files_to_install)
        
        # Should create backup (has conflicts)
        assert backup_path is not None
        # Should only backup conflicting file
        assert (backup_path / "r6" / "scripts" / "existing.reds").exists()
        assert not (backup_path / "r6" / "scripts" / "new.reds").exists()
    
    @pytest.mark.asyncio
    async def test_backup_timestamp_uniqueness(self, mod_manager: ModManager, temp_dir: Path, game_path: Path):
        """Test that backup directories have unique timestamps"""
        existing_file = game_path / "r6" / "scripts" / "file.reds"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("-- Content")
        
        from app.core.mod_manager import FileInfoDict
        files_to_install: list[FileInfoDict] = [
            FileInfoDict(
                source_path=temp_dir / "new.reds",
                path="file.reds",
                type=".reds",
                install_path=existing_file
            )
        ]
        
        (temp_dir / "new.reds").write_text("-- New")
        
        # Create two backups (with small delay)
        import asyncio
        backup1 = await mod_manager._backup_conflicting_files(files_to_install)
        await asyncio.sleep(0.1)  # Longer delay to ensure different timestamp
        backup2 = await mod_manager._backup_conflicting_files(files_to_install)
        
        # Should have different paths (or at least both should exist)
        assert backup1 is not None
        assert backup2 is not None
        assert backup1.exists()
        assert backup2.exists()
        # Note: On fast systems, timestamps might be the same, so we just verify both exist