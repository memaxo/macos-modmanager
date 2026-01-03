"""
Compatibility Database API

Endpoints for querying and reporting mod compatibility.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

from app.database import get_db
from app.core.compatibility_service import CompatibilityService
from app.models.compatibility_db import CompatibilityStatus

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# Request/Response Models
# ============================================================

class CompatibilityStatusEnum(str, Enum):
    works = "works"
    partial = "partial"
    broken = "broken"
    windows_only = "windows_only"
    unknown = "unknown"


class CreateReportRequest(BaseModel):
    nexus_mod_id: int
    mod_name: str
    status: CompatibilityStatusEnum
    mod_version: Optional[str] = None
    notes: Optional[str] = None
    macos_port_url: Optional[str] = None
    game_version: Optional[str] = None
    red4ext_version: Optional[str] = None
    macos_version: Optional[str] = None


class VoteRequest(BaseModel):
    is_upvote: bool


class AddAlternativeRequest(BaseModel):
    alternative_mod_id: int
    alternative_mod_name: str
    reason: Optional[str] = None
    mod_url: Optional[str] = None
    similarity: int = 50


# ============================================================
# Query Endpoints
# ============================================================

@router.get("/mod/{nexus_mod_id}")
async def get_mod_compatibility(
    nexus_mod_id: int,
    db: Session = Depends(get_db)
):
    """Get compatibility info for a specific mod"""
    service = CompatibilityService(db)
    result = service.get_compatibility(nexus_mod_id)
    
    if not result:
        return {
            "nexus_mod_id": nexus_mod_id,
            "status": "unknown",
            "confidence": 0,
            "total_reports": 0,
            "message": "No compatibility data available for this mod"
        }
    
    return result


@router.get("/mod/{nexus_mod_id}/alternatives")
async def get_mod_alternatives(
    nexus_mod_id: int,
    db: Session = Depends(get_db)
):
    """Get alternative mod suggestions for a broken mod"""
    service = CompatibilityService(db)
    alternatives = service.get_alternatives(nexus_mod_id)
    return {"alternatives": alternatives}


@router.get("/search")
async def search_compatible_mods(
    query: Optional[str] = Query(None),
    status: Optional[CompatibilityStatusEnum] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Search for mods with known compatibility"""
    service = CompatibilityService(db)
    
    compat_status = None
    if status:
        compat_status = CompatibilityStatus(status.value)
    
    mods = service.search_compatible_mods(
        query=query,
        status=compat_status,
        limit=limit
    )
    
    return {"mods": mods, "total": len(mods)}


@router.get("/known")
async def get_known_mods(db: Session = Depends(get_db)):
    """Get list of known macOS-compatible mods"""
    service = CompatibilityService(db)
    mods = service.get_known_macos_mods()
    return {"mods": mods, "total": len(mods)}


@router.get("/stats")
async def get_compatibility_stats(db: Session = Depends(get_db)):
    """Get compatibility database statistics"""
    service = CompatibilityService(db)
    return service.get_stats()


# ============================================================
# Report Endpoints
# ============================================================

@router.post("/report")
async def create_compatibility_report(
    request: Request,
    report: CreateReportRequest,
    db: Session = Depends(get_db)
):
    """Submit a new compatibility report"""
    service = CompatibilityService(db)
    
    # Generate voter ID from request
    voter_id = request.client.host if request.client else "anonymous"
    
    result = service.create_report(
        nexus_mod_id=report.nexus_mod_id,
        mod_name=report.mod_name,
        status=CompatibilityStatus(report.status.value),
        tested_by=voter_id,
        mod_version=report.mod_version,
        notes=report.notes,
        macos_port_url=report.macos_port_url,
        game_version=report.game_version,
        red4ext_version=report.red4ext_version,
        macos_version=report.macos_version,
    )
    
    return {
        "success": True,
        "report_id": result.id,
        "message": "Thank you for your compatibility report!"
    }


@router.post("/report/{report_id}/vote")
async def vote_on_report(
    request: Request,
    report_id: int,
    vote: VoteRequest,
    db: Session = Depends(get_db)
):
    """Vote on a compatibility report"""
    service = CompatibilityService(db)
    
    # Generate voter ID from request
    voter_id = request.client.host if request.client else "anonymous"
    
    success = service.vote_on_report(
        report_id=report_id,
        voter_id=voter_id,
        is_upvote=vote.is_upvote
    )
    
    return {"success": success}


@router.post("/report/{report_id}/alternative")
async def add_alternative(
    report_id: int,
    alt: AddAlternativeRequest,
    db: Session = Depends(get_db)
):
    """Add an alternative mod suggestion"""
    service = CompatibilityService(db)
    
    result = service.add_alternative(
        report_id=report_id,
        alternative_mod_id=alt.alternative_mod_id,
        alternative_mod_name=alt.alternative_mod_name,
        reason=alt.reason,
        mod_url=alt.mod_url,
        similarity=alt.similarity
    )
    
    return {
        "success": True,
        "alternative_id": result.id,
        "message": "Alternative suggestion added"
    }


# ============================================================
# HTML Endpoints (for HTMX)
# ============================================================

@router.get("/badge/{nexus_mod_id}", response_class=HTMLResponse)
async def get_compatibility_badge(
    request: Request,
    nexus_mod_id: int,
    db: Session = Depends(get_db)
):
    """Get a compatibility badge HTML component"""
    service = CompatibilityService(db)
    result = service.get_compatibility(nexus_mod_id)
    
    if not result:
        status = "unknown"
        confidence = 0
    else:
        status = result["status"]
        confidence = result.get("confidence", 0)
    
    # Map status to colors and icons
    status_config = {
        "works": {"color": "var(--accent-success)", "icon": "check-circle", "label": "Works"},
        "partial": {"color": "var(--accent-warning)", "icon": "alert-circle", "label": "Partial"},
        "broken": {"color": "var(--accent-error)", "icon": "x-circle", "label": "Broken"},
        "windows_only": {"color": "var(--text-tertiary)", "icon": "monitor", "label": "Windows Only"},
        "unknown": {"color": "var(--text-tertiary)", "icon": "help-circle", "label": "Unknown"},
    }
    
    config = status_config.get(status, status_config["unknown"])
    
    html = f'''
    <span class="compatibility-badge" style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: {config['color']}22; color: {config['color']};">
        <i data-lucide="{config['icon']}" style="width: 14px; height: 14px;"></i>
        <span>{config['label']}</span>
    </span>
    <script>if (typeof lucide !== 'undefined') lucide.createIcons();</script>
    '''
    
    return HTMLResponse(content=html)
