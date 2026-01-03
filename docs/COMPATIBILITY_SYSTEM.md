# Compatibility Checking System Design

## Overview
Comprehensive system for detecting and managing mod compatibility on macOS, specifically for Cyberpunk 2077. This system has been updated to recognize **macOS-ported mod frameworks**.

## macOS-Ported Mod Frameworks

The following mod frameworks have been ported to macOS ARM64 and are **fully compatible**:

| Framework | Repository | Status |
|-----------|-----------|--------|
| **RED4ext** | https://github.com/memaxo/RED4ext-macos | ✅ Ported |
| **RED4ext.SDK** | https://github.com/memaxo/RED4ext.SDK-macos | ✅ Ported |
| **TweakXL** | https://github.com/memaxo/cp2077-tweak-xl-macos | ✅ Ported |
| **ArchiveXL** | https://github.com/memaxo/cp2077-archive-xl-macos | 🟡 In Progress |

## Compatibility Rules

### macOS-Compatible Mods
✅ **Allowed:**
- Pure redscript mods (`.reds` files only)
- Mods that modify `r6/scripts/` directory
- **RED4ext-based mods** with macOS `.dylib` plugins
- **TweakXL-based mods** with `.yaml`/`.yml` tweak files
- **ArchiveXL-based mods** with `.archive` files
- Mods requiring Redscript (version 0.5.29+)
- Mods with `.dylib` files in `red4ext/plugins/`
- Mods with tweak files in `r6/tweaks/`

### macOS-Incompatible Mods
❌ **Blocked:**
- Mods requiring **Cyber Engine Tweaks (CET)** (Windows-only, no macOS port)
- Mods requiring **Codeware** (Windows-only, no macOS port)
- Mods containing Windows `.dll` files (need macOS `.dylib` equivalents)
- Mods modifying Windows-specific executables (bin/x64/, dinput8.dll, version.dll)

## Mod Types and Installation Paths

| Mod Type | File Extensions | Installation Path |
|----------|----------------|-------------------|
| Redscript | `.reds` | `r6/scripts/` |
| RED4ext Plugin | `.dylib` | `red4ext/plugins/` |
| TweakXL Tweak | `.yaml`, `.yml` | `r6/tweaks/` |
| ArchiveXL Mod | `.archive` | `archive/pc/mod/` |

## Detection Methods

### 1. File-Based Detection

#### Scan Mod Archive Contents
```python
async def scan_mod_files(archive_path: Path) -> ModScanResult:
    """Scan mod archive for compatibility indicators"""
    indicators = {
        'has_reds_files': False,      # Redscript (.reds)
        'has_dll_files': False,        # Windows DLLs (incompatible)
        'has_dylib_files': False,      # macOS libraries (compatible!)
        'has_tweak_files': False,      # TweakXL (.yaml/.yml)
        'has_red4ext_plugin': False,   # RED4ext plugin
        'has_archive_files': False,    # ArchiveXL mods
        'ported_dependencies': [],     # Using ported frameworks
        'incompatible_dependencies': [], # Using Windows-only frameworks
    }
```

### 2. Ported Mod Detection

The system now recognizes macOS-ported mods as **compatible**:

```python
MACOS_PORTED_MODS = {
    'red4ext': {
        'keywords': ['red4ext', 'red4 ext', 'red4_ext'],
        'repo': 'https://github.com/memaxo/RED4ext-macos',
        'install_path': 'red4ext/',
        'compatible': True
    },
    'tweakxl': {
        'keywords': ['tweakxl', 'tweak xl', 'tweak_xl'],
        'repo': 'https://github.com/memaxo/cp2077-tweak-xl-macos',
        'install_path': 'red4ext/plugins/TweakXL/',
        'compatible': True
    },
    'archivexl': {
        'keywords': ['archivexl', 'archive xl', 'archive_xl'],
        'repo': 'https://github.com/memaxo/cp2077-archive-xl-macos',
        'install_path': 'red4ext/plugins/ArchiveXL/',
        'compatible': True
    },
}
```

### 3. Truly Incompatible Mods

Only these are flagged as incompatible:

```python
INCOMPATIBLE_KEYWORDS = {
    'codeware': ['codeware', 'code ware', 'code_ware'],
    'cet': ['cyber engine tweaks', 'cet', 'cyberenginetweaks'],
}
```

## Compatibility Checking Flow

### Pre-Installation Check
```python
async def check_mod_compatibility(mod_file: Path) -> CompatibilityReport:
    """Comprehensive compatibility check"""
    
    report = CompatibilityReport()
    
    # 1. File-based scan
    scan_result = await scan_mod_files(mod_file)
    
    # 2. Check for Windows DLLs (incompatible)
    if scan_result.has_dll_files:
        return incompatible("Contains Windows DLL files")
    
    # 3. Check for truly incompatible dependencies (CET, Codeware)
    if scan_result.incompatible_dependencies:
        return incompatible(f"Requires {scan_result.incompatible_dependencies}")
    
    # 4. Check for macOS-native content (compatible!)
    if scan_result.has_dylib_files:
        return compatible("Contains macOS-native RED4ext plugin")
    
    if scan_result.has_tweak_files:
        return compatible("Contains TweakXL tweak files")
    
    if scan_result.has_reds_files:
        return compatible("Pure redscript mod")
    
    return unknown("Manual verification recommended")
```

## Installation Paths

The mod manager uses these paths for different mod types:

```python
# Configuration (config.py)
default_mod_path = "r6/scripts"           # Redscript mods
red4ext_plugins_path = "red4ext/plugins"  # RED4ext plugins (.dylib)
tweakxl_tweaks_path = "r6/tweaks"         # TweakXL tweaks (.yaml/.yml)
archivexl_mods_path = "archive/pc/mod"    # ArchiveXL mods (.archive)
```

## User Interface Integration

### Compatibility Status Display

```html
<!-- GREEN: Compatible with ported framework -->
<div class="compatibility-status compatible">
    <span class="status-icon">✅</span>
    <span class="status-text">Compatible - Uses TweakXL (macOS ported)</span>
    <a href="https://github.com/memaxo/cp2077-tweak-xl-macos">View Port</a>
</div>

<!-- RED: Incompatible (CET/Codeware) -->
<div class="compatibility-status incompatible">
    <span class="status-icon">❌</span>
    <span class="status-text">Incompatible - Requires Cyber Engine Tweaks (no macOS port)</span>
</div>

<!-- YELLOW: Unknown -->
<div class="compatibility-status warning">
    <span class="status-icon">⚠️</span>
    <span class="status-text">Unknown compatibility - Manual check recommended</span>
</div>
```

## Database Schema for Compatibility

### Updated Compatibility Result
```python
@dataclass
class CompatibilityResult:
    compatible: bool
    severity: str  # 'critical', 'warning', 'info'
    reason: str
    
    # File types detected
    has_reds_files: bool = False
    has_dll_files: bool = False
    has_dylib_files: bool = False      # NEW: macOS native libraries
    has_tweak_files: bool = False      # NEW: TweakXL tweaks
    has_red4ext_plugin: bool = False   # NEW: RED4ext plugins
    
    # Dependencies
    has_archivexl_refs: bool = False   # Now COMPATIBLE
    has_red4ext_refs: bool = False     # Now COMPATIBLE
    has_tweakxl_refs: bool = False     # Now COMPATIBLE
    has_codeware_refs: bool = False    # INCOMPATIBLE
    has_cet_refs: bool = False         # INCOMPATIBLE
    
    # Dependency lists
    ported_dependencies: List[str]      # NEW: macOS-ported deps
    incompatible_dependencies: List[str]
```

## Framework Installation

For mods that require the base frameworks, users need to install them first:

### Installing RED4ext (macOS)
```bash
# Clone and build RED4ext-macos
git clone --recursive https://github.com/memaxo/RED4ext-macos.git
cd RED4ext-macos
./scripts/macos_install.sh
```

### Installing TweakXL (macOS)
```bash
# Download from releases
# Extract TweakXL.dylib to: <game>/red4ext/plugins/TweakXL/
```

### Installing ArchiveXL (macOS)
```bash
# (In progress - check repository for updates)
# Extract ArchiveXL.dylib to: <game>/red4ext/plugins/ArchiveXL/
```

## Testing Compatibility

### Unit Tests
```python
async def test_red4ext_mod_compatible():
    """RED4ext-based mods are now compatible on macOS"""
    mod_file = Path("test_mods/red4ext_mod.zip")
    result = await check_compatibility(mod_file)
    
    assert result.compatible == True
    assert result.has_red4ext_refs == True
    assert 'red4ext' in result.ported_dependencies

async def test_tweakxl_mod_compatible():
    """TweakXL-based mods are now compatible on macOS"""
    mod_file = Path("test_mods/tweakxl_mod.zip")
    result = await check_compatibility(mod_file)
    
    assert result.compatible == True
    assert result.has_tweakxl_refs == True
    assert 'tweakxl' in result.ported_dependencies

async def test_cet_mod_incompatible():
    """CET-based mods remain incompatible"""
    mod_file = Path("test_mods/cet_mod.zip")
    result = await check_compatibility(mod_file)
    
    assert result.compatible == False
    assert result.has_cet_refs == True
    assert 'cet' in result.incompatible_dependencies
```

## Configuration

### Settings
```python
class CompatibilitySettings(BaseModel):
    strict_mode: bool = True           # Block truly incompatible mods
    auto_scan: bool = True             # Auto-scan on install
    show_warnings: bool = True         # Show compatibility warnings
    allow_override: bool = False       # Allow user to override
    check_database: bool = True        # Check compatibility database
    check_metadata: bool = True        # Check mod metadata
    check_files: bool = True           # Scan mod files
    
    # macOS mod repositories
    macos_red4ext_repo: str = "https://github.com/memaxo/RED4ext-macos"
    macos_tweakxl_repo: str = "https://github.com/memaxo/cp2077-tweak-xl-macos"
    macos_archivexl_repo: str = "https://github.com/memaxo/cp2077-archive-xl-macos"
```

## Changelog

### 2024-12-31
- **MAJOR**: RED4ext, TweakXL, and ArchiveXL are now marked as **COMPATIBLE** on macOS
- Added `MACOS_PORTED_MODS` dictionary with ported framework information
- Added `.dylib` file detection for RED4ext plugins
- Added `.yaml`/`.yml` detection for TweakXL tweaks
- Added `ported_dependencies` field to `CompatibilityResult`
- Updated installation paths for all mod types
- Removed RED4ext, TweakXL, ArchiveXL from `INCOMPATIBLE_KEYWORDS`
- Only CET and Codeware remain truly incompatible (no macOS ports)
