"""
Non-Interactive CLI for macOS Mod Manager

Provides command-line operations that can be run without user interaction,
suitable for scripting, automation, and CI/CD pipelines.
"""

import asyncio
import json
import sys
import warnings
from pathlib import Path
from typing import Optional, List, Dict, Any
import argparse
import logging

# Suppress module import warnings when run as __main__
warnings.filterwarnings("ignore", category=RuntimeWarning, module="runpy")

# Suppress httpx INFO logs
logging.getLogger("httpx").setLevel(logging.WARNING)

from app.tui.services.tui_service import TUIModService
from app.core.game_detector import get_primary_game_path, detect_game_installations
from app.core.mod_manager import ModInstallationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class NonInteractiveCLI:
    """
    Non-interactive CLI handler for mod management operations.
    
    All operations can be run without user input by providing
    appropriate flags (--yes, --force, etc.)
    """
    
    def __init__(
        self,
        game_path: Optional[Path] = None,
        quiet: bool = False,
        json_output: bool = False
    ):
        self.game_path = game_path
        self.quiet = quiet
        self.json_output = json_output
        self._service: Optional[TUIModService] = None
    
    async def _ensure_service(self) -> TUIModService:
        """Ensure the service is initialized."""
        if self._service is None:
            if self.game_path is None:
                self.game_path = await get_primary_game_path()
            self._service = TUIModService(self.game_path)
        return self._service
    
    def _output(self, data: any, message: str = "") -> None:
        """Output data in the appropriate format."""
        if self.quiet:
            return
        
        if self.json_output:
            if isinstance(data, str):
                print(json.dumps({"message": data}))
            else:
                print(json.dumps(data, default=str, indent=2))
        else:
            if message:
                print(message)
            elif isinstance(data, str):
                print(data)
            else:
                print(data)
    
    def _error(self, message: str, code: str = "ERROR") -> None:
        """Output error message."""
        if self.json_output:
            print(json.dumps({"error": message, "code": code}), file=sys.stderr)
        else:
            print(f"ERROR [{code}]: {message}", file=sys.stderr)
    
    # ==================== LIST OPERATIONS ====================
    
    async def list_mods(
        self,
        filter_type: Optional[str] = None,
        filter_enabled: Optional[bool] = None,
        format_output: str = "table"
    ) -> int:
        """
        List installed mods.
        
        Returns: Exit code (0 for success)
        """
        try:
            service = await self._ensure_service()
            mods = await service.get_installed_mods()
            
            # Apply filters
            if filter_type:
                mods = [m for m in mods if m.mod_type == filter_type]
            if filter_enabled is not None:
                mods = [m for m in mods if m.is_enabled == filter_enabled]
            
            if self.json_output:
                self._output([{
                    "id": m.id,
                    "name": m.name,
                    "version": m.version,
                    "type": m.mod_type,
                    "enabled": m.is_enabled,
                    "size": m.file_size
                } for m in mods])
            else:
                if not mods:
                    self._output("No mods installed.")
                else:
                    # Table format
                    self._output(f"{'ID':<6} {'Status':<8} {'Name':<40} {'Version':<12} {'Type':<12}")
                    self._output("-" * 80)
                    for m in mods:
                        status = "enabled" if m.is_enabled else "disabled"
                        name = m.name[:38] + ".." if len(m.name) > 40 else m.name
                        version = (m.version or "-")[:10]
                        mod_type = (m.mod_type or "unknown")[:10]
                        self._output(f"{m.id:<6} {status:<8} {name:<40} {version:<12} {mod_type:<12}")
            
            return 0
        except Exception as e:
            self._error(str(e))
            return 1
    
    async def list_game_installations(self) -> int:
        """List detected game installations."""
        try:
            installations = await detect_game_installations()
            
            if self.json_output:
                self._output(installations)
            else:
                if not installations:
                    self._output("No Cyberpunk 2077 installations found.")
                else:
                    for inst in installations:
                        self._output(f"  [{inst['launcher']}] {inst['path']}")
                        if inst.get('version'):
                            self._output(f"    Version: {inst['version']}")
            
            return 0
        except Exception as e:
            self._error(str(e))
            return 1
    
    # ==================== INSTALL OPERATIONS ====================
    
    async def install(
        self,
        source: str,
        yes: bool = False,
        skip_compatibility: bool = False,
        fomod_choices: Optional[str] = None,
        file_id: Optional[int] = None,
        list_files: bool = False
    ) -> int:
        """
        Install a mod from file path, URL, or Nexus ID.
        
        Args:
            source: Path to archive, URL, or "nexus:MOD_ID" for Nexus mods
            yes: Skip confirmation prompts
            skip_compatibility: Skip compatibility checks
            fomod_choices: JSON file with FOMOD choices for non-interactive FOMOD
            file_id: Specific Nexus file ID to download
            list_files: List available files instead of installing
        
        Returns: Exit code
        """
        try:
            service = await self._ensure_service()
            
            def progress_callback(stage: str, percent: int, message: str):
                if not self.quiet and not self.json_output:
                    print(f"\r[{percent:3d}%] {stage}: {message}", end="", flush=True)
            
            # Determine source type
            if source.startswith("nexus:"):
                # Nexus mod
                mod_id = int(source.split(":")[1])
                
                # List files mode
                if list_files:
                    return await self.list_nexus_files(mod_id)
                
                self._output(f"Installing from Nexus Mods (ID: {mod_id})...")
                if file_id:
                    self._output(f"Using file ID: {file_id}")
                
                try:
                    mod = await service.install_from_nexus(
                        mod_id,
                        file_id=file_id,
                        progress_callback=progress_callback,
                        check_compatibility=not skip_compatibility
                    )
                except Exception as e:
                    error_str = str(e)
                    if "403" in error_str:
                        self._error(
                            "Nexus Mods Premium membership required for direct download. "
                            "Download the mod manually from nexusmods.com and use: "
                            f"mod-manager install /path/to/downloaded-file.zip\n"
                            f"Or use: mod-manager install nexus:{mod_id} --list-files to see available versions",
                            "NEXUS_PREMIUM_REQUIRED"
                        )
                        return 1
                    raise
            
            elif source.startswith("http://") or source.startswith("https://"):
                # URL download
                return await self._install_from_url(
                    source,
                    yes=yes,
                    skip_compatibility=skip_compatibility,
                    fomod_choices=fomod_choices,
                    progress_callback=progress_callback
                )
            
            else:
                # Local file
                file_path = Path(source)
                if not file_path.exists():
                    self._error(f"File not found: {source}", "FILE_NOT_FOUND")
                    return 1
                
                # Check compatibility unless skipped
                if not skip_compatibility:
                    compat = await service.check_file_compatibility(file_path)
                    if not compat["compatible"]:
                        if not yes:
                            self._error(
                                f"Mod may not be compatible: {', '.join(compat['issues'])}",
                                "INCOMPATIBLE"
                            )
                            return 1
                        else:
                            logger.warning(f"Proceeding despite compatibility issues: {compat['issues']}")
                
                self._output(f"Installing from: {file_path}")
                
                # Handle FOMOD choices if provided
                if fomod_choices:
                    choices_path = Path(fomod_choices)
                    if choices_path.exists():
                        with open(choices_path) as f:
                            choices = json.load(f)
                        # TODO: Pass choices to installer for non-interactive FOMOD
                
                try:
                    mod = await service.install_local_mod(
                        file_path,
                        progress_callback=progress_callback
                    )
                except Exception as e:
                    if "FOMOD" in str(e) and not fomod_choices:
                        self._error(
                            "This mod requires FOMOD configuration. "
                            "Provide --fomod-choices JSON file for non-interactive install.",
                            "FOMOD_REQUIRED"
                        )
                        return 2
                    raise
            
            if not self.quiet and not self.json_output:
                print()  # Newline after progress
            
            if mod:
                self._output({
                    "success": True,
                    "mod_id": mod.id,
                    "name": mod.name,
                    "version": mod.version,
                    "type": mod.mod_type
                }, f"Successfully installed: {mod.name}")
            
            return 0
            
        except ModInstallationError as e:
            self._error(str(e), e.error_code if hasattr(e, 'error_code') else "INSTALL_ERROR")
            return 1
        except Exception as e:
            self._error(str(e))
            return 1
    
    async def _install_from_url(
        self,
        url: str,
        yes: bool = False,
        skip_compatibility: bool = False,
        fomod_choices: Optional[str] = None,
        progress_callback = None
    ) -> int:
        """Download and install a mod from a direct URL."""
        import httpx
        import tempfile
        from urllib.parse import urlparse, unquote
        
        service = await self._ensure_service()
        
        # Extract filename from URL
        parsed = urlparse(url)
        filename = unquote(parsed.path.split("/")[-1])
        if not filename or "." not in filename:
            filename = "downloaded_mod.zip"
        
        self._output(f"Downloading: {filename}")
        self._output(f"From: {url[:80]}{'...' if len(url) > 80 else ''}")
        
        # Download to temp file
        temp_dir = Path(tempfile.mkdtemp())
        temp_file = temp_dir / filename
        
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    
                    total = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    
                    with open(temp_file, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0 and progress_callback:
                                percent = int((downloaded / total) * 50)  # 0-50% for download
                                progress_callback("download", percent, f"Downloaded {downloaded // 1024}KB")
            
            if not self.quiet:
                print()  # Newline after download progress
            
            self._output(f"Downloaded: {temp_file.stat().st_size // 1024}KB")
            
            # Check compatibility unless skipped
            if not skip_compatibility:
                compat = await service.check_file_compatibility(temp_file)
                if not compat["compatible"]:
                    if not yes:
                        self._error(
                            f"Mod may not be compatible: {', '.join(compat['issues'])}",
                            "INCOMPATIBLE"
                        )
                        return 1
                    else:
                        logger.warning(f"Proceeding despite compatibility issues: {compat['issues']}")
            
            # Install from downloaded file
            self._output(f"Installing: {filename}")
            
            try:
                mod = await service.install_local_mod(
                    temp_file,
                    progress_callback=progress_callback
                )
            except Exception as e:
                if "FOMOD" in str(e) and not fomod_choices:
                    self._error(
                        "This mod requires FOMOD configuration. "
                        "Provide --fomod-choices JSON file for non-interactive install.",
                        "FOMOD_REQUIRED"
                    )
                    return 2
                raise
            
            if not self.quiet and not self.json_output:
                print()  # Newline after progress
            
            if mod:
                self._output({
                    "success": True,
                    "mod_id": mod.id,
                    "name": mod.name,
                    "version": mod.version,
                    "type": mod.mod_type,
                    "source_url": url
                }, f"Successfully installed: {mod.name}")
            
            return 0
            
        except httpx.HTTPStatusError as e:
            self._error(f"Download failed: HTTP {e.response.status_code}", "DOWNLOAD_FAILED")
            return 1
        except Exception as e:
            self._error(f"Download failed: {e}", "DOWNLOAD_FAILED")
            return 1
        finally:
            # Cleanup temp directory
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    async def list_nexus_files(self, mod_id: int) -> int:
        """List available files/versions for a Nexus mod."""
        try:
            service = await self._ensure_service()
            files = await service.get_nexus_mod_files(mod_id)
            
            if not files:
                self._error(f"No files found for mod {mod_id}", "NO_FILES")
                return 1
            
            if self.json_output:
                self._output(files)
            else:
                self._output(f"\nAvailable files for Nexus Mod {mod_id}:\n")
                self._output(f"{'ID':<10} {'Version':<15} {'Name':<40} {'Size':<10}")
                self._output("-" * 80)
                
                for f in files:
                    file_id = f.get("file_id", "?")
                    version = f.get("version", "-")[:13]
                    name = f.get("name", "Unknown")[:38]
                    size_kb = f.get("size_kb", 0)
                    size_str = f"{size_kb // 1024}MB" if size_kb > 1024 else f"{size_kb}KB"
                    category = f.get("category_name", "")
                    
                    self._output(f"{file_id:<10} {version:<15} {name:<40} {size_str:<10}")
                    if category:
                        self._output(f"           Category: {category}")
                
                self._output(f"\nTo install a specific version:")
                self._output(f"  mod-manager install nexus:{mod_id} --file-id FILE_ID")
            
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    async def nexus_info(self, mod_id: int) -> int:
        """Get information about a Nexus mod."""
        try:
            service = await self._ensure_service()
            info = await service.get_nexus_mod_info(mod_id)
            
            if not info:
                self._error(f"Mod not found: {mod_id}", "MOD_NOT_FOUND")
                return 1
            
            if self.json_output:
                self._output(info)
            else:
                self._output(f"\n{info.get('name', 'Unknown')}")
                self._output(f"{'=' * 60}")
                self._output(f"Mod ID: {mod_id}")
                self._output(f"Author: {info.get('author', 'Unknown')}")
                self._output(f"Version: {info.get('version', 'Unknown')}")
                self._output(f"Downloads: {info.get('mod_downloads', 0):,}")
                self._output(f"Endorsements: {info.get('endorsement_count', 0):,}")
                self._output(f"URL: https://www.nexusmods.com/cyberpunk2077/mods/{mod_id}")
                
                summary = info.get('summary', '')
                if summary:
                    self._output(f"\n{summary[:500]}{'...' if len(summary) > 500 else ''}")
                
                self._output(f"\nTo list available files:")
                self._output(f"  mod-manager install nexus:{mod_id} --list-files")
            
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    # ==================== UNINSTALL OPERATIONS ====================
    
    async def uninstall(
        self,
        mod_identifier: str,
        yes: bool = False
    ) -> int:
        """
        Uninstall a mod by ID or name.
        
        Args:
            mod_identifier: Mod ID (number) or name (string)
            yes: Skip confirmation prompt
        
        Returns: Exit code
        """
        try:
            service = await self._ensure_service()
            
            # Find mod
            mods = await service.get_installed_mods()
            
            # Try as ID first
            try:
                mod_id = int(mod_identifier)
                mod = next((m for m in mods if m.id == mod_id), None)
            except ValueError:
                # Search by name
                mod = next(
                    (m for m in mods if mod_identifier.lower() in m.name.lower()),
                    None
                )
            
            if not mod:
                self._error(f"Mod not found: {mod_identifier}", "MOD_NOT_FOUND")
                return 1
            
            if not yes and not self.quiet:
                self._output(f"Will uninstall: {mod.name} (ID: {mod.id})")
                # In non-interactive mode with --yes, we proceed
            
            await service.uninstall_mod(mod.id)
            
            self._output({
                "success": True,
                "mod_id": mod.id,
                "name": mod.name
            }, f"Successfully uninstalled: {mod.name}")
            
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    # ==================== ENABLE/DISABLE OPERATIONS ====================
    
    async def enable(self, mod_identifier: str) -> int:
        """Enable a mod by ID or name."""
        return await self._toggle_mod(mod_identifier, enable=True)
    
    async def disable(self, mod_identifier: str) -> int:
        """Disable a mod by ID or name."""
        return await self._toggle_mod(mod_identifier, enable=False)
    
    async def _toggle_mod(self, mod_identifier: str, enable: bool) -> int:
        """Toggle mod enabled state."""
        try:
            service = await self._ensure_service()
            mods = await service.get_installed_mods()
            
            # Find mod
            try:
                mod_id = int(mod_identifier)
                mod = next((m for m in mods if m.id == mod_id), None)
            except ValueError:
                mod = next(
                    (m for m in mods if mod_identifier.lower() in m.name.lower()),
                    None
                )
            
            if not mod:
                self._error(f"Mod not found: {mod_identifier}", "MOD_NOT_FOUND")
                return 1
            
            # Check current state
            if mod.is_enabled == enable:
                action = "enabled" if enable else "disabled"
                self._output(f"Mod is already {action}: {mod.name}")
                return 0
            
            await service.toggle_mod(mod.id)
            
            action = "Enabled" if enable else "Disabled"
            self._output({
                "success": True,
                "mod_id": mod.id,
                "name": mod.name,
                "enabled": enable
            }, f"{action}: {mod.name}")
            
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    # ==================== BATCH OPERATIONS ====================
    
    async def batch_install(
        self,
        sources: List[str],
        yes: bool = False,
        continue_on_error: bool = False
    ) -> int:
        """
        Install multiple mods.
        
        Args:
            sources: List of file paths or nexus:ID strings
            yes: Skip confirmations
            continue_on_error: Continue installing if one fails
        
        Returns: Exit code (0 if all succeeded)
        """
        results = []
        failed = 0
        
        for source in sources:
            self._output(f"\n--- Installing: {source} ---")
            result = await self.install(source, yes=yes)
            results.append({"source": source, "success": result == 0})
            
            if result != 0:
                failed += 1
                if not continue_on_error:
                    break
        
        if self.json_output:
            self._output({
                "total": len(sources),
                "succeeded": len(sources) - failed,
                "failed": failed,
                "results": results
            })
        else:
            self._output(f"\nBatch install complete: {len(sources) - failed}/{len(sources)} succeeded")
        
        return 0 if failed == 0 else 1
    
    async def batch_enable(self, mod_identifiers: List[str]) -> int:
        """Enable multiple mods."""
        failed = 0
        for mod_id in mod_identifiers:
            if await self.enable(mod_id) != 0:
                failed += 1
        return 0 if failed == 0 else 1
    
    async def batch_disable(self, mod_identifiers: List[str]) -> int:
        """Disable multiple mods."""
        failed = 0
        for mod_id in mod_identifiers:
            if await self.disable(mod_id) != 0:
                failed += 1
        return 0 if failed == 0 else 1
    
    # ==================== BULK CHECK OPERATIONS ====================
    
    def _parse_mod_url(self, url: str) -> Dict[str, Any]:
        """Parse a mod URL to extract source and ID."""
        import re
        
        url = url.strip()
        
        # Nexus Mods URL pattern
        nexus_pattern = r'nexusmods\.com/(?:games/)?cyberpunk2077/mods/(\d+)'
        nexus_match = re.search(nexus_pattern, url)
        if nexus_match:
            return {
                "source": "nexus",
                "mod_id": int(nexus_match.group(1)),
                "url": url
            }
        
        # GitHub URL pattern
        github_pattern = r'github\.com/([^/]+)/([^/\?]+)'
        github_match = re.search(github_pattern, url)
        if github_match:
            return {
                "source": "github",
                "owner": github_match.group(1),
                "repo": github_match.group(2).rstrip('.git'),
                "url": url
            }
        
        return {"source": "unknown", "url": url}
    
    async def bulk_check(
        self,
        urls: List[str],
        output_file: Optional[str] = None,
        check_files: bool = True
    ) -> int:
        """
        Bulk check mod compatibility from URLs.
        
        Args:
            urls: List of mod URLs (Nexus, GitHub, etc.)
            output_file: Optional file to save results
            check_files: Whether to check individual files for DLLs
        
        Returns: Exit code
        """
        import re
        
        service = await self._ensure_service()
        
        results = []
        nexus_mods = []
        github_repos = []
        unknown_urls = []
        
        # Parse all URLs
        for url in urls:
            parsed = self._parse_mod_url(url)
            if parsed["source"] == "nexus":
                nexus_mods.append(parsed)
            elif parsed["source"] == "github":
                github_repos.append(parsed)
            else:
                unknown_urls.append(parsed)
        
        if not self.quiet:
            self._output(f"\nBulk Compatibility Check")
            self._output(f"=" * 60)
            self._output(f"Nexus Mods: {len(nexus_mods)}")
            self._output(f"GitHub Repos: {len(github_repos)}")
            self._output(f"Unknown: {len(unknown_urls)}")
            self._output("")
        
        # Check Nexus mods
        for i, mod in enumerate(nexus_mods):
            mod_id = mod["mod_id"]
            
            if not self.quiet:
                print(f"\r[{i+1}/{len(nexus_mods)}] Checking Nexus mod {mod_id}...", end="", flush=True)
            
            try:
                # Get mod info
                info = await service.get_nexus_mod_info(mod_id)
                if not info:
                    results.append({
                        "url": mod["url"],
                        "source": "nexus",
                        "mod_id": mod_id,
                        "status": "error",
                        "error": "Could not fetch mod info"
                    })
                    continue
                
                result = {
                    "url": mod["url"],
                    "source": "nexus",
                    "mod_id": mod_id,
                    "name": info.get("name", "Unknown"),
                    "author": info.get("author", "Unknown"),
                    "version": info.get("version", "?"),
                    "downloads": info.get("mod_downloads", 0),
                    "status": "pending",
                    "compatible": None,
                    "has_dll": False,
                    "has_archive": False,
                    "has_scripts": False,
                    "file_types": [],
                    "issues": [],
                    "notes": []
                }
                
                # Check mod description for hints
                summary = info.get("summary", "").lower()
                description = info.get("description", "").lower()
                mod_text = summary + " " + description
                
                # Check for compatibility hints in description
                if "dll" in mod_text and ("red4ext" in mod_text or "asi" in mod_text):
                    result["has_dll"] = True
                    result["issues"].append("Mentions DLL/RED4ext (likely Windows-only)")
                
                if "redscript" in mod_text or ".reds" in mod_text:
                    result["has_scripts"] = True
                    result["notes"].append("Uses Redscript")
                
                if "archivexl" in mod_text or "archive-xl" in mod_text:
                    result["has_archive"] = True
                    result["notes"].append("Uses ArchiveXL")
                
                if "tweakxl" in mod_text or "tweak-xl" in mod_text:
                    result["notes"].append("Uses TweakXL")
                    result["has_scripts"] = True  # TweakXL mods are compatible
                
                if "cyber engine tweaks" in mod_text or "cet" in mod_text.split():
                    result["has_dll"] = True
                    result["issues"].append("Requires Cyber Engine Tweaks (DLL-based)")
                
                if "redmod" in mod_text:
                    result["notes"].append("Uses REDmod format")
                    result["has_archive"] = True
                
                # Check files if requested
                if check_files:
                    try:
                        files = await service.get_nexus_mod_files(mod_id)
                        
                        for f in files:
                            fname = f.get("file_name", "").lower()
                            name = f.get("name", "").lower()
                            
                            # Check file extensions
                            if fname.endswith(".dll"):
                                result["has_dll"] = True
                                if "Contains DLL (Windows-only)" not in result["issues"]:
                                    result["issues"].append("Contains DLL (Windows-only)")
                            if fname.endswith(".archive"):
                                result["has_archive"] = True
                            if fname.endswith(".reds"):
                                result["has_scripts"] = True
                            
                            # Infer from file names
                            if "macos" in fname or "mac" in fname or "macos" in name:
                                result["notes"].append(f"Has macOS version: {f.get('name', fname)}")
                            if "linux" in fname or "linux" in name:
                                result["notes"].append(f"Has Linux version: {f.get('name', fname)}")
                        
                        # Determine file types from main files
                        main_files = [f for f in files if f.get("category_name") == "MAIN"]
                        for f in main_files:
                            fname = f.get("file_name", "").lower()
                            if ".zip" in fname or ".7z" in fname or ".rar" in fname:
                                result["file_types"].append(f.get("name", fname)[:40])
                        
                    except Exception as e:
                        result["notes"].append(f"Could not check files: {e}")
                
                # Determine compatibility
                if result["has_dll"] and not any("macOS" in n for n in result["notes"]):
                    result["compatible"] = False
                    result["status"] = "incompatible"
                elif any("macOS" in n for n in result["notes"]):
                    result["compatible"] = True
                    result["status"] = "likely_compatible"
                    result["notes"].insert(0, "⭐ Has macOS-specific files!")
                elif result["has_archive"] or result["has_scripts"]:
                    result["compatible"] = True
                    result["status"] = "likely_compatible"
                elif "archive" in mod_text or "reshade" in mod_text or "texture" in mod_text:
                    # Archive/texture mods are usually compatible
                    result["compatible"] = True
                    result["status"] = "likely_compatible"
                    result["notes"].append("Archive/texture mod (usually compatible)")
                else:
                    result["compatible"] = None
                    result["status"] = "unknown"
                    if not result["notes"]:
                        result["notes"].append("Check mod page for compatibility info")
                
                results.append(result)
                
            except Exception as e:
                results.append({
                    "url": mod["url"],
                    "source": "nexus",
                    "mod_id": mod_id,
                    "status": "error",
                    "error": str(e)
                })
        
        if not self.quiet and nexus_mods:
            print()  # Newline after progress
        
        # Add GitHub repos (need manual checking)
        for repo in github_repos:
            results.append({
                "url": repo["url"],
                "source": "github",
                "owner": repo["owner"],
                "repo": repo["repo"],
                "status": "manual_check",
                "compatible": None,
                "notes": ["GitHub repos need manual compatibility check", 
                         "Check for macOS releases or .dylib files"]
            })
        
        # Add unknown URLs
        for unknown in unknown_urls:
            results.append({
                "url": unknown["url"],
                "source": "unknown",
                "status": "skipped",
                "notes": ["Unrecognized URL format"]
            })
        
        # Calculate summary
        compatible_count = sum(1 for r in results if r.get("compatible") is True)
        incompatible_count = sum(1 for r in results if r.get("compatible") is False)
        unknown_count = sum(1 for r in results if r.get("compatible") is None)
        
        # Output results
        if self.json_output:
            self._output({
                "summary": {
                    "total": len(results),
                    "compatible": compatible_count,
                    "incompatible": incompatible_count,
                    "unknown": unknown_count
                },
                "results": results
            })
        else:
            # Print detailed results
            self._output(f"\n{'='*80}")
            self._output(f"COMPATIBILITY REPORT")
            self._output(f"{'='*80}\n")
            
            # Group by status
            by_status = {"likely_compatible": [], "incompatible": [], "unknown": [], "manual_check": [], "error": [], "skipped": []}
            for r in results:
                status = r.get("status", "unknown")
                if status in by_status:
                    by_status[status].append(r)
                else:
                    by_status["unknown"].append(r)
            
            # Print compatible mods
            if by_status["likely_compatible"]:
                self._output(f"✅ LIKELY COMPATIBLE ({len(by_status['likely_compatible'])})")
                self._output("-" * 60)
                for r in by_status["likely_compatible"]:
                    self._output(f"  [{r['mod_id']}] {r.get('name', 'Unknown')[:45]}")
                    if r.get("notes"):
                        for note in r["notes"]:
                            self._output(f"       💡 {note}")
                self._output("")
            
            # Print incompatible mods
            if by_status["incompatible"]:
                self._output(f"❌ INCOMPATIBLE ({len(by_status['incompatible'])})")
                self._output("-" * 60)
                for r in by_status["incompatible"]:
                    self._output(f"  [{r['mod_id']}] {r.get('name', 'Unknown')[:45]}")
                    for issue in r.get("issues", []):
                        self._output(f"       ⚠️  {issue}")
                    if r.get("notes"):
                        for note in r["notes"]:
                            self._output(f"       💡 {note}")
                self._output("")
            
            # Print unknown mods
            if by_status["unknown"]:
                self._output(f"❓ NEEDS MANUAL CHECK ({len(by_status['unknown'])})")
                self._output("-" * 60)
                for r in by_status["unknown"]:
                    self._output(f"  [{r.get('mod_id', '?')}] {r.get('name', r.get('url', 'Unknown'))[:45]}")
                    if r.get("notes"):
                        for note in r["notes"]:
                            self._output(f"       💡 {note}")
                self._output("")
            
            # Print GitHub repos
            if by_status["manual_check"]:
                self._output(f"🐙 GITHUB REPOS ({len(by_status['manual_check'])})")
                self._output("-" * 60)
                for r in by_status["manual_check"]:
                    self._output(f"  {r.get('owner', '?')}/{r.get('repo', '?')}")
                    self._output(f"       Check: {r['url']}")
                self._output("")
            
            # Print errors
            if by_status["error"]:
                self._output(f"⚠️  ERRORS ({len(by_status['error'])})")
                self._output("-" * 60)
                for r in by_status["error"]:
                    self._output(f"  {r.get('url', '?')}: {r.get('error', 'Unknown error')}")
                self._output("")
            
            # Summary
            self._output(f"{'='*80}")
            self._output(f"SUMMARY: {compatible_count} compatible, {incompatible_count} incompatible, {unknown_count} unknown")
            self._output(f"{'='*80}")
        
        # Save to file if requested
        if output_file:
            import json as json_module
            with open(output_file, 'w') as f:
                json_module.dump({
                    "summary": {
                        "total": len(results),
                        "compatible": compatible_count,
                        "incompatible": incompatible_count,
                        "unknown": unknown_count
                    },
                    "results": results
                }, f, indent=2)
            if not self.quiet:
                self._output(f"\nResults saved to: {output_file}")
        
        return 0
    
    # ==================== BACKUP OPERATIONS ====================
    
    async def create_backup(self, name: Optional[str] = None) -> int:
        """Create a backup of current game state."""
        try:
            service = await self._ensure_service()
            
            def progress_callback(stage: str, percent: int, message: str):
                if not self.quiet and not self.json_output:
                    print(f"\r[{percent:3d}%] {message}", end="", flush=True)
            
            backup_id = await service.create_backup(
                backup_name=name,
                progress_callback=progress_callback
            )
            
            if not self.quiet and not self.json_output:
                print()
            
            self._output({
                "success": True,
                "backup_id": backup_id
            }, f"Backup created: {backup_id}")
            
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    async def list_backups(self) -> int:
        """List available backups."""
        try:
            service = await self._ensure_service()
            backups = await service.list_backups()
            
            if self.json_output:
                self._output(backups)
            else:
                if not backups:
                    self._output("No backups found.")
                else:
                    for b in backups:
                        self._output(f"  [{b['id']}] {b.get('name', 'Unnamed')} - {b.get('created_at', 'Unknown')}")
            
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    async def restore_backup(self, backup_id: str, yes: bool = False) -> int:
        """Restore from a backup."""
        try:
            service = await self._ensure_service()
            
            if not yes and not self.quiet:
                self._output(f"Will restore backup: {backup_id}")
            
            def progress_callback(stage: str, percent: int, message: str):
                if not self.quiet and not self.json_output:
                    print(f"\r[{percent:3d}%] {message}", end="", flush=True)
            
            success = await service.restore_backup(
                backup_id,
                progress_callback=progress_callback
            )
            
            if not self.quiet and not self.json_output:
                print()
            
            if success:
                self._output({"success": True}, f"Restored backup: {backup_id}")
                return 0
            else:
                self._error("Backup restoration failed", "RESTORE_FAILED")
                return 1
                
        except Exception as e:
            self._error(str(e))
            return 1
    
    # ==================== INFO OPERATIONS ====================
    
    async def mod_info(self, mod_identifier: str) -> int:
        """Get detailed information about a mod."""
        try:
            service = await self._ensure_service()
            mods = await service.get_installed_mods()
            
            # Find mod
            try:
                mod_id = int(mod_identifier)
                mod = next((m for m in mods if m.id == mod_id), None)
            except ValueError:
                mod = next(
                    (m for m in mods if mod_identifier.lower() in m.name.lower()),
                    None
                )
            
            if not mod:
                self._error(f"Mod not found: {mod_identifier}", "MOD_NOT_FOUND")
                return 1
            
            details = await service.get_mod_details(mod.id)
            
            if self.json_output:
                self._output({
                    "id": details.id,
                    "name": details.name,
                    "version": details.version,
                    "type": details.mod_type,
                    "enabled": details.is_enabled,
                    "author": details.author,
                    "description": details.description,
                    "file_size": details.file_size,
                    "created_at": str(details.created_at) if details.created_at else None,
                    "files": getattr(details, 'files', []),
                    "dependencies": getattr(details, 'dependencies', [])
                })
            else:
                self._output(f"Name: {details.name}")
                self._output(f"ID: {details.id}")
                self._output(f"Version: {details.version or 'Unknown'}")
                self._output(f"Type: {details.mod_type or 'Unknown'}")
                self._output(f"Status: {'Enabled' if details.is_enabled else 'Disabled'}")
                if details.author:
                    self._output(f"Author: {details.author}")
                if details.description:
                    self._output(f"Description: {details.description[:200]}...")
            
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    # ==================== SETTINGS OPERATIONS ====================
    
    async def get_setting(self, key: str) -> int:
        """Get a setting value."""
        try:
            service = await self._ensure_service()
            settings = await service.get_settings()
            
            if key in settings:
                self._output({key: settings[key]})
            else:
                self._error(f"Setting not found: {key}", "SETTING_NOT_FOUND")
                return 1
            
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    async def set_setting(self, key: str, value: str) -> int:
        """Set a setting value."""
        try:
            service = await self._ensure_service()
            await service.save_settings({key: value})
            
            self._output({"success": True, key: value}, f"Set {key} = {value}")
            return 0
            
        except Exception as e:
            self._error(str(e))
            return 1
    
    async def set_game_path(self, path: str) -> int:
        """Set the game installation path."""
        game_path = Path(path)
        
        if not game_path.exists():
            self._error(f"Path does not exist: {path}", "PATH_NOT_FOUND")
            return 1
        
        app_bundle = game_path / "Cyberpunk2077.app"
        if not app_bundle.exists():
            self._error(
                f"Cyberpunk2077.app not found in {path}",
                "GAME_NOT_FOUND"
            )
            return 1
        
        return await self.set_setting("custom_game_path", str(game_path))
    
    async def set_nexus_api_key(self, api_key: str) -> int:
        """Set the Nexus Mods API key."""
        # Validate key first
        service = await self._ensure_service()
        
        if await service.test_nexus_api_key(api_key):
            return await self.set_setting("nexus_api_key", api_key)
        else:
            self._error("Invalid Nexus API key", "INVALID_API_KEY")
            return 1


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="mod-manager",
        description="Cyberpunk 2077 Mod Manager for macOS - Non-Interactive CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all installed mods
  mod-manager list
  
  # Install a mod from local file
  mod-manager install ./my-mod.zip --yes
  
  # Install directly from URL (one-click!)
  mod-manager install https://github.com/.../releases/download/v1.0/mod.zip --yes
  
  # Browse Nexus mod versions
  mod-manager nexus-info 3858
  mod-manager install nexus:3858 --list-files
  
  # Install specific Nexus version
  mod-manager install nexus:3858 --file-id 12345 --yes
  
  # Batch install multiple mods
  mod-manager batch-install mod1.zip mod2.zip --yes --continue-on-error
  
  # Enable/disable mods
  mod-manager enable 1
  mod-manager disable "Mod Name"
  
  # Get mod information as JSON
  mod-manager info 1 --json
  
  # Configuration
  mod-manager config set-game-path /path/to/game
  mod-manager config set-nexus-key YOUR_API_KEY
"""
    )
    
    # Global options
    parser.add_argument(
        "--game-path",
        type=Path,
        help="Path to Cyberpunk 2077 installation"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-error output"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # === LIST ===
    list_parser = subparsers.add_parser("list", help="List installed mods")
    list_parser.add_argument("--type", help="Filter by mod type")
    list_parser.add_argument("--enabled", action="store_true", help="Show only enabled mods")
    list_parser.add_argument("--disabled", action="store_true", help="Show only disabled mods")
    
    # === INSTALL ===
    install_parser = subparsers.add_parser(
        "install",
        help="Install a mod from file, URL, or Nexus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Sources:
  /path/to/mod.zip          Local file
  https://example.com/x.zip Download from URL
  nexus:12345               Install from Nexus Mods (requires Premium)

Examples:
  mod-manager install ./my-mod.zip --yes
  mod-manager install https://github.com/.../releases/download/v1.0/mod.zip --yes
  mod-manager install nexus:3858 --list-files
  mod-manager install nexus:3858 --file-id 12345 --yes
"""
    )
    install_parser.add_argument("source", help="Path, URL, or nexus:MOD_ID")
    install_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmations")
    install_parser.add_argument(
        "--skip-compatibility",
        action="store_true",
        help="Skip compatibility checks"
    )
    install_parser.add_argument(
        "--fomod-choices",
        help="JSON file with FOMOD choices for non-interactive install"
    )
    install_parser.add_argument(
        "--file-id",
        type=int,
        help="Specific Nexus file ID to download (for version selection)"
    )
    install_parser.add_argument(
        "--list-files",
        action="store_true",
        help="List available files/versions instead of installing (for nexus: sources)"
    )
    
    # === BATCH INSTALL ===
    batch_parser = subparsers.add_parser("batch-install", help="Install multiple mods")
    batch_parser.add_argument("sources", nargs="+", help="Mod sources to install")
    batch_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmations")
    batch_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue if one installation fails"
    )
    
    # === BULK CHECK ===
    bulk_check_parser = subparsers.add_parser(
        "bulk-check",
        help="Check compatibility of multiple mod URLs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check URLs from command line
  mod-manager bulk-check https://nexusmods.com/cyberpunk2077/mods/3858 https://nexusmods.com/cyberpunk2077/mods/1234
  
  # Check URLs from a file (one URL per line)
  mod-manager bulk-check --file urls.txt
  
  # Output to JSON file
  mod-manager bulk-check --file urls.txt --output report.json --json
"""
    )
    bulk_check_parser.add_argument(
        "urls",
        nargs="*",
        help="Mod URLs to check (Nexus, GitHub)"
    )
    bulk_check_parser.add_argument(
        "--file", "-f",
        help="File containing URLs (one per line)"
    )
    bulk_check_parser.add_argument(
        "--output", "-o",
        help="Save results to JSON file"
    )
    bulk_check_parser.add_argument(
        "--no-files",
        action="store_true",
        help="Skip checking individual mod files (faster)"
    )
    
    # === UNINSTALL ===
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall a mod")
    uninstall_parser.add_argument("mod", help="Mod ID or name")
    uninstall_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    
    # === ENABLE ===
    enable_parser = subparsers.add_parser("enable", help="Enable a mod")
    enable_parser.add_argument("mod", help="Mod ID or name")
    
    # === DISABLE ===
    disable_parser = subparsers.add_parser("disable", help="Disable a mod")
    disable_parser.add_argument("mod", help="Mod ID or name")
    
    # === INFO ===
    info_parser = subparsers.add_parser("info", help="Get mod information")
    info_parser.add_argument("mod", help="Mod ID or name")
    
    # === DETECT ===
    subparsers.add_parser("detect", help="Detect game installations")
    
    # === NEXUS INFO ===
    nexus_info_parser = subparsers.add_parser("nexus-info", help="Get Nexus mod information")
    nexus_info_parser.add_argument("mod_id", type=int, help="Nexus mod ID")
    
    # === CONFIG ===
    config_parser = subparsers.add_parser("config", help="Configuration commands")
    config_sub = config_parser.add_subparsers(dest="config_command")
    
    config_get = config_sub.add_parser("get", help="Get a setting")
    config_get.add_argument("key", help="Setting key")
    
    config_set = config_sub.add_parser("set", help="Set a setting")
    config_set.add_argument("key", help="Setting key")
    config_set.add_argument("value", help="Setting value")
    
    config_sub.add_parser("set-game-path", help="Set game path").add_argument("path")
    config_sub.add_parser("set-nexus-key", help="Set Nexus API key").add_argument("key")
    
    # === BACKUP ===
    backup_parser = subparsers.add_parser("backup", help="Backup commands")
    backup_sub = backup_parser.add_subparsers(dest="backup_command")
    
    backup_create = backup_sub.add_parser("create", help="Create a backup")
    backup_create.add_argument("--name", help="Backup name")
    
    backup_sub.add_parser("list", help="List backups")
    
    backup_restore = backup_sub.add_parser("restore", help="Restore a backup")
    backup_restore.add_argument("backup_id", help="Backup ID to restore")
    backup_restore.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    
    # === TUI ===
    tui_parser = subparsers.add_parser("tui", help="Launch interactive TUI")
    tui_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    return parser


async def run_cli(args: argparse.Namespace) -> int:
    """Execute CLI command."""
    cli = NonInteractiveCLI(
        game_path=args.game_path,
        quiet=args.quiet,
        json_output=args.json
    )
    
    if args.command == "list":
        filter_enabled = None
        if args.enabled:
            filter_enabled = True
        elif args.disabled:
            filter_enabled = False
        return await cli.list_mods(
            filter_type=args.type,
            filter_enabled=filter_enabled
        )
    
    elif args.command == "install":
        return await cli.install(
            args.source,
            yes=args.yes,
            skip_compatibility=args.skip_compatibility,
            fomod_choices=args.fomod_choices,
            file_id=args.file_id,
            list_files=args.list_files
        )
    
    elif args.command == "batch-install":
        return await cli.batch_install(
            args.sources,
            yes=args.yes,
            continue_on_error=args.continue_on_error
        )
    
    elif args.command == "bulk-check":
        # Collect URLs from args and/or file
        urls = list(args.urls) if args.urls else []
        
        if args.file:
            try:
                with open(args.file, 'r') as f:
                    file_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    urls.extend(file_urls)
            except FileNotFoundError:
                print(f"ERROR: File not found: {args.file}", file=sys.stderr)
                return 1
        
        if not urls:
            print("ERROR: No URLs provided. Use positional args or --file", file=sys.stderr)
            return 1
        
        return await cli.bulk_check(
            urls,
            output_file=args.output,
            check_files=not args.no_files
        )
    
    elif args.command == "uninstall":
        return await cli.uninstall(args.mod, yes=args.yes)
    
    elif args.command == "enable":
        return await cli.enable(args.mod)
    
    elif args.command == "disable":
        return await cli.disable(args.mod)
    
    elif args.command == "info":
        return await cli.mod_info(args.mod)
    
    elif args.command == "detect":
        return await cli.list_game_installations()
    
    elif args.command == "nexus-info":
        return await cli.nexus_info(args.mod_id)
    
    elif args.command == "config":
        if args.config_command == "get":
            return await cli.get_setting(args.key)
        elif args.config_command == "set":
            return await cli.set_setting(args.key, args.value)
        elif args.config_command == "set-game-path":
            return await cli.set_game_path(args.path)
        elif args.config_command == "set-nexus-key":
            return await cli.set_nexus_api_key(args.key)
        else:
            print("Usage: mod-manager config {get|set|set-game-path|set-nexus-key}")
            return 1
    
    elif args.command == "backup":
        if args.backup_command == "create":
            return await cli.create_backup(name=args.name)
        elif args.backup_command == "list":
            return await cli.list_backups()
        elif args.backup_command == "restore":
            return await cli.restore_backup(args.backup_id, yes=args.yes)
        else:
            print("Usage: mod-manager backup {create|list|restore}")
            return 1
    
    elif args.command == "tui":
        # Launch interactive TUI
        from app.tui.app import ModManagerApp
        app = ModManagerApp(game_path=args.game_path)
        app.run()
        return 0
    
    else:
        # No command - show help
        create_parser().print_help()
        return 0


def main():
    """Main entry point for CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    exit_code = asyncio.run(run_cli(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
