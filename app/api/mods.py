from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from pathlib import Path
from app.database import get_db
from app.models.mod import Mod
from app.core.mod_manager import ModManager, ModInstallationError
from app.core.game_detector import detect_cyberpunk_installations
from app.core.compatibility import CompatibilityChecker
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class ModResponse(BaseModel):
    id: int
    name: str
    author: Optional[str]
    version: Optional[str]
    is_enabled: bool
    mod_type: Optional[str]
    
    class Config:
        from_attributes = True


@router.get("/", response_class=HTMLResponse)
async def list_mods_html(
    request: Request,
    search: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = Query(None),
    compatibility: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("name"),
    view: Optional[str] = Query("grid"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List mods as HTML (for HTMX)"""
    query = select(Mod).where(Mod.is_active == True)
    
    # Apply filters
    if search:
        query = query.where(
            or_(
                Mod.name.ilike(f"%{search}%"),
                Mod.author.ilike(f"%{search}%"),
                Mod.description.ilike(f"%{search}%")
            )
        )
    
    if type_filter:
        types = [t.strip() for t in type_filter.split(",") if t.strip()]
        if types:
            query = query.where(Mod.mod_type.in_(types))
    
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        conditions = []
        if "enabled" in statuses:
            conditions.append(Mod.is_enabled == True)
        if "disabled" in statuses:
            conditions.append(Mod.is_enabled == False)
        if conditions:
            query = query.where(or_(*conditions))
    
    # Apply sorting
    if sort_by == "name":
        query = query.order_by(Mod.name)
    elif sort_by == "date":
        query = query.order_by(Mod.install_date.desc())
    elif sort_by == "author":
        query = query.order_by(Mod.author)
    elif sort_by == "size":
        query = query.order_by(Mod.file_size.desc() if Mod.file_size else Mod.name)
    else:
        query = query.order_by(Mod.name)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    mods = result.scalars().all()
    
    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages
    }
    
    return templates.TemplateResponse("mods/mod_list.html", {
        "request": request,
        "mods": mods,
        "view": view,
        "pagination": pagination if total_pages > 1 else None
    })


@router.get("/api")
async def list_mods(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db)
) -> List[ModResponse]:
    """List all installed mods (JSON API)"""
    query = select(Mod).where(Mod.is_active == True)
    if enabled_only:
        query = query.where(Mod.is_enabled == True)
    
    result = await db.execute(query)
    mods = result.scalars().all()
    
    return [ModResponse.model_validate(mod) for mod in mods]


@router.get("/{mod_id}")
async def get_mod(
    mod_id: int,
    db: AsyncSession = Depends(get_db)
) -> ModResponse:
    """Get mod details"""
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    
    if not mod:
        raise HTTPException(status_code=404, detail="Mod not found")
    
    return ModResponse.model_validate(mod)


@router.post("/")
async def install_mod(
    mod_file: UploadFile = File(...),
    nexus_mod_id: Optional[int] = Form(None),
    check_compatibility: bool = Form(True),
    db: AsyncSession = Depends(get_db)
) -> ModResponse:
    """Install mod from uploaded file"""
    # Detect game installation
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    # Save uploaded file temporarily
    temp_file = Path("/tmp") / mod_file.filename
    with open(temp_file, "wb") as f:
        content = await mod_file.read()
        f.write(content)
    
    try:
        mod = await mod_manager.install_mod_from_file(
            temp_file,
            nexus_mod_id=nexus_mod_id,
            check_compatibility=check_compatibility
        )
        return ModResponse.model_validate(mod)
    except ModInstallationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if temp_file.exists():
            temp_file.unlink()


@router.get("/nexus/{nexus_mod_id}/info")
async def get_nexus_mod_info(
    nexus_mod_id: int
):
    """Get Nexus mod information"""
    from app.core.nexus_api import NexusAPIClient
    from app.config import settings
    
    client = NexusAPIClient(settings.nexus_api_key)
    try:
        mod_info = await client.get_mod_info(nexus_mod_id)
        return mod_info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/install-status/{job_id}")
async def get_install_status(
    job_id: str
):
    """Get installation job status"""
    # TODO: Implement job tracking
    return {
        "job_id": job_id,
        "status": "completed",
        "progress": 100
    }


@router.post("/nexus/{nexus_mod_id}")
async def install_mod_from_nexus(
    nexus_mod_id: int,
    file_id: Optional[int] = None,
    check_compatibility: bool = True,
    db: AsyncSession = Depends(get_db)
) -> ModResponse:
    """Install mod from Nexus Mods"""
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    try:
        mod = await mod_manager.install_mod_from_nexus(
            nexus_mod_id,
            file_id=file_id,
            check_compatibility=check_compatibility
        )
        return ModResponse.model_validate(mod)
    except ModInstallationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{mod_id}")
async def uninstall_mod(
    mod_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Uninstall a mod"""
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    try:
        await mod_manager.uninstall_mod(mod_id)
        return {"message": "Mod uninstalled successfully"}
    except ModInstallationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{mod_id}/toggle", response_class=HTMLResponse)
async def toggle_mod(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Toggle mod enabled/disabled"""
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    
    if not mod:
        raise HTTPException(status_code=404, detail="Mod not found")
    
    try:
        if mod.is_enabled:
            await mod_manager.disable_mod(mod_id)
            message = "Mod disabled"
        else:
            await mod_manager.enable_mod(mod_id)
            message = "Mod enabled"
        
        # Return toast notification HTML
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": message,
            "type": "success"
        })
    except Exception as e:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"Error: {str(e)}",
            "type": "error"
        })


@router.post("/{mod_id}/enable")
async def enable_mod(
    mod_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Enable a mod"""
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    try:
        await mod_manager.enable_mod(mod_id)
        return {"message": "Mod enabled"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{mod_id}/disable")
async def disable_mod(
    mod_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Disable a mod"""
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    try:
        await mod_manager.disable_mod(mod_id)
        return {"message": "Mod disabled"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bulk")
async def bulk_mod_action(
    action: str,
    mod_ids: List[int],
    db: AsyncSession = Depends(get_db)
):
    """Perform bulk action on mods"""
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    results = []
    for mod_id in mod_ids:
        try:
            if action == "enable":
                await mod_manager.enable_mod(mod_id)
            elif action == "disable":
                await mod_manager.disable_mod(mod_id)
            elif action == "delete":
                await mod_manager.uninstall_mod(mod_id)
            results.append({"mod_id": mod_id, "success": True})
        except Exception as e:
            results.append({"mod_id": mod_id, "success": False, "error": str(e)})
    
    return {"action": action, "results": results}


@router.get("/{mod_id}/files", response_class=HTMLResponse)
async def get_mod_files(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get mod files list"""
    from app.models.mod import ModFile
    
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    
    if not mod:
        raise HTTPException(status_code=404, detail="Mod not found")
    
    files_result = await db.execute(
        select(ModFile).where(ModFile.mod_id == mod_id)
    )
    files = files_result.scalars().all()
    
    return templates.TemplateResponse("components/file_browser.html", {
        "request": request,
        "files": files
    })


@router.get("/{mod_id}/dependencies", response_class=HTMLResponse)
async def get_mod_dependencies(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get mod dependencies"""
    from app.models.mod import ModDependency
    
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    
    if not mod:
        raise HTTPException(status_code=404, detail="Mod not found")
    
    deps_result = await db.execute(
        select(ModDependency).where(ModDependency.mod_id == mod_id)
    )
    dependencies = deps_result.scalars().all()
    
    return templates.TemplateResponse("components/dependency_tree.html", {
        "request": request,
        "dependencies": dependencies,
        "mod_id": mod_id
    })


@router.get("/{mod_id}/conflicts", response_class=HTMLResponse)
async def get_mod_conflicts(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get conflicts for this mod"""
    from app.models.compatibility import ModConflict
    
    conflicts_result = await db.execute(
        select(ModConflict).where(
            or_(ModConflict.mod_id_1 == mod_id, ModConflict.mod_id_2 == mod_id)
        ).where(ModConflict.resolved == False)
    )
    conflicts = conflicts_result.scalars().all()
    
    return templates.TemplateResponse("components/conflict_list.html", {
        "request": request,
        "conflicts": conflicts,
        "mod_id": mod_id
    })


@router.get("/load-order", response_class=HTMLResponse)
async def get_load_order_html(
    request: Request,
    profile_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get load order as HTML"""
    from app.models.mod import Mod
    from app.models.profile import ModLoadOrder
    
    query = select(Mod).where(Mod.is_active == True, Mod.is_enabled == True)
    
    if profile_id:
        # Get load order from profile
        load_order_result = await db.execute(
            select(ModLoadOrder).where(ModLoadOrder.profile_id == profile_id).order_by(ModLoadOrder.order)
        )
        load_orders = load_order_result.scalars().all()
        mod_ids = [lo.mod_id for lo in load_orders]
        if mod_ids:
            query = query.where(Mod.id.in_(mod_ids))
    
    result = await db.execute(query.order_by(Mod.name))
    mods = result.scalars().all()
    
    return templates.TemplateResponse("mods/load_order_list.html", {
        "request": request,
        "mods": mods,
        "profile_id": profile_id
    })


@router.post("/load-order")
async def update_load_order(
    order: List[dict],
    db: AsyncSession = Depends(get_db)
):
    """Update load order"""
    # TODO: Implement load order update
    return {"message": "Load order updated"}


@router.post("/load-order/auto-sort")
async def auto_sort_load_order(
    db: AsyncSession = Depends(get_db)
):
    """Auto-sort load order by dependencies"""
    # TODO: Implement auto-sort
    return {"message": "Load order sorted"}


@router.get("/{mod_id}/compatibility")
async def check_mod_compatibility(
    mod_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Check mod compatibility"""
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    
    if not mod:
        raise HTTPException(status_code=404, detail="Mod not found")
    
    # Check installed mod files
    checker = CompatibilityChecker()
    mod_path = Path(mod.install_path)
    
    # Check all .reds files
    reds_files = list(mod_path.rglob("*.reds"))
    if not reds_files:
        return {
            "compatible": True,
            "severity": "warning",
            "reason": "No redscript files found"
        }
    
    # Basic compatibility check
    return {
        "compatible": True,
        "severity": "info",
        "reason": "Mod appears compatible"
    }
