from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
import zipfile
import py7zr
import rarfile


@dataclass
class CompatibilityResult:
    compatible: bool
    severity: str  # critical, warning, info
    reason: str
    has_reds_files: bool = False
    has_dll_files: bool = False
    has_archivexl_refs: bool = False
    has_codeware_refs: bool = False
    has_red4ext_refs: bool = False
    has_cet_refs: bool = False
    incompatible_dependencies: List[str] = None
    
    def __post_init__(self):
        if self.incompatible_dependencies is None:
            self.incompatible_dependencies = []


class CompatibilityChecker:
    """Check mod compatibility with macOS"""
    
    INCOMPATIBLE_KEYWORDS = {
        'archivexl': ['archivexl', 'archive xl', 'archive_xl'],
        'codeware': ['codeware', 'code ware', 'code_ware'],
        'red4ext': ['red4ext', 'red4 ext', 'red4_ext'],
        'cet': ['cyber engine tweaks', 'cet', 'cyberenginetweaks'],
    }
    
    async def check_mod_file(self, mod_path: Path) -> CompatibilityResult:
        """Check mod archive for compatibility"""
        if not mod_path.exists():
            return CompatibilityResult(
                compatible=False,
                severity='critical',
                reason='Mod file does not exist'
            )
        
        # Extract and scan
        temp_dir = Path("/tmp") / f"mod_scan_{mod_path.stem}"
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # Extract archive
            await self._extract_archive(mod_path, temp_dir)
            
            # Scan files
            result = await self._scan_directory(temp_dir)
            
            return result
        finally:
            # Cleanup
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
    
    async def _extract_archive(self, archive_path: Path, dest: Path):
        """Extract archive to destination"""
        suffix = archive_path.suffix.lower()
        
        if suffix == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(dest)
        elif suffix in ['.7z', '.7zip']:
            with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                archive.extractall(path=dest)
        elif suffix == '.rar':
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(dest)
        else:
            raise ValueError(f"Unsupported archive format: {suffix}")
    
    async def _scan_directory(self, directory: Path) -> CompatibilityResult:
        """Scan directory for compatibility indicators"""
        has_reds = False
        has_dll = False
        incompatible_refs = []
        
        # Scan all files
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                # Check file extension
                if file_path.suffix == '.reds':
                    has_reds = True
                elif file_path.suffix == '.dll':
                    has_dll = True
                
                # Check file contents for keywords
                if file_path.suffix in ['.reds', '.txt', '.json', '.xml', '.md']:
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore').lower()
                        for dep_name, keywords in self.INCOMPATIBLE_KEYWORDS.items():
                            if any(kw in content for kw in keywords):
                                if dep_name not in incompatible_refs:
                                    incompatible_refs.append(dep_name)
                    except Exception:
                        pass
        
        # Generate result
        if has_dll:
            return CompatibilityResult(
                compatible=False,
                severity='critical',
                reason='Mod contains DLL files which are not supported on macOS',
                has_dll_files=True
            )
        
        if incompatible_refs:
            dep_names = ', '.join([d.title() for d in incompatible_refs])
            return CompatibilityResult(
                compatible=False,
                severity='critical',
                reason=f'Mod requires {dep_names} which is not compatible with macOS',
                has_archivexl_refs='archivexl' in incompatible_refs,
                has_codeware_refs='codeware' in incompatible_refs,
                has_red4ext_refs='red4ext' in incompatible_refs,
                has_cet_refs='cet' in incompatible_refs,
                incompatible_dependencies=incompatible_refs
            )
        
        if not has_reds:
            return CompatibilityResult(
                compatible=True,
                severity='warning',
                reason='Mod does not appear to contain redscript files',
                has_reds_files=False
            )
        
        return CompatibilityResult(
            compatible=True,
            severity='info',
            reason='Mod appears to be compatible with macOS',
            has_reds_files=True
        )
