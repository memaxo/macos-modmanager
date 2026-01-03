"""
Backup API Endpoints

Endpoints for managing mod backups.
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

from app.core.backup_manager import BackupManager, BackupType

router = APIRouter()

# Singleton manager
_manager: Optional[BackupManager] = None


def get_manager() -> BackupManager:
    global _manager
    if _manager is None:
        _manager = BackupManager()
    return _manager


# ============================================================
# Request/Response Models
# ============================================================

class BackupTypeEnum(str, Enum):
    full = "full"
    incremental = "incremental"
    manual = "manual"


class CreateBackupRequest(BaseModel):
    name: str
    backup_type: BackupTypeEnum = BackupTypeEnum.manual
    include_frameworks: bool = True
    include_plugins: bool = True
    include_scripts: bool = True
    include_tweaks: bool = True
    include_archives: bool = False
    compress: bool = True


class RestoreBackupRequest(BaseModel):
    create_safety_backup: bool = True


# ============================================================
# Backup Endpoints
# ============================================================

@router.get("/")
async def list_backups():
    """List all available backups"""
    manager = get_manager()
    backups = await manager.list_backups()
    
    return {
        "backups": [
            {
                "id": b.id,
                "name": b.name,
                "type": b.backup_type.value,
                "size_bytes": b.size_bytes,
                "size_mb": round(b.size_bytes / (1024 * 1024), 2),
                "file_count": b.file_count,
                "created_at": b.created_at.isoformat(),
                "is_compressed": b.is_compressed,
                "game_version": b.game_version,
            }
            for b in backups
        ],
        "total": len(backups),
    }


@router.post("/")
async def create_backup(request: CreateBackupRequest, background_tasks: BackgroundTasks):
    """Create a new backup"""
    manager = get_manager()
    
    try:
        backup_type = BackupType(request.backup_type.value)
        
        backup = await manager.create_backup(
            name=request.name,
            backup_type=backup_type,
            include_frameworks=request.include_frameworks,
            include_plugins=request.include_plugins,
            include_scripts=request.include_scripts,
            include_tweaks=request.include_tweaks,
            include_archives=request.include_archives,
            compress=request.compress,
        )
        
        return {
            "success": True,
            "backup": {
                "id": backup.id,
                "name": backup.name,
                "type": backup.backup_type.value,
                "size_bytes": backup.size_bytes,
                "size_mb": round(backup.size_bytes / (1024 * 1024), 2),
                "file_count": backup.file_count,
                "created_at": backup.created_at.isoformat(),
                "is_compressed": backup.is_compressed,
            },
            "message": f"Backup '{request.name}' created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{backup_id}")
async def get_backup(backup_id: str):
    """Get details about a specific backup"""
    manager = get_manager()
    backups = await manager.list_backups()
    
    backup = next((b for b in backups if b.id == backup_id), None)
    
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")
    
    # Verify integrity
    integrity = await manager.verify_integrity(backup_id)
    
    return {
        "id": backup.id,
        "name": backup.name,
        "type": backup.backup_type.value,
        "size_bytes": backup.size_bytes,
        "size_mb": round(backup.size_bytes / (1024 * 1024), 2),
        "file_count": backup.file_count,
        "created_at": backup.created_at.isoformat(),
        "is_compressed": backup.is_compressed,
        "game_version": backup.game_version,
        "integrity": integrity,
    }


@router.post("/{backup_id}/restore")
async def restore_backup(backup_id: str, request: RestoreBackupRequest):
    """Restore from a backup"""
    manager = get_manager()
    
    try:
        result = await manager.restore(
            backup_id=backup_id,
            create_pre_restore_backup=request.create_safety_backup,
        )
        
        return {
            "success": result.success,
            "message": result.message,
            "files_restored": result.files_restored,
            "errors": result.errors,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{backup_id}/verify")
async def verify_backup(backup_id: str):
    """Verify backup integrity"""
    manager = get_manager()
    
    try:
        result = await manager.verify_integrity(backup_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{backup_id}")
async def delete_backup(backup_id: str):
    """Delete a backup"""
    manager = get_manager()
    
    deleted = await manager.delete_backup(backup_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Backup not found")
    
    return {
        "success": True,
        "message": f"Backup {backup_id} deleted"
    }


@router.get("/storage/stats")
async def get_storage_stats():
    """Get backup storage statistics"""
    manager = get_manager()
    
    total_used = await manager.get_total_storage_used()
    backups = await manager.list_backups()
    
    return {
        "total_backups": len(backups),
        "total_bytes": total_used,
        "total_mb": round(total_used / (1024 * 1024), 2),
        "total_gb": round(total_used / (1024 * 1024 * 1024), 2),
        "backup_dir": str(manager.backup_dir),
    }


@router.post("/cleanup")
async def cleanup_old_backups(keep: int = Query(10, ge=1, le=50)):
    """Delete old backups, keeping the N most recent"""
    manager = get_manager()
    
    deleted = await manager.delete_old_backups(keep=keep)
    
    return {
        "success": True,
        "deleted_count": deleted,
        "message": f"Deleted {deleted} old backups, keeping {keep} most recent"
    }


@router.post("/quick")
async def create_quick_backup():
    """Create a quick backup with default settings"""
    manager = get_manager()
    
    try:
        from datetime import datetime
        
        backup = await manager.create_backup(
            name=f"Quick Backup {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            backup_type=BackupType.MANUAL,
            compress=True,
        )
        
        return {
            "success": True,
            "backup_id": backup.id,
            "message": "Quick backup created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
