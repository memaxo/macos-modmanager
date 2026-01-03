# Critical Mod Installation Functions - Testing Priority

## 🔴 **CRITICAL PRIORITY** - Core Installation Functions

These functions handle the core installation flow and have the highest risk of data corruption or system issues.

### 1. `install_mod_from_file()` ⚠️ **HIGHEST PRIORITY**
**Location:** `app/core/mod_manager.py:59`

**Why Critical:**
- Main entry point for mod installation
- Handles file extraction, structure detection, and deployment
- Creates database records and file system changes
- **Risk:** Can corrupt game files if backup/rollback fails

**Critical Test Cases:**
- ✅ Valid mod archive (zip, 7z, rar)
- ✅ Invalid/corrupted archive
- ✅ Mod already installed (duplicate detection)
- ✅ Compatibility check failures (DLL files, incompatible dependencies)
- ✅ Empty mod archive (no .reds files)
- ✅ Mod with nested r6/scripts structure
- ✅ Mod with files at root level
- ✅ Disk space exhaustion during extraction
- ✅ Permission errors during file operations
- ✅ Database transaction rollback on failure
- ✅ Temp directory cleanup on error
- ✅ Backup creation before overwriting existing files
- ✅ Hardlink creation vs copy fallback (cross-filesystem)

**Edge Cases:**
- Very long file paths (>255 chars)
- Special characters in file names
- Symlinks in mod archive
- Empty directories in mod structure

---

### 2. `_extract_archive()` ⚠️ **HIGH PRIORITY**
**Location:** `app/core/mod_manager.py:439`

**Why Critical:**
- Handles multiple archive formats (zip, 7z, rar)
- **Risk:** Can fail silently or extract malicious files

**Critical Test Cases:**
- ✅ ZIP archive extraction
- ✅ 7Z archive extraction
- ✅ RAR archive extraction
- ✅ Corrupted archive files
- ✅ Password-protected archives (should fail gracefully)
- ✅ Archives with path traversal attacks (`../` in paths)
- ✅ Archives with absolute paths
- ✅ Very large archives (>1GB)
- ✅ Archives with duplicate file names
- ✅ Archives with invalid file names (null bytes, etc.)

---

### 3. `_get_files_to_install()` ⚠️ **HIGH PRIORITY**
**Location:** `app/core/mod_manager.py:393`

**Why Critical:**
- Determines which files get installed and where
- **Risk:** Wrong file placement can break game or cause conflicts

**Critical Test Cases:**
- ✅ Mod with .reds files at root
- ✅ Mod with r6/scripts structure
- ✅ Mod with both structures (should prefer r6/scripts)
- ✅ Mod with no .reds files (should handle gracefully)
- ✅ Mod with nested directory structures
- ✅ Mod with files outside expected directories
- ✅ Path normalization (removing r6/scripts prefix correctly)

---

### 4. `enable_mod()` ⚠️ **HIGH PRIORITY**
**Location:** `app/core/mod_manager.py:298`

**Why Critical:**
- Creates hardlinks from staging to game directory
- **Risk:** Can overwrite game files or fail silently

**Critical Test Cases:**
- ✅ Hardlink creation on same filesystem
- ✅ Copy fallback when hardlink fails (cross-filesystem)
- ✅ Overwriting existing files (should backup first)
- ✅ Creating parent directories as needed
- ✅ Handling missing staging files gracefully
- ✅ Partial enable failure (some files succeed, some fail)
- ✅ Permission errors during link creation

---

### 5. `_backup_conflicting_files()` ⚠️ **HIGH PRIORITY**
**Location:** `app/core/mod_manager.py:420`

**Why Critical:**
- Creates backups before overwriting files
- **Risk:** Without backups, rollback is impossible

**Critical Test Cases:**
- ✅ Backup creation when files exist
- ✅ No backup when no conflicts (should return None)
- ✅ Backup directory structure preservation
- ✅ Backup timestamp uniqueness
- ✅ Disk space check before backup
- ✅ Backup failure handling (should abort install?)

---

## 🟠 **HIGH PRIORITY** - Supporting Functions

### 6. `install_mod_from_nexus()` 
**Location:** `app/core/mod_manager.py:183`

**Why Critical:**
- Downloads and installs mods from Nexus Mods API
- **Risk:** Network failures, API errors, download corruption

**Critical Test Cases:**
- ✅ Successful download and install
- ✅ Network timeout handling
- ✅ Invalid nexus_mod_id
- ✅ Missing file_id (should use latest)
- ✅ Download URL expiration
- ✅ Partial download failure
- ✅ Download corruption detection
- ✅ Progress callback accuracy
- ✅ Rate limiting handling
- ✅ API authentication failures

---

### 7. `_detect_mod_structure()`
**Location:** `app/core/mod_manager.py:455`

**Why Critical:**
- Identifies mod type and metadata
- **Risk:** Wrong type detection can cause compatibility issues

**Critical Test Cases:**
- ✅ Mod with modinfo.json
- ✅ Mod with mod.json
- ✅ Mod with info.json
- ✅ Mod with no metadata files
- ✅ Invalid JSON in metadata files
- ✅ Missing required fields in metadata
- ✅ Version string parsing

---

### 8. `_calculate_file_hash()`
**Location:** `app/core/mod_manager.py:489`

**Why Critical:**
- Used for duplicate detection
- **Risk:** Hash collisions or incorrect hashing

**Critical Test Cases:**
- ✅ SHA256 hash calculation accuracy
- ✅ Large file hashing (>1GB)
- ✅ Empty file handling
- ✅ Hash collision detection (unlikely but should test)

---

## 🟡 **MEDIUM PRIORITY** - Uninstallation & Management

### 9. `uninstall_mod()`
**Location:** `app/core/mod_manager.py:252`

**Why Critical:**
- Removes mod files and database records
- **Risk:** Can leave orphaned files or break other mods

**Critical Test Cases:**
- ✅ Complete uninstallation
- ✅ Mod with shared files (hardlinks)
- ✅ Empty directory cleanup
- ✅ Staging directory removal
- ✅ Database record cleanup
- ✅ Uninstall non-existent mod (should handle gracefully)
- ✅ Partial uninstall failure recovery

---

### 10. `disable_mod()`
**Location:** `app/core/mod_manager.py:334`

**Why Critical:**
- Removes hardlinks without deleting staging files
- **Risk:** Can leave broken links or fail partially

**Critical Test Cases:**
- ✅ Remove all hardlinks
- ✅ Empty directory cleanup
- ✅ Handle missing files gracefully
- ✅ Preserve staging directory

---

### 11. `rollback_mod_installation()`
**Location:** `app/core/mod_manager.py:344`

**Why Critical:**
- Restores files from backup
- **Risk:** Can restore wrong files or corrupt game

**Critical Test Cases:**
- ✅ Successful rollback
- ✅ Missing backup directory
- ✅ Backup file corruption
- ✅ Partial rollback failure
- ✅ Rollback when no backup exists

---

## 🔵 **LOWER PRIORITY** - Utility Functions

### 12. `_install_mod_files_from_list()`
**Location:** `app/core/mod_manager.py:410`

**Why Critical:**
- Actually copies files to game directory
- **Risk:** File copy failures

**Critical Test Cases:**
- ✅ Successful file copy
- ✅ Permission errors
- ✅ Disk space exhaustion
- ✅ Source file missing

---

## 🧪 **Recommended Test Structure**

```python
# Example test structure for install_mod_from_file

class TestModInstallation:
    """Test suite for critical mod installation functions"""
    
    async def test_install_valid_mod(self):
        """Test successful installation of valid mod"""
        pass
    
    async def test_install_duplicate_mod(self):
        """Test duplicate detection"""
        pass
    
    async def test_install_incompatible_mod(self):
        """Test compatibility check rejection"""
        pass
    
    async def test_install_corrupted_archive(self):
        """Test handling of corrupted archives"""
        pass
    
    async def test_install_with_backup(self):
        """Test backup creation before overwrite"""
        pass
    
    async def test_install_rollback_on_failure(self):
        """Test transaction rollback on failure"""
        pass
    
    async def test_extract_archive_formats(self):
        """Test all supported archive formats"""
        pass
    
    async def test_path_traversal_protection(self):
        """Test protection against path traversal attacks"""
        pass
```

---

## 📊 **Testing Priority Matrix**

| Function | Risk Level | Test Coverage Priority | Estimated Test Cases |
|----------|-----------|----------------------|---------------------|
| `install_mod_from_file` | 🔴 Critical | **P0** | 15+ |
| `_extract_archive` | 🔴 Critical | **P0** | 12+ |
| `_get_files_to_install` | 🔴 Critical | **P0** | 10+ |
| `enable_mod` | 🔴 Critical | **P0** | 10+ |
| `_backup_conflicting_files` | 🔴 Critical | **P0** | 8+ |
| `install_mod_from_nexus` | 🟠 High | **P1** | 10+ |
| `_detect_mod_structure` | 🟠 High | **P1** | 8+ |
| `_calculate_file_hash` | 🟠 High | **P1** | 5+ |
| `uninstall_mod` | 🟡 Medium | **P2** | 8+ |
| `disable_mod` | 🟡 Medium | **P2** | 6+ |
| `rollback_mod_installation` | 🟡 Medium | **P2** | 6+ |

---

## 🎯 **Key Testing Principles**

1. **Test failure paths first** - Most bugs occur in error handling
2. **Test edge cases** - Empty files, very large files, special characters
3. **Test transaction integrity** - Database should never be in inconsistent state
4. **Test cleanup** - Temp files and directories must be cleaned up
5. **Test cross-platform** - macOS-specific behavior (quarantine flags, permissions)
6. **Test concurrency** - Multiple installations happening simultaneously
7. **Test rollback** - Every operation should be reversible

---

## 🚨 **Critical Failure Scenarios to Test**

1. **Disk Space Exhaustion** - During extraction, backup, or file copy
2. **Permission Denied** - When creating directories or files
3. **Network Failures** - During Nexus API calls or downloads
4. **Database Transaction Failures** - Partial commits, rollbacks
5. **File System Errors** - Read-only filesystem, corrupted filesystem
6. **Concurrent Modifications** - Multiple processes modifying same files
7. **Invalid Archive Formats** - Malformed or malicious archives

---

## 📝 **Notes**

- All tests should use temporary directories and databases
- Mock external dependencies (Nexus API, file system)
- Test both success and failure paths
- Verify database state after each operation
- Check file system state matches database records
- Test cleanup happens even on exceptions
