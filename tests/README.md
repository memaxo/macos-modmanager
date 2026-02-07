# Test Suite for macOS Mod Manager

For overall project status and run-state docs, see `../docs/STATUS.md`.

## Overview

This test suite covers all critical mod installation functions with comprehensive test cases for success paths, error handling, and edge cases.

## Test Structure

### P0 Priority Tests (Critical)
- `test_mod_installation.py` - Tests for `install_mod_from_file()`
- `test_extract_archive.py` - Tests for `_extract_archive()`
- `test_get_files_to_install.py` - Tests for `_get_files_to_install()`
- `test_enable_mod.py` - Tests for `enable_mod()`
- `test_backup_conflicting_files.py` - Tests for `_backup_conflicting_files()`

### P1 Priority Tests (High)
- `test_install_from_nexus.py` - Tests for `install_mod_from_nexus()`
- `test_detect_mod_structure.py` - Tests for `_detect_mod_structure()`

## Running Tests

### Install Dependencies

Using `uv` (recommended):
```bash
uv sync
```

Using `pip`:
```bash
pip install -r requirements.txt
```

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest tests/test_mod_installation.py
```

### Run Specific Test
```bash
pytest tests/test_mod_installation.py::TestInstallModFromFile::test_install_valid_mod
```

### Run with Coverage
```bash
pytest --cov=app --cov-report=html
```

### Run Only Fast Tests
```bash
pytest -m "not slow"
```

## Test Coverage

### install_mod_from_file() - 15+ test cases
- ✅ Valid mod installation
- ✅ Duplicate detection
- ✅ Compatibility checks
- ✅ Empty mods
- ✅ Various mod structures
- ✅ Corrupted archives
- ✅ Backup creation
- ✅ Transaction rollback
- ✅ Temp cleanup
- ✅ Metadata handling
- ✅ Special characters

### _extract_archive() - 12+ test cases
- ✅ ZIP extraction
- ✅ 7Z extraction
- ✅ RAR extraction (error handling)
- ✅ Unsupported formats
- ✅ Corrupted archives
- ✅ Path traversal protection
- ✅ Absolute paths handling
- ✅ Large archives
- ✅ Permissions preservation
- ✅ Duplicate names
- ✅ Empty archives

### _get_files_to_install() - 10+ test cases
- ✅ Root level .reds files
- ✅ r6/scripts structure
- ✅ No .reds files
- ✅ Nested directories
- ✅ Path preservation
- ✅ Special characters
- ✅ Empty mods
- ✅ Only .reds files

### enable_mod() - 10+ test cases
- ✅ Hardlink creation
- ✅ Copy fallback
- ✅ Overwrite handling
- ✅ Parent directory creation
- ✅ Missing file handling
- ✅ Non-existent mod
- ✅ Multiple files

### _backup_conflicting_files() - 8+ test cases
- ✅ Backup creation
- ✅ No conflicts
- ✅ Directory structure preservation
- ✅ Multiple files
- ✅ Mixed conflicts
- ✅ Timestamp uniqueness

## Fixtures

- `temp_db` - In-memory SQLite database for testing
- `temp_dir` - Temporary directory for test files
- `game_path` - Mock game directory structure
- `mod_manager` - ModManager instance for testing
- `staging_dir` - Staging directory
- `backup_dir` - Backup directory
- `mock_settings` - Mocked settings using temp directories

## Notes

- All tests use temporary directories and in-memory databases
- Tests are isolated and don't affect each other
- External dependencies (Nexus API) are mocked
- File system operations use temp directories
- Database operations use in-memory SQLite
