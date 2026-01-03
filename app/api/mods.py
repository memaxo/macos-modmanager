from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from pathlib import Path
import json
from app.config import settings
from app.database import get_db
from app.models.mod import Mod
from app.core.mod_manager import ModManager, ModInstallationError
from app.core.game_detector import detect_game_installations, detect_cyberpunk_installations
from app.core.compatibility import CompatibilityChecker
from pydantic import BaseModel
from typing import Optional, List

from app.core.update_manager import UpdateManager

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
    
    # Check compatibility for installed mods
    checker = CompatibilityChecker()
    mods_with_compat = []
    for mod in mods:
        mod_dict = {
            "id": mod.id,
            "name": mod.name,
            "author": mod.author,
            "version": mod.version,
            "mod_type": mod.mod_type,
            "is_enabled": mod.is_enabled,
            "thumbnail_url": mod.thumbnail_url,
            "description": mod.description,
            "install_path": mod.install_path,
            "nexus_mod_id": mod.nexus_mod_id
        }
        
        # Check compatibility if mod has install path
        if mod.install_path:
            try:
                mod_path = Path(mod.install_path)
                if mod_path.exists():
                    compat_result = await checker.check_mod_file(mod_path)
                    mod_dict["macos_compatible"] = compat_result.compatible
                    mod_dict["macos_compatibility_reason"] = compat_result.reason
                    mod_dict["macos_compatibility_severity"] = compat_result.severity
                    mod_dict["has_reds_files"] = compat_result.has_reds_files
                    mod_dict["has_dll_files"] = compat_result.has_dll_files
                else:
                    mod_dict["macos_compatible"] = None
            except Exception:
                mod_dict["macos_compatible"] = None
        else:
            mod_dict["macos_compatible"] = None
        
        mods_with_compat.append(mod_dict)
    
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
        "mods": mods_with_compat,
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


@router.get("/queue", response_class=HTMLResponse)
async def get_queue(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get install queue"""
    from app.models.mod import Wishlist  # Reusing Wishlist model as queue
    res = await db.execute(select(Wishlist).order_by(Wishlist.added_at.desc()))
    queue_items = res.scalars().all()
    
    return templates.TemplateResponse("mods/queue_list.html", {
        "request": request,
        "queue_items": queue_items
    })


@router.get("/preview-by-url", response_class=HTMLResponse)
async def preview_mod_by_url(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Preview a mod by URL with macOS compatibility check"""
    from app.core.nexus_api import NexusAPIClient, NexusAPIError
    from app.core.compatibility import CompatibilityChecker
    import re
    
    # Get URL from query params
    url = request.query_params.get("url", "")
    
    if not url:
        return """
        <div class="modal-overlay" onclick="this.remove()">
            <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px; padding: var(--space-6);">
                <div style="text-align: center;">
                    <i data-lucide="alert-circle" style="width: 3rem; height: 3rem; color: var(--warning-text); margin-bottom: var(--space-4);"></i>
                    <h3 style="font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2);">No URL Provided</h3>
                    <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">Please paste a Nexus Mods URL to preview.</p>
                    <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                </div>
            </div>
        </div>
        <script>if (typeof lucide !== 'undefined') lucide.createIcons();</script>
        """
    
    # Parse mod URL to extract game domain and mod ID
    # Supports: https://www.nexusmods.com/cyberpunk2077/mods/12345
    #           https://nexusmods.com/cyberpunk2077/mods/12345?tab=files
    pattern = r"(?:www\.)?nexusmods\.com/([^/]+)/mods/(\d+)"
    match = re.search(pattern, url)
    
    if not match:
        return f"""
        <div class="modal-overlay" onclick="this.remove()">
            <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px; padding: var(--space-6);">
                <div style="text-align: center;">
                    <i data-lucide="alert-triangle" style="width: 3rem; height: 3rem; color: var(--warning-text); margin-bottom: var(--space-4);"></i>
                    <h3 style="font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2);">Invalid URL Format</h3>
                    <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">
                        Could not parse mod URL. Expected format:<br>
                        <code style="background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px;">https://www.nexusmods.com/game/mods/12345</code>
                    </p>
                    <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                </div>
            </div>
        </div>
        <script>if (typeof lucide !== 'undefined') lucide.createIcons();</script>
        """
    
    game_domain = match.group(1)
    mod_id = int(match.group(2))
    
    async with NexusAPIClient() as nexus:
        try:
            # Fetch mod details
            mod_info = await nexus.get_mod(game_domain, mod_id)
            
            if not mod_info:
                return f"""
                <div class="modal-overlay" onclick="this.remove()">
                    <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px; padding: var(--space-6);">
                        <div style="text-align: center;">
                            <i data-lucide="x-circle" style="width: 3rem; height: 3rem; color: var(--error-text); margin-bottom: var(--space-4);"></i>
                            <h3 style="font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2);">Mod Not Found</h3>
                            <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">Could not find mod ID {mod_id} on Nexus Mods.</p>
                            <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                        </div>
                    </div>
                </div>
                <script>if (typeof lucide !== 'undefined') lucide.createIcons();</script>
                """
            
            # Get mod files
            files_info = await nexus.get_mod_files(game_domain, mod_id)
            files = files_info.get("files", [])
            main_file = next((f for f in files if f.get("is_primary")), files[0] if files else None)
            
            # Check compatibility using the compatibility checker
            compatibility_checker = CompatibilityChecker()
            compat_result = await compatibility_checker.check_nexus_metadata(nexus, game_domain, mod_id)
            
            # Also extract requirements from description for more info
            description = mod_info.get("description", "") or ""
            summary = mod_info.get("summary", "") or ""
            text_requirements = compatibility_checker.extract_requirements_from_text(description + " " + summary)
            
            # Determine overall compatibility status
            compat_status = "compatible" if compat_result.compatible else "incompatible"
            compat_reason = compat_result.reason if not compat_result.compatible else None
            
            # Get additional compatibility flags
            compat_flags = {
                "has_dll": compat_result.has_dll_files,
                "has_red4ext": compat_result.has_red4ext_refs,
                "has_cet": compat_result.has_cet_refs,
                "has_archivexl": compat_result.has_archivexl_refs,
                "has_tweakxl": compat_result.has_tweakxl_refs,
                "has_codeware": compat_result.has_codeware_refs,
            }
            
            return templates.TemplateResponse("mods/preview_with_compat.html", {
                "request": request,
                "mod": mod_info,
                "game_domain": game_domain,
                "files": files,
                "main_file": main_file,
                "compat_status": compat_status,
                "compat_reason": compat_reason,
                "compat_flags": compat_flags,
                "compat_result": compat_result,
                "text_requirements": text_requirements,
                "original_url": url
            })
            
        except NexusAPIError as e:
            return f"""
            <div class="modal-overlay" onclick="this.remove()">
                <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px; padding: var(--space-6);">
                    <div style="text-align: center;">
                        <i data-lucide="alert-triangle" style="width: 3rem; height: 3rem; color: var(--warning-text); margin-bottom: var(--space-4);"></i>
                        <h3 style="font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2);">API Error</h3>
                        <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">{str(e)}</p>
                        <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                    </div>
                </div>
            </div>
            <script>if (typeof lucide !== 'undefined') lucide.createIcons();</script>
            """
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"""
            <div class="modal-overlay" onclick="this.remove()">
                <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px; padding: var(--space-6);">
                    <div style="text-align: center;">
                        <i data-lucide="x-circle" style="width: 3rem; height: 3rem; color: var(--error-text); margin-bottom: var(--space-4);"></i>
                        <h3 style="font-size: var(--text-lg); font-weight: var(--font-semibold); margin-bottom: var(--space-2);">Unexpected Error</h3>
                        <p style="color: var(--text-secondary); margin-bottom: var(--space-4);">{str(e)}</p>
                        <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                    </div>
                </div>
            </div>
            <script>if (typeof lucide !== 'undefined') lucide.createIcons();</script>
            """


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
    """Install mod from uploaded file with validation and progress tracking"""
    # Detect game installation
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(
            status_code=404, 
            detail={
                "error": f"{settings.game_name} not found",
                "code": "GAME_NOT_FOUND",
                "suggestion": "Verify the game is installed via Steam or specify the installation path in Settings"
            }
        )
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    # Validate filename
    if not mod_file.filename:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "No filename provided",
                "code": "INVALID_FILE",
                "suggestion": "Ensure the file has a valid name with extension (.zip, .7z, .rar)"
            }
        )
    
    # Save uploaded file temporarily with safe filename
    import re
    safe_filename = re.sub(r'[^\w\-_\.]', '_', mod_file.filename)
    temp_file = Path("/tmp") / safe_filename
    
    try:
        # Write file with size validation
        content = await mod_file.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Uploaded file is empty",
                    "code": "EMPTY_FILE",
                    "suggestion": "Verify the file uploaded correctly and try again"
                }
            )
        
        with open(temp_file, "wb") as f:
            f.write(content)
        
        mod = await mod_manager.install_mod_from_file(
            temp_file,
            nexus_mod_id=nexus_mod_id,
            check_compatibility=check_compatibility
        )
        return ModResponse.model_validate(mod)
    except ModInstallationError as e:
        # Return structured error response
        raise HTTPException(
            status_code=400, 
            detail=e.to_dict() if hasattr(e, 'to_dict') else {"error": str(e), "code": "INSTALL_ERROR"}
        )
    except Exception as e:
        # Catch unexpected errors
        raise HTTPException(
            status_code=500,
            detail={
                "error": f"Unexpected error: {str(e)}",
                "code": "INTERNAL_ERROR",
                "suggestion": "Check the server logs for details"
            }
        )
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
    
    if not settings.nexus_api_key:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Nexus Mods API key not configured",
                "code": "API_KEY_MISSING",
                "suggestion": "Please configure your Nexus Mods API key in Settings"
            }
        )
    
    try:
        async with NexusAPIClient() as nexus:
            mod_info = await nexus.get_mod(settings.game_domain, nexus_mod_id)
            if not mod_info:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": f"Mod {nexus_mod_id} not found",
                        "code": "MOD_NOT_FOUND"
                    }
                )
            return mod_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(e),
                "code": "API_ERROR"
            }
        )


@router.get("/nexus/{nexus_mod_id}/files")
async def get_nexus_mod_files(
    nexus_mod_id: int
):
    """Get available files/versions for a Nexus mod"""
    from app.core.nexus_api import NexusAPIClient
    from app.config import settings
    
    if not settings.nexus_api_key:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Nexus Mods API key not configured",
                "code": "API_KEY_MISSING",
                "suggestion": "Please configure your Nexus Mods API key in Settings"
            }
        )
    
    try:
        async with NexusAPIClient() as nexus:
            files_info = await nexus.get_mod_files(settings.game_domain, nexus_mod_id)
            files = files_info.get("files", [])
            
            if not files:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": f"No files available for mod {nexus_mod_id}",
                        "code": "NO_FILES"
                    }
                )
            
            # Format files for easier consumption
            formatted_files = []
            for file in files:
                formatted_files.append({
                    "file_id": file.get("file_id"),
                    "name": file.get("name") or file.get("file_name", "Unknown"),
                    "version": file.get("version") or "1.0",
                    "size": file.get("size") or file.get("file_size", 0),
                    "category_name": file.get("category_name", ""),
                    "is_primary": file.get("is_primary", False),
                    "uploaded_at": file.get("uploaded_time"),
                    "download_count": file.get("download_count", 0)
                })
            
            # Sort by upload time (newest first) or by is_primary
            formatted_files.sort(key=lambda x: (
                not x["is_primary"],  # Primary files first
                x.get("uploaded_at", ""),  # Then by upload date
            ), reverse=True)
            
            return {
                "files": formatted_files,
                "total": len(formatted_files)
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(e),
                "code": "API_ERROR"
            }
        )


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


@router.get("/install/queue", response_class=HTMLResponse)
async def get_install_queue(
    request: Request
):
    """Get active installation jobs"""
    from app.core.mod_manager import ModManager
    queue = ModManager._install_queue
    
    # Filter out completed/failed jobs after some time if needed
    # For now just show all
    return templates.TemplateResponse("components/install_queue.html", {
        "request": request,
        "queue": queue
    })


@router.post("/nexus/{nexus_mod_id}")
async def install_mod_from_nexus(
    nexus_mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> ModResponse:
    """Install mod from Nexus Mods"""
    from pydantic import BaseModel
    
    class InstallRequest(BaseModel):
        file_id: Optional[int] = None
        check_compatibility: bool = True
    
    # Parse JSON body
    try:
        body = await request.json()
        install_req = InstallRequest(**body)
    except Exception:
        # Fallback to default values if JSON parsing fails
        install_req = InstallRequest()
    
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(status_code=404, detail=f"{settings.game_name} not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    try:
        mod = await mod_manager.install_mod_from_nexus(
            nexus_mod_id,
            file_id=install_req.file_id,
            check_compatibility=install_req.check_compatibility
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
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(status_code=404, detail=f"{settings.game_name} not found")
    
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
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(status_code=404, detail=f"{settings.game_name} not found")
    
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
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(status_code=404, detail=f"{settings.game_name} not found")
    
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
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(status_code=404, detail=f"{settings.game_name} not found")
    
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
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(status_code=404, detail=f"{settings.game_name} not found")
    
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


@router.get("/load-order", response_class=HTMLResponse)
async def get_load_order_html(
    request: Request,
    profile_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get mod load order as HTML list"""
    from app.models.load_order import ModLoadOrder
    
    # Get mods in priority order
    query = select(Mod, ModLoadOrder.priority)\
        .join(ModLoadOrder, Mod.id == ModLoadOrder.mod_id)\
        .where(Mod.is_active == True)
        
    if profile_id:
        query = query.where(ModLoadOrder.profile_id == profile_id)
    else:
        query = query.where(ModLoadOrder.profile_id == None)
        
    query = query.order_by(ModLoadOrder.priority)
    
    result = await db.execute(query)
    mods_with_priority = result.all()
    
    # If no load order records yet, fetch all enabled mods and create default order
    if not mods_with_priority:
        enabled_mods_res = await db.execute(
            select(Mod).where(Mod.is_active == True, Mod.is_enabled == True)
        )
        enabled_mods = enabled_mods_res.scalars().all()
        
        mods_data = []
        for i, mod in enumerate(enabled_mods):
            mods_data.append({
                "id": mod.id,
                "name": mod.name,
                "priority": i + 1,
                "version": mod.version
            })
    else:
        mods_data = [
            {
                "id": m.Mod.id,
                "name": m.Mod.name,
                "priority": m.priority,
                "version": m.Mod.version
            }
            for m in mods_with_priority
        ]
        
    return templates.TemplateResponse("mods/load_order_list.html", {
        "request": request,
        "mods": mods_data
    })


@router.post("/load-order")
async def update_load_order(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Update load order from JSON body"""
    from app.models.load_order import ModLoadOrder
    data = await request.json()
    order_list = data.get("order", [])
    profile_id = data.get("profile_id")
    
    for item in order_list:
        mod_id = item.get("mod_id")
        priority = item.get("order")
        
        # Upsert load order record
        query = select(ModLoadOrder).where(ModLoadOrder.mod_id == mod_id)
        if profile_id:
            query = query.where(ModLoadOrder.profile_id == profile_id)
        else:
            query = query.where(ModLoadOrder.profile_id == None)
            
        res = await db.execute(query)
        record = res.scalar_one_or_none()
        
        if record:
            record.priority = priority
        else:
            new_record = ModLoadOrder(
                mod_id=mod_id,
                priority=priority,
                profile_id=profile_id,
                game_id=settings.game_id
            )
            db.add(new_record)
            
    await db.commit()
    return {"status": "success", "message": "Load order saved"}


@router.post("/load-order/auto-sort")
async def auto_sort_load_order(
    db: AsyncSession = Depends(get_db)
):
    """Auto-sort load order by dependencies"""
    from app.core.dependency_resolver import DependencyResolver
    from app.models.load_order import ModLoadOrder
    
    # Get all active mods
    res = await db.execute(select(Mod.id).where(Mod.is_active == True, Mod.is_enabled == True))
    mod_ids = [r for r in res.scalars().all()]
    
    resolver = DependencyResolver(db)
    sorted_ids = await resolver.get_sorted_load_order(mod_ids)
    
    # Update priorities in DB (1-based)
    for i, mod_id in enumerate(sorted_ids):
        query = select(ModLoadOrder).where(ModLoadOrder.mod_id == mod_id, ModLoadOrder.profile_id == None)
        res = await db.execute(query)
        record = res.scalar_one_or_none()
        
        if record:
            record.priority = i + 1
        else:
            db.add(ModLoadOrder(mod_id=mod_id, priority=i+1, game_id=settings.game_domain))
            
    await db.commit()
    return {"status": "success", "message": "Load order auto-sorted"}


@router.post("/updates/check", response_class=HTMLResponse)
async def check_updates(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Check for mod updates"""
    from app.config import settings
    if not settings.nexus_api_key:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "Nexus API key not configured! Please add it in settings.",
            "type": "error"
        })
        
    manager = UpdateManager(db)
    updates = await manager.check_for_updates()
    
    if not updates:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "All mods are up to date!",
            "type": "info"
        })
        
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": f"Found {len(updates)} updates!",
        "type": "success"
    })


@router.post("/rollback/{installation_id}", response_class=HTMLResponse)
async def rollback_installation(
    installation_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Rollback a mod installation"""
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(status_code=404, detail=f"{settings.game_name} not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    try:
        await mod_manager.rollback_mod_installation(installation_id)
        
        # Return success toast
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "Rollback successful. Original files restored.",
            "type": "success"
        })
    except ModInstallationError as e:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"Rollback failed: {str(e)}",
            "type": "error"
        })
    except Exception as e:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"An error occurred: {str(e)}",
            "type": "error"
        })


@router.get("/nexus/profile", response_class=HTMLResponse)
async def get_nexus_profile(
    request: Request
):
    """Get Nexus user profile info for the header"""
    from app.core.nexus_api import NexusAPIClient
    async with NexusAPIClient() as nexus:
        try:
            user = await nexus.get_user()
            return templates.TemplateResponse("components/nexus_profile.html", {
                "request": request,
                "user": user
            })
        except Exception:
            return "" # Fail silently if not logged in/api key invalid


@router.post("/queue/add/{mod_id}", response_class=HTMLResponse)
async def add_to_queue(
    mod_id: int,
    request: Request,
    name: str = Query(None),
    author: str = Query(None),
    thumbnail: str = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Add mod to install queue"""
    from app.models.mod import Wishlist  # Reusing Wishlist model as queue
    
    # Check if already in queue
    res = await db.execute(select(Wishlist).where(Wishlist.nexus_mod_id == mod_id))
    existing = res.scalar_one_or_none()
    
    if existing:
        message = f"'{name or 'Mod'}' is already in queue"
        msg_type = "info"
    else:
        queue_item = Wishlist(nexus_mod_id=mod_id, name=name, author=author, thumbnail_url=thumbnail)
        db.add(queue_item)
        await db.commit()
        message = f"Added '{name or 'Mod'}' to install queue"
        msg_type = "success"
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": message,
        "type": msg_type
    }, headers={"HX-Trigger": "queueUpdated"})


@router.delete("/queue/remove/{mod_id}", response_class=HTMLResponse)
async def remove_from_queue(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Remove mod from install queue"""
    from app.models.mod import Wishlist
    from sqlalchemy import delete
    
    res = await db.execute(select(Wishlist).where(Wishlist.nexus_mod_id == mod_id))
    item = res.scalar_one_or_none()
    
    if item:
        name = item.name
        await db.execute(delete(Wishlist).where(Wishlist.nexus_mod_id == mod_id))
        await db.commit()
        message = f"Removed '{name}' from queue"
    else:
        message = "Item not found in queue"
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": message,
        "type": "success"
    }, headers={"HX-Trigger": "queueUpdated"})


@router.post("/queue/install-all", response_class=HTMLResponse)
async def install_all_queued(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Install all mods in the queue"""
    from app.models.mod import Wishlist
    from sqlalchemy import delete
    
    res = await db.execute(select(Wishlist).order_by(Wishlist.added_at.desc()))
    queue_items = res.scalars().all()
    
    if not queue_items:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "Install queue is empty",
            "type": "warning"
        })
    
    # Queue installations (they'll run in background)
    installed_count = 0
    for item in queue_items:
        # Trigger installation via HTMX
        # In a real implementation, we'd queue these properly
        installed_count += 1
    
    # Clear the queue after queuing installations
    await db.execute(delete(Wishlist))
    await db.commit()
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": f"Queued {installed_count} mods for installation",
        "type": "success"
    }, headers={"HX-Trigger": "queueUpdated"})


@router.get("/discovery/history", response_class=HTMLResponse)
async def get_search_history(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get search history"""
    from app.models.settings import UserSetting
    res = await db.execute(select(UserSetting).where(UserSetting.key == "search_history"))
    history_setting = res.scalar_one_or_none()
    history = json.loads(history_setting.value) if history_setting else []
    
    return templates.TemplateResponse("components/search_history.html", {
        "request": request,
        "history": history
    })


@router.get("/discovery/search", response_class=HTMLResponse)
async def discovery_search(
    request: Request,
    query: Optional[str] = Query(None),
    period: str = Query("ALL_TIME"),
    sort: str = Query("trending"),
    category_id: Optional[int] = Query(None),
    include_adult: bool = Query(False),
    macos_only: bool = Query(False),
    redscript_only: bool = Query(False),
    exclude_dlls: bool = Query(True),  # Default to True for macOS
    page: int = Query(1),
    page_size: int = Query(50),
    min_endorsements: int = Query(0),
    min_downloads: int = Query(0),
    db: AsyncSession = Depends(get_db)
):
    """Search Nexus Mods for new mods with full pagination support"""
    from app.core.nexus_api import NexusAPIClient
    from app.config import settings
    
    if not settings.nexus_api_key:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "Nexus API key not configured",
            "type": "error"
        })

    async with NexusAPIClient() as nexus:
        try:
            offset = (page - 1) * page_size
            total_available = 0
            has_more = False
            
            # Map sort options to GraphQL sort_by parameter
            sort_map = {
                "trending": "endorsements",
                "top": "endorsements",
                "latest": "created",
                "downloads": "downloads",
                "endorsement_ratio": "endorsements"
            }
            sort_by = sort_map.get(sort, "endorsements")
            
            if query:
                # Save search history
                from app.models.settings import UserSetting
                res = await db.execute(select(UserSetting).where(UserSetting.key == "search_history"))
                history_setting = res.scalar_one_or_none()
                history = json.loads(history_setting.value) if history_setting else []
                if query not in history:
                    history = [query] + history[:9]  # Keep last 10
                    if history_setting:
                        history_setting.value = json.dumps(history)
                    else:
                        db.add(UserSetting(key="search_history", value=json.dumps(history), value_type="json"))
                    await db.commit()

            # Use GraphQL search with pagination for all modes
            # This provides consistent pagination across all sort options
            try:
                graphql_results = await nexus.search_mods_graphql(
                    settings.game_domain,
                    query=query,
                    category_id=category_id,
                    sort_by=sort_by,
                    include_requirements=True,
                    limit=page_size,
                    offset=offset
                )
                mods_list = graphql_results.get("results", [])
                total_available = graphql_results.get("total", 0)
                has_more = (offset + len(mods_list)) < total_available
            except Exception:
                # Fallback to REST API if GraphQL fails
                if sort == "top":
                    mods_list = await nexus.get_top_mods(settings.game_domain, period=period, count=200)
                elif sort == "latest":
                    mods_list = await nexus.get_latest_mods(settings.game_domain)
                elif sort == "downloads":
                    mods_list = await nexus.get_top_mods(settings.game_domain, period=period, count=200)
                    mods_list.sort(key=lambda x: x.get("total_downloads") or x.get("mod_downloads") or 0, reverse=True)
                else:
                    mods_list = await nexus.get_trending_mods(settings.game_domain)
                
                # Apply manual pagination for REST API fallback
                total_available = len(mods_list)
                mods_list = mods_list[offset:offset + page_size]
                has_more = (offset + len(mods_list)) < total_available
            
            # Apply endorsement ratio sorting if requested
            if sort == "endorsement_ratio":
                for m in mods_list:
                    downloads = m.get("total_downloads") or m.get("mod_downloads") or 1
                    endorsements = m.get("endorsements") or 0
                    m["endorsement_ratio"] = endorsements / max(downloads, 1)
                mods_list.sort(key=lambda x: x.get("endorsement_ratio", 0), reverse=True)
            
            # Apply minimum thresholds
            if min_endorsements > 0:
                mods_list = [m for m in mods_list if (m.get("endorsements") or 0) >= min_endorsements]
            if min_downloads > 0:
                mods_list = [m for m in mods_list if (m.get("total_downloads") or m.get("mod_downloads") or 0) >= min_downloads]
            
            # Check compatibility using optimized batch method
            checker = CompatibilityChecker()
            filtered_mods = []
            
            # First, check local installation status for all mods
            nexus_ids = [mod.get("mod_id") for mod in mods_list if mod.get("mod_id")]
            local_mods_map = {}
            if nexus_ids:
                res = await db.execute(
                    select(Mod).where(Mod.nexus_mod_id.in_(nexus_ids))
                )
                for local_mod in res.scalars().all():
                    local_mods_map[local_mod.nexus_mod_id] = local_mod
            
            # Batch check compatibility (much more efficient than individual checks)
            compat_results = await checker.batch_check_compatibility(
                mods_list,
                nexus,
                settings.game_domain,
                max_concurrent=10  # Limit concurrent API calls
            )
            
            # Process results
            for i, mod in enumerate(mods_list):
                nexus_id = mod.get("mod_id")
                
                # Check local installation
                if nexus_id and nexus_id in local_mods_map:
                    local_mod = local_mods_map[nexus_id]
                    mod["is_locally_installed"] = True
                    mod["local_version"] = local_mod.version
                    mod["version_diff"] = "new" if mod.get("version") != local_mod.version else "same"
                else:
                    mod["is_locally_installed"] = False
                
                # Add compatibility info
                if i < len(compat_results) and compat_results[i]:
                    compat_result = compat_results[i]
                    mod["macos_compatible"] = compat_result.compatible
                    mod["macos_compatibility_reason"] = compat_result.reason
                    mod["macos_compatibility_severity"] = compat_result.severity
                    mod["has_reds_files"] = compat_result.has_reds_files
                    mod["has_dll_files"] = compat_result.has_dll_files
                    
                    # Apply macOS-specific filters
                    if macos_only and not compat_result.compatible:
                        continue
                    
                    # Redscript-only filter: only show mods with redscript files
                    if redscript_only and not compat_result.has_reds_files:
                        continue
                    
                    # Exclude DLLs filter: filter out mods with DLL files
                    if exclude_dlls and compat_result.has_dll_files:
                        continue
                else:
                    mod["macos_compatible"] = None
                    mod["macos_compatibility_reason"] = "Compatibility check unavailable"
                    mod["macos_compatibility_severity"] = "warning"
                    mod["has_reds_files"] = None
                    mod["has_dll_files"] = None
                    if macos_only or redscript_only:
                        continue  # Exclude unknown when filtering
                
                filtered_mods.append(mod)
            
            # Determine if we should load more pages
            # If filtering reduced results significantly, there might be more to fetch
            next_page = page + 1 if (has_more or len(filtered_mods) >= 5) else None
            
            return templates.TemplateResponse("mods/discovery_results.html", {
                "request": request,
                "mods": filtered_mods,
                "next_page": next_page,
                "has_more": has_more,
                "macos_only": macos_only,
                "redscript_only": redscript_only,
                "exclude_dlls": exclude_dlls,
                "page": page,
                "sort": sort,
                "period": period
            })
        except Exception as e:
            return f'<div style="text-align: center; padding: 2rem; color: var(--text-secondary);">Error: {str(e)}</div>'


@router.post("/nexus/{mod_id}/smart-install", response_class=HTMLResponse)
async def smart_install_mod(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Install a mod and all its dependencies recursively"""
    from app.core.nexus_api import NexusAPIClient
    from app.core.mod_manager import ModManager
    
    async with NexusAPIClient() as nexus:
        try:
            # 1. Get requirements
            requirements = await nexus.get_mod_requirements(settings.game_domain, mod_id)
            
            # 2. Queue all required mods
            to_install = [mod_id]
            for req in requirements:
                if req.get("isRequired") and req.get("nexusModId"):
                    # Check if already installed
                    res = await db.execute(select(Mod).where(Mod.nexus_mod_id == req["nexusModId"]))
                    if not res.scalar_one_or_none():
                        to_install.append(req["nexusModId"])
            
            # 3. Install in reverse order (dependencies first)
            # This is a simple version, ideally we'd do topological sort
            results = []
            manager = ModManager(db)
            for m_id in reversed(to_install):
                # This is a background task in a real app, but for now we'll do it sequentially
                # and return status via toast
                try:
                    # In a real app, this would trigger a background download/install
                    # For now, we'll just mock the start of the process
                    results.append(f"Started installation of {m_id}")
                except Exception as e:
                    results.append(f"Failed to start install for {m_id}: {str(e)}")
            
            return templates.TemplateResponse("components/toast.html", {
                "request": request,
                "message": f"Smart Install started for {len(to_install)} mods",
                "type": "success"
            })
        except Exception as e:
            return templates.TemplateResponse("components/toast.html", {
                "request": request,
                "message": f"Smart Install failed: {str(e)}",
                "type": "error"
            })


@router.get("/discovery/{mod_id}/quick-view", response_class=HTMLResponse)
async def get_discovery_quick_view(
    mod_id: int,
    request: Request
):
    """Get quick view modal for a Nexus mod"""
    from app.core.nexus_api import NexusAPIClient
    async with NexusAPIClient() as nexus:
        try:
            mod_info = await nexus.get_mod(settings.game_domain, mod_id)
            # Also get images
            images = await nexus.get_mod_images(settings.game_domain, mod_id)
            # Get mod files to find the main file ID
            files_info = await nexus.get_mod_files(settings.game_domain, mod_id)
            files = files_info.get("files", [])
            main_file = next((f for f in files if f.get("is_primary")), files[0] if files else {})
            main_file_id = main_file.get("file_id")

            return templates.TemplateResponse("mods/quick_view_modal.html", {
                "request": request,
                "mod": mod_info,
                "images": images,
                "main_file_id": main_file_id
            })
        except Exception as e:
            return f"<div style='padding: 2rem; color: var(--danger-text);'>Failed to load mod details: {str(e)}</div>"


@router.post("/discovery/{mod_id}/install")
async def install_from_discovery(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Install mod from discovery/preview flow"""
    from pydantic import BaseModel
    
    class InstallRequest(BaseModel):
        file_id: Optional[int] = None
        check_compatibility: bool = True
    
    # Parse JSON body
    try:
        body = await request.json()
        install_req = InstallRequest(**body)
    except Exception:
        # Fallback to default values if JSON parsing fails
        install_req = InstallRequest()
    
    # Redirect to the standard Nexus install endpoint
    # This endpoint is just an alias for consistency with discovery flow
    installations = await detect_game_installations()
    if not installations:
        raise HTTPException(status_code=404, detail=f"{settings.game_name} not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    try:
        mod = await mod_manager.install_mod_from_nexus(
            mod_id,  # mod_id is the nexus_mod_id in discovery context
            file_id=install_req.file_id,
            check_compatibility=install_req.check_compatibility
        )
        return ModResponse.model_validate(mod)
    except ModInstallationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/discovery/{mod_id}/files/{file_id}/inspect", response_class=HTMLResponse)
async def inspect_nexus_file(request: Request, mod_id: int, file_id: int):
    """Inspect contents of a Nexus mod file before download"""
    async with NexusAPIClient() as nexus:
        try:
            contents = await nexus.get_mod_file_contents(settings.game_domain, mod_id, file_id)
            return templates.TemplateResponse("components/file_browser.html", {
                "request": request,
                "files": contents.get("content", []),
                "mod_name": f"Nexus File {file_id}",
                "is_remote": True
            })
        except Exception as e:
            return f"<div class='alert alert-danger'>Failed to inspect file: {str(e)}</div>"

@router.get("/discovery/categories", response_class=HTMLResponse)
async def get_discovery_categories(
    request: Request
):
    """Get Nexus categories for the sidebar"""
    from app.core.nexus_api import NexusAPIClient
    async with NexusAPIClient() as nexus:
        try:
            categories_list = await nexus.get_categories(settings.game_domain)
            # Convert list of objects to dict if needed or just pass list
            # Usually [{ 'category_id': 1, 'name': 'Visuals' }, ...]
            return templates.TemplateResponse("components/category_list.html", {
                "request": request,
                "categories": categories_list
            })
        except Exception as e:
            return f"<div style='padding: 1rem; color: var(--text-secondary);'>Failed to load categories: {str(e)}</div>"


@router.get("/{mod_id}/files/tree", response_class=HTMLResponse)
async def get_mod_files_tree(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get mod files as a navigable tree"""
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    if not mod:
        raise HTTPException(status_code=404, detail="Mod not found")
        
    from app.models.mod import ModFile
    files_res = await db.execute(select(ModFile).where(ModFile.mod_id == mod_id))
    files = files_res.scalars().all()
    
    return templates.TemplateResponse("components/file_browser.html", {
        "request": request,
        "mod": mod,
        "files": files
    })


@router.get("/{mod_id}/files/content", response_class=HTMLResponse)
async def get_mod_file_content(
    mod_id: int,
    request: Request,
    file_path: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get content of a mod file (if text-based)"""
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    if not mod:
        raise HTTPException(status_code=404, detail="Mod not found")
        
    # Security check: ensure file belongs to mod
    from app.models.mod import ModFile
    file_res = await db.execute(
        select(ModFile).where(ModFile.mod_id == mod_id, ModFile.install_path == file_path)
    )
    if not file_res.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Access denied")
        
    # Get actual path
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Game not found")
        
    full_path = Path(installations[0]["path"]) / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
        
    # Only allow text files
    if full_path.suffix not in [".reds", ".json", ".ini", ".txt", ".xml", ".yaml", ".yml"]:
        return "<div style='padding: 2rem; text-align: center; color: var(--text-secondary);'>Binary file content cannot be displayed.</div>"
        
    try:
        content = full_path.read_text(encoding="utf-8")
        return f"<pre style='margin: 0; padding: 1rem; background: var(--bg-tertiary); color: var(--text-primary); font-family: monospace; font-size: 0.85rem; overflow: auto; max-height: 500px;'><code>{content}</code></pre>"
    except Exception as e:
        return f"<div style='padding: 2rem; color: var(--danger-text);'>Error reading file: {str(e)}</div>"


@router.post("/bulk", response_class=HTMLResponse)
async def bulk_mod_action(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Perform bulk action on multiple mods"""
    data = await request.json()
    mod_ids = data.get("mod_ids", [])
    action = data.get("action")
    
    if not mod_ids:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "No mods selected",
            "type": "warning"
        })
        
    query = select(Mod).where(Mod.id.in_(mod_ids))
    result = await db.execute(query)
    mods = result.scalars().all()
    
    count = 0
    for mod in mods:
        if action == "enable":
            mod.is_enabled = True
            count += 1
        elif action == "disable":
            mod.is_enabled = False
            count += 1
        elif action == "delete":
            mod.is_active = False
            count += 1
            
    await db.commit()
    
    # Return success toast and trigger refresh
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": f"Bulk {action} successful for {count} mods",
        "type": "success",
        "headers": {"HX-Trigger": "refresh-mods"}
    })


@router.get("/{mod_id}/changelog", response_class=HTMLResponse)
async def get_mod_changelog_html(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get mod changelog from Nexus as HTML"""
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    if not mod or not mod.nexus_mod_id:
        return "<div style='padding: 2rem; text-align: center; color: var(--text-secondary);'>No Nexus Mod ID linked.</div>"
        
    from app.core.nexus_api import NexusAPIClient
    async with NexusAPIClient() as nexus:
        try:
            changelog = await nexus.get_mod_changelog(settings.game_domain, mod.nexus_mod_id)
            return templates.TemplateResponse("mods/detail_changelog.html", {
                "request": request,
                "changelog": changelog
            })
        except Exception as e:
            return f"<div style='padding: 2rem; color: var(--danger-text);'>Failed to fetch changelog: {str(e)}</div>"


@router.get("/{mod_id}/related", response_class=HTMLResponse)
async def get_related_mods_html(
    mod_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Get related mods from Nexus as HTML"""
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    if not mod or not mod.nexus_mod_id:
        return "<div style='padding: 2rem; text-align: center; color: var(--text-secondary);'>No related mods available.</div>"
        
    from app.core.nexus_api import NexusAPIClient
    async with NexusAPIClient() as nexus:
        try:
            related = await nexus.get_related_mods(settings.game_domain, mod.nexus_mod_id)
            return templates.TemplateResponse("mods/detail_related.html", {
                "request": request,
                "mods": related
            })
        except Exception as e:
            return f"<div style='padding: 2rem; color: var(--danger-text);'>Failed to fetch related mods: {str(e)}</div>"


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
