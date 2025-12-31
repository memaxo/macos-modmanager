import httpx
import asyncio
from typing import Optional, List, Dict, Any, Callable, Union, Awaitable
from pathlib import Path
import json
from app.config import settings


class NexusAPIError(Exception):
    """Base exception for Nexus API errors"""
    pass


class NexusAPIClient:
    """Async client for Nexus Mods API"""
    
    BASE_URL_V1 = "https://api.nexusmods.com/v1"
    BASE_URL_V2 = "https://api.nexusmods.com/v2"
    GRAPHQL_URL = f"{BASE_URL_V2}/graphql"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.nexus_api_key
        if not self.api_key:
            raise NexusAPIError("Nexus Mods API key is required")
        
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL_V1,
            headers={
                "apikey": self.api_key,
                "User-Agent": f"{settings.app_name}/1.0",
                "Accept": "application/json"
            },
            timeout=30.0
        )
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    # User endpoints
    async def get_user(self) -> Dict[str, Any]:
        """Get current user information"""
        response = await self.client.get("/users/validate.json")
        response.raise_for_status()
        return response.json()
    
    # Game endpoints
    async def get_games(self) -> List[Dict[str, Any]]:
        """Get list of all games"""
        response = await self.client.get("/games.json")
        response.raise_for_status()
        return response.json()
    
    async def get_game(self, game_domain: str) -> Dict[str, Any]:
        """Get game information"""
        response = await self.client.get(f"/games/{game_domain}.json")
        response.raise_for_status()
        return response.json()
    
    # Mod endpoints
    async def get_mod(self, game_domain: str, mod_id: int) -> Dict[str, Any]:
        """Get mod information"""
        response = await self.client.get(f"/games/{game_domain}/mods/{mod_id}.json")
        response.raise_for_status()
        return response.json()
    
    async def get_mod_files(self, game_domain: str, mod_id: int) -> Dict[str, Any]:
        """Get mod files"""
        response = await self.client.get(f"/games/{game_domain}/mods/{mod_id}/files.json")
        response.raise_for_status()
        return response.json()
    
    async def get_mod_updates(self, game_domain: str, mod_id: int, period: str = "1m") -> List[Dict[str, Any]]:
        """Get mod updates
        
        Args:
            game_domain: Game domain name
            mod_id: Mod ID
            period: Time period (1d, 1w, 1m)
        """
        response = await self.client.get(
            f"/games/{game_domain}/mods/{mod_id}/updates.json",
            params={"period": period}
        )
        response.raise_for_status()
        return response.json()
    
    async def get_download_link(
        self, 
        game_domain: str, 
        mod_id: int, 
        file_id: int,
        key: Optional[str] = None,
        expires: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get download link for mod file
        
        Args:
            game_domain: Game domain name
            mod_id: Mod ID
            file_id: File ID
            key: Download key (for premium users)
            expires: Expiration time
        """
        params = {}
        if key:
            params["key"] = key
        if expires:
            params["expires"] = expires
        
        response = await self.client.get(
            f"/games/{game_domain}/mods/{mod_id}/files/{file_id}/download_link.json",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def search_mods(
        self,
        game_domain: str,
        query: Optional[str] = None,
        category_id: Optional[int] = None,
        author: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        updated: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Search mods
        
        Args:
            game_domain: Game domain name
            query: Search query
            category_id: Category filter
            author: Author filter
            uploaded_by: Uploader filter
            updated: Updated filter (1d, 1w, 1m, 3m, 6m, 1y)
            status: Status filter (published, hidden, etc.)
            page: Page number
            page_size: Results per page
        """
        params = {
            "page": page,
            "page_size": page_size
        }
        if query:
            params["q"] = query
        if category_id:
            params["category_id"] = category_id
        if author:
            params["author"] = author
        if uploaded_by:
            params["uploaded_by"] = uploaded_by
        if updated:
            params["updated"] = updated
        if status:
            params["status"] = status
        
        response = await self.client.get(
            f"/games/{game_domain}/mods.json",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    # Collections endpoints (GraphQL)
    async def get_collection(self, collection_id: str, game_domain: str) -> Dict[str, Any]:
        """Get collection information using GraphQL"""
        query = """
        query GetCollection($collectionId: String!, $gameDomain: String!) {
            collection(id: $collectionId, gameDomainName: $gameDomain) {
                id
                name
                summary
                description
                author {
                    name
                    memberId
                }
                game {
                    domainName
                    name
                }
                currentRevision {
                    mods {
                        mod {
                            id
                            name
                            author
                            nexusModId
                        }
                        fileId
                        isRequired
                    }
                }
                latestPublishedRevision {
                    mods {
                        mod {
                            id
                            name
                            author
                            nexusModId
                        }
                        fileId
                        isRequired
                    }
                }
            }
        }
        """
        
        variables = {
            "collectionId": collection_id,
            "gameDomain": game_domain
        }
        
        response = await httpx.AsyncClient().post(
            self.GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={
                "apikey": self.api_key,
                "Content-Type": "application/json"
            },
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            raise NexusAPIError(f"GraphQL errors: {data['errors']}")
        
        return data.get("data", {}).get("collection")
    
    async def parse_collection_url(self, url: str) -> tuple[str, str]:
        """Parse collection URL to extract game domain and collection ID
        
        Args:
            url: Collection URL (e.g., https://www.nexusmods.com/games/cyberpunk2077/collections/9uzsfp)
        
        Returns:
            Tuple of (game_domain, collection_id)
        """
        # Extract from URL pattern: nexusmods.com/games/{game}/collections/{id}
        import re
        pattern = r"nexusmods\.com/games/([^/]+)/collections/([^/?]+)"
        match = re.search(pattern, url)
        if not match:
            raise NexusAPIError(f"Invalid collection URL: {url}")
        return match.group(1), match.group(2)
    
    # Download helper
    async def download_file(
        self,
        download_url: str,
        destination: Path,
        progress_callback: Optional[Callable[[int, int], Union[None, Awaitable[None]]]] = None
    ) -> Path:
        """Download a file from Nexus Mods
        
        Args:
            download_url: Download URL
            destination: Destination path
            progress_callback: Optional callback for progress updates
        """
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", download_url) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                
                destination.parent.mkdir(parents=True, exist_ok=True)
                
                downloaded = 0
                with open(destination, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            if asyncio.iscoroutinefunction(progress_callback):
                                await progress_callback(downloaded, total_size)
                            else:
                                progress_callback(downloaded, total_size)
        
        return destination
