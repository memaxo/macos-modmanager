#!/usr/bin/env python3
"""
Cyberpunk 2077 macOS Mod Installer
Installs compatible mods with backup and rollback support.

Usage:
    python install_mods.py                    # Interactive mode
    python install_mods.py --yes              # Auto-confirm all
    python install_mods.py --dry-run          # Show what would be installed
    python install_mods.py --rollback         # Restore from last backup
    python install_mods.py --category texture # Install only texture mods
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.tui.services.tui_service import TUIModService
from app.core.game_detector import get_primary_game_path


@dataclass
class ModDefinition:
    """Definition of a mod to install."""
    mod_id: int
    name: str
    category: str  # texture, redscript, archivexl, tweakxl
    priority: int  # Lower = install first
    dependencies: List[int] = field(default_factory=list)
    url: str = ""
    
    def __post_init__(self):
        self.url = f"https://www.nexusmods.com/cyberpunk2077/mods/{self.mod_id}"


# Compatible mods grouped by category
COMPATIBLE_MODS = [
    # HD/Texture Mods (safe, no dependencies) - Priority 1
    ModDefinition(7652, "Cyberpunk 2077 HD Reworked Project", "texture", 1),
    ModDefinition(8157, "Preem Skin", "texture", 1),
    ModDefinition(8275, "Preem Water 2.0", "texture", 1),
    ModDefinition(17811, "Realistic Map", "texture", 1),
    ModDefinition(7160, "Better Building Windows", "texture", 1),
    ModDefinition(8105, "Blur Begone", "texture", 1),
    ModDefinition(3901, "Enhanced Weather V6", "texture", 1),
    ModDefinition(3040, "2077 More Gore V3.0", "texture", 1),
    ModDefinition(3196, "Weather Probability Rebalance", "texture", 1),
    ModDefinition(10150, "Judy Enhanced Body with 4K Texture", "texture", 1),
    ModDefinition(9887, "NPCs Enhancement - Hyst Bodies", "texture", 1),
    ModDefinition(1528, "Misty Appearance Overhaul", "texture", 1),
    ModDefinition(9274, "GITS 3.X", "texture", 1),
    
    # Redscript Mods - Priority 2
    ModDefinition(3858, "Ragdoll Physics Overhaul", "redscript", 2),
    ModDefinition(1654, "Kiroshi Opticals - Crowd Scanner", "redscript", 2),
    ModDefinition(1512, "Annoy Me No More", "redscript", 2),
    ModDefinition(2687, "Smarter Scrapper", "redscript", 2),
    ModDefinition(5115, "Immersive Timeskip", "redscript", 2),
    ModDefinition(3963, "No Special Outfit Lock", "redscript", 2),
    ModDefinition(9496, "Enable Finisher Ragdolls", "redscript", 2),
    ModDefinition(5534, "Talk to Me", "redscript", 2),
    ModDefinition(5097, "All Cyberware-EX (System-EX Patch)", "redscript", 2),
    ModDefinition(10395, "NIGHT CITY ALIVE (REDmod)", "redscript", 2),
    
    # ArchiveXL Mods - Priority 3
    ModDefinition(12681, "H10 Megabuilding Unlocked", "archivexl", 3),
    ModDefinition(5437, "V's Edgerunners Mansion", "archivexl", 3),
    ModDefinition(2592, "Limited HUD", "archivexl", 3),
    
    # TweakXL Mods - Priority 3
    ModDefinition(15043, "New Game Plus - Native", "tweakxl", 3),
    ModDefinition(18318, "Deceptious Bug Fixes", "tweakxl", 3),
]


@dataclass
class InstallResult:
    """Result of a mod installation attempt."""
    mod: ModDefinition
    success: bool
    error: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None


class ModInstaller:
    """Handles batch mod installation with backup and rollback."""
    
    def __init__(self, game_path: Path, auto_confirm: bool = False, dry_run: bool = False):
        self.game_path = game_path
        self.auto_confirm = auto_confirm
        self.dry_run = dry_run
        self.service: Optional[TUIModService] = None
        self.backup_id: Optional[str] = None
        self.installed_mod_ids: List[int] = []
        self.results: List[InstallResult] = []
        self.log_file = Path(f"/tmp/mod_install_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        self.state_file = Path("/tmp/mod_installer_state.json")
    
    def log(self, message: str, level: str = "INFO"):
        """Log message to console and file."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {level}: {message}"
        print(line)
        with open(self.log_file, "a") as f:
            f.write(line + "\n")
    
    def save_state(self):
        """Save installer state for rollback."""
        state = {
            "backup_id": self.backup_id,
            "installed_mod_ids": self.installed_mod_ids,
            "timestamp": datetime.now().isoformat()
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)
    
    def load_state(self) -> Optional[dict]:
        """Load installer state from file."""
        if self.state_file.exists():
            with open(self.state_file) as f:
                return json.load(f)
        return None
    
    async def initialize(self):
        """Initialize the mod service."""
        self.service = TUIModService(self.game_path)
    
    async def create_backup(self) -> bool:
        """Create a backup before installation."""
        self.log("Creating pre-installation backup...")
        try:
            backup_name = f"pre-mod-install-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.backup_id = await self.service.create_backup(backup_name)
            self.log(f"Backup created: {self.backup_id}", "SUCCESS")
            self.save_state()
            return True
        except Exception as e:
            self.log(f"Backup creation failed: {e}", "WARN")
            return False
    
    async def rollback(self) -> bool:
        """Rollback to the last backup."""
        state = self.load_state()
        if not state or not state.get("backup_id"):
            self.log("No backup found to restore", "ERROR")
            return False
        
        backup_id = state["backup_id"]
        self.log(f"Restoring backup: {backup_id}")
        
        try:
            await self.service.restore_backup(backup_id)
            self.log("Backup restored successfully", "SUCCESS")
            
            # Uninstall mods installed in this session
            for mod_id in state.get("installed_mod_ids", []):
                try:
                    await self.service.uninstall_mod(mod_id)
                    self.log(f"Uninstalled mod {mod_id}")
                except Exception:
                    pass
            
            # Clear state
            if self.state_file.exists():
                self.state_file.unlink()
            
            return True
        except Exception as e:
            self.log(f"Rollback failed: {e}", "ERROR")
            return False
    
    async def get_installed_mod_ids(self) -> set:
        """Get set of already installed mod IDs."""
        try:
            mods = await self.service.get_installed_mods()
            # Note: This checks local DB, not Nexus IDs
            return {m.nexus_mod_id for m in mods if m.nexus_mod_id}
        except Exception:
            return set()
    
    async def install_mod(self, mod: ModDefinition) -> InstallResult:
        """Install a single mod."""
        self.log(f"Installing [{mod.mod_id}] {mod.name}...")
        
        if self.dry_run:
            return InstallResult(mod=mod, success=True, skipped=True, skip_reason="dry-run")
        
        try:
            result_mod = await self.service.install_from_nexus(
                mod.mod_id,
                check_compatibility=False  # We've already filtered for compatibility
            )
            
            if result_mod:
                self.installed_mod_ids.append(mod.mod_id)
                self.save_state()
                self.log(f"  ✓ Installed successfully", "SUCCESS")
                return InstallResult(mod=mod, success=True)
            else:
                return InstallResult(mod=mod, success=False, error="No mod returned")
                
        except Exception as e:
            error_msg = str(e)
            
            # Check for premium requirement
            if "403" in error_msg or "Premium" in error_msg:
                self.log(f"  ⚠ Nexus Premium required - download manually:", "WARN")
                self.log(f"    {mod.url}")
                return InstallResult(mod=mod, success=False, skipped=True, 
                                    skip_reason="Nexus Premium required")
            
            self.log(f"  ✗ Failed: {error_msg}", "ERROR")
            return InstallResult(mod=mod, success=False, error=error_msg)
    
    async def install_all(self, mods: List[ModDefinition]) -> List[InstallResult]:
        """Install all mods in priority order."""
        # Sort by priority
        sorted_mods = sorted(mods, key=lambda m: m.priority)
        
        # Get already installed
        installed_ids = await self.get_installed_mod_ids()
        
        for mod in sorted_mods:
            # Skip if already installed
            if mod.mod_id in installed_ids:
                self.log(f"Skipping [{mod.mod_id}] {mod.name} - already installed")
                self.results.append(InstallResult(
                    mod=mod, success=True, skipped=True, skip_reason="already installed"
                ))
                continue
            
            result = await self.install_mod(mod)
            self.results.append(result)
            
            # Pause to avoid rate limiting
            if not self.dry_run:
                await asyncio.sleep(1)
        
        return self.results
    
    def print_summary(self):
        """Print installation summary."""
        success = [r for r in self.results if r.success and not r.skipped]
        failed = [r for r in self.results if not r.success and not r.skipped]
        skipped = [r for r in self.results if r.skipped]
        
        print("\n" + "=" * 60)
        print("INSTALLATION SUMMARY")
        print("=" * 60)
        print(f"\n  ✓ Successful:  {len(success)}")
        print(f"  ✗ Failed:      {len(failed)}")
        print(f"  ⊘ Skipped:     {len(skipped)}")
        print(f"\n  Log file:      {self.log_file}")
        print(f"  Backup ID:     {self.backup_id or 'none'}")
        
        if failed:
            print("\nFailed mods:")
            for r in failed:
                print(f"  - [{r.mod.mod_id}] {r.mod.name}: {r.error}")
        
        if skipped:
            premium_required = [r for r in skipped if r.skip_reason == "Nexus Premium required"]
            if premium_required:
                print("\nManual download required (Nexus Premium):")
                for r in premium_required:
                    print(f"  - {r.mod.url}")
        
        print("\nTo rollback: python install_mods.py --rollback")
        print()


async def main():
    parser = argparse.ArgumentParser(description="Install compatible Cyberpunk 2077 mods")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm all prompts")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be installed")
    parser.add_argument("--rollback", action="store_true", help="Restore from last backup")
    parser.add_argument("--category", choices=["texture", "redscript", "archivexl", "tweakxl"],
                       help="Install only specific category")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()
    
    # Detect game path
    game_path = await get_primary_game_path()
    if not game_path:
        print("ERROR: Could not detect Cyberpunk 2077 installation")
        sys.exit(1)
    
    print(f"Game path: {game_path}")
    
    # Create installer
    installer = ModInstaller(game_path, auto_confirm=args.yes, dry_run=args.dry_run)
    await installer.initialize()
    
    # Handle rollback
    if args.rollback:
        success = await installer.rollback()
        sys.exit(0 if success else 1)
    
    # Filter mods by category
    mods = COMPATIBLE_MODS
    if args.category:
        mods = [m for m in mods if m.category == args.category]
    
    # Show plan
    print(f"\nMods to install: {len(mods)}")
    by_category = {}
    for m in mods:
        by_category.setdefault(m.category, []).append(m)
    
    for cat, cat_mods in by_category.items():
        print(f"  {cat}: {len(cat_mods)}")
    
    if args.dry_run:
        print("\nDRY RUN - would install:")
        for m in sorted(mods, key=lambda x: x.priority):
            print(f"  [{m.mod_id}] {m.name} ({m.category})")
        sys.exit(0)
    
    # Confirm
    if not args.yes:
        response = input("\nProceed with installation? (y/N) ")
        if response.lower() != "y":
            print("Installation cancelled.")
            sys.exit(0)
    
    # Create backup
    await installer.create_backup()
    
    # Install
    print("\nStarting installation...\n")
    results = await installer.install_all(mods)
    
    # Output
    if args.json:
        output = {
            "backup_id": installer.backup_id,
            "results": [
                {
                    "mod_id": r.mod.mod_id,
                    "name": r.mod.name,
                    "success": r.success,
                    "skipped": r.skipped,
                    "error": r.error,
                    "skip_reason": r.skip_reason
                }
                for r in results
            ]
        }
        print(json.dumps(output, indent=2))
    else:
        installer.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
