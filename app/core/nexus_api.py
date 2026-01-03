import httpx
import asyncio
from typing import Optional, List, Dict, Any, Callable, Union, Awaitable, TypedDict
from pathlib import Path
import json
import aiofiles
from app.config import settings


ProgressCallback = Callable[[int, int], Union[None, Awaitable[None]]]


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
        
        self.cache_dir = settings.cache_dir / "nexus_api_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.rate_limits = {
            "daily_limit": None,
            "daily_remaining": None,
            "hourly_limit": None,
            "hourly_remaining": None,
            "reset": None
        }
        
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL_V1,
            headers={
                "apikey": self.api_key,
                "User-Agent": f"{settings.app_name}/1.0",
                "Accept": "application/json"
            },
            timeout=30.0
        )

    async def _get_with_cache(self, url: str, params: Optional[Dict[str, Any]] = None, cache_ttl: int = 3600) -> Dict[str, Any]:
        """GET request with file-based caching and rate limit tracking"""
        import hashlib
        cache_key = hashlib.md5(f"{url}{json.dumps(params or {}, sort_keys=True)}".encode()).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        
        # Check cache
        if cache_path.exists():
            from datetime import datetime, timedelta
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            if datetime.now() - mtime < timedelta(seconds=cache_ttl):
                async with aiofiles.open(cache_path, 'r') as f:
                    return json.loads(await f.read())
        
        # Check rate limits before making request
        if self.rate_limits["daily_remaining"] == 0 or self.rate_limits["hourly_remaining"] == 0:
            raise NexusAPIError("Nexus API rate limit reached. Please wait.")

        response = await self.client.get(url, params=params)
        
        # Update rate limits from headers
        self.rate_limits["daily_limit"] = response.headers.get("x-rl-daily-limit")
        self.rate_limits["daily_remaining"] = int(response.headers.get("x-rl-daily-remaining", 100))
        self.rate_limits["hourly_limit"] = response.headers.get("x-rl-hourly-limit")
        self.rate_limits["hourly_remaining"] = int(response.headers.get("x-rl-hourly-remaining", 100))
        
        response.raise_for_status()
        data = response.json()
        
        # Save to cache
        async with aiofiles.open(cache_path, 'w') as f:
            await f.write(json.dumps(data))
            
        return data
    
    async def _post_graphql_with_cache(
        self,
        query: str,
        variables: Dict[str, Any],
        cache_ttl: int = 3600
    ) -> Dict[str, Any]:
        """POST GraphQL request with file-based caching"""
        import hashlib
        import aiofiles
        cache_key = hashlib.md5(f"{query}{json.dumps(variables, sort_keys=True)}".encode()).hexdigest()
        cache_path = self.cache_dir / f"graphql_{cache_key}.json"
        
        # Check cache
        if cache_path.exists():
            from datetime import datetime, timedelta
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            if datetime.now() - mtime < timedelta(seconds=cache_ttl):
                async with aiofiles.open(cache_path, 'r') as f:
                    return json.loads(await f.read())
        
        # Check rate limits before making request
        if self.rate_limits["daily_remaining"] == 0 or self.rate_limits["hourly_remaining"] == 0:
            raise NexusAPIError("Nexus API rate limit reached. Please wait.")
        
        async with httpx.AsyncClient() as graphql_client:
            response = await graphql_client.post(
                self.GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers={
                    "apikey": self.api_key,
                    "User-Agent": f"{settings.app_name}/1.0",
                    "Accept": "application/json"
                },
                timeout=30.0
            )
        
        # Update rate limits from headers
        self.rate_limits["daily_remaining"] = int(response.headers.get("x-rl-daily-remaining", 100))
        self.rate_limits["hourly_remaining"] = int(response.headers.get("x-rl-hourly-remaining", 100))
        
        response.raise_for_status()
        data = response.json()
        
        # Save to cache
        async with aiofiles.open(cache_path, 'w') as f:
            await f.write(json.dumps(data))
        
        return data
    
    async def close(self) -> None:
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def __aenter__(self) -> "NexusAPIClient":
        return self
    
    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any]
    ) -> None:
        await self.close()
    
    # User endpoints
    async def get_user(self) -> Dict[str, Any]:
        """Get current user information and limits"""
        return await self._get_with_cache("/users/validate.json", cache_ttl=300)
    
    # Game endpoints
    async def get_games(self) -> List[Dict[str, Any]]:
        """Get list of all games"""
        return await self._get_with_cache("/games.json", cache_ttl=86400)
    
    async def get_game(self, game_domain: str) -> Dict[str, Any]:
        """Get game information"""
        return await self._get_with_cache(f"/games/{game_domain}.json", cache_ttl=86400)
    
    async def get_categories(self, game_domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get categories for a game using GraphQL"""
        game_domain = game_domain or settings.game_domain
        query = """
        query GetCategories($gameDomain: String!) {
            game(domainName: $gameDomain) {
                modCategories {
                    id
                    name
                }
            }
        }
        """
        variables = {"gameDomain": game_domain}
        
        try:
            data = await self._post_graphql_with_cache(query, variables, cache_ttl=86400)
            categories = data.get("data", {}).get("game", {}).get("modCategories", [])
            
            # Transform to match expected format (category_id)
            return [
                {
                    "category_id": int(cat["id"]),
                    "name": cat["name"]
                }
                for cat in categories
            ]
        except Exception:
            # Fallback to a hardcoded list of common Cyberpunk categories if API fails
            if game_domain == "cyberpunk2077":
                return [
                    {"category_id": 1, "name": "Visuals and Graphics"},
                    {"category_id": 2, "name": "Gameplay"},
                    {"category_id": 3, "name": "User Interface"},
                    {"category_id": 4, "name": "Vehicles"},
                    {"category_id": 5, "name": "Characters"},
                    {"category_id": 6, "name": "Clothing and Accessories"},
                    {"category_id": 7, "name": "Weapons"},
                    {"category_id": 8, "name": "Quests and Adventures"},
                    {"category_id": 9, "name": "Utilities"},
                    {"category_id": 10, "name": "Scripts and Tools"}
                ]
            return []
    
    # Mod endpoints
    async def get_mod(self, game_domain: str, mod_id: int) -> Dict[str, Any]:
        """Get mod information"""
        return await self._get_with_cache(f"/games/{game_domain}/mods/{mod_id}.json", cache_ttl=3600)
    
    async def get_mod_files(self, game_domain: str, mod_id: int) -> Dict[str, Any]:
        """Get mod files"""
        return await self._get_with_cache(f"/games/{game_domain}/mods/{mod_id}/files.json", cache_ttl=1800)
    
    async def get_mod_images(self, game_domain: str, mod_id: int) -> List[Dict[str, Any]]:
        """Get mod images"""
        return await self._get_with_cache(f"/games/{game_domain}/mods/{mod_id}/images.json", cache_ttl=3600)

    async def get_mod_requirements(self, mod_id: int, game_domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get mod requirements (dependencies) using GraphQL"""
        game_domain = game_domain or settings.game_domain
        query = """
        query GetModRequirements($gameDomain: String!, $modId: Int!) {
            mod(gameDomainName: $gameDomain, nexusModId: $modId) {
                requirements {
                    id
                    nexusModId
                    name
                    isRequired
                    type
                }
            }
        }
        """
        variables = {
            "gameDomain": game_domain,
            "modId": mod_id
        }
        try:
            data = await self._post_graphql_with_cache(query, variables, cache_ttl=3600)
            return data.get("data", {}).get("mod", {}).get("requirements", [])
        except Exception:
            return []
    
    async def search_mods_graphql(
        self,
        game_domain: str,
        query: Optional[str] = None,
        category_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None,
        sort_by: str = "endorsements",  # endorsements, downloads, updated, created
        include_requirements: bool = True,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Search mods using GraphQL API v2 with requirements included
        
        This is more efficient than REST API v1 as it can include requirements
        in the same query, reducing API calls.
        
        Sort options:
        - endorsements: Most endorsed mods
        - downloads: Most downloaded mods
        - updated: Recently updated mods
        - created: Recently added mods (latest)
        
        Note: GraphQL API v2 is still in development, so this may not support
        all features. Falls back to REST API if GraphQL fails.
        """
        graphql_query = """
        query SearchMods(
            $gameDomain: String!
            $query: String
            $categoryId: Int
            $limit: Int
            $offset: Int
        ) {
            mods(
                gameDomainName: $gameDomain
                filter: {
                    name: $query
                    categoryId: $categoryId
                }
                count: $limit
                offset: $offset
            ) {
                nodes {
                    id
                    nexusModId
                    name
                    summary
                    description
                    author
                    pictureUrl
                    endorsements
                    totalDownloads
                    uniqueDownloads
                    updatedAt
                    createdAt
                    category {
                        id
                        name
                    }
                    requirements @include(if: $includeRequirements) {
                        id
                        nexusModId
                        name
                        isRequired
                        type
                    }
                }
                nodesCount
                totalCount
            }
        }
        """
        
        variables = {
            "gameDomain": game_domain,
            "query": query,
            "categoryId": category_id,
            "limit": limit,
            "offset": offset,
            "includeRequirements": include_requirements
        }
        
        try:
            data = await self._post_graphql_with_cache(graphql_query, variables, cache_ttl=1800)
            mods_data = data.get("data", {}).get("mods", {})
            
            # Transform to match REST API format for compatibility
            mods_list = []
            for mod in mods_data.get("nodes", []):
                mod_dict = {
                    "mod_id": mod.get("nexusModId"),
                    "name": mod.get("name"),
                    "summary": mod.get("summary"),
                    "description": mod.get("description"),
                    "author": mod.get("author"),
                    "picture_url": mod.get("pictureUrl"),
                    "endorsements": mod.get("endorsements", 0),
                    "total_downloads": mod.get("totalDownloads", 0),
                    "mod_unique_downloads": mod.get("uniqueDownloads", 0),
                    "updated_at": mod.get("updatedAt"),
                    "created_at": mod.get("createdAt"),
                    "category": mod.get("category", {}).get("name") if mod.get("category") else None,
                    "requirements": mod.get("requirements", []) if include_requirements else []
                }
                mods_list.append(mod_dict)
            
            # Sort results based on sort_by parameter (server may not support all sort options)
            if sort_by == "downloads":
                mods_list.sort(key=lambda x: x.get("total_downloads", 0), reverse=True)
            elif sort_by == "endorsements":
                mods_list.sort(key=lambda x: x.get("endorsements", 0), reverse=True)
            elif sort_by == "updated":
                mods_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            elif sort_by == "created":
                mods_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            return {
                "results": mods_list,
                "total": mods_data.get("totalCount", 0),
                "count": mods_data.get("nodesCount", 0)
            }
        except Exception as e:
            # Fallback to REST API if GraphQL fails
            # This ensures backward compatibility
            return await self.search_mods(
                game_domain, 
                query=query, 
                category_id=category_id,
                page=(offset // limit) + 1,
                page_size=limit
            )
    
    async def search_collections(
        self,
        game_domain: str,
        sort_by: str = "downloads",  # downloads, endorsements, trending, updated
        count: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Search collections using GraphQL API v2
        
        Sort options:
        - downloads: Most downloaded collections
        - endorsements: Most endorsed collections
        - trending: Trending collections
        - updated: Recently updated collections
        """
        # Map our sort names to GraphQL enum values
        sort_map = {
            "downloads": "DOWNLOADS",
            "endorsements": "ENDORSEMENTS", 
            "trending": "TRENDING",
            "updated": "UPDATED_AT"
        }
        graphql_sort = sort_map.get(sort_by, "DOWNLOADS")
        
        graphql_query = """
        query SearchCollections(
            $gameDomain: String!
            $count: Int!
            $offset: Int!
        ) {
            collections(
                gameDomainName: $gameDomain
                count: $count
                offset: $offset
            ) {
                nodes {
                    id
                    slug
                    name
                    summary
                    description
                    endorsements
                    totalDownloads
                    tileImage {
                        url
                        thumbnailUrl
                    }
                    headerImage {
                        url
                    }
                    user {
                        name
                        avatar
                    }
                    latestPublishedRevision {
                        modCount
                        revisionNumber
                        updatedAt
                    }
                    adultContent
                    category {
                        name
                    }
                    updatedAt
                    createdAt
                }
                nodesCount
                totalCount
            }
        }
        """
        
        variables = {
            "gameDomain": game_domain,
            "count": count,
            "offset": offset
        }
        
        try:
            data = await self._post_graphql_with_cache(graphql_query, variables, cache_ttl=1800)
            
            # Check for GraphQL errors
            if "errors" in data:
                import logging
                logging.error(f"GraphQL errors for collections: {data['errors']}")
                return {
                    "results": [],
                    "total": 0,
                    "count": 0,
                    "error": data["errors"][0].get("message", "GraphQL error") if data["errors"] else "Unknown GraphQL error"
                }
            
            collections_data = data.get("data", {}).get("collections", {})
            
            # Transform to a friendlier format
            collections_list = []
            for coll in collections_data.get("nodes", []):
                revision = coll.get("latestPublishedRevision", {}) or {}
                tile_image = coll.get("tileImage", {}) or {}
                user = coll.get("user", {}) or {}
                
                coll_dict = {
                    "id": coll.get("id"),
                    "slug": coll.get("slug"),
                    "name": coll.get("name"),
                    "summary": coll.get("summary"),
                    "description": coll.get("description"),
                    "endorsements": coll.get("endorsements", 0),
                    "total_downloads": coll.get("totalDownloads", 0),
                    "tile_image": tile_image.get("url"),
                    "tile_thumbnail": tile_image.get("thumbnailUrl"),
                    "header_image": (coll.get("headerImage") or {}).get("url"),
                    "author": user.get("name"),
                    "author_avatar": user.get("avatar"),
                    "mod_count": revision.get("modCount", 0),
                    "revision": revision.get("revisionNumber", 0),
                    "adult_content": coll.get("adultContent", False),
                    "category": (coll.get("category") or {}).get("name"),
                    "updated_at": coll.get("updatedAt"),
                    "created_at": coll.get("createdAt"),
                }
                collections_list.append(coll_dict)
            
            # Apply local sorting since GraphQL may not fully support it
            if sort_by == "downloads":
                collections_list.sort(key=lambda x: x.get("total_downloads", 0), reverse=True)
            elif sort_by == "endorsements":
                collections_list.sort(key=lambda x: x.get("endorsements", 0), reverse=True)
            elif sort_by == "updated":
                collections_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            
            return {
                "results": collections_list,
                "total": collections_data.get("totalCount", 0),
                "count": collections_data.get("nodesCount", 0)
            }
        except Exception as e:
            # Return empty results on error
            return {
                "results": [],
                "total": 0,
                "count": 0,
                "error": str(e)
            }
    
    async def batch_get_mod_requirements(
        self,
        mod_ids: List[int],
        game_domain: Optional[str] = None,
        max_concurrent: int = 10
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Batch fetch requirements for multiple mods with concurrency limit
        
        This is more efficient than calling get_mod_requirements individually
        for each mod, especially when checking compatibility for search results.
        """
        game_domain = game_domain or settings.game_domain
        results: Dict[int, List[Dict[str, Any]]] = {}
        
        # Use semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_requirements(mod_id: int):
            async with semaphore:
                try:
                    reqs = await self.get_mod_requirements(mod_id, game_domain)
                    return mod_id, reqs
                except Exception:
                    return mod_id, []
        
        # Fetch all requirements concurrently
        tasks = [fetch_requirements(mod_id) for mod_id in mod_ids]
        fetched_results = await asyncio.gather(*tasks)
        
        for mod_id, requirements in fetched_results:
            results[mod_id] = requirements
        
        return results

    async def get_related_mods(self, game_domain: str, mod_id: int) -> List[Dict[str, Any]]:
        """Get related mods using GraphQL API"""
        query = """
        query GetRelatedMods($gameDomain: String!, $modId: Int!) {
            mod(gameDomainName: $gameDomain, nexusModId: $modId) {
                relatedMods {
                    id
                    name
                    summary
                    pictureUrl
                    nexusModId
                }
            }
        }
        """
        variables = {
            "gameDomain": game_domain,
            "modId": mod_id
        }
        
        try:
            data = await self._post_graphql_with_cache(query, variables, cache_ttl=3600)
            return data.get("data", {}).get("mod", {}).get("relatedMods", [])
        except Exception:
            return []

    async def get_collection(self, collection_id: str, game_domain: str) -> Dict[str, Any]:
        """Get collection information using GraphQL"""
        query = """
        query GetCollection($collectionId: String!, $gameDomain: String!) {
            collection(id: $collectionId, gameDomainName: $gameDomain) {
                id
                slug
                name
                summary
                description
                endorsements
                totalDownloads
                author {
                    name
                    memberId
                }
                headerImage {
                    url
                }
                tileImage {
                    url
                }
                game {
                    domainName
                    name
                }
                latestPublishedRevision {
                    revisionNumber
                    modCount
                    mods {
                        mod {
                            id
                            name
                            author
                            summary
                            nexusModId
                            pictureUrl
                        }
                        fileId
                        isRequired
                    }
                }
                currentRevision {
                    revisionNumber
                    modCount
                    mods {
                        mod {
                            id
                            name
                            author
                            summary
                            nexusModId
                            pictureUrl
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
        
        try:
            data = await self._post_graphql_with_cache(query, variables, cache_ttl=3600)
            return data.get("data", {}).get("collection")
        except Exception as e:
            raise NexusAPIError(f"Failed to get collection: {str(e)}")

    async def parse_collection_url(self, url: str) -> tuple[str, str]:
        """Parse a Nexus Mods collection URL to extract game domain and collection slug
        
        Supports formats:
        - https://next.nexusmods.com/cyberpunk2077/collections/abc123
        - https://www.nexusmods.com/cyberpunk2077/mods/collections/abc123
        - https://nexusmods.com/cyberpunk2077/collections/abc123
        
        Returns:
            Tuple of (game_domain, collection_slug)
        """
        import re
        
        # Pattern for next.nexusmods.com format
        next_pattern = r"next\.nexusmods\.com/([^/]+)/collections/([^/?#]+)"
        # Pattern for www.nexusmods.com format
        www_pattern = r"(?:www\.)?nexusmods\.com/([^/]+)/(?:mods/)?collections/([^/?#]+)"
        
        match = re.search(next_pattern, url)
        if match:
            return match.group(1), match.group(2)
        
        match = re.search(www_pattern, url)
        if match:
            return match.group(1), match.group(2)
        
        raise NexusAPIError(f"Could not parse collection URL: {url}")

    async def get_mod_changelog(self, game_domain: str, mod_id: int) -> Dict[str, Any]:
        """Get mod changelog from Nexus"""
        return await self._get_with_cache(f"/games/{game_domain}/mods/{mod_id}/changelogs.json", cache_ttl=86400)

    async def get_mod_updates(self, game_domain: str, mod_id: int, period: str = "1m") -> List[Dict[str, Any]]:
        """Get mod updates"""
        return await self._get_with_cache(
            f"/games/{game_domain}/mods/{mod_id}/updates.json",
            params={"period": period},
            cache_ttl=3600
        )
    
    async def get_download_link(
        self, 
        game_domain: str, 
        mod_id: int, 
        file_id: int,
        key: Optional[str] = None,
        expires: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get download link for mod file (Never cached as links expire)"""
        params = {}
        if key:
            params["key"] = key
        if expires:
            params["expires"] = expires
        
        # Rate limit check still applies
        if self.rate_limits["daily_remaining"] == 0 or self.rate_limits["hourly_remaining"] == 0:
            raise NexusAPIError("Nexus API rate limit reached.")

        response = await self.client.get(
            f"/games/{game_domain}/mods/{mod_id}/files/{file_id}/download_link.json",
            params=params
        )
        self.rate_limits["daily_remaining"] = int(response.headers.get("x-rl-daily-remaining", 100))
        self.rate_limits["hourly_remaining"] = int(response.headers.get("x-rl-hourly-remaining", 100))
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
        """Search mods"""
        params = {
            "page": page,
            "page_size": page_size
        }
        if query:
            params["terms"] = query.split()
        
        return await self._get_with_cache(
            f"/games/{game_domain}/mods/search.json",
            params=params,
            cache_ttl=1800
        )

    async def get_latest_mods(self, game_domain: str) -> List[Dict[str, Any]]:
        """Get latest added mods"""
        return await self._get_with_cache(f"/games/{game_domain}/mods/latest.json", cache_ttl=1800)

    async def get_trending_mods(self, game_domain: str) -> List[Dict[str, Any]]:
        """Get trending mods"""
        return await self._get_with_cache(f"/games/{game_domain}/mods/trending.json", cache_ttl=1800)
    
    async def get_top_mods(self, game_domain: str, period: str = "ALL_TIME", count: int = 100) -> List[Dict[str, Any]]:
        """Get top mods by endorsements for a period
        
        Note: REST API v1 doesn't have a direct 'top' endpoint, so we use updated.json
        which returns mods sorted by endorsements. For better results, consider using
        GraphQL API v2 search with sorting.
        """
        # Use updated.json endpoint with period filter
        # This returns mods updated in the period, sorted by endorsements
        results = await self._get_with_cache(
            f"/games/{game_domain}/mods/updated.json",
            params={"period": period.lower()},
            cache_ttl=1800
        )
        mods = results if isinstance(results, list) else results.get("mods", [])
        # Limit to requested count
        return mods[:count] if mods else []

    async def get_mod_file_contents(self, game_domain: str, mod_id: int, file_id: int) -> Dict[str, Any]:
        """Get contents of a mod file archive without downloading"""
        return await self._get_with_cache(
            f"/games/{game_domain}/mods/{mod_id}/files/{file_id}/contents.json",
            cache_ttl=86400
        )
    async def download_file(
        self,
        download_url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Path:
        """Download a file from Nexus Mods
        
        Args:
            download_url: Download URL
            destination: Destination path
            progress_callback: Optional callback for progress updates
        """
        import aiofiles
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
