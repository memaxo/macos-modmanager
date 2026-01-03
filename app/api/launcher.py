from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from app.core.launcher import Launcher, LaunchError
from app.core.validation_engine import ValidationEngine
from app.core.launch_logger import get_launch_logger, LogLevel, LogSource
from typing import Optional, Set
import asyncio
import json

router = APIRouter()
launcher = Launcher()

@router.post("/launch")
async def launch_game(
    request: Request,
    skip_validation: bool = Query(default=False, description="Skip pre-launch validation")
):
    """Launch Cyberpunk 2077 with mods"""
    try:
        # Run validation first unless skipped
        if not skip_validation:
            engine = ValidationEngine()
            validation = await engine.run_all()
            
            if not validation.can_launch:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "validation_failed",
                        "message": "Pre-launch validation found blocking issues",
                        "validation": {
                            "success": validation.success,
                            "can_launch": validation.can_launch,
                            "error_count": validation.error_count,
                            "warning_count": validation.warning_count,
                            "issues": [
                                {
                                    "severity": i.severity.value,
                                    "title": i.title,
                                    "message": i.message,
                                }
                                for i in validation.issues
                                if i.severity.value == "error"
                            ]
                        }
                    }
                )
        
        # Launch the game
        result = await launcher.launch_game()
        
        # Return redirect response to activity page
        session_id = launcher.get_current_session_id()
        return JSONResponse(
            content={
                "status": "success",
                "message": "Game launched",
                "pid": result.get("pid"),
                "session_id": session_id,
                "redirect": "/activity"
            },
            headers={"HX-Redirect": "/activity"}
        )
    except LaunchError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.get("/validate")
async def validate_before_launch():
    """Run pre-launch validation checks"""
    try:
        engine = ValidationEngine()
        report = await engine.run_all()
        
        return {
            "success": report.success,
            "can_launch": report.can_launch,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "info_count": report.info_count,
            "duration_ms": report.duration_ms,
            "checks": [
                {
                    "name": c.name,
                    "category": c.category.value,
                    "passed": c.passed,
                    "message": c.message,
                    "duration_ms": c.duration_ms,
                    "issues": [
                        {
                            "severity": i.severity.value,
                            "title": i.title,
                            "message": i.message,
                            "file_path": i.file_path,
                            "line_number": i.line_number,
                            "suggestion": i.suggestion,
                            "auto_fix_available": i.auto_fix_available,
                        }
                        for i in c.issues
                    ]
                }
                for c in report.checks
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_launch_status():
    """Get current launch/game status"""
    metrics = launcher.get_process_metrics()
    session_id = launcher.get_current_session_id()
    
    return {
        "is_running": launcher._is_launching,
        "pid": launcher._current_process.pid if launcher._current_process else None,
        "session_id": session_id,
        "metrics": metrics
    }

@router.post("/stop")
async def stop_game():
    """Stop the running game (graceful termination)"""
    success = launcher.stop_game()
    if success:
        return {"status": "success", "message": "Game stop signal sent"}
    else:
        raise HTTPException(status_code=400, detail="No running game process found")


@router.get("/metrics")
async def get_metrics():
    """Get current process metrics"""
    metrics = launcher.get_process_metrics()
    if metrics is None:
        return {
            "status": "stopped",
            "pid": None,
            "uptime_seconds": 0,
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "memory_percent": 0.0,
            "is_running": False
        }
    return metrics


@router.get("/logs")
async def get_launch_logs(
    limit: Optional[int] = Query(None, ge=1, le=10000, description="Maximum number of log lines"),
    level: Optional[str] = Query(None, description="Filter by level (info, warning, error, debug)"),
    source: Optional[str] = Query(None, description="Filter by source (launcher, red4ext, tweakxl, etc.)"),
    search: Optional[str] = Query(None, description="Search string")
):
    """Get buffered launch logs"""
    logger = get_launch_logger()
    session_id = launcher.get_current_session_id()
    
    level_filter = None
    if level:
        try:
            level_filter = {LogLevel(level)}
        except ValueError:
            pass
    
    source_filter = None
    if source:
        try:
            source_filter = {LogSource(source)}
        except ValueError:
            pass
    
    logs = logger.get_logs(
        session_id=session_id,
        level_filter=level_filter,
        source_filter=source_filter,
        search=search,
        limit=limit
    )
    
    return {
        "logs": logs,
        "session_id": session_id,
        "count": len(logs)
    }


@router.post("/restart")
async def restart_game(
    skip_validation: bool = Query(default=False, description="Skip pre-launch validation")
):
    """Restart the game"""
    # Stop current game
    launcher.stop_game()
    
    # Wait a moment for graceful shutdown
    await asyncio.sleep(2)
    
    # Launch again
    try:
        result = await launcher.launch_game()
        return {
            "status": "success",
            "message": "Game restarted",
            "pid": result.get("pid"),
            "session_id": launcher.get_current_session_id()
        }
    except LaunchError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/force-kill")
async def force_kill_game():
    """Force kill the running game"""
    success = launcher.force_kill_game()
    if success:
        return {"status": "success", "message": "Game force killed"}
    else:
        raise HTTPException(status_code=400, detail="No running game process found")


@router.post("/set-priority")
async def set_priority(nice: int = Query(..., ge=-20, le=19, description="Nice level (-20 to 19)")):
    """Set process priority (nice level)"""
    success = launcher.set_process_priority(nice)
    if success:
        return {"status": "success", "message": f"Process priority set to {nice}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to set process priority")


@router.get("/options")
async def get_launch_options():
    """Get current launch options"""
    # TODO: Store launch options in config/settings
    return {
        "skip_validation": False,
        "launch_script": "launch_red4ext.sh",
        "performance_profile": "default",
        "environment_variables": {}
    }


@router.post("/options")
async def set_launch_options(
    skip_validation: Optional[bool] = None,
    launch_script: Optional[str] = None,
    performance_profile: Optional[str] = None,
    environment_variables: Optional[dict] = None
):
    """Set launch options"""
    # TODO: Store launch options in config/settings
    return {
        "status": "success",
        "message": "Launch options updated",
        "options": {
            "skip_validation": skip_validation,
            "launch_script": launch_script,
            "performance_profile": performance_profile,
            "environment_variables": environment_variables
        }
    }


@router.post("/hot-reload")
async def hot_reload_mods():
    """Hot reload mods without restarting game"""
    # TODO: Implement mod hot-reload functionality
    return {
        "status": "not_implemented",
        "message": "Mod hot-reload is not yet implemented"
    }


@router.get("/logs/stream")
async def stream_launch_logs(request: Request):
    """Stream launch logs via Server-Sent Events"""
    logger = get_launch_logger()
    session_id = launcher.get_current_session_id()
    
    async def event_generator():
        last_count = 0
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                # Get current logs
                logs = logger.get_logs(session_id=session_id)
                
                # Send only new logs
                if len(logs) > last_count:
                    for log in logs[last_count:]:
                        yield f"data: {json.dumps(log)}\n\n"
                    last_count = len(logs)
                
                # Small delay to prevent busy-waiting
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
