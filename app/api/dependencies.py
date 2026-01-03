from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models.mod import Mod, ModDependency
from app.core.dependency_resolver import DependencyResolver, DependencyStatus
from app.core.game_detector import detect_cyberpunk_installations
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class DependencyInstallRequest(BaseModel):
    """Request to install specific dependencies"""
    dependency_names: List[str]


class DependencyPreviewResponse(BaseModel):
    """Preview of dependency installation"""
    will_install: List[dict]
    already_installed: List[dict]
    incompatible: List[dict]
    cannot_install: List[dict]
    total_download_size_estimate: int
    can_proceed: bool
    has_warnings: bool
    block_reason: Optional[str] = None


async def get_resolver_with_game_path(db: AsyncSession) -> DependencyResolver:
    """Helper to create a DependencyResolver with game path set"""
    resolver = DependencyResolver(db)
    installations = await detect_cyberpunk_installations()
    if installations:
        resolver.set_game_path(Path(installations[0]["path"]))
    return resolver


@router.get("/tree", response_class=HTMLResponse)
async def get_dependency_tree(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get dependency tree as HTML"""
    resolver = await get_resolver_with_game_path(db)
    tree_data = await resolver.get_dependency_graph()
    
    return templates.TemplateResponse("components/dependency_tree.html", {
        "request": request,
        "tree_data": tree_data
    })


@router.get("/check/{mod_id}")
async def check_mod_dependencies(
    mod_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Check dependencies for a specific mod
    
    Returns detailed status of each dependency including:
    - Whether it's satisfied, missing, or incompatible
    - Whether it can be auto-installed
    - Nexus Mod ID for manual installation
    """
    resolver = await get_resolver_with_game_path(db)
    deps = await resolver.check_mod_dependencies(mod_id)
    
    return {
        "mod_id": mod_id,
        "dependencies": [
            {
                "name": dep.name,
                "status": dep.status.value,
                "is_required": dep.is_required,
                "required_version": dep.required_version,
                "installed_version": dep.installed_version,
                "nexus_mod_id": dep.nexus_mod_id,
                "auto_installable": dep.auto_installable,
                "message": dep.message
            }
            for dep in deps
        ],
        "summary": {
            "total": len(deps),
            "satisfied": len([d for d in deps if d.status == DependencyStatus.SATISFIED]),
            "missing": len([d for d in deps if d.status == DependencyStatus.MISSING]),
            "incompatible": len([d for d in deps if d.status == DependencyStatus.INCOMPATIBLE])
        }
    }


@router.get("/preview/{nexus_mod_id}")
async def preview_installation_dependencies(
    nexus_mod_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Preview dependencies before installing a mod from Nexus
    
    Shows what dependencies will be needed and whether they can be
    auto-installed. Use this before starting an installation.
    """
    resolver = await get_resolver_with_game_path(db)
    preview = await resolver.preview_dependency_installation(nexus_mod_id=nexus_mod_id)
    return preview


@router.get("/frameworks/status")
async def get_framework_status(
    db: AsyncSession = Depends(get_db)
):
    """Get installation status of all core frameworks
    
    Returns status of RED4ext, TweakXL, ArchiveXL, etc.
    """
    resolver = await get_resolver_with_game_path(db)
    
    frameworks = []
    for name, info in resolver.CORE_DEPENDENCIES.items():
        is_installed = resolver.is_framework_installed(name)
        
        frameworks.append({
            "name": name,
            "installed": is_installed,
            "macos_compatible": info.get("macos_compatible", False),
            "description": info.get("description", ""),
            "install_path": info.get("install_path"),
            "github_repo": info.get("github_repo"),
            "nexus_mod_id": resolver.NEXUS_MOD_IDS.get(name),
            "auto_installable": info.get("auto_install", False) and info.get("macos_compatible", False)
        })
    
    return {
        "frameworks": frameworks,
        "summary": {
            "total": len(frameworks),
            "installed": len([f for f in frameworks if f["installed"]]),
            "macos_compatible": len([f for f in frameworks if f["macos_compatible"]]),
            "available_to_install": len([
                f for f in frameworks 
                if f["macos_compatible"] and not f["installed"] and f["auto_installable"]
            ])
        }
    }


@router.post("/install-missing/{mod_id}")
async def install_missing_dependencies(
    mod_id: int,
    request: Request,
    skip_incompatible: bool = Query(True, description="Skip macOS-incompatible deps"),
    db: AsyncSession = Depends(get_db)
):
    """Install all missing dependencies for a mod
    
    Automatically downloads and installs missing dependencies from Nexus Mods.
    Skips macOS-incompatible dependencies by default.
    """
    resolver = await get_resolver_with_game_path(db)
    
    if not resolver.game_path:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Game installation not found",
                "code": "GAME_NOT_FOUND",
                "suggestion": "Verify the game is installed"
            }
        )
    
    result = await resolver.install_all_missing_dependencies(
        mod_id=mod_id,
        skip_incompatible=skip_incompatible
    )
    
    # Return JSON for API calls, HTML for HTMX
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        installed_count = len(result.get("installed", []))
        failed_count = len(result.get("failed", []))
        
        if installed_count > 0 and failed_count == 0:
            msg_type = "success"
            message = f"Installed {installed_count} dependencies"
        elif installed_count > 0:
            msg_type = "warning"
            message = f"Installed {installed_count} deps, {failed_count} failed"
        elif failed_count > 0:
            msg_type = "error"
            message = f"Failed to install {failed_count} dependencies"
        else:
            msg_type = "info"
            message = "No dependencies to install"
        
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": message,
            "type": msg_type
        })
    
    return result


@router.post("/install")
async def install_specific_dependencies(
    request_body: DependencyInstallRequest,
    db: AsyncSession = Depends(get_db)
):
    """Install specific dependencies by name
    
    Install one or more dependencies (e.g., ["RED4ext", "TweakXL"]).
    Only installs macOS-compatible dependencies.
    """
    resolver = await get_resolver_with_game_path(db)
    
    if not resolver.game_path:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Game installation not found",
                "code": "GAME_NOT_FOUND"
            }
        )
    
    results = {
        "installed": [],
        "failed": [],
        "skipped": []
    }
    
    for dep_name in request_body.dependency_names:
        normalized = resolver.normalize_dependency_name(dep_name)
        
        if not normalized:
            results["skipped"].append({
                "name": dep_name,
                "reason": "Unknown dependency"
            })
            continue
        
        core_info = resolver.CORE_DEPENDENCIES.get(normalized, {})
        
        if not core_info.get("macos_compatible", True):
            results["skipped"].append({
                "name": normalized,
                "reason": "Not compatible with macOS"
            })
            continue
        
        if resolver.is_framework_installed(normalized):
            results["skipped"].append({
                "name": normalized,
                "reason": "Already installed"
            })
            continue
        
        # Try to install
        install_result = await resolver.install_dependency_from_nexus(normalized)
        
        if install_result.success:
            results["installed"].append({
                "name": normalized,
                "mod_id": install_result.mod_id
            })
        else:
            results["failed"].append({
                "name": normalized,
                "error": install_result.error
            })
    
    return results


@router.get("/missing")
async def get_all_missing_dependencies(
    db: AsyncSession = Depends(get_db)
):
    """Get all missing required dependencies across all installed mods"""
    resolver = await get_resolver_with_game_path(db)
    missing = await resolver.find_missing_dependencies()
    
    # Enrich with details
    result = []
    for mod_id, dep_names in missing.items():
        mod_result = await db.execute(select(Mod).where(Mod.id == mod_id))
        mod = mod_result.scalar_one_or_none()
        
        if mod:
            result.append({
                "mod_id": mod_id,
                "mod_name": mod.name,
                "missing_dependencies": dep_names
            })
    
    return {
        "mods_with_missing_deps": result,
        "total_mods_affected": len(result)
    }


@router.get("/incompatible")
async def get_all_incompatible_dependencies(
    db: AsyncSession = Depends(get_db)
):
    """Get all mods with macOS-incompatible dependencies"""
    resolver = await get_resolver_with_game_path(db)
    incompatible = await resolver.find_incompatible_dependencies()
    
    result = []
    for mod_id, dep_names in incompatible.items():
        mod_result = await db.execute(select(Mod).where(Mod.id == mod_id))
        mod = mod_result.scalar_one_or_none()
        
        if mod:
            result.append({
                "mod_id": mod_id,
                "mod_name": mod.name,
                "incompatible_dependencies": dep_names,
                "suggestion": "These dependencies require Windows-only mods (CET, Codeware)"
            })
    
    return {
        "mods_with_incompatible_deps": result,
        "total_mods_affected": len(result)
    }
