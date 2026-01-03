"""
Framework Management API

Endpoints for managing RED4ext, TweakXL, ArchiveXL on macOS.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.core.framework_manager import FrameworkManager, LogWatcher, GameProcessMonitor
from app.core.game_detector import detect_game_installations
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class FrameworkStatusResponse(BaseModel):
    name: str
    installed: bool
    version: Optional[str] = None
    latest_version: Optional[str] = None
    update_available: bool = False
    healthy: bool = True
    missing_files: List[str] = []
    error: Optional[str] = None


class InstallResponse(BaseModel):
    success: bool
    framework: str
    version: Optional[str] = None
    message: str
    installed_files: List[str] = []


class AllStatusResponse(BaseModel):
    red4ext: FrameworkStatusResponse
    tweakxl: FrameworkStatusResponse
    archivexl: FrameworkStatusResponse
    game_detected: bool
    game_path: Optional[str] = None


class GameStatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    memory_mb: Optional[float] = None
    uptime_seconds: Optional[float] = None


class LogsResponse(BaseModel):
    lines: List[str]
    errors: List[str]


async def get_framework_manager() -> FrameworkManager:
    """Get framework manager with game path"""
    installations = await detect_game_installations()
    game_path = Path(installations[0]['path']) if installations else None
    return FrameworkManager(game_path)


@router.get("/status", response_model=AllStatusResponse)
async def get_all_framework_status():
    """Get status of all frameworks"""
    installations = await detect_game_installations()
    game_detected = len(installations) > 0
    game_path = installations[0]['path'] if installations else None
    
    manager = await get_framework_manager()
    
    try:
        statuses = await manager.check_all_status()
        
        return AllStatusResponse(
            red4ext=FrameworkStatusResponse(**{
                'name': statuses['red4ext'].name,
                'installed': statuses['red4ext'].installed,
                'version': statuses['red4ext'].version,
                'latest_version': statuses['red4ext'].latest_version,
                'update_available': statuses['red4ext'].update_available,
                'healthy': statuses['red4ext'].healthy,
                'missing_files': statuses['red4ext'].missing_files,
                'error': statuses['red4ext'].error,
            }),
            tweakxl=FrameworkStatusResponse(**{
                'name': statuses['tweakxl'].name,
                'installed': statuses['tweakxl'].installed,
                'version': statuses['tweakxl'].version,
                'latest_version': statuses['tweakxl'].latest_version,
                'update_available': statuses['tweakxl'].update_available,
                'healthy': statuses['tweakxl'].healthy,
                'missing_files': statuses['tweakxl'].missing_files,
                'error': statuses['tweakxl'].error,
            }),
            archivexl=FrameworkStatusResponse(**{
                'name': statuses['archivexl'].name,
                'installed': statuses['archivexl'].installed,
                'version': statuses['archivexl'].version,
                'latest_version': statuses['archivexl'].latest_version,
                'update_available': statuses['archivexl'].update_available,
                'healthy': statuses['archivexl'].healthy,
                'missing_files': statuses['archivexl'].missing_files,
                'error': statuses['archivexl'].error,
            }),
            game_detected=game_detected,
            game_path=game_path,
        )
    finally:
        await manager.close()


@router.get("/{framework}/status", response_model=FrameworkStatusResponse)
async def get_framework_status(framework: str):
    """Get status of a specific framework"""
    if framework not in ['red4ext', 'tweakxl', 'archivexl']:
        raise HTTPException(status_code=404, detail=f"Unknown framework: {framework}")
    
    manager = await get_framework_manager()
    try:
        status = await manager.check_status(framework)
        return FrameworkStatusResponse(
            name=status.name,
            installed=status.installed,
            version=status.version,
            latest_version=status.latest_version,
            update_available=status.update_available,
            healthy=status.healthy,
            missing_files=status.missing_files,
            error=status.error,
        )
    finally:
        await manager.close()


@router.post("/{framework}/install", response_model=InstallResponse)
async def install_framework(framework: str, version: str = 'latest'):
    """Install a framework"""
    if framework not in ['red4ext', 'tweakxl', 'archivexl']:
        raise HTTPException(status_code=404, detail=f"Unknown framework: {framework}")
    
    manager = await get_framework_manager()
    try:
        result = await manager.install(framework, version)
        return InstallResponse(
            success=result.success,
            framework=result.framework,
            version=result.version,
            message=result.message,
            installed_files=result.installed_files,
        )
    finally:
        await manager.close()


@router.post("/{framework}/update", response_model=InstallResponse)
async def update_framework(framework: str):
    """Update a framework to latest version"""
    if framework not in ['red4ext', 'tweakxl', 'archivexl']:
        raise HTTPException(status_code=404, detail=f"Unknown framework: {framework}")
    
    manager = await get_framework_manager()
    try:
        result = await manager.update(framework)
        return InstallResponse(
            success=result.success,
            framework=result.framework,
            version=result.version,
            message=result.message,
            installed_files=result.installed_files,
        )
    finally:
        await manager.close()


@router.post("/{framework}/uninstall", response_model=InstallResponse)
async def uninstall_framework(framework: str):
    """Uninstall a framework"""
    if framework not in ['red4ext', 'tweakxl', 'archivexl']:
        raise HTTPException(status_code=404, detail=f"Unknown framework: {framework}")
    
    manager = await get_framework_manager()
    try:
        result = await manager.uninstall(framework)
        return InstallResponse(
            success=result.success,
            framework=result.framework,
            message=result.message,
        )
    finally:
        await manager.close()


@router.post("/{framework}/verify", response_model=FrameworkStatusResponse)
async def verify_framework(framework: str):
    """Verify framework installation integrity"""
    if framework not in ['red4ext', 'tweakxl', 'archivexl']:
        raise HTTPException(status_code=404, detail=f"Unknown framework: {framework}")
    
    manager = await get_framework_manager()
    try:
        status = await manager.verify_integrity(framework)
        return FrameworkStatusResponse(
            name=status.name,
            installed=status.installed,
            version=status.version,
            latest_version=status.latest_version,
            update_available=status.update_available,
            healthy=status.healthy,
            missing_files=status.missing_files,
            error=status.error,
        )
    finally:
        await manager.close()


@router.post("/install-all")
async def install_all_frameworks():
    """Install all frameworks"""
    manager = await get_framework_manager()
    try:
        results = await manager.install_all()
        return {
            name: InstallResponse(
                success=r.success,
                framework=r.framework,
                version=r.version,
                message=r.message,
                installed_files=r.installed_files,
            )
            for name, r in results.items()
        }
    finally:
        await manager.close()


@router.post("/update-all")
async def update_all_frameworks():
    """Update all installed frameworks"""
    manager = await get_framework_manager()
    try:
        results = await manager.update_all()
        return {
            name: InstallResponse(
                success=r.success,
                framework=r.framework,
                version=r.version,
                message=r.message,
                installed_files=r.installed_files,
            )
            for name, r in results.items()
        }
    finally:
        await manager.close()


# Game monitoring endpoints

@router.get("/game/status", response_model=GameStatusResponse)
async def get_game_status():
    """Get game process status"""
    installations = await detect_game_installations()
    if not installations:
        return GameStatusResponse(running=False)
    
    game_path = Path(installations[0]['path'])
    monitor = GameProcessMonitor(game_path)
    
    running = await monitor.is_running()
    
    if running:
        pid = await monitor.get_pid()
        memory = await monitor.get_memory_usage()
        uptime = await monitor.get_uptime()
        
        return GameStatusResponse(
            running=True,
            pid=pid,
            memory_mb=round(memory / (1024 * 1024), 2) if memory else None,
            uptime_seconds=uptime,
        )
    
    return GameStatusResponse(running=False)


@router.get("/logs/recent", response_model=LogsResponse)
async def get_recent_logs(lines: int = 100):
    """Get recent log lines"""
    installations = await detect_game_installations()
    if not installations:
        return LogsResponse(lines=[], errors=[])
    
    game_path = Path(installations[0]['path'])
    watcher = LogWatcher(game_path)
    
    log_lines = await watcher.get_recent_logs(lines)
    errors = await watcher.get_errors()
    
    return LogsResponse(lines=log_lines, errors=errors)


# HTML endpoints for HTMX

@router.get("/panel", response_class=HTMLResponse)
async def framework_panel(request: Request):
    """Render framework status panel for dashboard"""
    status = await get_all_framework_status()
    
    return templates.TemplateResponse("components/framework_panel.html", {
        "request": request,
        "status": status,
    })


@router.get("/game-panel", response_class=HTMLResponse)
async def game_status_panel(request: Request):
    """Render game status panel for dashboard"""
    game_status = await get_game_status()
    logs = await get_recent_logs(20)
    
    return templates.TemplateResponse("components/game_panel.html", {
        "request": request,
        "game_status": game_status,
        "recent_logs": logs.lines[-10:],
        "errors": logs.errors[-5:],
    })
