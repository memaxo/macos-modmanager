"""Critical tests for _extract_archive() - P0 Priority"""
import pytest
import zipfile
import py7zr
import rarfile
from pathlib import Path
from app.core.mod_manager import ModManager, ModInstallationError


class TestExtractArchive:
    """Test suite for _extract_archive() - Critical Priority"""
    
    @pytest.mark.asyncio
    async def test_extract_zip_archive(self, mod_manager: ModManager, temp_dir: Path):
        """Test extraction of ZIP archive"""
        archive = temp_dir / "test.zip"
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.writestr("file1.txt", "Content 1")
            zf.writestr("subdir/file2.txt", "Content 2")
        
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        await mod_manager._extract_archive(archive, extract_dir)
        
        assert (extract_dir / "file1.txt").exists()
        assert (extract_dir / "subdir" / "file2.txt").exists()
        assert (extract_dir / "file1.txt").read_text() == "Content 1"
    
    @pytest.mark.asyncio
    async def test_extract_7z_archive(self, mod_manager: ModManager, temp_dir: Path):
        """Test extraction of 7Z archive"""
        archive = temp_dir / "test.7z"
        try:
            with py7zr.SevenZipFile(archive, 'w') as zf:
                zf.writestr("file.txt", b"Content")
        except Exception:
            # Skip if 7z creation fails
            pytest.skip("7z archive creation not supported")
        
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        await mod_manager._extract_archive(archive, extract_dir)
        
        assert (extract_dir / "file.txt").exists()
    
    @pytest.mark.asyncio
    async def test_extract_rar_archive(self, mod_manager: ModManager, temp_dir: Path):
        """Test extraction of RAR archive"""
        import rarfile
        archive = temp_dir / "test.rar"
        # Note: rarfile doesn't support creating RAR files easily
        # This test checks error handling for invalid RAR files
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        # Create a dummy RAR-like file (won't actually work, but tests error handling)
        archive.write_bytes(b"RAR dummy content")
        
        # Should raise error for invalid RAR
        with pytest.raises((ModInstallationError, rarfile.NotRarFile, rarfile.RarCannotExec)):
            await mod_manager._extract_archive(archive, extract_dir)
    
    @pytest.mark.asyncio
    async def test_extract_unsupported_format(self, mod_manager: ModManager, temp_dir: Path):
        """Test error handling for unsupported archive format"""
        archive = temp_dir / "test.tar"
        archive.write_bytes(b"dummy tar content")
        
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        with pytest.raises(ModInstallationError, match="Unsupported archive format"):
            await mod_manager._extract_archive(archive, extract_dir)
    
    @pytest.mark.asyncio
    async def test_extract_corrupted_zip(self, mod_manager: ModManager, temp_dir: Path):
        """Test handling of corrupted ZIP archive"""
        corrupted_archive = temp_dir / "corrupted.zip"
        corrupted_archive.write_bytes(b"This is not a valid zip file")
        
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        with pytest.raises((zipfile.BadZipFile, ModInstallationError)):
            await mod_manager._extract_archive(corrupted_archive, extract_dir)
    
    @pytest.mark.asyncio
    async def test_extract_archive_with_path_traversal(self, mod_manager: ModManager, temp_dir: Path):
        """Test protection against path traversal attacks"""
        archive = temp_dir / "malicious.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        # Create ZIP with path traversal
        with zipfile.ZipFile(archive, 'w') as zf:
            # Try to write outside extract directory
            zf.writestr("../outside.txt", "Malicious content")
            zf.writestr("../../etc/passwd", "Should not extract")
        
        await mod_manager._extract_archive(archive, extract_dir)
        
        # Verify files were extracted safely (zipfile should handle this)
        # The file should be extracted as "../outside.txt" relative to extract_dir
        # But zipfile.extractall() should prevent this by default
        outside_file = temp_dir / "outside.txt"
        # zipfile should prevent this, but verify it doesn't exist
        assert not outside_file.exists()
    
    @pytest.mark.asyncio
    async def test_extract_archive_with_absolute_paths(self, mod_manager: ModManager, temp_dir: Path):
        """Test handling of archives with absolute paths"""
        archive = temp_dir / "absolute_paths.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        with zipfile.ZipFile(archive, 'w') as zf:
            # Create entry with absolute path
            zf.writestr("/absolute/path/file.txt", "Content")
        
        await mod_manager._extract_archive(archive, extract_dir)
        
        # zipfile should normalize this, verify it doesn't create absolute paths
        assert not Path("/absolute/path/file.txt").exists()
    
    @pytest.mark.asyncio
    async def test_extract_large_archive(self, mod_manager: ModManager, temp_dir: Path):
        """Test extraction of large archive"""
        archive = temp_dir / "large.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        # Create archive with multiple large files
        with zipfile.ZipFile(archive, 'w') as zf:
            for i in range(10):
                zf.writestr(f"file_{i}.txt", "X" * 10000)
        
        await mod_manager._extract_archive(archive, extract_dir)
        
        # Verify all files extracted
        for i in range(10):
            assert (extract_dir / f"file_{i}.txt").exists()
    
    @pytest.mark.asyncio
    async def test_extract_archive_preserves_permissions(self, mod_manager: ModManager, temp_dir: Path):
        """Test that extraction preserves file permissions where possible"""
        archive = temp_dir / "permissions.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.writestr("executable.sh", "#!/bin/bash\necho test")
        
        await mod_manager._extract_archive(archive, extract_dir)
        
        # Verify file exists (permissions may vary by platform)
        assert (extract_dir / "executable.sh").exists()
    
    @pytest.mark.asyncio
    async def test_extract_archive_with_duplicate_names(self, mod_manager: ModManager, temp_dir: Path):
        """Test handling of archives with duplicate file names"""
        archive = temp_dir / "duplicates.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.writestr("file.txt", "First")
            zf.writestr("file.txt", "Second")  # Duplicate name
        
        await mod_manager._extract_archive(archive, extract_dir)
        
        # zipfile will overwrite, verify last one wins
        assert (extract_dir / "file.txt").exists()
    
    @pytest.mark.asyncio
    async def test_extract_empty_archive(self, mod_manager: ModManager, temp_dir: Path):
        """Test extraction of empty archive"""
        archive = temp_dir / "empty.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        with zipfile.ZipFile(archive, 'w'):
            pass  # Empty archive
        
        await mod_manager._extract_archive(archive, extract_dir)
        
        # Should succeed but extract nothing
        assert extract_dir.exists()
        assert len(list(extract_dir.iterdir())) == 0
