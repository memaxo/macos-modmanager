from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.collection import Collection, CollectionMod
from app.core.nexus_api import NexusAPIClient, NexusAPIError
from app.core.mod_manager import ModManager, ModInstallationError
from app.core.game_detector import detect_cyberpunk_installations
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class CollectionResponse(BaseModel):
    id: int
    name: str
    author: Optional[str]
    mod_count: int
    nexus_url: Optional[str]
    
    class Config:
        from_attributes = True


class CollectionImportRequest(BaseModel):
    url: HttpUrl


@router.get("/", response_class=HTMLResponse)
async def list_collections_html(
    request: Request,
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """List collections as HTML"""
    query = select(Collection)
    
    if search:
        query = query.where(
            Collection.name.ilike(f"%{search}%")
        )
    
    result = await db.execute(query)
    collections = result.scalars().all()
    
    # Get mod counts
    collections_data = []
    for collection in collections:
        count_result = await db.execute(
            select(func.count(CollectionMod.id)).where(CollectionMod.collection_id == collection.id)
        )
        mod_count = count_result.scalar() or 0
        
        collections_data.append({
            "id": collection.id,
            "name": collection.name,
            "author": collection.author,
            "mod_count": mod_count,
            "version": None,  # TODO: Extract from collection_data
            "thumbnail_url": None,  # TODO: Extract from collection_data
            "nexus_url": collection.nexus_url
        })
    
    return templates.TemplateResponse("collections/collection_list.html", {
        "request": request,
        "collections": collections_data
    })


@router.get("/api")
async def list_collections(db: AsyncSession = Depends(get_db)) -> List[CollectionResponse]:
    """List imported collections (JSON API)"""
    result = await db.execute(select(Collection))
    collections = result.scalars().all()
    return [CollectionResponse.model_validate(c) for c in collections]


@router.post("/import", response_class=HTMLResponse)
async def import_collection_html(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Import collection from URL (HTML response)"""
    form = await request.form()
    url = form.get("url")
    
    if not url:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": "URL is required",
            "type": "error"
        })
    
    try:
        import_request = CollectionImportRequest(url=url)
        collection = await _import_collection(import_request, db)
        
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"Collection '{collection.name}' imported successfully!",
            "type": "success"
        })
    except HTTPException as e:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"Error: {e.detail}",
            "type": "error"
        })


@router.post("/import/api")
async def import_collection(
    request: CollectionImportRequest,
    db: AsyncSession = Depends(get_db)
) -> CollectionResponse:
    """Import collection from Nexus Mods URL (JSON API)"""
    return await _import_collection(request, db)


async def _import_collection(
    request: CollectionImportRequest,
    db: AsyncSession
) -> CollectionResponse:
    """Internal import collection function"""
    async with NexusAPIClient() as nexus:
        try:
            # Parse collection URL
            game_domain, collection_id = await nexus.parse_collection_url(str(request.url))
            
            # Get collection data
            collection_data = await nexus.get_collection(collection_id, game_domain)
            
            if not collection_data:
                raise HTTPException(status_code=404, detail="Collection not found")
            
            # Get revision (use latest published or current)
            revision = collection_data.get("latestPublishedRevision") or collection_data.get("currentRevision")
            if not revision:
                raise HTTPException(status_code=400, detail="Collection has no published revision")
            
            mods = revision.get("mods", [])
            
            # Create collection record
            collection = Collection(
                nexus_collection_id=collection_id,
                name=collection_data.get("name", "Unknown"),
                author=collection_data.get("author", {}).get("name"),
                description=collection_data.get("description"),
                game_id=game_domain,
                mod_count=len(mods),
                nexus_url=str(request.url),
                collection_data=collection_data
            )
            
            db.add(collection)
            await db.flush()
            
            # Create collection mod records
            for idx, mod_entry in enumerate(mods):
                mod_info = mod_entry.get("mod", {})
                collection_mod = CollectionMod(
                    collection_id=collection.id,
                    nexus_mod_id=mod_info.get("nexusModId") or mod_info.get("id"),
                    nexus_file_id=mod_entry.get("fileId"),
                    is_required=mod_entry.get("isRequired", True),
                    install_order=idx
                )
                db.add(collection_mod)
            
            await db.commit()
            await db.refresh(collection)
            
            return CollectionResponse.model_validate(collection)
            
        except NexusAPIError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/{collection_id}/install", response_class=HTMLResponse)
async def install_collection_html(
    collection_id: int,
    request: Request,
    check_compatibility: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Install collection (HTML response)"""
    result = await _install_collection(collection_id, check_compatibility, db)
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": f"Installed {result['installed']} mods. {result['failed']} failed.",
        "type": "success" if result['failed'] == 0 else "warning"
    })


@router.post("/{collection_id}/install/api")
async def install_collection(
    collection_id: int,
    check_compatibility: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Install all mods from a collection (JSON API)"""
    return await _install_collection(collection_id, check_compatibility, db)


async def _install_collection(
    collection_id: int,
    check_compatibility: bool,
    db: AsyncSession
):
    """Internal install collection function"""
    # Get collection
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Get collection mods
    mods_result = await db.execute(
        select(CollectionMod).where(CollectionMod.collection_id == collection_id)
    )
    collection_mods = mods_result.scalars().all()
    
    # Detect game installation
    installations = await detect_cyberpunk_installations()
    if not installations:
        raise HTTPException(status_code=404, detail="Cyberpunk 2077 not found")
    
    game_path = Path(installations[0]["path"])
    mod_manager = ModManager(db, game_path)
    
    installed = []
    failed = []
    
    # Install each mod
    for collection_mod in sorted(collection_mods, key=lambda m: m.install_order or 0):
        try:
            mod = await mod_manager.install_mod_from_nexus(
                collection_mod.nexus_mod_id,
                file_id=collection_mod.nexus_file_id,
                check_compatibility=check_compatibility
            )
            
            # Link installed mod to collection
            collection_mod.mod_id = mod.id
            installed.append(mod.id)
            
        except ModInstallationError as e:
            failed.append({
                "nexus_mod_id": collection_mod.nexus_mod_id,
                "error": str(e)
            })
    
    await db.commit()
    
    return {
        "installed": len(installed),
        "failed": len(failed),
        "installed_mods": installed,
        "failed_mods": failed
    }


@router.get("/{collection_id}")
async def get_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db)
) -> CollectionResponse:
    """Get collection details"""
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    return CollectionResponse.model_validate(collection)


@router.delete("/{collection_id}")
async def delete_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a collection (does not uninstall mods)"""
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    await db.delete(collection)
    await db.commit()
    
    return {"message": "Collection deleted"}
