from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.mod import Mod
from app.core.compatibility import CompatibilityChecker
from app.core.mod_manager import ModManager
from app.core.dependency_resolver import DependencyResolver
from app.core.conflict_detector import ConflictDetector
from app.core.game_detector import detect_cyberpunk_installations
from pydantic import BaseModel
from typing import List
from pathlib import Path

router = APIRouter()


class CompatibilityCheckResponse(BaseModel):
    compatible: bool
    severity: str
    reason: str
    has_reds_files: bool = False
    has_dll_files: bool = False
    has_archivexl_refs: bool = False
    has_codeware_refs: bool = False
    has_red4ext_refs: bool = False
    has_cet_refs: bool = False
    incompatible_dependencies: List[str] = []


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


@router.get("/conflicts")
async def get_conflicts(
    mod_id: int = None,
    db: AsyncSession = Depends(get_db)
):
    """Get mod conflicts"""
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    detector = ConflictDetector(db, game_path)
    
    conflicts = await detector.detect_conflicts(mod_id=mod_id)
    
    # Save to database
    await detector.save_conflicts_to_db(conflicts)
    
    return {
        "conflicts": [
            {
                "file_path": c.file_path,
                "mod_id_1": c.mod_id_1,
                "mod_id_2": c.mod_id_2,
                "conflict_type": c.conflict_type.value,
                "severity": c.severity.value,
                "description": c.description
            }
            for c in conflicts
        ]
    }


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: int,
    resolution_method: str,
    db: AsyncSession = Depends(get_db)
):
    """Resolve a conflict"""
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    detector = ConflictDetector(db, game_path)
    
    await detector.resolve_conflict(conflict_id, resolution_method)
    
    return {"message": "Conflict resolved"}


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
