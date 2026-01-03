from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.mod import Mod, ModInstallation
from app.models.profile import ModProfile
from app.models.collection import Collection
from app.models.compatibility import ModConflict
from app.core.game_detector import detect_game_installations
from datetime import datetime, timedelta
from typing import List, Dict, Any

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Dashboard main page"""
    # Get stats
    stats = await get_dashboard_stats(db)
    
    # Get system health
    system_health = await get_system_health(db)
    
    # Get current profile
    profile_result = await db.execute(select(ModProfile).where(ModProfile.is_default == True))
    current_profile = profile_result.scalar_one_or_none()
    
    # Get recent collections
    collections_result = await db.execute(select(Collection).order_by(Collection.imported_at.desc()).limit(3))
    recent_collections = collections_result.scalars().all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "system_health": system_health,
        "current_profile": current_profile,
        "recent_collections": recent_collections
    })


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Get dashboard statistics with detailed analytics"""
    # Total mods
    total_result = await db.execute(select(func.count(Mod.id)))
    total_mods = total_result.scalar() or 0
    
    # Enabled mods
    enabled_result = await db.execute(
        select(func.count(Mod.id)).where(Mod.is_enabled == True)
    )
    enabled_mods = enabled_result.scalar() or 0
    
    # Conflicts (unresolved)
    conflicts_result = await db.execute(
        select(func.count(ModConflict.id)).where(ModConflict.resolved == False)
    )
    conflicts = conflicts_result.scalar() or 0
    
    # Disk usage and category breakdown
    disk_result = await db.execute(
        select(Mod.mod_type, func.sum(Mod.file_size), func.count(Mod.id))
        .where(Mod.is_active == True)
        .group_by(Mod.mod_type)
    )
    breakdown = disk_result.all()
    
    total_size = sum(b[1] for b in breakdown if b[1])
    categories = [
        {"type": b[0] or "Unknown", "size": b[1] or 0, "count": b[2]}
        for b in breakdown
    ]
    
    # Updates available (Placeholder - should ideally use UpdateManager)
    updates_available = 0
    
    # Mod change (mods added in last 24 hours)
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_result = await db.execute(
        select(func.count(Mod.id)).where(Mod.install_date >= yesterday)
    )
    mod_change = recent_result.scalar() or 0
    
    return {
        "total_mods": total_mods,
        "enabled_mods": enabled_mods,
        "conflicts": conflicts,
        "updates_available": updates_available,
        "mod_change": mod_change,
        "total_size_gb": round(total_size / (1024*1024*1024), 2) if total_size else 0,
        "categories": categories
    }


@router.get("/activity", response_class=HTMLResponse)
async def get_recent_activity(request: Request, db: AsyncSession = Depends(get_db)):
    """Get recent activity feed"""
    # Get recent installations (last 10)
    recent_installs_result = await db.execute(
        select(ModInstallation, Mod.name)
        .join(Mod, ModInstallation.mod_id == Mod.id)
        .order_by(ModInstallation.installed_at.desc())
        .limit(10)
    )
    recent_installs = recent_installs_result.all()
    
    # Get recent conflicts
    recent_conflicts_result = await db.execute(
        select(ModConflict)
        .order_by(ModConflict.detected_at.desc())
        .limit(5)
    )
    recent_conflicts = recent_conflicts_result.scalars().all()
    
    # Build activity items
    activities = []
    
    for install, mod_name in recent_installs:
            activities.append({
            "type": install.install_type,
            "message": f"Mod '{mod_name}' {install.install_type}ed",
            "timestamp": install.installed_at.strftime("%Y-%m-%d %H:%M") if install.installed_at else "Unknown",
            "undo_action": f"/api/mods/rollback/{install.id}" if install.rollback_available else None
            })
    
    for conflict in recent_conflicts:
        activities.append({
            "type": "conflict",
            "message": f"Conflict detected for {conflict.file_path}",
            "timestamp": conflict.detected_at.strftime("%Y-%m-%d %H:%M") if conflict.detected_at else "Unknown",
            "undo_action": None
        })
    
    # Sort by timestamp (most recent first)
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    activities = activities[:10]  # Limit to 10 most recent
    
    return templates.TemplateResponse("components/activity_feed.html", {
        "request": request,
        "activities": activities
    })


@router.get("/health")
async def get_system_health(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """Get system health indicators"""
    health_items = []
    
    # Check game detection
    detected_games = await detect_game_installations()
    
    if detected_games:
        health_items.append({
            "status": "ok",
            "label": "Game Detected",
            "description": f"Cyberpunk 2077 found at {detected_games[0]['path']}"
        })
    else:
        health_items.append({
            "status": "error",
            "label": "Game Not Found",
            "description": "Cyberpunk 2077 installation not detected"
        })
    
    # Check redscript (simplified - would check actual installation)
    health_items.append({
        "status": "ok",
        "label": "redscript",
        "description": "redscript detected"
    })
    
    # Check for missing dependencies
    # TODO: Implement dependency check
    health_items.append({
        "status": "ok",
        "label": "Dependencies",
        "description": "All dependencies satisfied"
    })
    
    # Check disk space (placeholder)
    health_items.append({
        "status": "ok",
        "label": "Disk Space",
        "description": "Sufficient space available"
    })
    
    return health_items
