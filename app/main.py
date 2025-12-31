from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from app.config import settings
from app.database import init_db, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.mod import Mod

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
    pass


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
from app.api import mods, collections, compatibility, games, profiles, dashboard, dependencies

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(mods.router, prefix="/api/mods", tags=["mods"])
app.include_router(collections.router, prefix="/api/collections", tags=["collections"])
app.include_router(compatibility.router, prefix="/api/compatibility", tags=["compatibility"])
app.include_router(games.router, prefix="/api/games", tags=["games"])
app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"])
app.include_router(dependencies.router, prefix="/api/dependencies", tags=["dependencies"])


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: AsyncSession = Depends(get_db)):
    """Redirect to dashboard"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Dashboard page"""
    return await dashboard.dashboard(request, db)


@app.get("/mods", response_class=HTMLResponse)
async def mods_browser_page(request: Request):
    """Mod browser page"""
    return templates.TemplateResponse("mods/browser.html", {"request": request})


@app.get("/mods/install", response_class=HTMLResponse)
async def mod_install_page(request: Request):
    """Mod installation page"""
    return templates.TemplateResponse("mods/install.html", {"request": request})


@app.get("/collections", response_class=HTMLResponse)
async def collections_browser_page(request: Request):
    """Collections browser page"""
    return templates.TemplateResponse("collections/browser.html", {"request": request})


@app.get("/collections/import", response_class=HTMLResponse)
async def collections_import_page(request: Request):
    """Collection import page"""
    return templates.TemplateResponse("collections/import.html", {"request": request})


@app.get("/collections/{collection_id}", response_class=HTMLResponse)
async def collection_detail_page(request: Request, collection_id: int, db: AsyncSession = Depends(get_db)):
    """Collection detail page"""
    from sqlalchemy import select
    from app.models.collection import Collection, CollectionMod
    
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    
    if not collection:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Collection not found")
    
    mods_result = await db.execute(
        select(CollectionMod).where(CollectionMod.collection_id == collection_id).order_by(CollectionMod.install_order)
    )
    mods = mods_result.scalars().all()
    
    return templates.TemplateResponse("collections/detail.html", {
        "request": request,
        "collection": collection,
        "mods": mods
    })


@app.get("/mods/load-order", response_class=HTMLResponse)
async def load_order_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Load order manager page"""
    from app.api.profiles import ProfileManager
    manager = ProfileManager(db)
    profiles = await manager.list_profiles()
    
    return templates.TemplateResponse("mods/load_order.html", {
        "request": request,
        "profiles": profiles
    })


@app.get("/conflicts", response_class=HTMLResponse)
async def conflicts_page(request: Request):
    """Conflicts resolution page"""
    return templates.TemplateResponse("conflicts/resolve.html", {"request": request})


@app.get("/profiles", response_class=HTMLResponse)
async def profiles_page(request: Request):
    """Profiles manager page"""
    return templates.TemplateResponse("profiles/manager.html", {"request": request})


@app.get("/profiles/create", response_class=HTMLResponse)
async def profile_create_page(request: Request):
    """Create profile page"""
    return templates.TemplateResponse("profiles/editor.html", {
        "request": request,
        "profile": None
    })


@app.get("/profiles/{profile_id}/edit", response_class=HTMLResponse)
async def profile_edit_page(request: Request, profile_id: int, db: AsyncSession = Depends(get_db)):
    """Edit profile page"""
    from app.api.profiles import ProfileManager
    manager = ProfileManager(db)
    profile = await manager.get_profile(profile_id)
    
    if not profile:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return templates.TemplateResponse("profiles/editor.html", {
        "request": request,
        "profile": profile
    })


@app.get("/dependencies", response_class=HTMLResponse)
async def dependencies_page(request: Request):
    """Dependencies manager page"""
    return templates.TemplateResponse("dependencies/manager.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page"""
    return templates.TemplateResponse("settings.html", {"request": request})


@app.get("/activity", response_class=HTMLResponse)
async def activity_page(request: Request):
    """Activity log page"""
    return templates.TemplateResponse("activity.html", {"request": request})


@app.get("/mods/{mod_id}", response_class=HTMLResponse)
async def mod_detail_page(request: Request, mod_id: int, db: AsyncSession = Depends(get_db)):
    """Mod detail page"""
    from sqlalchemy import select
    from app.models.mod import Mod
    
    result = await db.execute(select(Mod).where(Mod.id == mod_id))
    mod = result.scalar_one_or_none()
    
    if not mod:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Mod not found")
    
    return templates.TemplateResponse("mods/detail.html", {
        "request": request,
        "mod": mod,
        "active_tab": "overview"
    })


@app.get("/api/mods", response_class=HTMLResponse)
async def mods_list_html(request: Request, db: AsyncSession = Depends(get_db)):
    """HTMX endpoint for mod list"""
    from app.database import get_db
    from fastapi import Depends
    
    result = await db.execute(select(Mod).where(Mod.is_active == True))
    mods = result.scalars().all()
    
    mods_data = [
        {
            "id": mod.id,
            "name": mod.name,
            "author": mod.author,
            "version": mod.version,
            "is_enabled": mod.is_enabled
        }
        for mod in mods
    ]
    
    return templates.TemplateResponse("mods_list.html", {
        "request": request,
        "mods": mods_data
    })
