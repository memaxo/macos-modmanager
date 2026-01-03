from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path
from app.database import get_db
from app.models.settings import UserSetting
from app.config import settings
from app.utils.security import encrypt_value, decrypt_value, is_encrypted
from app.core.game_detector import detect_game_installations, validate_and_set_custom_path
from typing import Optional

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def get_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Get settings page"""
    # Load settings from database
    result = await db.execute(select(UserSetting))
    settings_list = result.scalars().all()
    db_settings = {}
    needs_migration = False
    
    for setting in settings_list:
        # Decrypt encrypted values (like API keys)
        if setting.value_type == "encrypted":
            try:
                db_settings[setting.key] = decrypt_value(setting.value)
            except Exception:
                # If decryption fails, don't expose the encrypted value
                db_settings[setting.key] = ""
        elif setting.key == "nexus_api_key" and is_encrypted(setting.value):
            # Handle legacy encrypted values that don't have value_type set
            try:
                db_settings[setting.key] = decrypt_value(setting.value)
                # Auto-migrate: update value_type to encrypted
                setting.value_type = "encrypted"
                needs_migration = True
            except Exception:
                # If decryption fails, treat as plaintext (might be unencrypted)
                db_settings[setting.key] = setting.value
        else:
            db_settings[setting.key] = setting.value
    
    # Commit any migrations
    if needs_migration:
        await db.commit()
    
    # Get detected game installations
    game_installations = await detect_game_installations()
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "db_settings": db_settings,
        "config": settings,
        "game_installations": game_installations,
        "custom_game_path": settings.custom_game_path or ""
    })

@router.post("/nexus-api-key", response_class=HTMLResponse)
async def save_nexus_key(
    request: Request,
    api_key: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Save Nexus API Key (encrypted)"""
    # Check if exists
    result = await db.execute(select(UserSetting).where(UserSetting.key == "nexus_api_key"))
    setting = result.scalar_one_or_none()
    
    # Encrypt the API key before storing
    encrypted_key = encrypt_value(api_key)
    
    if setting:
        setting.value = encrypted_key
    else:
        setting = UserSetting(key="nexus_api_key", value=encrypted_key, value_type="encrypted")
        db.add(setting)
    
    await db.commit()
    
    # Update runtime config with plaintext (only in memory)
    settings.nexus_api_key = api_key
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": "Nexus API key saved and encrypted successfully!",
        "type": "success"
    })

@router.post("/general", response_class=HTMLResponse)
async def save_general_settings(
    request: Request,
    auto_check_updates: bool = Form(False),
    backup_before_install: bool = Form(False),
    db: AsyncSession = Depends(get_db)
):
    """Save general settings"""
    # This is a bit simplified, usually you'd loop or use a more robust way
    for key, val in [("auto_check_updates", str(auto_check_updates)), ("backup_before_install", str(backup_before_install))]:
        result = await db.execute(select(UserSetting).where(UserSetting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = val
        else:
            db.add(UserSetting(key=key, value=val, value_type="boolean"))
    
    await db.commit()
    
    # Update runtime config
    settings.auto_check_updates = auto_check_updates
    settings.backup_before_install = backup_before_install
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": "General settings saved!",
        "type": "success"
    })


@router.post("/game-path", response_class=HTMLResponse)
async def save_game_path(
    request: Request,
    game_path: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Save custom game installation path"""
    # Validate the path
    success, message = await validate_and_set_custom_path(game_path)
    
    if not success:
        return templates.TemplateResponse("components/toast.html", {
            "request": request,
            "message": f"Invalid game path: {message}",
            "type": "error"
        })
    
    # Save to database for persistence
    result = await db.execute(select(UserSetting).where(UserSetting.key == "custom_game_path"))
    setting = result.scalar_one_or_none()
    
    if setting:
        setting.value = game_path
    else:
        db.add(UserSetting(key="custom_game_path", value=game_path, value_type="string"))
    
    await db.commit()
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": f"Game path set to: {game_path}",
        "type": "success"
    })


@router.post("/game-path/clear", response_class=HTMLResponse)
async def clear_game_path(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Clear custom game path (use auto-detection)"""
    # Clear from config
    settings.custom_game_path = None
    
    # Remove from database
    result = await db.execute(select(UserSetting).where(UserSetting.key == "custom_game_path"))
    setting = result.scalar_one_or_none()
    if setting:
        await db.delete(setting)
        await db.commit()
    
    return templates.TemplateResponse("components/toast.html", {
        "request": request,
        "message": "Custom game path cleared. Using auto-detection.",
        "type": "success"
    })


@router.get("/game-path/detect", response_class=HTMLResponse)
async def detect_game_path(request: Request):
    """Detect all game installations and return as HTML"""
    installations = await detect_game_installations()
    
    if not installations:
        return """
        <div class="alert alert-warning">
            <i data-lucide="alert-triangle"></i>
            <span>No Cyberpunk 2077 installations found. Please set the path manually.</span>
        </div>
        <script>if (typeof lucide !== 'undefined') lucide.createIcons();</script>
        """
    
    html_items = []
    for inst in installations:
        html_items.append(f"""
        <div class="detected-game" style="padding: 0.5rem; margin: 0.25rem 0; background: var(--bg-secondary); border-radius: 4px; cursor: pointer;"
             onclick="document.getElementById('game-path-input').value = '{inst['path']}'">
            <strong>{inst['launcher'].capitalize()}</strong>
            <small style="color: var(--text-secondary); display: block;">{inst['path']}</small>
            {f"<small>Version: {inst['version']}</small>" if inst.get('version') else ""}
        </div>
        """)
    
    return f"""
    <div class="detected-installations">
        <p style="color: var(--text-secondary); margin-bottom: 0.5rem;">Click to use:</p>
        {''.join(html_items)}
    </div>
    """
