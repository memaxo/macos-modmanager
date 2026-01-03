"""
FOMOD Wizard API Endpoints

Provides endpoints for the FOMOD installer wizard UI.
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.database import get_db
from app.core.fomod_session import FomodSessionManager, FomodSession
from app.core.fomod_parser import FomodParser

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class GroupChoice(BaseModel):
    """A single choice selection"""
    name: str
    idx: int


class StepChoices(BaseModel):
    """Choices for a single group in a step"""
    name: str
    choices: List[GroupChoice]


class SubmitStepRequest(BaseModel):
    """Request body for submitting step choices"""
    step_idx: int
    groups: List[StepChoices]


class CompleteWizardRequest(BaseModel):
    """Request body for completing the wizard"""
    install_immediately: bool = True


# =====================
# Session Endpoints
# =====================

@router.get("/wizard/{session_id}")
async def get_fomod_wizard(
    request: Request,
    session_id: str
):
    """Get FOMOD wizard configuration for display
    
    Returns the full wizard configuration and current state.
    """
    session_manager = FomodSessionManager.get_instance()
    session = session_manager.get_session(session_id)
    
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    return {
        "status": "ok",
        "session": session.to_dict()
    }


@router.get("/wizard/{session_id}/modal", response_class=HTMLResponse)
async def get_wizard_modal(
    request: Request,
    session_id: str
):
    """Get the wizard modal HTML (HTMX)
    
    Returns the full wizard modal for embedding in the page.
    """
    session_manager = FomodSessionManager.get_instance()
    session = session_manager.get_session(session_id)
    
    if session is None:
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": "Session not found or expired"
        })
    
    return templates.TemplateResponse("fomod/wizard_modal.html", {
        "request": request,
        "session_id": session_id,
        "session": session,
        "config": session.config.to_dict(),
        "mod_info": session.mod_info,
        "current_step_data": session.get_current_step_data()
    })


@router.get("/wizard/{session_id}/step/{step_idx}", response_class=HTMLResponse)
async def get_wizard_step(
    request: Request,
    session_id: str,
    step_idx: int
):
    """Get HTML for a specific wizard step (HTMX)
    
    Returns the step content to be swapped into the wizard modal.
    """
    session_manager = FomodSessionManager.get_instance()
    session = session_manager.get_session(session_id)
    
    if session is None:
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": "Session not found or expired"
        })
    
    # Update current step
    session.current_step = step_idx
    step_data = session.get_current_step_data()
    
    if step_data is None:
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": "Invalid step index"
        })
    
    # Get existing choices for this step
    visible_steps = session.get_visible_steps()
    actual_step_idx = visible_steps[step_idx] if step_idx < len(visible_steps) else 0
    
    existing_choices = {}
    if actual_step_idx < len(session.choices.get("options", [])):
        step_choices = session.choices["options"][actual_step_idx]
        for group in step_choices.get("groups", []):
            existing_choices[group["name"]] = [c["idx"] for c in group.get("choices", [])]
    
    return templates.TemplateResponse("fomod/wizard_step.html", {
        "request": request,
        "session_id": session_id,
        "step_data": step_data,
        "config": session.config.to_dict(),
        "existing_choices": existing_choices,
        "fomod_path": str(session.config.fomod_path) if session.config.fomod_path else None
    })


@router.post("/wizard/{session_id}/step/{step_idx}", response_class=HTMLResponse)
async def submit_wizard_step(
    request: Request,
    session_id: str,
    step_idx: int,
    db: AsyncSession = Depends(get_db)
):
    """Submit choices for a wizard step and advance to next step (HTMX)
    
    Processes the form submission and returns the next step content.
    """
    session_manager = FomodSessionManager.get_instance()
    session = session_manager.get_session(session_id)
    
    if session is None:
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": "Session not found or expired"
        })
    
    # Parse form data
    form_data = await request.form()
    
    # Build group choices from form data
    visible_steps = session.get_visible_steps()
    if step_idx >= len(visible_steps):
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": "Invalid step index"
        })
    
    actual_step_idx = visible_steps[step_idx]
    step = session.config.steps[actual_step_idx]
    
    group_choices = []
    for group in step.groups:
        choices = []
        
        # Check for radio button selection (SelectExactlyOne, SelectAtMostOne)
        radio_key = f"group_{group.name}"
        if radio_key in form_data:
            plugin_idx = int(form_data[radio_key])
            if plugin_idx >= 0:  # -1 means "None" for SelectAtMostOne
                choices.append({
                    "name": group.plugins[plugin_idx].name,
                    "idx": plugin_idx
                })
        
        # Check for checkbox selections (SelectAtLeastOne, SelectAny)
        for idx, plugin in enumerate(group.plugins):
            checkbox_key = f"group_{group.name}_{idx}"
            if checkbox_key in form_data:
                choices.append({
                    "name": plugin.name,
                    "idx": idx
                })
        
        group_choices.append({
            "name": group.name,
            "choices": choices
        })
    
    # Save choices
    session.set_step_choices(step_idx, group_choices)
    
    # Determine next action
    direction = form_data.get("direction", "next")
    
    if direction == "back" and session.can_go_back():
        session.go_back()
        step_data = session.get_current_step_data()
        existing_choices = _get_existing_choices(session)
        
        return templates.TemplateResponse("fomod/wizard_step.html", {
            "request": request,
            "session_id": session_id,
            "step_data": step_data,
            "config": session.config.to_dict(),
            "existing_choices": existing_choices,
            "fomod_path": str(session.config.fomod_path) if session.config.fomod_path else None
        })
    
    elif direction == "next" and session.can_advance():
        session.advance_step()
        step_data = session.get_current_step_data()
        existing_choices = _get_existing_choices(session)
        
        return templates.TemplateResponse("fomod/wizard_step.html", {
            "request": request,
            "session_id": session_id,
            "step_data": step_data,
            "config": session.config.to_dict(),
            "existing_choices": existing_choices,
            "fomod_path": str(session.config.fomod_path) if session.config.fomod_path else None
        })
    
    elif direction == "complete":
        # Show summary before installation
        summary = session.get_summary()
        return templates.TemplateResponse("fomod/choice_summary.html", {
            "request": request,
            "session_id": session_id,
            "summary": summary,
            "mod_info": session.mod_info
        })
    
    else:
        # Stay on current step
        step_data = session.get_current_step_data()
        existing_choices = _get_existing_choices(session)
        
        return templates.TemplateResponse("fomod/wizard_step.html", {
            "request": request,
            "session_id": session_id,
            "step_data": step_data,
            "config": session.config.to_dict(),
            "existing_choices": existing_choices,
            "fomod_path": str(session.config.fomod_path) if session.config.fomod_path else None
        })


def _get_existing_choices(session: FomodSession) -> Dict[str, List[int]]:
    """Extract existing choices for the current step"""
    existing_choices = {}
    visible_steps = session.get_visible_steps()
    actual_step_idx = visible_steps[session.current_step] if session.current_step < len(visible_steps) else 0
    
    if actual_step_idx < len(session.choices.get("options", [])):
        step_choices = session.choices["options"][actual_step_idx]
        for group in step_choices.get("groups", []):
            existing_choices[group["name"]] = [c["idx"] for c in group.get("choices", [])]
    
    return existing_choices


@router.post("/wizard/{session_id}/complete", response_class=HTMLResponse)
async def complete_fomod_wizard(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Complete the wizard and install the mod
    
    Processes all choices and performs the actual mod installation.
    """
    from app.core.mod_manager import ModManager, ModInstallationError
    from app.core.fomod_parser import FomodParser
    from app.core.game_detector import detect_game_installations
    from pathlib import Path
    from app.config import settings
    
    session_manager = FomodSessionManager.get_instance()
    result = session_manager.complete_session(session_id)
    
    if result is None:
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": "Session not found or expired"
        })
    
    choices = result["choices"]
    temp_dir = result["temp_dir"]
    config = result["config"]
    mod_info = result["mod_info"]
    
    try:
        # Detect game installation - CRITICAL FIX: ModManager requires game_path
        installations = await detect_game_installations()
        if not installations:
            return templates.TemplateResponse("fomod/wizard_error.html", {
                "request": request,
                "error": f"{settings.game_name} installation not found. Please configure the game path in Settings."
            })
        
        game_path = Path(installations[0]["path"])
        
        # Resolve files based on choices
        parser = FomodParser()
        files_to_install = parser.resolve_files(config, choices, temp_dir)
        
        if not files_to_install:
            return templates.TemplateResponse("fomod/wizard_error.html", {
                "request": request,
                "error": "No files to install based on your selections. Please go back and make different choices."
            })
        
        # Install the mod using ModManager with required game_path
        mod_manager = ModManager(db, game_path)
        
        # Create mod record and install files
        mod = await mod_manager.install_mod_with_fomod(
            mod_info=mod_info,
            files_to_install=files_to_install,
            temp_dir=temp_dir,
            fomod_choices=choices
        )
        
        return templates.TemplateResponse("fomod/install_success.html", {
            "request": request,
            "mod": mod,
            "files_installed": len(files_to_install)
        })
        
    except ModInstallationError as e:
        logger.error(f"FOMOD installation failed: {e}", exc_info=True)
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": e.message,
            "suggestion": e.suggestion if hasattr(e, 'suggestion') else None
        })
    except Exception as e:
        logger.error(f"FOMOD installation failed: {e}", exc_info=True)
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": f"Installation failed: {str(e)}"
        })


@router.post("/wizard/{session_id}/cancel", response_class=HTMLResponse)
async def cancel_fomod_wizard(
    request: Request,
    session_id: str
):
    """Cancel the wizard and clean up resources"""
    session_manager = FomodSessionManager.get_instance()
    success = session_manager.cancel_session(session_id)
    
    if not success:
        return templates.TemplateResponse("fomod/wizard_error.html", {
            "request": request,
            "error": "Session not found"
        })
    
    return templates.TemplateResponse("fomod/wizard_cancelled.html", {
        "request": request
    })


# =====================
# Image Serving
# =====================

@router.get("/session/{session_id}/image/{image_path:path}")
async def get_fomod_image(
    session_id: str,
    image_path: str
):
    """Serve an image from a FOMOD installer
    
    Images are stored in the temp directory during the wizard session.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path
    
    session_manager = FomodSessionManager.get_instance()
    session = session_manager.get_session(session_id)
    
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Construct full path
    # The image_path is relative to the mod's root directory (where fomod folder is)
    full_path = session.temp_dir / image_path
    
    # Security: ensure path is within temp_dir
    try:
        full_path = full_path.resolve()
        if not str(full_path).startswith(str(session.temp_dir.resolve())):
            raise HTTPException(status_code=403, detail="Invalid path")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")
    
    if not full_path.exists():
        # Try in fomod directory
        full_path = session.temp_dir / "fomod" / image_path
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(full_path)


# =====================
# Debug Endpoints
# =====================

@router.get("/sessions")
async def list_active_sessions():
    """List all active FOMOD sessions (for debugging)"""
    session_manager = FomodSessionManager.get_instance()
    return {
        "sessions": session_manager.get_active_sessions()
    }


@router.post("/cleanup")
async def cleanup_expired_sessions():
    """Manually trigger cleanup of expired sessions"""
    session_manager = FomodSessionManager.get_instance()
    count = session_manager.cleanup_expired()
    return {
        "cleaned_up": count
    }
