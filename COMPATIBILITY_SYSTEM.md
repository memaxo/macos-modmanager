# Compatibility Checking System Design

## Overview
Comprehensive system for detecting and preventing installation of incompatible mods on macOS, specifically for Cyberpunk 2077.

## Compatibility Rules

### macOS-Compatible Mods
✅ **Allowed:**
- Pure redscript mods (`.reds` files only)
- Mods that only modify `r6/scripts/` directory
- Mods with no external dependencies
- Mods requiring only redscript (version 0.5.29+)

### macOS-Incompatible Mods
❌ **Blocked:**
- Mods requiring **ArchiveXL** (requires RED4ext DLL)
- Mods requiring **Codeware** (requires RED4ext DLL)
- Mods requiring **RED4ext** (Windows-only DLL loader)
- Mods requiring **Cyber Engine Tweaks (CET)** (Windows-only)
- Mods containing `.dll` files
- Mods modifying game executables
- Mods requiring TweakXL (if it requires RED4ext)

## Detection Methods

### 1. File-Based Detection

#### Scan Mod Archive Contents
```python
async def scan_mod_files(archive_path: Path) -> ModScanResult:
    """Scan mod archive for compatibility indicators"""
    indicators = {
        'has_reds_files': False,
        'has_dll_files': False,
        'has_archivexl_refs': False,
        'has_codeware_refs': False,
        'has_red4ext_refs': False,
        'has_cet_refs': False,
        'file_structure': {}
    }
    
    with zipfile.ZipFile(archive_path) as zip_file:
        for file_info in zip_file.filelist:
            file_path = Path(file_info.filename)
            
            # Check for .reds files (compatible)
            if file_path.suffix == '.reds':
                indicators['has_reds_files'] = True
            
            # Check for .dll files (incompatible)
            if file_path.suffix == '.dll':
                indicators['has_dll_files'] = True
            
            # Check file contents for dependency references
            if file_path.suffix in ['.reds', '.txt', '.json', '.xml']:
                content = zip_file.read(file_info)
                content_str = content.decode('utf-8', errors='ignore').lower()
                
                # Check for ArchiveXL references
                if any(keyword in content_str for keyword in [
                    'archivexl', 'archive xl', 'archive_xl'
                ]):
                    indicators['has_archivexl_refs'] = True
                
                # Check for Codeware references
                if any(keyword in content_str for keyword in [
                    'codeware', 'code ware', 'code_ware'
                ]):
                    indicators['has_codeware_refs'] = True
                
                # Check for RED4ext references
                if any(keyword in content_str for keyword in [
                    'red4ext', 'red4 ext', 'red4_ext'
                ]):
                    indicators['has_red4ext_refs'] = True
                
                # Check for CET references
                if any(keyword in content_str for keyword in [
                    'cyber engine tweaks', 'cet', 'cyberenginetweaks'
                ]):
                    indicators['has_cet_refs'] = True
            
            # Track file structure
            indicators['file_structure'][str(file_path)] = {
                'size': file_info.file_size,
                'is_dir': file_info.is_dir()
            }
    
    return ModScanResult(**indicators)
```

### 2. Metadata-Based Detection

#### Parse Mod Description
```python
async def parse_mod_metadata(nexus_mod_id: int) -> ModMetadata:
    """Fetch and parse mod metadata from Nexus Mods"""
    mod_data = await nexus_api.get_mod(nexus_mod_id)
    
    # Extract dependencies from description
    description = mod_data.get('description', '')
    requirements = extract_requirements(description)
    
    # Check requirements section
    requirements_section = mod_data.get('requirements', [])
    
    return ModMetadata(
        mod_id=nexus_mod_id,
        name=mod_data['name'],
        description=description,
        requirements=requirements,
        requirements_section=requirements_section,
        files=mod_data.get('files', [])
    )

def extract_requirements(description: str) -> List[str]:
    """Extract dependency names from mod description"""
    requirements = []
    
    # Common patterns
    patterns = [
        r'requires?\s+([A-Za-z0-9\s]+)',
        r'dependencies?:\s*([^\n]+)',
        r'needs?\s+([A-Za-z0-9\s]+)',
    ]
    
    description_lower = description.lower()
    
    # Check for known incompatible dependencies
    incompatible_keywords = [
        'archivexl', 'codeware', 'red4ext', 
        'cyber engine tweaks', 'cet', 'tweakxl'
    ]
    
    for keyword in incompatible_keywords:
        if keyword in description_lower:
            requirements.append(keyword.title())
    
    return requirements
```

### 3. Database-Based Detection

#### Query Compatibility Database
```python
async def check_compatibility_database(
    mod_id: int, 
    nexus_mod_id: int = None
) -> CompatibilityResult:
    """Check mod compatibility against database"""
    
    # Check for explicit compatibility rules
    rules = await db.query(
        select(CompatibilityRule)
        .where(
            or_(
                CompatibilityRule.mod_id == mod_id,
                CompatibilityRule.nexus_mod_id == nexus_mod_id
            )
        )
        .where(CompatibilityRule.platform == 'macos')
    )
    
    # Check for incompatible dependencies
    incompatible_deps = await db.query(
        select(ModDependency)
        .where(ModDependency.mod_id == mod_id)
        .where(ModDependency.dependency_type == 'incompatible')
        .where(
            ModDependency.dependency_name.in_([
                'ArchiveXL', 'Codeware', 'RED4ext', 'CET', 'TweakXL'
            ])
        )
    )
    
    return CompatibilityResult(
        is_compatible=len(incompatible_deps) == 0,
        rules=rules,
        incompatible_dependencies=incompatible_deps
    )
```

## Compatibility Checking Flow

### Pre-Installation Check
```python
async def check_mod_compatibility(
    mod_file: Path,
    nexus_mod_id: int = None
) -> CompatibilityReport:
    """Comprehensive compatibility check before installation"""
    
    report = CompatibilityReport()
    
    # 1. File-based scan
    scan_result = await scan_mod_files(mod_file)
    report.add_scan_result(scan_result)
    
    # 2. Metadata check (if Nexus mod)
    if nexus_mod_id:
        metadata = await parse_mod_metadata(nexus_mod_id)
        report.add_metadata(metadata)
    
    # 3. Database check
    db_result = await check_compatibility_database(
        mod_id=None,  # Not installed yet
        nexus_mod_id=nexus_mod_id
    )
    report.add_database_result(db_result)
    
    # 4. Dependency check
    dependencies = await resolve_dependencies(
        scan_result, metadata, db_result
    )
    report.add_dependencies(dependencies)
    
    # 5. Conflict check (with installed mods)
    conflicts = await check_conflicts(scan_result)
    report.add_conflicts(conflicts)
    
    # 6. Generate compatibility verdict
    verdict = generate_verdict(report)
    report.set_verdict(verdict)
    
    return report

def generate_verdict(report: CompatibilityReport) -> CompatibilityVerdict:
    """Generate final compatibility verdict"""
    
    # Critical incompatibilities
    if report.has_dll_files:
        return CompatibilityVerdict(
            compatible=False,
            severity='critical',
            reason='Mod contains DLL files which are not supported on macOS'
        )
    
    if report.has_archivexl_refs:
        return CompatibilityVerdict(
            compatible=False,
            severity='critical',
            reason='Mod requires ArchiveXL which is not compatible with macOS'
        )
    
    if report.has_codeware_refs:
        return CompatibilityVerdict(
            compatible=False,
            severity='critical',
            reason='Mod requires Codeware which is not compatible with macOS'
        )
    
    if report.has_red4ext_refs:
        return CompatibilityVerdict(
            compatible=False,
            severity='critical',
            reason='Mod requires RED4ext which is not compatible with macOS'
        )
    
    if report.has_cet_refs:
        return CompatibilityVerdict(
            compatible=False,
            severity='critical',
            reason='Mod requires Cyber Engine Tweaks (CET) which is not compatible with macOS'
        )
    
    # Warnings
    if not report.has_reds_files:
        return CompatibilityVerdict(
            compatible=True,
            severity='warning',
            reason='Mod does not appear to contain redscript files. May not be a script mod.'
        )
    
    # Compatible
    return CompatibilityVerdict(
        compatible=True,
        severity='info',
        reason='Mod appears to be compatible with macOS'
    )
```

## Protection Mechanisms

### 1. Installation Blocking

#### Strict Mode (Default)
```python
async def install_mod_with_protection(
    mod_file: Path,
    game_path: Path,
    strict_mode: bool = True
) -> InstallationResult:
    """Install mod with compatibility protection"""
    
    # Run compatibility check
    report = await check_mod_compatibility(mod_file)
    
    # Block installation if incompatible
    if not report.verdict.compatible and strict_mode:
        raise CompatibilityError(
            f"Cannot install mod: {report.verdict.reason}",
            report=report
        )
    
    # Warn but allow if not strict mode
    if not report.verdict.compatible and not strict_mode:
        logger.warning(f"Installing incompatible mod: {report.verdict.reason}")
        # Show user confirmation dialog
    
    # Proceed with installation
    return await install_mod(mod_file, game_path)
```

### 2. Runtime Protection

#### File System Monitoring
```python
class ModProtectionMonitor:
    """Monitor game directory for unauthorized changes"""
    
    def __init__(self, game_path: Path):
        self.game_path = game_path
        self.observer = Observer()
        self.protected_files = set()
    
    def start_monitoring(self):
        """Start monitoring game directory"""
        handler = ModFileHandler(self)
        self.observer.schedule(
            handler, 
            str(self.game_path / "r6"), 
            recursive=True
        )
        self.observer.start()
    
    def on_file_modified(self, file_path: Path):
        """Handle file modification events"""
        # Check if file is protected
        if file_path in self.protected_files:
            logger.warning(f"Protected file modified: {file_path}")
            # Optionally restore from backup
    
    def protect_file(self, file_path: Path):
        """Add file to protection list"""
        self.protected_files.add(file_path)
```

### 3. Collection Protection

#### Collection Pre-Installation Scan
```python
async def scan_collection_compatibility(
    collection_id: str
) -> CollectionCompatibilityReport:
    """Scan entire collection for compatibility"""
    
    collection = await fetch_collection(collection_id)
    report = CollectionCompatibilityReport()
    
    for mod_entry in collection.mods:
        mod_compatibility = await check_mod_compatibility(
            mod_file=None,  # Not downloaded yet
            nexus_mod_id=mod_entry.nexus_mod_id
        )
        
        report.add_mod_result(mod_entry, mod_compatibility)
    
    # Generate collection-level verdict
    if report.has_incompatible_mods:
        report.verdict = CollectionVerdict(
            installable=False,
            incompatible_count=report.incompatible_count,
            compatible_count=report.compatible_count
        )
    else:
        report.verdict = CollectionVerdict(
            installable=True,
            incompatible_count=0,
            compatible_count=report.compatible_count
        )
    
    return report
```

## User Interface Integration

### Compatibility Warning UI
```html
<!-- HTMX-compatible compatibility warning -->
<div id="compatibility-warning" class="hidden">
    <div class="alert alert-warning">
        <h3>⚠️ Compatibility Warning</h3>
        <div id="warning-details"></div>
        <div class="actions">
            <button 
                hx-post="/api/mods/install" 
                hx-include="#mod-form"
                class="btn-danger">
                Install Anyway (Not Recommended)
            </button>
            <button 
                onclick="document.getElementById('compatibility-warning').classList.add('hidden')"
                class="btn-secondary">
                Cancel
            </button>
        </div>
    </div>
</div>

<!-- Compatibility check result -->
<div id="compatibility-result" 
     hx-get="/api/compatibility/check/{mod_id}"
     hx-trigger="load">
    <div class="compatibility-status">
        <span class="status-icon">⏳</span>
        <span class="status-text">Checking compatibility...</span>
    </div>
</div>
```

### Compatibility Report Display
```html
<!-- Detailed compatibility report -->
<div class="compatibility-report">
    <h2>Compatibility Report</h2>
    
    <div class="verdict verdict-{{ report.verdict.severity }}">
        <strong>{{ report.verdict.reason }}</strong>
    </div>
    
    <div class="details">
        <h3>Scan Results</h3>
        <ul>
            <li>Redscript Files: {{ report.has_reds_files }}</li>
            <li>DLL Files: {{ report.has_dll_files }}</li>
            <li>ArchiveXL References: {{ report.has_archivexl_refs }}</li>
            <li>Codeware References: {{ report.has_codeware_refs }}</li>
        </ul>
        
        <h3>Dependencies</h3>
        <ul>
            {% for dep in report.dependencies %}
            <li class="dep-{{ dep.status }}">
                {{ dep.name }}: {{ dep.status }}
            </li>
            {% endfor %}
        </ul>
        
        <h3>Conflicts</h3>
        <ul>
            {% for conflict in report.conflicts %}
            <li class="conflict-{{ conflict.severity }}">
                {{ conflict.description }}
            </li>
            {% endfor %}
        </ul>
    </div>
</div>
```

## Database Schema for Compatibility

### Compatibility Rules Table
```sql
CREATE TABLE compatibility_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mod_id INTEGER,
    nexus_mod_id INTEGER,
    rule_type TEXT NOT NULL,  -- 'compatible', 'incompatible', 'requires', 'conflicts_with'
    target_mod_id INTEGER,
    target_nexus_mod_id INTEGER,
    target_dependency TEXT,  -- e.g., 'ArchiveXL', 'Codeware'
    platform TEXT,  -- 'macos', 'windows', 'linux', NULL for all
    game_version_min TEXT,
    game_version_max TEXT,
    severity TEXT DEFAULT 'warning',  -- 'critical', 'warning', 'info'
    description TEXT,
    source TEXT DEFAULT 'user',  -- 'user', 'community', 'official', 'auto'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verified BOOLEAN DEFAULT 0,
    FOREIGN KEY (mod_id) REFERENCES mods(id) ON DELETE CASCADE,
    FOREIGN KEY (target_mod_id) REFERENCES mods(id) ON DELETE CASCADE
);
```

### Auto-Generated Rules
```python
async def auto_generate_compatibility_rules(mod_id: int):
    """Auto-generate compatibility rules based on mod scan"""
    
    mod = await get_mod(mod_id)
    scan_result = await scan_mod_files(mod.install_path)
    
    rules = []
    
    # Generate incompatible rules
    if scan_result.has_archivexl_refs:
        rules.append({
            'mod_id': mod_id,
            'rule_type': 'incompatible',
            'target_dependency': 'ArchiveXL',
            'platform': 'macos',
            'severity': 'critical',
            'description': 'Mod requires ArchiveXL which is not compatible with macOS',
            'source': 'auto'
        })
    
    # Save rules to database
    for rule_data in rules:
        await create_compatibility_rule(rule_data)
```

## Testing Compatibility

### Unit Tests
```python
async def test_archivexl_detection():
    """Test detection of ArchiveXL dependencies"""
    mod_file = Path("test_mods/archivexl_mod.zip")
    scan_result = await scan_mod_files(mod_file)
    
    assert scan_result.has_archivexl_refs == True
    assert scan_result.compatible == False

async def test_redscript_only_mod():
    """Test detection of pure redscript mod"""
    mod_file = Path("test_mods/redscript_only.zip")
    scan_result = await scan_mod_files(mod_file)
    
    assert scan_result.has_reds_files == True
    assert scan_result.has_dll_files == False
    assert scan_result.compatible == True
```

## Configuration

### Settings
```python
class CompatibilitySettings(BaseModel):
    strict_mode: bool = True  # Block incompatible mods
    auto_scan: bool = True  # Auto-scan on install
    show_warnings: bool = True  # Show compatibility warnings
    allow_override: bool = False  # Allow user to override
    check_database: bool = True  # Check compatibility database
    check_metadata: bool = True  # Check mod metadata
    check_files: bool = True  # Scan mod files
```

## Future Enhancements

1. **Machine Learning**: Train model to detect compatibility
2. **Community Reports**: User-submitted compatibility reports
3. **Auto-Updates**: Auto-update compatibility database
4. **Smart Suggestions**: Suggest compatible alternatives
5. **Version-Specific Rules**: Game version-specific compatibility
