from typing import List, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.profile import ModProfile, ProfileMod
from app.models.mod import Mod
from app.models.load_order import ModLoadOrder


class ProfileManager:
    """Manage mod profiles and load order"""
    
    def __init__(self, db: AsyncSession, game_id: str = "cyberpunk2077"):
        self.db = db
        self.game_id = game_id
    
    async def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        is_default: bool = False
    ) -> ModProfile:
        """Create a new mod profile"""
        # If this is default, unset other defaults
        if is_default:
            await self._unset_default_profiles()
        
        profile = ModProfile(
            name=name,
            game_id=self.game_id,
            description=description,
            is_default=is_default
        )
        
        self.db.add(profile)
        await self.db.flush()
        
        # Copy mods from default profile if exists
        if not is_default:
            default_profile = await self.get_default_profile()
            if default_profile:
                await self._copy_profile_mods(default_profile.id, profile.id)
        
        await self.db.commit()
        await self.db.refresh(profile)
        
        return profile
    
    async def get_profile(self, profile_id: int) -> Optional[ModProfile]:
        """Get a profile by ID"""
        result = await self.db.execute(
            select(ModProfile).where(ModProfile.id == profile_id)
        )
        return result.scalar_one_or_none()
    
    async def get_default_profile(self) -> Optional[ModProfile]:
        """Get the default profile"""
        result = await self.db.execute(
            select(ModProfile).where(
                ModProfile.game_id == self.game_id,
                ModProfile.is_default == True
            )
        )
        return result.scalar_one_or_none()
    
    async def list_profiles(self) -> List[ModProfile]:
        """List all profiles"""
        result = await self.db.execute(
            select(ModProfile).where(ModProfile.game_id == self.game_id)
        )
        return list(result.scalars().all())
    
    async def delete_profile(self, profile_id: int) -> None:
        """Delete a profile"""
        result = await self.db.execute(
            select(ModProfile).where(ModProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        
        if profile:
            if profile.is_default:
                raise ValueError("Cannot delete default profile")
            await self.db.delete(profile)
            await self.db.commit()
    
    async def add_mod_to_profile(
        self,
        profile_id: int,
        mod_id: int,
        enabled: bool = True
    ) -> ProfileMod:
        """Add a mod to a profile"""
        # Check if already exists
        result = await self.db.execute(
            select(ProfileMod).where(
                ProfileMod.profile_id == profile_id,
                ProfileMod.mod_id == mod_id
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.is_enabled = enabled
            return existing
        
        profile_mod = ProfileMod(
            profile_id=profile_id,
            mod_id=mod_id,
            is_enabled=enabled
        )
        
        self.db.add(profile_mod)
        await self.db.commit()
        await self.db.refresh(profile_mod)
        
        return profile_mod
    
    async def remove_mod_from_profile(self, profile_id: int, mod_id: int) -> None:
        """Remove a mod from a profile"""
        result = await self.db.execute(
            select(ProfileMod).where(
                ProfileMod.profile_id == profile_id,
                ProfileMod.mod_id == mod_id
            )
        )
        profile_mod = result.scalar_one_or_none()
        
        if profile_mod:
            await self.db.delete(profile_mod)
            await self.db.commit()
    
    async def get_profile_mods(self, profile_id: int) -> List[Dict]:
        """Get all mods in a profile"""
        result = await self.db.execute(
            select(ProfileMod, Mod).join(Mod).where(
                ProfileMod.profile_id == profile_id
            ).order_by(ProfileMod.id)
        )
        
        mods = []
        for profile_mod, mod in result.all():
            mods.append({
                "mod_id": mod.id,
                "name": mod.name,
                "enabled": profile_mod.is_enabled,
                "mod": mod
            })
        
        return mods
    
    async def set_load_order(
        self,
        profile_id: Optional[int],
        mod_priorities: Dict[int, int]
    ) -> None:
        """Set load order for mods in a profile"""
        # Clear existing load order
        query = select(ModLoadOrder).where(
            ModLoadOrder.game_id == self.game_id,
            ModLoadOrder.profile_id == profile_id
        )
        result = await self.db.execute(query)
        existing = result.scalars().all()
        
        for load_order in existing:
            await self.db.delete(load_order)
        
        # Create new load order entries
        for mod_id, priority in mod_priorities.items():
            load_order = ModLoadOrder(
                mod_id=mod_id,
                game_id=self.game_id,
                profile_id=profile_id,
                priority=priority
            )
            self.db.add(load_order)
        
        await self.db.commit()
    
    async def get_load_order(
        self,
        profile_id: Optional[int] = None
    ) -> List[Dict]:
        """Get load order for a profile"""
        query = select(ModLoadOrder, Mod).join(Mod).where(
            ModLoadOrder.game_id == self.game_id,
            ModLoadOrder.profile_id == profile_id
        ).order_by(ModLoadOrder.priority)
        
        result = await self.db.execute(query)
        
        load_order = []
        for load_order_entry, mod in result.all():
            load_order.append({
                "mod_id": mod.id,
                "mod_name": mod.name,
                "priority": load_order_entry.priority
            })
        
        return load_order
    
    async def activate_profile(self, profile_id: int) -> None:
        """Activate a profile (enable/disable mods accordingly)"""
        profile_mods = await self.get_profile_mods(profile_id)
        
        # Get all mods
        all_mods_result = await self.db.execute(
            select(Mod).where(Mod.is_active == True)
        )
        all_mods = {mod.id: mod for mod in all_mods_result.scalars().all()}
        
        # Enable/disable mods based on profile
        profile_mod_ids = {pm["mod_id"] for pm in profile_mods}
        
        for mod_id, mod in all_mods.items():
            if mod_id in profile_mod_ids:
                # Check if enabled in profile
                profile_mod = next(
                    pm for pm in profile_mods if pm["mod_id"] == mod_id
                )
                mod.is_enabled = profile_mod["enabled"]
            else:
                # Mod not in profile, disable it
                mod.is_enabled = False
        
        await self.db.commit()
    
    async def _unset_default_profiles(self) -> None:
        """Unset default flag from all profiles"""
        result = await self.db.execute(
            select(ModProfile).where(
                ModProfile.game_id == self.game_id,
                ModProfile.is_default == True
            )
        )
        profiles = result.scalars().all()
        for profile in profiles:
            profile.is_default = False
    
    async def _copy_profile_mods(
        self,
        source_profile_id: int,
        target_profile_id: int
    ) -> None:
        """Copy mods from one profile to another"""
        source_mods = await self.get_profile_mods(source_profile_id)
        
        for mod_info in source_mods:
            await self.add_mod_to_profile(
                target_profile_id,
                mod_info["mod_id"],
                enabled=mod_info["enabled"]
            )
