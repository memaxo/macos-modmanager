from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.profile_manager import ProfileManager
from app.models.profile import ModProfile
from pydantic import BaseModel
from typing import List, Optional, Dict

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class ProfileResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_default: bool
    mod_count: int = 0
    
    class Config:
        from_attributes = True


class ProfileCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    is_default: bool = False


class LoadOrderRequest(BaseModel):
    mod_priorities: Dict[int, int]  # mod_id -> priority


@router.get("/", response_class=HTMLResponse)
async def list_profiles_html(request: Request, db: AsyncSession = Depends(get_db)):
    """List profiles as HTML"""
    manager = ProfileManager(db)
    profiles = await manager.list_profiles()
    
    profiles_data = []
    for profile in profiles:
        mods = await manager.get_profile_mods(profile.id)
        profiles_data.append({
            "id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "is_default": profile.is_default,
            "mod_count": len(mods)
        })
    
    return templates.TemplateResponse("profiles/profile_list.html", {
        "request": request,
        "profiles": profiles_data
    })


@router.get("/api")
async def list_profiles(db: AsyncSession = Depends(get_db)) -> List[ProfileResponse]:
    """List all mod profiles (JSON API)"""
    manager = ProfileManager(db)
    profiles = await manager.list_profiles()
    
    result = []
    for profile in profiles:
        mods = await manager.get_profile_mods(profile.id)
        result.append(ProfileResponse(
            id=profile.id,
            name=profile.name,
            description=profile.description,
            is_default=profile.is_default,
            mod_count=len(mods)
        ))
    
    return result


@router.post("/", response_class=HTMLResponse)
async def create_profile_html(
    request: Request,
    name: str = None,
    description: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Create profile (HTML response)"""
    if not name:
        # Get from form data
        form = await request.form()
        name = form.get("name")
        description = form.get("description")
    
    if not name:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "Profile name is required",
            "type": "error"
        })
    
    manager = ProfileManager(db)
    try:
        profile = await manager.create_profile(name=name, description=description)
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"Profile '{profile.name}' created successfully!",
            "type": "success"
        })
    except ValueError as e:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"Error: {str(e)}",
            "type": "error"
        })


@router.post("/api")
async def create_profile(
    request: ProfileCreateRequest,
    db: AsyncSession = Depends(get_db)
) -> ProfileResponse:
    """Create a new mod profile"""
    manager = ProfileManager(db)
    
    try:
        profile = await manager.create_profile(
            name=request.name,
            description=request.description,
            is_default=request.is_default
        )
        return ProfileResponse.model_validate(profile)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{profile_id}")
async def get_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db)
) -> ProfileResponse:
    """Get profile details"""
    manager = ProfileManager(db)
    profile = await manager.get_profile(profile_id)
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    mods = await manager.get_profile_mods(profile_id)
    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        is_default=profile.is_default,
        mod_count=len(mods)
    )


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a profile"""
    manager = ProfileManager(db)
    
    try:
        await manager.delete_profile(profile_id)
        return {"message": "Profile deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{profile_id}/mods")
async def get_profile_mods(
    profile_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get mods in a profile"""
    manager = ProfileManager(db)
    mods = await manager.get_profile_mods(profile_id)
    
    return {
        "mods": [
            {
                "mod_id": m["mod_id"],
                "name": m["name"],
                "enabled": m["enabled"]
            }
            for m in mods
        ]
    }


@router.post("/{profile_id}/mods/{mod_id}")
async def add_mod_to_profile(
    profile_id: int,
    mod_id: int,
    enabled: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Add a mod to a profile"""
    manager = ProfileManager(db)
    await manager.add_mod_to_profile(profile_id, mod_id, enabled)
    return {"message": "Mod added to profile"}


@router.delete("/{profile_id}/mods/{mod_id}")
async def remove_mod_from_profile(
    profile_id: int,
    mod_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Remove a mod from a profile"""
    manager = ProfileManager(db)
    await manager.remove_mod_from_profile(profile_id, mod_id)
    return {"message": "Mod removed from profile"}


@router.post("/{profile_id}/load-order")
async def set_load_order(
    profile_id: int,
    request: LoadOrderRequest,
    db: AsyncSession = Depends(get_db)
):
    """Set load order for mods in a profile"""
    manager = ProfileManager(db)
    await manager.set_load_order(profile_id, request.mod_priorities)
    return {"message": "Load order updated"}


@router.get("/{profile_id}/load-order")
async def get_load_order(
    profile_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get load order for a profile"""
    manager = ProfileManager(db)
    load_order = await manager.get_load_order(profile_id)
    return {"load_order": load_order}


@router.post("/{profile_id}/activate", response_class=HTMLResponse)
async def activate_profile_html(
    profile_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Activate profile (HTML response)"""
    manager = ProfileManager(db)
    try:
        await manager.activate_profile(profile_id)
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "Profile activated successfully!",
            "type": "success"
        })
    except Exception as e:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"Error: {str(e)}",
            "type": "error"
        })


@router.post("/{profile_id}/activate/api")
async def activate_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Activate a profile (enable/disable mods accordingly)"""
    manager = ProfileManager(db)
    await manager.activate_profile(profile_id)
    return {"message": "Profile activated"}
