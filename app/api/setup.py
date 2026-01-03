"""
Setup Wizard API

Endpoints for the one-click setup wizard.
"""

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import json

from app.core.setup_wizard import (
    SetupWizard, 
    SetupOptions, 
    SetupStatus,
    SetupProgress,
    get_setup_status
)
from app.core.game_detector import detect_game_installations

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Store for active setup sessions
_active_setups: Dict[str, Dict[str, Any]] = {}


class SetupStatusResponse(BaseModel):
    status: str
    game_detected: bool
    game_path: Optional[str] = None
    red4ext_installed: bool = False
    tweakxl_installed: bool = False
    archivexl_installed: bool = False
    setup_needed: bool = True
    issues: List[str] = []


class StartSetupRequest(BaseModel):
    install_red4ext: bool = True
    install_tweakxl: bool = True
    install_archivexl: bool = True
    create_launch_script: bool = True
    game_path: Optional[str] = None


# ============================================================
# HTML Endpoints (for HTMX)
# ============================================================

@router.get("/wizard", response_class=HTMLResponse)
async def setup_wizard_page(request: Request):
    """Render the setup wizard page"""
    return templates.TemplateResponse("setup/wizard.html", {
        "request": request,
    })


@router.get("/detect", response_class=HTMLResponse)
async def detect_environment(request: Request):
    """Detect environment and return step 1 template"""
    wizard = SetupWizard()
    try:
        environment = await wizard.detect_environment()
        return templates.TemplateResponse("setup/step_detect.html", {
            "request": request,
            "environment": environment,
        })
    finally:
        await wizard.close()


@router.get("/step/select", response_class=HTMLResponse)
async def select_frameworks_step(request: Request):
    """Render framework selection step"""
    installations = await detect_game_installations()
    game_path = installations[0]['path'] if installations else None
    
    return templates.TemplateResponse("setup/step_select.html", {
        "request": request,
        "game_path": game_path,
    })


@router.post("/start", response_class=HTMLResponse)
async def start_setup(
    request: Request,
    install_red4ext: bool = Form(default=True),
    install_tweakxl: bool = Form(default=True),
    install_archivexl: bool = Form(default=True),
    create_launch_script: bool = Form(default=True),
    game_path: Optional[str] = Form(default=None),
):
    """Start the setup process"""
    from pathlib import Path
    
    # Create setup options
    options = SetupOptions(
        install_red4ext=True,  # Always required
        install_tweakxl=install_tweakxl,
        install_archivexl=install_archivexl,
        create_launch_script=create_launch_script,
        game_path=Path(game_path) if game_path else None,
    )
    
    # Create a session ID for tracking
    import uuid
    session_id = str(uuid.uuid4())
    
    # Initialize progress tracking
    _active_setups[session_id] = {
        "status": "running",
        "progress": 0,
        "current_step": 1,
        "total_steps": 5,
        "message": "Starting setup...",
        "log_entries": [],
        "result": None,
    }
    
    # Run setup in background
    async def run_setup():
        wizard = SetupWizard()
        
        def on_progress(progress: SetupProgress):
            _active_setups[session_id]["progress"] = int(progress.step_progress * 100)
            _active_setups[session_id]["current_step"] = progress.step_number
            _active_setups[session_id]["total_steps"] = progress.total_steps
            _active_setups[session_id]["message"] = progress.message
            _active_setups[session_id]["log_entries"].append({
                "type": "error" if progress.is_error else "success" if "installed" in progress.message.lower() else "info",
                "message": progress.message,
            })
        
        try:
            result = await wizard.run_setup(options, on_progress)
            _active_setups[session_id]["status"] = "complete"
            _active_setups[session_id]["result"] = result
        except Exception as e:
            _active_setups[session_id]["status"] = "error"
            _active_setups[session_id]["message"] = str(e)
        finally:
            await wizard.close()
    
    # Start background task
    asyncio.create_task(run_setup())
    
    # Return progress page with session ID
    return templates.TemplateResponse("setup/step_progress.html", {
        "request": request,
        "session_id": session_id,
        "progress_percent": 0,
        "current_message": "Starting setup...",
        "current_step": 1,
        "total_steps": 5,
        "log_entries": [],
        "is_complete": False,
    })


@router.get("/progress", response_class=HTMLResponse)
async def get_progress(request: Request, session_id: Optional[str] = None):
    """Get current setup progress"""
    # Find the most recent session if not specified
    if not session_id and _active_setups:
        session_id = list(_active_setups.keys())[-1]
    
    if not session_id or session_id not in _active_setups:
        # No active setup, redirect to detect
        return templates.TemplateResponse("setup/step_detect.html", {
            "request": request,
            "environment": None,
        })
    
    session = _active_setups[session_id]
    
    if session["status"] == "complete":
        # Setup complete, show results
        result = session["result"]
        # Clean up session
        del _active_setups[session_id]
        
        return templates.TemplateResponse("setup/step_complete.html", {
            "request": request,
            "result": result,
        })
    
    if session["status"] == "error":
        # Setup failed
        from app.core.setup_wizard import SetupResult, SetupStatus as SS
        result = SetupResult(
            success=False,
            status=SS.FAILED,
            message=session["message"],
            warnings=session.get("log_entries", []),
        )
        del _active_setups[session_id]
        
        return templates.TemplateResponse("setup/step_complete.html", {
            "request": request,
            "result": result,
        })
    
    # Still in progress
    return templates.TemplateResponse("setup/step_progress.html", {
        "request": request,
        "session_id": session_id,
        "progress_percent": session["progress"],
        "current_message": session["message"],
        "current_step": session["current_step"],
        "total_steps": session["total_steps"],
        "log_entries": session["log_entries"],
        "is_complete": False,
    })


@router.post("/cancel", response_class=HTMLResponse)
async def cancel_setup(request: Request, session_id: Optional[str] = None):
    """Cancel the current setup"""
    if session_id and session_id in _active_setups:
        _active_setups[session_id]["status"] = "cancelled"
        del _active_setups[session_id]
    
    return templates.TemplateResponse("setup/step_detect.html", {
        "request": request,
        "environment": None,
    })


# ============================================================
# JSON API Endpoints
# ============================================================

@router.get("/status", response_model=SetupStatusResponse)
async def check_setup_status():
    """Check if setup is needed (JSON API)"""
    status = await get_setup_status()
    return SetupStatusResponse(**status)


@router.get("/verify")
async def verify_setup():
    """Verify the current setup (JSON API)"""
    wizard = SetupWizard()
    try:
        result = await wizard.verify_setup()
        return {
            "success": result.success,
            "checks_passed": result.checks_passed,
            "checks_failed": result.checks_failed,
            "checks": result.checks,
            "issues": result.issues,
            "recommendations": result.recommendations,
        }
    finally:
        await wizard.close()


@router.get("/environment")
async def get_environment():
    """Get detailed environment information (JSON API)"""
    wizard = SetupWizard()
    try:
        env = await wizard.detect_environment()
        return {
            "game_detected": env.game_detected,
            "game_path": str(env.game_path) if env.game_path else None,
            "game_version": env.game_version,
            "game_launcher": env.game_launcher,
            "red4ext_installed": env.red4ext_installed,
            "red4ext_version": env.red4ext_version,
            "tweakxl_installed": env.tweakxl_installed,
            "tweakxl_version": env.tweakxl_version,
            "archivexl_installed": env.archivexl_installed,
            "archivexl_version": env.archivexl_version,
            "frida_gadget_installed": env.frida_gadget_installed,
            "launch_script_exists": env.launch_script_exists,
            "macos_version": env.macos_version,
            "is_apple_silicon": env.is_apple_silicon,
            "setup_needed": env.setup_needed,
            "issues": env.issues,
        }
    finally:
        await wizard.close()


@router.post("/run")
async def run_setup_api(options: StartSetupRequest):
    """Run setup programmatically (JSON API)"""
    from pathlib import Path
    
    setup_options = SetupOptions(
        install_red4ext=options.install_red4ext,
        install_tweakxl=options.install_tweakxl,
        install_archivexl=options.install_archivexl,
        create_launch_script=options.create_launch_script,
        game_path=Path(options.game_path) if options.game_path else None,
    )
    
    wizard = SetupWizard()
    try:
        result = await wizard.run_setup(setup_options)
        return {
            "success": result.success,
            "status": result.status.value,
            "message": result.message,
            "installed_frameworks": result.installed_frameworks,
            "failed_frameworks": result.failed_frameworks,
            "warnings": result.warnings,
            "duration_seconds": result.duration_seconds,
        }
    finally:
        await wizard.close()
