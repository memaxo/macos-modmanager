from typing import List, Dict, Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.mod import Mod, ModDependency
from app.core.nexus_api import NexusAPIClient, NexusAPIError
from dataclasses import dataclass
from enum import Enum


class DependencyStatus(Enum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    VERSION_MISMATCH = "version_mismatch"


@dataclass
class DependencyInfo:
    name: str
    status: DependencyStatus
    required_version: Optional[str] = None
    installed_version: Optional[str] = None
    nexus_mod_id: Optional[int] = None
    is_required: bool = True
    message: str = ""


class DependencyResolver:
    """Resolve mod dependencies and check compatibility"""
    
    # Known core dependencies for Cyberpunk 2077
    CORE_DEPENDENCIES = {
        "redscript": {
            "macos_compatible": True,
            "min_version": "0.5.29",
            "description": "Redscript compiler"
        },
        "ArchiveXL": {
            "macos_compatible": False,
            "description": "Archive extension (requires RED4ext)"
        },
        "Codeware": {
            "macos_compatible": False,
            "description": "Code extension (requires RED4ext)"
        },
        "RED4ext": {
            "macos_compatible": False,
            "description": "RED4 extension loader (Windows only)"
        },
        "CET": {
            "macos_compatible": False,
            "description": "Cyber Engine Tweaks (Windows only)"
        },
        "TweakXL": {
            "macos_compatible": False,
            "description": "Tweak extension (may require RED4ext)"
        }
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
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
    ) -> Dict[str, any]:
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
        """Check a single dependency"""
        dep_name = dependency.dependency_name
        
        # Check if it's a known core dependency
        if dep_name in self.CORE_DEPENDENCIES:
            core_info = self.CORE_DEPENDENCIES[dep_name]
            
            # Check macOS compatibility
            if not core_info.get("macos_compatible", True):
                return DependencyInfo(
                    name=dep_name,
                    status=DependencyStatus.INCOMPATIBLE,
                    is_required=dependency.dependency_type == "required",
                    message=f"{dep_name} is not compatible with macOS"
                )
            
            # Check if installed
            installed = await self._check_installed_dependency(dep_name)
            if not installed:
                return DependencyInfo(
                    name=dep_name,
                    status=DependencyStatus.MISSING,
                    is_required=dependency.dependency_type == "required",
                    required_version=dependency.min_version or core_info.get("min_version"),
                    nexus_mod_id=dependency.nexus_mod_id,
                    message=f"{dep_name} is not installed"
                )
            
            # Check version if specified
            if dependency.min_version:
                # TODO: Compare versions
                pass
            
            return DependencyInfo(
                name=dep_name,
                status=DependencyStatus.SATISFIED,
                is_required=dependency.dependency_type == "required",
                installed_version=installed.get("version") if isinstance(installed, dict) else None
            )
        
        # Check for installed mod with this dependency name
        installed = await self._check_installed_dependency(dep_name)
        if installed:
            return DependencyInfo(
                name=dep_name,
                status=DependencyStatus.SATISFIED,
                is_required=dependency.dependency_type == "required"
            )
        
        # Check Nexus Mods if nexus_mod_id provided
        if dependency.nexus_mod_id:
            return DependencyInfo(
                name=dep_name,
                status=DependencyStatus.MISSING,
                is_required=dependency.dependency_type == "required",
                nexus_mod_id=dependency.nexus_mod_id,
                message=f"{dep_name} is not installed (available on Nexus Mods)"
            )
        
        return DependencyInfo(
            name=dep_name,
            status=DependencyStatus.MISSING,
            is_required=dependency.dependency_type == "required",
            message=f"{dep_name} is not installed"
        )
    
    async def _check_installed_dependency(self, dependency_name: str) -> Optional[Dict]:
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
