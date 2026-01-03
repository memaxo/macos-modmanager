from typing import List, Dict, Any, Optional, TypedDict
from app.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.mod import Mod
from app.core.nexus_api import NexusAPIClient
from datetime import datetime


class UpdateInfoDict(TypedDict):
    mod_id: int
    mod_name: str
    current_version: Optional[str]
    latest_version: str
    nexus_mod_id: Optional[int]

class UpdateManager:
    """Checks for mod updates via Nexus API"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_for_updates(self, mod_id: Optional[int] = None) -> List[UpdateInfoDict]:
        """Check for updates for one or all mods"""
        if not settings.nexus_api_key:
            return []
            
        query = select(Mod).where(Mod.is_active == True, Mod.nexus_mod_id != None)
        if mod_id:
            query = query.where(Mod.id == mod_id)
            
        result = await self.db.execute(query)
        mods = result.scalars().all()
        
        updates: List[UpdateInfoDict] = []
        async with NexusAPIClient() as nexus:
            for mod in mods:
                try:
                    # Get latest info from Nexus
                    nexus_info = await nexus.get_mod(settings.game_domain, mod.nexus_mod_id)
                    latest_version = nexus_info.get("version")
                    
                    if latest_version and latest_version != mod.version:
                        updates.append(UpdateInfoDict(
                            mod_id=mod.id,
                            mod_name=mod.name,
                            current_version=mod.version,
                            latest_version=latest_version,
                            nexus_mod_id=mod.nexus_mod_id
                        ))
                        
                    # Update last_checked timestamp
                    mod.last_checked = datetime.utcnow()
                    await self.db.flush()
                    
                except Exception:
                    # Skip if API fails for one mod
                    continue
                    
        await self.db.commit()
        return updates
