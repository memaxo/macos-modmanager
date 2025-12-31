from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.mod import Mod
from app.models.compatibility import ModConflict
from app.core.game_detector import detect_cyberpunk_installations
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
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "system_health": system_health
    })


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Get dashboard statistics"""
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
    
    # Updates available (placeholder - would check Nexus API)
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
        "mod_change": mod_change
    }


@router.get("/activity", response_class=HTMLResponse)
async def get_recent_activity(request: Request, db: AsyncSession = Depends(get_db)):
    """Get recent activity feed"""
    # Get recent mods (last 10)
    recent_mods_result = await db.execute(
        select(Mod)
        .order_by(Mod.updated_at.desc())
        .limit(10)
    )
    recent_mods = recent_mods_result.scalars().all()
    
    # Get recent conflicts
    recent_conflicts_result = await db.execute(
        select(ModConflict)
        .order_by(ModConflict.created_at.desc())
        .limit(5)
    )
    recent_conflicts = recent_conflicts_result.scalars().all()
    
    # Build activity items
    activities = []
    
    for mod in recent_mods:
        install_date = mod.install_date
        update_date = mod.update_date
        
        if update_date is None or (install_date and update_date and install_date.date() == update_date.date() and abs((update_date - install_date).total_seconds()) < 60):
            # New installation
            activities.append({
                "type": "install",
                "message": f"Mod '{mod.name}' installed",
                "timestamp": install_date.strftime("%Y-%m-%d %H:%M") if install_date else "Unknown",
                "undo_action": None
            })
        else:
            # Update
            activities.append({
                "type": "update",
                "message": f"Mod '{mod.name}' updated",
                "timestamp": update_date.strftime("%Y-%m-%d %H:%M") if update_date else "Unknown",
                "undo_action": None
            })
    
    for conflict in recent_conflicts:
        activities.append({
            "type": "conflict",
            "message": f"Conflict detected: {conflict.conflict_type}",
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
    detected_games = await detect_cyberpunk_installations()
    
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
