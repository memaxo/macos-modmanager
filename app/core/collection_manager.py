import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.collection import Collection, CollectionMod
from app.models.mod import Mod
from app.core.mod_manager import ModManager, ModInstallationError, FomodInstallRequired
from app.core.nexus_api import NexusAPIClient
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class CollectionError(Exception):
    """Exception raised during collection operations"""
    pass

class CollectionManager:
    """Manages Nexus Mods collections import and installation"""
    
    def __init__(self, db: AsyncSession, mod_manager: ModManager):
        self.db = db
        self.mod_manager = mod_manager

    async def import_collection(self, nexus_collection_id: str, game_domain: Optional[str] = None) -> Collection:
        """Import collection metadata from Nexus Mods"""
        game_domain = game_domain or settings.game_domain
        async with NexusAPIClient() as nexus:
            try:
                collection_info = await nexus.get_collection(nexus_collection_id, game_domain)
            except Exception as e:
                raise CollectionError(f"Failed to fetch collection from Nexus: {str(e)}")
            
            if not collection_info:
                raise CollectionError(f"Collection {nexus_collection_id} not found")

            # Extract mods from GraphQL response
            mods_data = []
            revision = collection_info.get("latestPublishedRevision") or collection_info.get("currentRevision")
            if revision:
                for mod_item in revision.get("mods", []):
                    mod_info = mod_item.get("mod", {})
                    
                    # Extract FOMOD installer choices if present
                    installer_choices = None
                    if mod_item.get("choices"):
                        installer_choices = {
                            "type": mod_item.get("choices", {}).get("type", "fomod"),
                            "options": mod_item.get("choices", {}).get("options", [])
                        }
                    
                    mods_data.append({
                        "nexus_mod_id": mod_info.get("nexusModId"),
                        "nexus_file_id": mod_item.get("fileId"),
                        "is_required": mod_item.get("isRequired", True),
                        "installer_choices": installer_choices
                    })
            
            # Create collection record
            collection = Collection(
                nexus_collection_id=nexus_collection_id,
                name=collection_info.get("name", "Unknown Collection"),
                author=collection_info.get("author", {}).get("name", "Unknown"),
                description=collection_info.get("summary") or collection_info.get("description"),
                game_id=game_domain,
                version="latest",
                mod_count=len(mods_data),
                collection_data=collection_info
            )
            
            self.db.add(collection)
            await self.db.flush()
            
            # Add mods to collection
            for i, m_data in enumerate(mods_data):
                col_mod = CollectionMod(
                    collection_id=collection.id,
                    nexus_mod_id=m_data["nexus_mod_id"],
                    nexus_file_id=m_data["nexus_file_id"],
                    is_required=m_data["is_required"],
                    install_order=i,
                    installer_choices=m_data.get("installer_choices")  # Pre-saved FOMOD choices
                )
                self.db.add(col_mod)
                
            await self.db.commit()
            return collection

    async def install_collection(
        self,
        collection_id: int,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> None:
        """Batch install all mods in a collection"""
        result = await self.db.execute(
            select(Collection).where(Collection.id == collection_id)
        )
        collection = result.scalar_one_or_none()
        if not collection:
            raise CollectionError("Collection not found")
        
        # Get mods in order
        mods_result = await self.db.execute(
            select(CollectionMod)
            .where(CollectionMod.collection_id == collection_id)
            .order_by(CollectionMod.install_order)
        )
        collection_mods = mods_result.scalars().all()
        
        total_mods = len(collection_mods)
        fomod_pending: List[Dict[str, Any]] = []  # Track mods needing FOMOD wizard
        
        for i, col_mod in enumerate(collection_mods):
            if on_progress:
                on_progress(i, total_mods, f"Installing mod {i+1}/{total_mods}")
            
            try:
                # Install mod via mod_manager with FOMOD support
                installed_mod = await self._install_collection_mod(col_mod)
                
                # Update link in collection_mods
                col_mod.mod_id = installed_mod.id
                await self.db.flush()
                
            except FomodInstallRequired as e:
                # FOMOD wizard required - track for later
                logger.info(f"FOMOD wizard required for mod in collection: {e.mod_info.get('name', 'Unknown')}")
                fomod_pending.append({
                    "collection_mod": col_mod,
                    "session_id": e.session_id,
                    "mod_info": e.mod_info
                })
                # Continue with other mods
                continue
                
            except ModInstallationError as e:
                if col_mod.is_required:
                    raise CollectionError(f"Failed to install required mod in collection: {str(e)}")
                # If optional, we can continue
                continue
            except Exception as e:
                if col_mod.is_required:
                    raise CollectionError(f"Unexpected error installing collection mod: {str(e)}")
                continue
        
        # If there are pending FOMOD mods without pre-saved choices, raise an exception
        # so the UI can handle the wizard flow
        if fomod_pending:
            raise CollectionFomodPending(
                collection=collection,
                pending_mods=fomod_pending,
                installed_count=total_mods - len(fomod_pending)
            )
                
        collection.installed_at = func.now()
        await self.db.commit()
    
    async def _install_collection_mod(self, col_mod: CollectionMod) -> Mod:
        """Install a single mod from a collection with FOMOD support"""
        async with NexusAPIClient() as nexus:
            # Get mod info
            mod_info = await nexus.get_mod(settings.game_domain, col_mod.nexus_mod_id)
            
            # Get mod files
            files_info = await nexus.get_mod_files(settings.game_domain, col_mod.nexus_mod_id)
            files = files_info.get("files", [])
            
            if not files:
                raise ModInstallationError("No files available for this mod")
            
            # Use specified file or latest
            target_file = next(
                (f for f in files if f["file_id"] == col_mod.nexus_file_id), 
                files[0]
            )
            
            # Download mod file
            download_links = await nexus.get_download_link(
                settings.game_domain,
                col_mod.nexus_mod_id,
                target_file["file_id"]
            )
            
            # API returns a list of download links, use the first one
            if isinstance(download_links, list) and download_links:
                download_url = download_links[0].get("URI")
            else:
                download_url = download_links.get("URI") if isinstance(download_links, dict) else None
            
            if not download_url:
                raise ModInstallationError("Could not get download URL")
            
            # Download to temp location
            temp_file = settings.cache_dir / f"{col_mod.nexus_mod_id}_{target_file['file_id']}.zip"
            await nexus.download_file(download_url, temp_file)
            
            try:
                # Install with FOMOD support - pass pre-saved choices if available
                installed_mod = await self.mod_manager.install_mod_from_file_with_fomod_check(
                    temp_file,
                    nexus_mod_id=col_mod.nexus_mod_id,
                    mod_info={
                        "name": mod_info.get("name"),
                        "author": mod_info.get("author"),
                        "version": mod_info.get("version"),
                        "description": mod_info.get("summary"),
                        "thumbnail_url": mod_info.get("picture_url"),
                        "nexus_url": f"https://www.nexusmods.com/{settings.game_domain}/mods/{col_mod.nexus_mod_id}"
                    },
                    fomod_choices=col_mod.installer_choices  # Use pre-saved choices if available
                )
                
                return installed_mod
                
            finally:
                # Cleanup temp file
                if temp_file.exists():
                    temp_file.unlink()


class CollectionFomodPending(Exception):
    """Exception raised when collection installation has mods pending FOMOD wizard"""
    
    def __init__(self, collection: Collection, pending_mods: List[Dict[str, Any]], installed_count: int):
        self.collection = collection
        self.pending_mods = pending_mods
        self.installed_count = installed_count
        super().__init__(
            f"Collection '{collection.name}' has {len(pending_mods)} mod(s) requiring FOMOD configuration"
        )