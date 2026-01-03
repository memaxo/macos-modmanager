from pathlib import Path
from typing import List, Dict, Optional, Literal, Any
from dataclasses import dataclass, field
import zipfile
import py7zr
import rarfile
import re
import asyncio


SeverityType = Literal["critical", "warning", "info"]


@dataclass
class CompatibilityResult:
    compatible: bool
    severity: SeverityType
    reason: str
    has_reds_files: bool = False
    has_dll_files: bool = False
    has_dylib_files: bool = False  # macOS native libraries
    has_archivexl_refs: bool = False
    has_codeware_refs: bool = False
    has_red4ext_refs: bool = False
    has_cet_refs: bool = False
    has_tweakxl_refs: bool = False
    modifies_executable: bool = False
    has_r6_scripts_only: bool = False
    has_red4ext_plugin: bool = False  # Native RED4ext plugin (.dylib)
    has_tweak_files: bool = False  # TweakXL .yaml/.yml files
    incompatible_dependencies: List[str] = field(default_factory=list)
    ported_dependencies: List[str] = field(default_factory=list)  # macOS-ported deps


class CompatibilityChecker:
    """Check mod compatibility with macOS
    
    Updated for macOS-ported mods:
    - RED4ext: https://github.com/memaxo/RED4ext-macos
    - TweakXL: https://github.com/memaxo/cp2077-tweak-xl-macos
    - RED4ext.SDK: https://github.com/memaxo/RED4ext.SDK-macos
    """
    
    # Mods that have been ported to macOS and ARE compatible
    MACOS_PORTED_MODS: Dict[str, Dict[str, Any]] = {
        'red4ext': {
            'keywords': ['red4ext', 'red4 ext', 'red4_ext'],
            'repo': 'https://github.com/memaxo/RED4ext-macos',
            'install_path': 'red4ext/',
            'compatible': True,
            'note': 'RED4ext has been ported to macOS ARM64'
        },
        'tweakxl': {
            'keywords': ['tweakxl', 'tweak xl', 'tweak_xl'],
            'repo': 'https://github.com/memaxo/cp2077-tweak-xl-macos',
            'install_path': 'red4ext/plugins/TweakXL/',
            'compatible': True,
            'note': 'TweakXL has been ported to macOS ARM64'
        },
        'archivexl': {
            'keywords': ['archivexl', 'archive xl', 'archive_xl'],
            'repo': 'https://github.com/memaxo/cp2077-archive-xl-macos',
            'install_path': 'red4ext/plugins/ArchiveXL/',
            'compatible': True,  # Porting in progress
            'note': 'ArchiveXL macOS port in progress'
        },
    }
    
    # Mods that are still Windows-only (NOT ported yet)
    INCOMPATIBLE_KEYWORDS: Dict[str, List[str]] = {
        'codeware': ['codeware', 'code ware', 'code_ware'],
        'cet': ['cyber engine tweaks', 'cet', 'cyberenginetweaks'],
    }
    
    def extract_requirements_from_text(self, text: str) -> tuple[List[str], List[str]]:
        """Extract dependency names from mod description/text
        
        Returns:
            Tuple of (incompatible_deps, ported_deps)
        """
        if not text:
            return [], []
        
        incompatible = []
        ported = []
        text_lower = text.lower()
        
        # Check for macOS-ported dependencies (these are NOW compatible!)
        for dep_name, dep_info in self.MACOS_PORTED_MODS.items():
            if any(kw in text_lower for kw in dep_info['keywords']):
                if dep_name not in ported:
                    ported.append(dep_name)
        
        # Check for known incompatible dependencies (still Windows-only)
        for dep_name, keywords in self.INCOMPATIBLE_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                if dep_name not in incompatible:
                    incompatible.append(dep_name)
        
        # Also check for common patterns
        patterns = [
            r'requires?\s+([A-Za-z0-9\s]+)',
            r'dependencies?:\s*([^\n]+)',
            r'needs?\s+([A-Za-z0-9\s]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                match_text = match if isinstance(match, str) else match[0] if match else ''
                
                # Check ported mods
                for dep_name, dep_info in self.MACOS_PORTED_MODS.items():
                    if any(kw in match_text for kw in dep_info['keywords']):
                        if dep_name not in ported:
                            ported.append(dep_name)
                
                # Check incompatible mods
                for dep_name, keywords in self.INCOMPATIBLE_KEYWORDS.items():
                    if any(kw in match_text for kw in keywords):
                        if dep_name not in incompatible:
                            incompatible.append(dep_name)
        
        return incompatible, ported
    
    async def check_nexus_metadata(
        self, 
        nexus_api_client,
        game_domain: str,
        nexus_mod_id: int
    ) -> CompatibilityResult:
        """Check compatibility based on Nexus Mods metadata
        
        Now recognizes macOS-ported mods (RED4ext, TweakXL, ArchiveXL) as compatible.
        """
        try:
            # Get mod information
            mod_data = await nexus_api_client.get_mod(game_domain, nexus_mod_id)
            description = mod_data.get('description', '') or mod_data.get('summary', '')
            
            # Get requirements from GraphQL API
            requirements = await nexus_api_client.get_mod_requirements(nexus_mod_id, game_domain)
            
            # Extract dependencies from description
            incompatible_refs, ported_refs = self.extract_requirements_from_text(description)
            
            # Check requirements list for dependencies
            for req in requirements:
                req_name = req.get('name', '').lower()
                
                # Check for ported mods (now compatible!)
                for dep_name, dep_info in self.MACOS_PORTED_MODS.items():
                    if any(kw in req_name for kw in dep_info['keywords']):
                        if dep_name not in ported_refs:
                            ported_refs.append(dep_name)
                
                # Check for truly incompatible mods
                for dep_name, keywords in self.INCOMPATIBLE_KEYWORDS.items():
                    if any(kw in req_name for kw in keywords):
                        if dep_name not in incompatible_refs:
                            incompatible_refs.append(dep_name)
            
            # Check if redscript is mentioned (compatible)
            has_redscript_mention = any(
                kw in description.lower() 
                for kw in ['redscript', 'red script', '.reds']
            )
            
            # Only truly incompatible mods (CET, Codeware) block installation
            if incompatible_refs:
                dep_names = ', '.join([d.title() for d in incompatible_refs])
                return CompatibilityResult(
                    compatible=False,
                    severity='critical',
                    reason=f'Mod requires {dep_names} which is not compatible with macOS (no macOS port available)',
                    has_codeware_refs='codeware' in incompatible_refs,
                    has_cet_refs='cet' in incompatible_refs,
                    incompatible_dependencies=incompatible_refs,
                    ported_dependencies=ported_refs
                )
            
            # If mod uses ported dependencies, it's compatible!
            if ported_refs:
                ported_names = ', '.join([d.title() for d in ported_refs])
                return CompatibilityResult(
                    compatible=True,
                    severity='info',
                    reason=f'Mod uses {ported_names} which has been ported to macOS',
                    has_red4ext_refs='red4ext' in ported_refs,
                    has_tweakxl_refs='tweakxl' in ported_refs,
                    has_archivexl_refs='archivexl' in ported_refs,
                    has_reds_files=has_redscript_mention,
                    ported_dependencies=ported_refs
                )
            
            # If no incompatible refs found and redscript is mentioned, likely compatible
            if has_redscript_mention:
                return CompatibilityResult(
                    compatible=True,
                    severity='info',
                    reason='Mod appears compatible with macOS (redscript-only mod based on Nexus Mods metadata)',
                    has_reds_files=True
                )
            
            # Unknown compatibility status
            return CompatibilityResult(
                compatible=True,
                severity='warning',
                reason='Could not determine compatibility from Nexus Mods metadata. File scan recommended.',
                has_reds_files=False
            )
            
        except Exception as e:
            # If metadata check fails, return unknown status
            return CompatibilityResult(
                compatible=True,
                severity='warning',
                reason=f'Could not check Nexus Mods metadata: {str(e)}. File scan recommended.',
                has_reds_files=False
            )
    
    async def check_mod_comprehensive(
        self,
        mod_path: Optional[Path] = None,
        nexus_api_client = None,
        game_domain: str = "cyberpunk2077",
        nexus_mod_id: Optional[int] = None
    ) -> CompatibilityResult:
        """Comprehensive compatibility check combining file scan and metadata check
        
        This method combines both file-based detection and Nexus Mods metadata
        checking for the most accurate compatibility assessment.
        """
        results: List[CompatibilityResult] = []
        
        # 1. File-based check (if mod file provided)
        if mod_path and mod_path.exists():
            file_result = await self.check_mod_file(mod_path)
            results.append(file_result)
        
        # 2. Metadata check (if Nexus mod ID provided)
        if nexus_mod_id and nexus_api_client:
            try:
                metadata_result = await self.check_nexus_metadata(
                    nexus_api_client, game_domain, nexus_mod_id
                )
                results.append(metadata_result)
            except Exception:
                pass  # Metadata check is optional
        
        # Combine results - if any check says incompatible, mod is incompatible
        if not results:
            return CompatibilityResult(
                compatible=True,
                severity='warning',
                reason='No compatibility data available. Manual verification recommended.'
            )
        
        # Find most severe result
        incompatible_results = [r for r in results if not r.compatible]
        if incompatible_results:
            # Return the first incompatible result (they should all have similar reasons)
            return incompatible_results[0]
        
        # All checks passed or were warnings
        compatible_results = [r for r in results if r.compatible]
        if compatible_results:
            # Return the most informative compatible result
            # Prefer results with redscript files detected
            reds_results = [r for r in compatible_results if r.has_reds_files]
            if reds_results:
                return reds_results[0]
            return compatible_results[0]
        
        # Fallback
        return results[0]
    
    async def batch_check_compatibility(
        self,
        mod_data_list: List[Dict[str, Any]],
        nexus_api_client,
        game_domain: str = "cyberpunk2077",
        max_concurrent: int = 10
    ) -> List[CompatibilityResult]:
        """Batch check compatibility for multiple mods with concurrency limit
        
        This is optimized for checking compatibility of search results.
        Uses batch requirements fetching and concurrent processing.
        """
        results: List[CompatibilityResult] = []
        
        # Extract mod IDs
        mod_ids = [
            mod.get("mod_id") or mod.get("nexusModId")
            for mod in mod_data_list
            if mod.get("mod_id") or mod.get("nexusModId")
        ]
        
        # Batch fetch requirements for all mods
        requirements_map = await nexus_api_client.batch_get_mod_requirements(
            mod_ids, game_domain, max_concurrent=max_concurrent
        )
        
        # Check compatibility for each mod
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def check_mod(mod_data: Dict[str, Any]):
            async with semaphore:
                mod_id = mod_data.get("mod_id") or mod_data.get("nexusModId")
                if not mod_id:
                    return CompatibilityResult(
                        compatible=True,
                        severity='warning',
                        reason='No mod ID provided'
                    )
                
                # Get requirements from batch fetch
                requirements = requirements_map.get(mod_id, [])
                
                # Extract description
                description = (
                    mod_data.get("description", "") or 
                    mod_data.get("summary", "") or
                    ""
                )
                
                # Check for dependencies (both incompatible and ported)
                incompatible_refs, ported_refs = self.extract_requirements_from_text(description)
                
                # Check requirements list
                for req in requirements:
                    req_name = req.get("name", "").lower()
                    
                    # Check for ported mods (now compatible!)
                    for dep_name, dep_info in self.MACOS_PORTED_MODS.items():
                        if any(kw in req_name for kw in dep_info['keywords']):
                            if dep_name not in ported_refs:
                                ported_refs.append(dep_name)
                    
                    # Check truly incompatible mods
                    for dep_name, keywords in self.INCOMPATIBLE_KEYWORDS.items():
                        if any(kw in req_name for kw in keywords):
                            if dep_name not in incompatible_refs:
                                incompatible_refs.append(dep_name)
                
                # Check if redscript is mentioned
                has_redscript = any(
                    kw in description.lower() 
                    for kw in ['redscript', 'red script', '.reds']
                )
                
                # Generate result - only truly incompatible mods block installation
                if incompatible_refs:
                    dep_names = ', '.join([d.title() for d in incompatible_refs])
                    return CompatibilityResult(
                        compatible=False,
                        severity='critical',
                        reason=f'Mod requires {dep_names} which is not compatible with macOS',
                        has_codeware_refs='codeware' in incompatible_refs,
                        has_cet_refs='cet' in incompatible_refs,
                        incompatible_dependencies=incompatible_refs,
                        ported_dependencies=ported_refs
                    )
                
                # If mod uses ported dependencies, it's compatible!
                if ported_refs:
                    ported_names = ', '.join([d.title() for d in ported_refs])
                    return CompatibilityResult(
                        compatible=True,
                        severity='info',
                        reason=f'Mod uses {ported_names} which has been ported to macOS',
                        has_red4ext_refs='red4ext' in ported_refs,
                        has_tweakxl_refs='tweakxl' in ported_refs,
                        has_archivexl_refs='archivexl' in ported_refs,
                        has_reds_files=has_redscript,
                        ported_dependencies=ported_refs
                    )
                
                if has_redscript:
                    return CompatibilityResult(
                        compatible=True,
                        severity='info',
                        reason='Mod appears compatible with macOS (redscript-only mod)',
                        has_reds_files=True
                    )
                
                return CompatibilityResult(
                    compatible=True,
                    severity='warning',
                    reason='Could not determine compatibility from metadata',
                    has_reds_files=False
                )
        
        # Process all mods concurrently
        tasks = [check_mod(mod_data) for mod_data in mod_data_list]
        results = await asyncio.gather(*tasks)
        
        return results
    
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
    
    async def _extract_archive(self, archive_path: Path, dest: Path) -> None:
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
        """Scan directory for compatibility indicators
        
        Updated to recognize macOS-native mod types:
        - .dylib files in red4ext/plugins/ are RED4ext plugins (compatible!)
        - .yaml/.yml files in r6/tweaks/ are TweakXL tweaks (compatible!)
        """
        has_reds: bool = False
        has_dll: bool = False
        has_dylib: bool = False
        has_tweak_files: bool = False
        has_red4ext_plugin: bool = False
        modifies_executable: bool = False
        has_r6_scripts_only: bool = True
        incompatible_refs: List[str] = []
        ported_refs: List[str] = []
        file_paths = []
        
        # Scan all files
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                file_paths.append(file_path)
                rel_path = file_path.relative_to(directory)
                rel_str = str(rel_path).replace('\\', '/').lower()
                
                # Check file extension
                if file_path.suffix == '.reds':
                    has_reds = True
                elif file_path.suffix == '.dll':
                    has_dll = True
                elif file_path.suffix == '.dylib':
                    has_dylib = True
                    # Check if it's a RED4ext plugin (macOS native!)
                    if 'red4ext/plugins' in rel_str or 'red4ext\\plugins' in str(rel_path).lower():
                        has_red4ext_plugin = True
                        if 'red4ext' not in ported_refs:
                            ported_refs.append('red4ext')
                elif file_path.suffix in ['.yaml', '.yml']:
                    # Check if it's a TweakXL tweak file
                    if 'r6/tweaks' in rel_str or 'tweaks' in rel_str:
                        has_tweak_files = True
                        if 'tweakxl' not in ported_refs:
                            ported_refs.append('tweakxl')
                
                # Check for executable modifications (only Windows exe paths are suspicious)
                if any(exe_name in rel_str for exe_name in [
                    'bin/x64', 'dinput8.dll', 'version.dll'
                ]):
                    modifies_executable = True
                
                # Check if mod only modifies r6/scripts/ (macOS compatible structure)
                # Now also allow r6/tweaks/ and red4ext/plugins/
                allowed_dirs = [
                    'r6/scripts/', 'r6/scripts', 'scripts/',
                    'r6/tweaks/', 'r6/tweaks', 'tweaks/',
                    'red4ext/plugins/', 'red4ext/plugins',
                    'archive/pc/mod/',  # For ArchiveXL mods
                ]
                is_allowed = any(rel_str.startswith(d) for d in allowed_dirs)
                
                if not is_allowed:
                    # Allow README, LICENSE, and other documentation files
                    if not any(doc_name in rel_str for doc_name in [
                        'readme', 'license', 'changelog', '.md', '.txt', '.json', '.toml'
                    ]):
                        has_r6_scripts_only = False
                
                # Check file contents for keywords
                if file_path.suffix in ['.reds', '.txt', '.json', '.xml', '.md', '.yml', '.yaml', '.toml']:
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore').lower()
                        
                        # Check for ported mods (these are compatible!)
                        for dep_name, dep_info in self.MACOS_PORTED_MODS.items():
                            if any(kw in content for kw in dep_info['keywords']):
                                if dep_name not in ported_refs:
                                    ported_refs.append(dep_name)
                        
                        # Check truly incompatible dependencies
                        for dep_name, keywords in self.INCOMPATIBLE_KEYWORDS.items():
                            if any(kw in content for kw in keywords):
                                if dep_name not in incompatible_refs:
                                    incompatible_refs.append(dep_name)
                    except Exception:
                        pass
        
        # Generate result
        
        # DLLs are incompatible (Windows-only binaries)
        if has_dll:
            return CompatibilityResult(
                compatible=False,
                severity='critical',
                reason='Mod contains Windows DLL files. Need macOS .dylib version.',
                has_dll_files=True,
                ported_dependencies=ported_refs
            )
        
        # Executable modifications are always suspicious
        if modifies_executable:
            return CompatibilityResult(
                compatible=False,
                severity='critical',
                reason='Mod appears to modify game executables which is not supported on macOS',
                modifies_executable=True
            )
        
        # Only truly incompatible mods (CET, Codeware) block installation
        if incompatible_refs:
            dep_names = ', '.join([d.title() for d in incompatible_refs])
            return CompatibilityResult(
                compatible=False,
                severity='critical',
                reason=f'Mod requires {dep_names} which is not compatible with macOS (no macOS port available)',
                has_codeware_refs='codeware' in incompatible_refs,
                has_cet_refs='cet' in incompatible_refs,
                incompatible_dependencies=incompatible_refs,
                ported_dependencies=ported_refs
            )
        
        # .dylib files in red4ext/plugins/ are macOS-native RED4ext plugins!
        if has_red4ext_plugin or has_dylib:
            return CompatibilityResult(
                compatible=True,
                severity='info',
                reason='Mod contains macOS-native RED4ext plugin (.dylib)',
                has_dylib_files=True,
                has_red4ext_plugin=True,
                has_red4ext_refs=True,
                ported_dependencies=ported_refs
            )
        
        # TweakXL tweak files are compatible
        if has_tweak_files:
            return CompatibilityResult(
                compatible=True,
                severity='info',
                reason='Mod contains TweakXL tweak files (.yaml/.yml)',
                has_tweak_files=True,
                has_tweakxl_refs=True,
                ported_dependencies=ported_refs
            )
        
        # Mods that use ported dependencies are compatible
        if ported_refs:
            ported_names = ', '.join([d.title() for d in ported_refs])
            return CompatibilityResult(
                compatible=True,
                severity='info',
                reason=f'Mod uses {ported_names} which has been ported to macOS',
                has_red4ext_refs='red4ext' in ported_refs,
                has_tweakxl_refs='tweakxl' in ported_refs,
                has_archivexl_refs='archivexl' in ported_refs,
                has_reds_files=has_reds,
                ported_dependencies=ported_refs
            )
        
        if not has_reds and not has_tweak_files:
            return CompatibilityResult(
                compatible=True,
                severity='warning',
                reason='Mod does not appear to contain redscript or tweak files',
                has_reds_files=False,
                has_r6_scripts_only=has_r6_scripts_only
            )
        
        return CompatibilityResult(
            compatible=True,
            severity='info',
            reason='Mod appears to be compatible with macOS (pure redscript mod)',
            has_reds_files=True,
            has_r6_scripts_only=has_r6_scripts_only
        )
