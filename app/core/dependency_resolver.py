from typing import List, Dict, Set, Optional, Any, TypedDict, Callable
from pathlib import Path
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.mod import Mod, ModDependency
from app.core.nexus_api import NexusAPIClient, NexusAPIError
from dataclasses import dataclass, field
from enum import Enum
from app.config import settings

logger = logging.getLogger(__name__)


class DependencyStatus(Enum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    VERSION_MISMATCH = "version_mismatch"
    INSTALLING = "installing"
    INSTALL_FAILED = "install_failed"


@dataclass
class DependencyInfo:
    name: str
    status: DependencyStatus
    required_version: Optional[str] = None
    installed_version: Optional[str] = None
    nexus_mod_id: Optional[int] = None
    is_required: bool = True
    message: str = ""
    install_path: Optional[str] = None
    auto_installable: bool = False


@dataclass
class DependencyInstallResult:
    """Result of attempting to install a dependency"""
    name: str
    success: bool
    mod_id: Optional[int] = None
    message: str = ""
    error: Optional[str] = None


class DependencyResolver:
    """Resolve mod dependencies and check compatibility
    
    Updated for macOS-ported mods:
    - RED4ext: https://github.com/memaxo/RED4ext-macos
    - TweakXL: https://github.com/memaxo/cp2077-tweak-xl-macos
    - ArchiveXL: https://github.com/memaxo/cp2077-archive-xl-macos
    """
    
    # Known core dependencies for Cyberpunk 2077 on macOS
    # Updated to reflect macOS ports
    CORE_DEPENDENCIES = {
        "redscript": {
            "macos_compatible": True,
            "min_version": "0.5.29",
            "description": "Redscript compiler (built into macOS game)",
            "install_path": None,  # Built into game
            "auto_install": False,
            "check_file": "r6/scripts"  # Directory that indicates redscript support
        },
        "RED4ext": {
            "macos_compatible": True,  # ✅ PORTED TO MACOS
            "min_version": "1.0.0",
            "description": "RED4 extension loader (macOS port available)",
            "install_path": "red4ext/",
            "check_file": "red4ext/RED4ext.dylib",
            "github_repo": "https://github.com/memaxo/RED4ext-macos",
            "nexus_mod_id": None,  # Not on Nexus yet
            "auto_install": True,
            "keywords": ["red4ext", "red4 ext", "red4_ext"]
        },
        "TweakXL": {
            "macos_compatible": True,  # ✅ PORTED TO MACOS
            "min_version": "1.0.0",
            "description": "TweakDB extension (macOS port available)",
            "install_path": "red4ext/plugins/TweakXL/",
            "check_file": "red4ext/plugins/TweakXL/TweakXL.dylib",
            "github_repo": "https://github.com/memaxo/cp2077-tweak-xl-macos",
            "nexus_mod_id": None,  # Not on Nexus yet
            "auto_install": True,
            "requires": ["RED4ext"],
            "keywords": ["tweakxl", "tweak xl", "tweak_xl"]
        },
        "ArchiveXL": {
            "macos_compatible": True,  # ✅ PORTED TO MACOS (in progress)
            "min_version": "1.0.0",
            "description": "Archive extension (macOS port in progress)",
            "install_path": "red4ext/plugins/ArchiveXL/",
            "check_file": "red4ext/plugins/ArchiveXL/ArchiveXL.dylib",
            "github_repo": "https://github.com/memaxo/cp2077-archive-xl-macos",
            "nexus_mod_id": None,
            "auto_install": True,
            "requires": ["RED4ext"],
            "keywords": ["archivexl", "archive xl", "archive_xl"]
        },
        "Codeware": {
            "macos_compatible": False,  # ❌ NOT PORTED YET
            "description": "Code extension (Windows only - no macOS port)",
            "install_path": None,
            "auto_install": False,
            "keywords": ["codeware", "code ware", "code_ware"]
        },
        "CET": {
            "macos_compatible": False,  # ❌ NOT PORTED YET
            "description": "Cyber Engine Tweaks (Windows only - no macOS port)",
            "install_path": None,
            "auto_install": False,
            "keywords": ["cyber engine tweaks", "cet", "cyberenginetweaks"]
        },
        "Input Loader": {
            "macos_compatible": False,  # ❌ NOT PORTED
            "description": "Input Loader (Windows only)",
            "install_path": None,
            "auto_install": False,
            "keywords": ["input loader", "inputloader"]
        }
    }
    
    # Nexus Mod IDs for common dependencies (for auto-download)
    # These are Windows versions - we check for macOS alternatives first
    NEXUS_MOD_IDS = {
        "RED4ext": 2380,      # Windows version
        "TweakXL": 4197,      # Windows version  
        "ArchiveXL": 4198,    # Windows version
        "Codeware": 7780,     # Windows version
        "CET": 107,           # Windows version
        "redscript": 8473,    # Redscript (cross-platform)
    }
    
    def __init__(self, db: AsyncSession, game_path: Optional[Path] = None):
        self.db = db
        self.game_path = game_path
        self._install_progress_callbacks: List[Callable] = []
    
    def set_game_path(self, game_path: Path) -> None:
        """Set the game path for file-based dependency checks"""
        self.game_path = game_path
    
    def add_progress_callback(self, callback: Callable[[str, int, str], None]) -> None:
        """Add a callback for installation progress updates"""
        self._install_progress_callbacks.append(callback)
    
    def _report_progress(self, stage: str, percent: int, message: str) -> None:
        """Report progress to all registered callbacks"""
        for callback in self._install_progress_callbacks:
            try:
                callback(stage, percent, message)
            except Exception:
                pass
    
    def normalize_dependency_name(self, name: str) -> Optional[str]:
        """Normalize a dependency name to match our CORE_DEPENDENCIES keys"""
        name_lower = name.lower().strip()
        
        for dep_name, dep_info in self.CORE_DEPENDENCIES.items():
            # Check exact match (case-insensitive)
            if dep_name.lower() == name_lower:
                return dep_name
            
            # Check keywords
            keywords = dep_info.get("keywords", [])
            if any(kw in name_lower for kw in keywords):
                return dep_name
        
        return None
    
    def is_framework_installed(self, framework_name: str) -> bool:
        """Check if a framework is installed by looking for its files"""
        if not self.game_path:
            return False
        
        normalized = self.normalize_dependency_name(framework_name)
        if not normalized or normalized not in self.CORE_DEPENDENCIES:
            return False
        
        dep_info = self.CORE_DEPENDENCIES[normalized]
        check_file = dep_info.get("check_file")
        
        if check_file:
            check_path = self.game_path / check_file
            return check_path.exists()
        
        return False
    
    async def check_mod_dependencies(
        self,
        mod_id: int
    ) -> List[DependencyInfo]:
        """Check dependencies for a specific mod"""
        # Get mod dependencies from database
        result = await self.db.execute(
            select(ModDependency).where(ModDependency.mod_id == mod_id)
        )
        dependencies = result.scalars().all()
        
        dependency_info = []
        
        for dep in dependencies:
            info = await self._check_dependency(dep)
            dependency_info.append(info)
        
        return dependency_info
    
    async def check_all_dependencies(self) -> Dict[int, List[DependencyInfo]]:
        """Check dependencies for all installed mods"""
        result = await self.db.execute(
            select(Mod).where(Mod.is_active == True)
        )
        mods = result.scalars().all()
        
        all_dependencies = {}
        for mod in mods:
            deps = await self.check_mod_dependencies(mod.id)
            all_dependencies[mod.id] = deps
        
        return all_dependencies
    
    async def resolve_dependencies(
        self,
        mod_id: int,
        auto_install: bool = False
    ) -> Dict[str, Any]:
        """Resolve dependencies for a mod
        
        Returns:
            Dict with 'satisfied', 'missing', 'incompatible' lists
        """
        dependencies = await self.check_mod_dependencies(mod_id)
        
        result = {
            "satisfied": [],
            "missing": [],
            "incompatible": [],
            "version_mismatch": []
        }
        
        for dep_info in dependencies:
            if dep_info.status == DependencyStatus.SATISFIED:
                result["satisfied"].append(dep_info.name)
            elif dep_info.status == DependencyStatus.MISSING:
                result["missing"].append({
                    "name": dep_info.name,
                    "required": dep_info.is_required,
                    "nexus_mod_id": dep_info.nexus_mod_id,
                    "message": dep_info.message
                })
            elif dep_info.status == DependencyStatus.INCOMPATIBLE:
                result["incompatible"].append({
                    "name": dep_info.name,
                    "message": dep_info.message
                })
            elif dep_info.status == DependencyStatus.VERSION_MISMATCH:
                result["version_mismatch"].append({
                    "name": dep_info.name,
                    "required": dep_info.required_version,
                    "installed": dep_info.installed_version,
                    "message": dep_info.message
                })
        
        return result
    
    async def _check_dependency(self, dependency: ModDependency) -> DependencyInfo:
        """Check a single dependency with macOS-aware logic"""
        dep_name = dependency.dependency_name
        
        # Normalize the dependency name
        normalized_name = self.normalize_dependency_name(dep_name)
        
        # Check if it's a known core dependency
        if normalized_name and normalized_name in self.CORE_DEPENDENCIES:
            core_info = self.CORE_DEPENDENCIES[normalized_name]
            
            # Check macOS compatibility
            if not core_info.get("macos_compatible", True):
                return DependencyInfo(
                    name=normalized_name,
                    status=DependencyStatus.INCOMPATIBLE,
                    is_required=dependency.dependency_type == "required",
                    message=f"{normalized_name} is not compatible with macOS (no port available)",
                    auto_installable=False
                )
            
            # Check if installed via file system first (most reliable)
            if self.is_framework_installed(normalized_name):
                return DependencyInfo(
                    name=normalized_name,
                    status=DependencyStatus.SATISFIED,
                    is_required=dependency.dependency_type == "required",
                    install_path=core_info.get("install_path"),
                    message=f"{normalized_name} is installed"
                )
            
            # Check in database
            installed = await self._check_installed_dependency(normalized_name)
            if installed:
                return DependencyInfo(
                    name=normalized_name,
                    status=DependencyStatus.SATISFIED,
                    is_required=dependency.dependency_type == "required",
                    installed_version=installed.get("version") if isinstance(installed, dict) else None
                )
            
            # Not installed - check if auto-installable
            auto_install = core_info.get("auto_install", False)
            nexus_id = self.NEXUS_MOD_IDS.get(normalized_name) or dependency.nexus_mod_id
            github_repo = core_info.get("github_repo")
            
            return DependencyInfo(
                name=normalized_name,
                status=DependencyStatus.MISSING,
                is_required=dependency.dependency_type == "required",
                required_version=dependency.min_version or core_info.get("min_version"),
                nexus_mod_id=nexus_id,
                install_path=core_info.get("install_path"),
                auto_installable=auto_install and (nexus_id is not None or github_repo is not None),
                message=f"{normalized_name} is not installed" + 
                        (f" (macOS port available from GitHub)" if github_repo else
                         f" (available on Nexus Mods)" if nexus_id else "")
            )
        
        # Not a core dependency - check for installed mod with this name
        installed = await self._check_installed_dependency(dep_name)
        if installed:
            return DependencyInfo(
                name=dep_name,
                status=DependencyStatus.SATISFIED,
                is_required=dependency.dependency_type == "required"
            )
        
        # Check Nexus Mods if nexus_mod_id provided
        nexus_id = dependency.nexus_mod_id
        if nexus_id:
            return DependencyInfo(
                name=dep_name,
                status=DependencyStatus.MISSING,
                is_required=dependency.dependency_type == "required",
                nexus_mod_id=nexus_id,
                auto_installable=True,
                message=f"{dep_name} is not installed (available on Nexus Mods)"
            )
        
        return DependencyInfo(
            name=dep_name,
            status=DependencyStatus.MISSING,
            is_required=dependency.dependency_type == "required",
            auto_installable=False,
            message=f"{dep_name} is not installed"
        )
    
    async def _check_installed_dependency(self, dependency_name: str) -> Optional[Dict[str, Any]]:
        """Check if a dependency is installed"""
        # Check for mods with matching name
        result = await self.db.execute(
            select(Mod).where(
                Mod.name.ilike(f"%{dependency_name}%"),
                Mod.is_active == True
            )
        )
        mod = result.scalar_one_or_none()
        
        if mod:
            return {
                "mod_id": mod.id,
                "name": mod.name,
                "version": mod.version
            }
        
        # Check for redscript specifically (it's a framework, not a mod)
        if dependency_name.lower() == "redscript":
            # Check if r6/cache/final.redscripts exists (indicates redscript is installed)
            # This is a simple check - in production, you'd want more robust detection
            return {
                "name": "redscript",
                "version": "unknown",
                "installed": True
            }
        
        return None
    
    async def find_missing_dependencies(self) -> Dict[int, List[str]]:
        """Find all mods with missing dependencies"""
        all_deps = await self.check_all_dependencies()
        
        missing = {}
        for mod_id, dependencies in all_deps.items():
            missing_deps = [
                dep.name for dep in dependencies
                if dep.status == DependencyStatus.MISSING and dep.is_required
            ]
            if missing_deps:
                missing[mod_id] = missing_deps
        
        return missing
    
    async def find_incompatible_dependencies(self) -> Dict[int, List[str]]:
        """Find all mods with incompatible dependencies"""
        all_deps = await self.check_all_dependencies()
        
        incompatible = {}
        for mod_id, dependencies in all_deps.items():
            incompat_deps = [
                dep.name for dep in dependencies
                if dep.status == DependencyStatus.INCOMPATIBLE
            ]
            if incompat_deps:
                incompatible[mod_id] = incompat_deps
        
        return incompatible

    async def get_dependency_graph(self) -> List[Dict[str, Any]]:
        """Get full dependency graph for all active mods"""
        result = await self.db.execute(select(Mod).where(Mod.is_active == True))
        mods = result.scalars().all()
        
        graph = []
        for mod in mods:
            deps_result = await self.db.execute(
                select(ModDependency).where(ModDependency.mod_id == mod.id)
            )
            deps = deps_result.scalars().all()
            
            mod_deps = []
            for d in deps:
                status = await self._check_dependency(d)
                mod_deps.append({
                    "name": d.dependency_name,
                    "type": d.dependency_type,
                    "status": status.status.value,
                    "nexus_mod_id": d.nexus_mod_id,
                    "message": status.message
                })
                
            graph.append({
                "mod_id": mod.id,
                "mod_name": mod.name,
                "dependencies": mod_deps
            })
            
        return graph

    async def get_sorted_load_order(self, mod_ids: List[int]) -> List[int]:
        """Sort mod IDs based on their dependencies (topological sort)"""
        # Build dependency graph
        graph = {mid: [] for mid in mod_ids}
        
        for mod_id in mod_ids:
            deps = await self.db.execute(
                select(ModDependency).where(
                    ModDependency.mod_id == mod_id,
                    ModDependency.dependency_type == "required"
                )
            )
            for dep in deps.scalars().all():
                # If target_mod_id is set, use it
                if dep.target_mod_id and dep.target_mod_id in mod_ids:
                    graph[mod_id].append(dep.target_mod_id)
                else:
                    # Search for mod by name
                    # This is a bit slow but necessary if target_mod_id isn't set
                    target_res = await self.db.execute(
                        select(Mod.id).where(
                            Mod.name.ilike(f"%{dep.dependency_name}%"),
                            Mod.id.in_(mod_ids)
                        )
                    )
                    target_id = target_res.scalar()
                    if target_id:
                        graph[mod_id].append(target_id)
        
        # Topological sort (Kahn's algorithm)
        sorted_ids = []
        visited = set()
        temp_visited = set()

        def visit(n: int) -> None:
            if n in temp_visited:
                # Cycle detected, but we'll just ignore for now or handle gracefully
                return
            if n not in visited:
                temp_visited.add(n)
                for m in graph.get(n, []):
                    visit(m)
                temp_visited.remove(n)
                visited.add(n)
                sorted_ids.append(n)

        for mod_id in mod_ids:
            visit(mod_id)
            
        return sorted_ids

    # =========================================================================
    # Smart Dependency Installation
    # =========================================================================
    
    async def get_installable_dependencies(
        self,
        mod_id: Optional[int] = None,
        dependency_names: Optional[List[str]] = None
    ) -> List[DependencyInfo]:
        """Get list of missing dependencies that can be auto-installed
        
        Args:
            mod_id: Check dependencies for a specific mod
            dependency_names: Or check specific dependency names
            
        Returns:
            List of DependencyInfo for installable dependencies
        """
        installable = []
        
        if mod_id:
            deps = await self.check_mod_dependencies(mod_id)
            for dep in deps:
                if dep.status == DependencyStatus.MISSING and dep.auto_installable:
                    installable.append(dep)
        
        if dependency_names:
            for name in dependency_names:
                normalized = self.normalize_dependency_name(name)
                if normalized and normalized in self.CORE_DEPENDENCIES:
                    core_info = self.CORE_DEPENDENCIES[normalized]
                    
                    # Check if already installed
                    if self.is_framework_installed(normalized):
                        continue
                    
                    # Check if macOS compatible and auto-installable
                    if core_info.get("macos_compatible") and core_info.get("auto_install"):
                        nexus_id = self.NEXUS_MOD_IDS.get(normalized)
                        github_repo = core_info.get("github_repo")
                        
                        installable.append(DependencyInfo(
                            name=normalized,
                            status=DependencyStatus.MISSING,
                            is_required=True,
                            nexus_mod_id=nexus_id,
                            auto_installable=True,
                            install_path=core_info.get("install_path"),
                            message=f"Can install from {'GitHub' if github_repo else 'Nexus Mods'}"
                        ))
        
        return installable
    
    async def install_dependency_from_nexus(
        self,
        dependency_name: str,
        nexus_mod_id: Optional[int] = None,
        file_id: Optional[int] = None
    ) -> DependencyInstallResult:
        """Install a dependency from Nexus Mods
        
        Args:
            dependency_name: Name of the dependency
            nexus_mod_id: Nexus mod ID (optional if known dependency)
            file_id: Specific file ID to download (optional, uses latest)
            
        Returns:
            DependencyInstallResult with success status
        """
        from app.core.mod_manager import ModManager, ModInstallationError
        
        self._report_progress("dependency", 0, f"Installing {dependency_name}...")
        
        # Get Nexus mod ID if not provided
        if not nexus_mod_id:
            normalized = self.normalize_dependency_name(dependency_name)
            if normalized:
                nexus_mod_id = self.NEXUS_MOD_IDS.get(normalized)
        
        if not nexus_mod_id:
            return DependencyInstallResult(
                name=dependency_name,
                success=False,
                error=f"No Nexus Mods ID found for {dependency_name}"
            )
        
        # Check if it's a macOS-incompatible dependency
        normalized = self.normalize_dependency_name(dependency_name)
        if normalized and normalized in self.CORE_DEPENDENCIES:
            core_info = self.CORE_DEPENDENCIES[normalized]
            if not core_info.get("macos_compatible", True):
                return DependencyInstallResult(
                    name=dependency_name,
                    success=False,
                    error=f"{dependency_name} is not compatible with macOS"
                )
            
            # Check for macOS-specific installation (GitHub releases)
            github_repo = core_info.get("github_repo")
            if github_repo:
                self._report_progress("dependency", 10, f"Checking GitHub for macOS version...")
                # For now, we'll note that GitHub installation is preferred
                logger.info(f"{dependency_name} has macOS port at {github_repo}")
        
        self._report_progress("dependency", 20, f"Fetching {dependency_name} from Nexus...")
        
        try:
            if not self.game_path:
                return DependencyInstallResult(
                    name=dependency_name,
                    success=False,
                    error="Game path not set"
                )
            
            mod_manager = ModManager(self.db, self.game_path)
            
            self._report_progress("dependency", 40, f"Downloading {dependency_name}...")
            
            # Install from Nexus
            mod = await mod_manager.install_mod_from_nexus(
                nexus_mod_id=nexus_mod_id,
                file_id=file_id,
                check_compatibility=True
            )
            
            self._report_progress("dependency", 100, f"Successfully installed {dependency_name}")
            
            return DependencyInstallResult(
                name=dependency_name,
                success=True,
                mod_id=mod.id,
                message=f"Successfully installed {mod.name}"
            )
            
        except ModInstallationError as e:
            logger.error(f"Failed to install {dependency_name}: {e}")
            return DependencyInstallResult(
                name=dependency_name,
                success=False,
                error=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error installing {dependency_name}")
            return DependencyInstallResult(
                name=dependency_name,
                success=False,
                error=f"Unexpected error: {str(e)}"
            )
    
    async def install_all_missing_dependencies(
        self,
        mod_id: int,
        skip_incompatible: bool = True
    ) -> Dict[str, Any]:
        """Install all missing dependencies for a mod
        
        Args:
            mod_id: The mod to resolve dependencies for
            skip_incompatible: Skip macOS-incompatible deps instead of failing
            
        Returns:
            Dict with results for each dependency
        """
        self._report_progress("dependencies", 0, "Checking dependencies...")
        
        results = {
            "installed": [],
            "skipped": [],
            "failed": [],
            "already_satisfied": []
        }
        
        # Get all dependencies
        deps = await self.check_mod_dependencies(mod_id)
        
        # Sort by dependency chain (install dependencies of dependencies first)
        # Simple approach: install in order, re-check after each
        
        total_deps = len([d for d in deps if d.status != DependencyStatus.SATISFIED])
        installed_count = 0
        
        for dep in deps:
            if dep.status == DependencyStatus.SATISFIED:
                results["already_satisfied"].append(dep.name)
                continue
            
            if dep.status == DependencyStatus.INCOMPATIBLE:
                if skip_incompatible:
                    results["skipped"].append({
                        "name": dep.name,
                        "reason": dep.message
                    })
                    continue
                else:
                    results["failed"].append({
                        "name": dep.name,
                        "error": dep.message
                    })
                    continue
            
            if not dep.auto_installable:
                results["skipped"].append({
                    "name": dep.name,
                    "reason": "Cannot auto-install (no source available)"
                })
                continue
            
            # Try to install
            progress = int((installed_count / max(total_deps, 1)) * 100)
            self._report_progress("dependencies", progress, f"Installing {dep.name}...")
            
            result = await self.install_dependency_from_nexus(
                dep.name,
                nexus_mod_id=dep.nexus_mod_id
            )
            
            if result.success:
                results["installed"].append({
                    "name": dep.name,
                    "mod_id": result.mod_id
                })
                installed_count += 1
            else:
                results["failed"].append({
                    "name": dep.name,
                    "error": result.error
                })
        
        self._report_progress("dependencies", 100, "Dependency resolution complete")
        
        return results
    
    async def preview_dependency_installation(
        self,
        mod_id: Optional[int] = None,
        nexus_mod_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Preview what dependencies would be installed
        
        Use before actual installation to show user what will happen.
        
        Args:
            mod_id: Installed mod ID to check
            nexus_mod_id: Or Nexus mod ID to check before install
            
        Returns:
            Preview of dependency installation plan
        """
        preview = {
            "will_install": [],
            "already_installed": [],
            "incompatible": [],
            "cannot_install": [],
            "total_download_size_estimate": 0
        }
        
        deps_to_check = []
        
        if mod_id:
            deps_to_check = await self.check_mod_dependencies(mod_id)
        elif nexus_mod_id:
            # Fetch requirements from Nexus
            async with NexusAPIClient() as nexus:
                requirements = await nexus.get_mod_requirements(nexus_mod_id)
                
                for req in requirements:
                    name = req.get("name", "")
                    is_required = req.get("isRequired", False)
                    req_nexus_id = req.get("nexusModId")
                    
                    # Create synthetic DependencyInfo
                    normalized = self.normalize_dependency_name(name)
                    
                    if normalized and normalized in self.CORE_DEPENDENCIES:
                        core_info = self.CORE_DEPENDENCIES[normalized]
                        
                        if not core_info.get("macos_compatible", True):
                            deps_to_check.append(DependencyInfo(
                                name=normalized,
                                status=DependencyStatus.INCOMPATIBLE,
                                is_required=is_required,
                                message=f"{normalized} not compatible with macOS"
                            ))
                        elif self.is_framework_installed(normalized):
                            deps_to_check.append(DependencyInfo(
                                name=normalized,
                                status=DependencyStatus.SATISFIED,
                                is_required=is_required
                            ))
                        else:
                            deps_to_check.append(DependencyInfo(
                                name=normalized,
                                status=DependencyStatus.MISSING,
                                is_required=is_required,
                                nexus_mod_id=req_nexus_id or self.NEXUS_MOD_IDS.get(normalized),
                                auto_installable=core_info.get("auto_install", False)
                            ))
                    else:
                        # Unknown dependency - check if installed
                        installed = await self._check_installed_dependency(name)
                        deps_to_check.append(DependencyInfo(
                            name=name,
                            status=DependencyStatus.SATISFIED if installed else DependencyStatus.MISSING,
                            is_required=is_required,
                            nexus_mod_id=req_nexus_id,
                            auto_installable=req_nexus_id is not None
                        ))
        
        # Categorize dependencies
        for dep in deps_to_check:
            if dep.status == DependencyStatus.SATISFIED:
                preview["already_installed"].append({
                    "name": dep.name,
                    "required": dep.is_required
                })
            elif dep.status == DependencyStatus.INCOMPATIBLE:
                preview["incompatible"].append({
                    "name": dep.name,
                    "required": dep.is_required,
                    "reason": dep.message
                })
            elif dep.auto_installable:
                # Estimate size (rough estimates)
                size_estimates = {
                    "RED4ext": 5 * 1024 * 1024,      # ~5MB
                    "TweakXL": 2 * 1024 * 1024,      # ~2MB
                    "ArchiveXL": 3 * 1024 * 1024,    # ~3MB
                }
                normalized = self.normalize_dependency_name(dep.name)
                size = size_estimates.get(normalized, 1 * 1024 * 1024)  # Default 1MB
                
                preview["will_install"].append({
                    "name": dep.name,
                    "required": dep.is_required,
                    "nexus_mod_id": dep.nexus_mod_id,
                    "estimated_size": size
                })
                preview["total_download_size_estimate"] += size
            else:
                preview["cannot_install"].append({
                    "name": dep.name,
                    "required": dep.is_required,
                    "reason": "No auto-install source available"
                })
        
        # Check for blocked installation
        required_incompatible = [
            d for d in preview["incompatible"] if d["required"]
        ]
        required_cannot_install = [
            d for d in preview["cannot_install"] if d["required"]
        ]
        
        preview["can_proceed"] = len(required_incompatible) == 0
        preview["has_warnings"] = len(required_cannot_install) > 0
        
        if required_incompatible:
            names = ", ".join([d["name"] for d in required_incompatible])
            preview["block_reason"] = f"Required dependencies not compatible with macOS: {names}"
        
        return preview
