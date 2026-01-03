# macOS Mod Manager - Improvement Roadmap

**Date:** December 31, 2024  
**Author:** Claude (AI Assistant)  
**Scope:** Comprehensive overhaul plan for deeper RED4ext/TweakXL/ArchiveXL integration

---

## Executive Summary

This document outlines a comprehensive plan to transform the macOS mod manager from a basic mod installer into a deeply integrated modding platform for Cyberpunk 2077 on macOS. The improvements focus on:

1. **Enhanced Dashboard** - Real-time system status with RED4ext integration
2. **Framework Management** - Install/update RED4ext, TweakXL, ArchiveXL from within the app
3. **Improved Observability** - Live logs, mod loading status, error detection
4. **Hardened Workflows** - Safer installations, rollbacks, conflict prevention
5. **Auto-Porting Research** - Feasibility of automated DLL→dylib conversion

---

## 1. Dashboard Overhaul

### Current State

The current dashboard provides:
- Basic stats (total mods, enabled mods, conflicts, disk usage)
- Quick actions (launch game, discover mods, install)
- System health indicators (placeholder)
- Activity feed

### Proposed Improvements

#### 1.1 RED4ext Integration Panel

```
┌─────────────────────────────────────────────────────────────────┐
│ 🔧 RED4ext Framework                                    [v1.27] │
├─────────────────────────────────────────────────────────────────┤
│ Status: ✅ Installed & Ready                                    │
│                                                                 │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│ │ RED4ext.dylib │ │ Frida Gadget│ │ Addresses   │                │
│ │ ✅ Present    │ │ ✅ Present   │ │ ✅ Loaded    │                │
│ └─────────────┘ └─────────────┘ └─────────────┘                │
│                                                                 │
│ Loaded Plugins (3):                                             │
│   • TweakXL.dylib        v1.11.3  ✅                            │
│   • ArchiveXL.dylib      v1.17.0  ✅                            │
│   • CustomPlugin.dylib   v0.1.0   ✅                            │
│                                                                 │
│ [View Logs] [Reinstall] [Check Updates]                         │
└─────────────────────────────────────────────────────────────────┘
```

#### 1.2 Real-Time Game Status

```
┌─────────────────────────────────────────────────────────────────┐
│ 🎮 Game Status                                                  │
├─────────────────────────────────────────────────────────────────┤
│ ● RUNNING (PID: 12345)                      Uptime: 2h 34m      │
│                                                                 │
│ Redscript:  ✅ Compiled (142 scripts)                           │
│ TweakDB:    ✅ 847 tweaks applied                               │
│ Archives:   ✅ 23 archives loaded                               │
│                                                                 │
│ Last Error: None                                                │
│ Memory:     4.2 GB / 16 GB                                      │
│                                                                 │
│ [▶ Launch] [⏹ Stop] [📋 View Output]                           │
└─────────────────────────────────────────────────────────────────┘
```

#### 1.3 Framework Health Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│ 🏥 Framework Health                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ RED4ext        ████████████████████ 100%  ✅ Healthy            │
│ TweakXL        ████████████████████ 100%  ✅ Healthy            │
│ ArchiveXL      ████████████████░░░░  80%  ⚠️ Update Available   │
│ Redscript      ████████████████████ 100%  ✅ Healthy            │
│ Input Loader   ░░░░░░░░░░░░░░░░░░░░   0%  ❌ Not Installed      │
│                                                                 │
│ [Install All] [Update All] [Verify Integrity]                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Framework Management System

### 2.1 Integrated Framework Installer

The mod manager should be able to install/update the macOS-ported frameworks:

```python
class FrameworkManager:
    """Manages RED4ext, TweakXL, ArchiveXL installations"""
    
    FRAMEWORKS = {
        'red4ext': {
            'repo': 'memaxo/RED4ext-macos',
            'asset_pattern': 'RED4ext-macos-*.zip',
            'install_path': 'red4ext/',
            'required_files': ['RED4ext.dylib', 'FridaGadget.dylib'],
        },
        'tweakxl': {
            'repo': 'memaxo/cp2077-tweak-xl-macos',
            'asset_pattern': 'TweakXL-*.zip',
            'install_path': 'red4ext/plugins/TweakXL/',
            'required_files': ['TweakXL.dylib'],
        },
        'archivexl': {
            'repo': 'memaxo/cp2077-archive-xl-macos',
            'asset_pattern': 'ArchiveXL-*.zip',
            'install_path': 'red4ext/plugins/ArchiveXL/',
            'required_files': ['ArchiveXL.dylib'],
        },
    }
    
    async def check_installation_status(self, framework: str) -> FrameworkStatus
    async def install_framework(self, framework: str, version: str = 'latest')
    async def update_framework(self, framework: str)
    async def verify_integrity(self, framework: str) -> IntegrityReport
    async def get_installed_version(self, framework: str) -> Optional[str]
    async def get_latest_version(self, framework: str) -> str
```

### 2.2 GitHub Release Integration

```python
class GitHubReleaseManager:
    """Fetches releases from GitHub for framework updates"""
    
    async def get_latest_release(self, repo: str) -> Release
    async def download_asset(self, repo: str, asset_name: str, dest: Path)
    async def compare_versions(self, installed: str, latest: str) -> int
```

### 2.3 One-Click Setup

New users should be able to set up their entire modding environment with one click:

```
┌─────────────────────────────────────────────────────────────────┐
│ 🚀 Quick Setup                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Welcome! Let's set up Cyberpunk 2077 modding on your Mac.       │
│                                                                 │
│ Game detected at:                                               │
│ ~/Library/Application Support/Steam/.../Cyberpunk 2077          │
│                                                                 │
│ ☑️ Install RED4ext (mod loader)                                 │
│ ☑️ Install TweakXL (tweaks)                                     │
│ ☑️ Install ArchiveXL (archives)                                 │
│ ☐ Install Input Loader (custom keybinds)                        │
│                                                                 │
│           [ 🚀 Start Setup ]                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Improved Observability

### 3.1 Live Log Viewer

Real-time log streaming from RED4ext and the game:

```python
class LogWatcher:
    """Watches RED4ext and game logs in real-time"""
    
    def __init__(self, game_path: Path):
        self.log_files = [
            game_path / "red4ext" / "logs" / "red4ext.log",
            game_path / "red4ext" / "logs" / "plugins.log",
        ]
    
    async def stream_logs(self) -> AsyncGenerator[LogEntry, None]:
        """Stream log entries as they appear"""
        
    def parse_log_entry(self, line: str) -> LogEntry:
        """Parse log line into structured entry"""
        
    async def get_recent_errors(self) -> List[LogEntry]:
        """Get recent error entries"""
```

### 3.2 Log Viewer UI

```html
<!-- Live log viewer component -->
<div class="log-viewer">
    <div class="log-header">
        <h3>📋 Live Logs</h3>
        <div class="log-filters">
            <button class="filter-btn active" data-level="all">All</button>
            <button class="filter-btn" data-level="error">Errors</button>
            <button class="filter-btn" data-level="warn">Warnings</button>
            <button class="filter-btn" data-level="info">Info</button>
        </div>
    </div>
    <div class="log-content" 
         hx-get="/api/logs/stream" 
         hx-trigger="every 1s"
         hx-swap="beforeend">
    </div>
</div>
```

### 3.3 Mod Loading Status

Track which mods are actually being loaded by the game:

```python
class ModLoadingTracker:
    """Tracks mod loading status from RED4ext logs"""
    
    async def get_loaded_plugins(self) -> List[PluginInfo]:
        """Get list of successfully loaded plugins"""
        
    async def get_failed_plugins(self) -> List[PluginError]:
        """Get list of plugins that failed to load"""
        
    async def get_redscript_status(self) -> RedscriptStatus:
        """Get redscript compilation status"""
        
    async def get_tweak_status(self) -> TweakStatus:
        """Get TweakXL status"""
```

### 3.4 Error Detection & Reporting

```python
class ErrorDetector:
    """Detects and categorizes errors from logs"""
    
    ERROR_PATTERNS = {
        'redscript_syntax': r'\[ERROR\].*\.reds.*line (\d+)',
        'plugin_load_fail': r'Could not load plugin.*Error: (.+)',
        'tweak_parse_error': r'TweakXL.*Failed to parse.*',
        'missing_dependency': r'Missing dependency: (.+)',
    }
    
    async def analyze_logs(self) -> ErrorReport:
        """Analyze logs and return categorized errors"""
        
    def suggest_fix(self, error: DetectedError) -> Optional[str]:
        """Suggest fix for common errors"""
```

---

## 4. Enhanced Launch System

### 4.1 Pre-Launch Checks

Run validation before launching the game:

```python
class PreLaunchValidator:
    """Validates mod setup before game launch"""
    
    async def validate(self) -> ValidationResult:
        checks = [
            self._check_red4ext_installed(),
            self._check_frida_gadget(),
            self._check_address_files(),
            self._check_plugins_loadable(),
            self._check_redscript_compilable(),
            self._check_tweak_syntax(),
            self._check_disk_space(),
        ]
        return await asyncio.gather(*checks)
```

### 4.2 Launch Profiles

Different launch configurations:

```python
class LaunchProfile:
    name: str
    enabled_mods: List[int]
    environment: Dict[str, str]
    pre_launch_commands: List[str]
    flags: List[str]  # e.g., -skipStartScreen
    
class LaunchManager:
    async def launch_with_profile(self, profile: LaunchProfile) -> LaunchResult
    async def launch_vanilla(self) -> LaunchResult  # No mods
    async def launch_minimal(self) -> LaunchResult  # Framework only
```

### 4.3 Output Capture & Display

```python
class GameOutputCapture:
    """Captures and displays game output"""
    
    async def capture_output(self, process: Process) -> AsyncGenerator[str, None]:
        """Stream stdout/stderr from game process"""
        
    def detect_crash(self, output: str) -> Optional[CrashInfo]:
        """Detect if game crashed and extract crash info"""
        
    def detect_redscript_error(self, output: str) -> Optional[RedscriptError]:
        """Detect redscript compilation errors"""
```

---

## 5. Hardened Workflows

### 5.1 Atomic Mod Installation

```python
class AtomicModInstaller:
    """Installs mods atomically with full rollback support"""
    
    async def install(self, mod_file: Path) -> InstallResult:
        """
        1. Create staging directory
        2. Extract to staging
        3. Validate all files
        4. Create backup of conflicting files
        5. Perform atomic swap
        6. Verify installation
        7. Clean up staging
        """
        
    async def rollback(self, install_id: int) -> RollbackResult:
        """Restore pre-installation state"""
```

### 5.2 Conflict Prevention

```python
class ConflictPrevention:
    """Prevents conflicts before they happen"""
    
    async def check_before_install(self, mod: ModFile) -> List[PotentialConflict]:
        """Check for potential conflicts before installing"""
        
    async def suggest_load_order(self, mods: List[Mod]) -> List[Mod]:
        """Suggest optimal load order to minimize conflicts"""
        
    def detect_incompatible_combination(self, mods: List[Mod]) -> List[Incompatibility]:
        """Detect known incompatible mod combinations"""
```

### 5.3 Backup System

```python
class BackupManager:
    """Comprehensive backup system"""
    
    async def create_full_backup(self) -> BackupInfo:
        """Backup entire mod setup"""
        
    async def create_incremental_backup(self) -> BackupInfo:
        """Backup only changed files"""
        
    async def restore_backup(self, backup_id: int) -> RestoreResult:
        """Restore from backup"""
        
    async def list_backups(self) -> List[BackupInfo]:
        """List available backups"""
```

### 5.4 Safe Mode

```python
class SafeMode:
    """Launch game without mods for troubleshooting"""
    
    async def enable(self) -> None:
        """Temporarily disable all mods"""
        
    async def disable(self) -> None:
        """Re-enable mods"""
        
    async def launch_safe(self) -> LaunchResult:
        """Launch game with mods disabled"""
```

---

## 6. Auto-Porting Research: DLL → dylib

### 6.1 Feasibility Analysis

**Question:** Can we automatically port Windows .dll mods to macOS .dylib?

**Answer:** **Partially feasible, but with significant limitations.**

#### What's Possible:

1. **Pure Data Mods** ✅
   - `.archive` files - Already work (just need correct path)
   - `.yaml`/`.yml` tweaks - Already work
   - `.reds` scripts - Already work
   - `.json` configs - Already work

2. **Simple Native Plugins** ⚠️ (Theoretically Possible)
   - If the plugin only uses RED4ext SDK calls
   - If it doesn't use Windows-specific APIs
   - Requires: Source code access + recompilation

3. **Source-Available Plugins** ⚠️
   - Can be recompiled with macOS toolchain
   - Requires fixing platform-specific code
   - Example: TweakXL was ported this way

#### What's NOT Possible:

1. **Binary DLL Translation** ❌
   - x64 Windows → ARM64 macOS requires:
     - Instruction set translation (x64 → ARM64)
     - ABI translation (Windows → macOS)
     - API translation (Win32 → POSIX/Cocoa)
   - This would essentially require a full emulator

2. **Closed-Source Plugins** ❌
   - No source code = no recompilation
   - Binary translation too complex

3. **Windows API-Dependent Plugins** ❌
   - Plugins using Win32, DirectX, etc.
   - Would need complete reimplementation

### 6.2 Assisted Porting Tool

Instead of auto-porting, we could create an **assisted porting tool**:

```python
class PortingAssistant:
    """Helps port RED4ext plugins to macOS"""
    
    async def analyze_dll(self, dll_path: Path) -> DLLAnalysis:
        """Analyze DLL to determine portability"""
        # Check for Windows API imports
        # Check for x64-specific code
        # Check for DirectX dependencies
        
    def generate_porting_guide(self, analysis: DLLAnalysis) -> PortingGuide:
        """Generate a guide for porting this plugin"""
        
    def estimate_effort(self, analysis: DLLAnalysis) -> EffortEstimate:
        """Estimate effort required to port"""
```

### 6.3 DLL Analysis Report

```
┌─────────────────────────────────────────────────────────────────┐
│ 📊 DLL Analysis: ExampleMod.dll                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Portability Score: 72/100 ⚠️                                    │
│                                                                 │
│ ✅ Uses RED4ext SDK                                              │
│ ✅ No DirectX dependencies                                       │
│ ⚠️ Uses Win32 file APIs (can be replaced)                       │
│ ⚠️ Uses Windows threading (can be replaced)                     │
│ ❌ Uses MiniHook (needs replacement with fishhook)              │
│                                                                 │
│ Estimated Porting Effort: Medium (2-4 hours)                    │
│                                                                 │
│ Required Changes:                                               │
│ 1. Replace MiniHook with fishhook                               │
│ 2. Replace CreateFile/ReadFile with POSIX equivalents           │
│ 3. Replace CreateThread with std::thread                        │
│                                                                 │
│ [📖 View Full Guide] [📧 Request Port]                          │
└─────────────────────────────────────────────────────────────────┘
```

### 6.4 Community Port Request System

```python
class PortRequestSystem:
    """System for requesting and tracking plugin ports"""
    
    async def request_port(self, nexus_mod_id: int, notes: str) -> PortRequest
    async def list_requests(self) -> List[PortRequest]
    async def vote_for_port(self, request_id: int) -> None
    async def mark_ported(self, request_id: int, repo_url: str) -> None
```

---

## 7. Enhanced Mod Discovery

### 7.1 Compatibility-Aware Search

```python
class CompatibilityAwareSearch:
    """Search Nexus with macOS compatibility filtering"""
    
    async def search(self, query: str, **filters) -> SearchResults:
        results = await self.nexus_api.search(query, **filters)
        
        for mod in results:
            mod.macos_status = await self._check_macos_compatibility(mod)
            
        return results
    
    async def _check_macos_compatibility(self, mod: NexusMod) -> MacOSStatus:
        """
        Returns:
        - NATIVE: macOS-native mod available
        - COMPATIBLE: Works with ported frameworks
        - INCOMPATIBLE: Requires Windows-only features
        - UNKNOWN: Manual verification needed
        """
```

### 7.2 Search UI Enhancements

```html
<!-- Enhanced search with compatibility indicators -->
<div class="search-filters">
    <label>
        <input type="checkbox" checked> ✅ Native macOS
    </label>
    <label>
        <input type="checkbox" checked> ⚠️ Requires frameworks
    </label>
    <label>
        <input type="checkbox"> ❌ Windows only
    </label>
</div>

<div class="search-results">
    {% for mod in results %}
    <div class="mod-card">
        <div class="compatibility-badge {{ mod.macos_status }}">
            {% if mod.macos_status == 'native' %}
                ✅ Native
            {% elif mod.macos_status == 'compatible' %}
                ⚠️ Needs RED4ext
            {% else %}
                ❌ Windows Only
            {% endif %}
        </div>
        <!-- rest of mod card -->
    </div>
    {% endfor %}
</div>
```

---

## 8. Implementation Roadmap

### Phase 1: Dashboard Enhancement (Week 1-2)

- [ ] Redesign dashboard layout
- [ ] Add RED4ext status panel
- [ ] Add framework health indicators
- [ ] Implement live log viewer
- [ ] Add game status monitoring

### Phase 2: Framework Management (Week 3-4)

- [ ] Implement FrameworkManager class
- [ ] Add GitHub release integration
- [ ] Create one-click setup wizard
- [ ] Add framework update checking

### Phase 3: Observability (Week 5-6)

- [ ] Implement LogWatcher
- [ ] Add error detection
- [ ] Create mod loading tracker
- [ ] Add crash detection

### Phase 4: Workflow Hardening (Week 7-8)

- [ ] Implement atomic installations
- [ ] Add conflict prevention
- [ ] Create backup system
- [ ] Implement safe mode

### Phase 5: Advanced Features (Week 9-10)

- [ ] DLL analysis tool
- [ ] Porting assistant
- [ ] Enhanced search
- [ ] Community features

---

## 9. Technical Specifications

### 9.1 New API Endpoints

```python
# Framework management
POST   /api/frameworks/{name}/install
POST   /api/frameworks/{name}/update
GET    /api/frameworks/{name}/status
GET    /api/frameworks/health

# Log streaming
GET    /api/logs/stream          # SSE endpoint
GET    /api/logs/recent
GET    /api/logs/errors

# Launch management
POST   /api/launch/start
POST   /api/launch/stop
GET    /api/launch/status
GET    /api/launch/output

# Backup
POST   /api/backup/create
GET    /api/backup/list
POST   /api/backup/{id}/restore

# DLL Analysis
POST   /api/analyze/dll
GET    /api/ports/requests
POST   /api/ports/request
```

### 9.2 New Database Tables

```sql
CREATE TABLE framework_installations (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    version VARCHAR(50),
    installed_at TIMESTAMP,
    install_path VARCHAR(500),
    status VARCHAR(20)
);

CREATE TABLE mod_load_history (
    id INTEGER PRIMARY KEY,
    mod_id INTEGER REFERENCES mods(id),
    loaded_at TIMESTAMP,
    success BOOLEAN,
    error_message TEXT
);

CREATE TABLE backups (
    id INTEGER PRIMARY KEY,
    created_at TIMESTAMP,
    backup_type VARCHAR(20),
    backup_path VARCHAR(500),
    size_bytes INTEGER,
    mod_count INTEGER
);

CREATE TABLE port_requests (
    id INTEGER PRIMARY KEY,
    nexus_mod_id INTEGER,
    requested_at TIMESTAMP,
    votes INTEGER DEFAULT 0,
    status VARCHAR(20),
    ported_repo VARCHAR(500)
);
```

---

## 10. Conclusion

This roadmap transforms the macOS mod manager from a basic installer into a comprehensive modding platform deeply integrated with RED4ext, TweakXL, and ArchiveXL. The key improvements are:

1. **Real-time Visibility** - See exactly what's happening with your mods
2. **Framework Management** - Install/update everything from one place
3. **Safer Operations** - Atomic installs, backups, rollbacks
4. **Better Discovery** - Find mods that actually work on macOS
5. **Developer Tools** - Assist with porting efforts

The auto-porting of DLLs is **not feasible** for binary translation, but the assisted porting tools can help the community port more mods to macOS.
