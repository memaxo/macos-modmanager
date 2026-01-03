from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.models.mod import Mod
from app.core.compatibility import CompatibilityChecker
from app.core.mod_manager import ModManager
from app.core.dependency_resolver import DependencyResolver
from app.core.conflict_detector import ConflictDetector
from app.core.game_detector import detect_cyberpunk_installations
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class CompatibilityCheckResponse(BaseModel):
    compatible: bool
    severity: str
    reason: str
    has_reds_files: bool = False
    has_dll_files: bool = False
    has_dylib_files: bool = False  # macOS native libraries
    has_archivexl_refs: bool = False  # Now COMPATIBLE (ported to macOS)
    has_codeware_refs: bool = False   # INCOMPATIBLE (no macOS port)
    has_red4ext_refs: bool = False    # Now COMPATIBLE (ported to macOS)
    has_cet_refs: bool = False        # INCOMPATIBLE (no macOS port)
    has_tweakxl_refs: bool = False    # Now COMPATIBLE (ported to macOS)
    modifies_executable: bool = False
    has_r6_scripts_only: bool = False
    has_red4ext_plugin: bool = False  # Native RED4ext plugin (.dylib)
    has_tweak_files: bool = False     # TweakXL .yaml/.yml files
    incompatible_dependencies: List[str] = []
    ported_dependencies: List[str] = []  # macOS-ported dependencies


@router.get("/check/{mod_id}")
async def check_mod_compatibility(
    mod_id: int,
    db: AsyncSession = Depends(get_db)
) -> CompatibilityCheckResponse:
    """Check compatibility of an installed mod"""
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    
    if not mod:
        raise HTTPException(status_code=404, detail="Mod not found")
    
    # Check installed mod files
    mod_path = Path(mod.install_path)
    checker = CompatibilityChecker()
    
    # Check all .reds files for compatibility issues
    reds_files = list(mod_path.rglob("*.reds"))
    
    if not reds_files:
        return CompatibilityCheckResponse(
            compatible=True,
            severity="warning",
            reason="No redscript files found in mod",
            has_reds_files=False
        )
    
    # Basic check - mod is installed and has redscript files
    # Full compatibility check would require re-scanning the archive
    return CompatibilityCheckResponse(
        compatible=True,
        severity="info",
        reason="Mod appears compatible (redscript files detected)",
        has_reds_files=True
    )


@router.post("/scan")
async def scan_all_mods(db: AsyncSession = Depends(get_db)) -> List[CompatibilityCheckResponse]:
    """Scan all installed mods for compatibility issues"""
    result = await db.execute(select(Mod).where(Mod.is_active == True))
    mods = result.scalars().all()
    
    results = []
    for mod in mods:
        check = await check_mod_compatibility(mod.id, db)
        results.append(check)
    
    return results


@router.get("/conflicts", response_class=HTMLResponse)
async def get_conflicts_html(
    request: Request,
    mod_id: int = None,
    db: AsyncSession = Depends(get_db)
):
    """Get mod conflicts as HTML list"""
    installations = await detect_cyberpunk_installations()
    game_path = Path(installations[0]["path"]) if installations else Path(".")
    detector = ConflictDetector(db, game_path)
    
    # Trigger detection first to ensure DB is up to date
    new_conflicts = await detector.detect_conflicts(mod_id=mod_id)
    await detector.save_conflicts_to_db(new_conflicts)
    
    # Fetch unresolved conflicts with mod names
    from app.models.compatibility import ModConflict
    from sqlalchemy.orm import aliased
    Mod1 = aliased(Mod)
    Mod2 = aliased(Mod)
    
    query = select(ModConflict, Mod1.name.label("mod_name_1"), Mod2.name.label("mod_name_2"))\
        .join(Mod1, ModConflict.mod_id_1 == Mod1.id)\
        .join(Mod2, ModConflict.mod_id_2 == Mod2.id)\
        .where(ModConflict.resolved == False)
        
    if mod_id:
        query = query.where((ModConflict.mod_id_1 == mod_id) | (ModConflict.mod_id_2 == mod_id))
        
    result = await db.execute(query)
    conflicts = result.all()
    
    conflicts_data = [
            {
            "id": c.ModConflict.id,
            "file_path": c.ModConflict.file_path,
            "mod_name_1": c.mod_name_1,
            "mod_name_2": c.mod_name_2,
            "conflict_type": c.ModConflict.conflict_type,
            "severity": c.ModConflict.severity,
            "detected_at": c.ModConflict.detected_at.strftime("%Y-%m-%d %H:%M") if c.ModConflict.detected_at else "Unknown"
            }
            for c in conflicts
        ]
    
    return templates.TemplateResponse("components/conflict_list.html", {
        "request": request,
        "conflicts": conflicts_data
    })


@router.get("/conflicts/{conflict_id}", response_class=HTMLResponse)
async def get_conflict_detail(
    conflict_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get detail for a specific conflict"""
    installations = await detect_cyberpunk_installations()
    game_path = Path(installations[0]["path"]) if installations else Path(".")
    detector = ConflictDetector(db, game_path)
    
    details = await detector.get_conflict_details(conflict_id)
    if not details:
        raise HTTPException(status_code=404, detail="Conflict not found")
        
    return templates.TemplateResponse("conflicts/resolve_modal.html", {
        "request": request,
        "conflict": details
    })


@router.post("/conflicts/resolve", response_class=HTMLResponse)
async def resolve_conflict_html(
    request: Request,
    conflict_id: int = Form(...),
    winning_mod_id: int = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Resolve a conflict via HTML form"""
    installations = await detect_cyberpunk_installations()
    game_path = Path(installations[0]["path"]) if installations else Path(".")
    detector = ConflictDetector(db, game_path)
    
    await detector.resolve_conflict(conflict_id, f"mod_{winning_mod_id}_wins")
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": "Conflict resolved successfully",
        "type": "success"
    })


@router.get("/dependencies")
async def get_dependencies(db: AsyncSession = Depends(get_db)):
    """Get dependency status for all mods"""
    resolver = DependencyResolver(db)
    missing = await resolver.find_missing_dependencies()
    incompatible = await resolver.find_incompatible_dependencies()
    
    return {
        "missing": missing,
        "incompatible": incompatible
    }


@router.get("/dependencies/{mod_id}")
async def get_mod_dependencies(
    mod_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get dependencies for a specific mod"""
    resolver = DependencyResolver(db)
    result = await resolver.resolve_dependencies(mod_id)
    return result
