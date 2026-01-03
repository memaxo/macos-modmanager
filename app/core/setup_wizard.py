"""
Setup Wizard for macOS Mod Manager

Provides one-click setup for Cyberpunk 2077 modding on macOS.
Handles game detection, framework installation, and verification.
"""

import asyncio
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, TypedDict, Literal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.core.game_detector import detect_game_installations
from app.core.framework_manager import FrameworkManager, FrameworkStatus
from app.config import settings


class SetupStep(str, Enum):
    """Setup wizard steps"""
    DETECT_GAME = "detect_game"
    CHECK_FRAMEWORKS = "check_frameworks"
    INSTALL_RED4EXT = "install_red4ext"
    INSTALL_TWEAKXL = "install_tweakxl"
    INSTALL_ARCHIVEXL = "install_archivexl"
    CREATE_LAUNCHER = "create_launcher"
    VERIFY = "verify"
    COMPLETE = "complete"


class SetupStatus(str, Enum):
    """Overall setup status"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_SETUP = "needs_setup"


@dataclass
class EnvironmentInfo:
    """Information about the user's environment"""
    game_detected: bool = False
    game_path: Optional[Path] = None
    game_version: Optional[str] = None
    game_launcher: Optional[str] = None  # steam, gog
    
    red4ext_installed: bool = False
    red4ext_version: Optional[str] = None
    
    tweakxl_installed: bool = False
    tweakxl_version: Optional[str] = None
    
    archivexl_installed: bool = False
    archivexl_version: Optional[str] = None
    
    redscript_installed: bool = False
    redscript_version: Optional[str] = None
    
    frida_gadget_installed: bool = False
    launch_script_exists: bool = False
    
    macos_version: Optional[str] = None
    is_apple_silicon: bool = False
    
    setup_needed: bool = True
    issues: List[str] = field(default_factory=list)


@dataclass
class SetupOptions:
    """Options for setup wizard"""
    install_red4ext: bool = True
    install_tweakxl: bool = True
    install_archivexl: bool = True
    install_redscript: bool = False  # Optional
    create_launch_script: bool = True
    game_path: Optional[Path] = None


@dataclass
class SetupProgress:
    """Progress information for setup"""
    current_step: SetupStep
    step_number: int
    total_steps: int
    step_progress: float  # 0.0 to 1.0
    message: str
    is_error: bool = False
    error_message: Optional[str] = None


@dataclass
class SetupResult:
    """Result of setup operation"""
    success: bool
    status: SetupStatus
    message: str
    environment: Optional[EnvironmentInfo] = None
    installed_frameworks: List[str] = field(default_factory=list)
    failed_frameworks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class VerificationResult:
    """Result of setup verification"""
    success: bool
    checks_passed: int
    checks_failed: int
    checks: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# Type for progress callback
ProgressCallback = Callable[[SetupProgress], None]


class SetupWizard:
    """
    One-click setup wizard for Cyberpunk 2077 modding on macOS.
    
    Handles:
    - Game detection and validation
    - Framework installation (RED4ext, TweakXL, ArchiveXL)
    - Launch script creation
    - Verification of installation
    """
    
    def __init__(self, game_path: Optional[Path] = None):
        self.game_path = game_path
        self._framework_manager: Optional[FrameworkManager] = None
        self._progress_callback: Optional[ProgressCallback] = None
        self._cancelled = False
    
    async def _get_framework_manager(self) -> FrameworkManager:
        """Get or create framework manager"""
        if self._framework_manager is None:
            self._framework_manager = FrameworkManager(self.game_path)
        return self._framework_manager
    
    async def close(self):
        """Cleanup resources"""
        if self._framework_manager:
            await self._framework_manager.close()
            self._framework_manager = None
    
    def _report_progress(
        self, 
        step: SetupStep, 
        step_number: int, 
        total_steps: int,
        progress: float,
        message: str,
        is_error: bool = False,
        error_message: Optional[str] = None
    ):
        """Report progress to callback"""
        if self._progress_callback:
            self._progress_callback(SetupProgress(
                current_step=step,
                step_number=step_number,
                total_steps=total_steps,
                step_progress=progress,
                message=message,
                is_error=is_error,
                error_message=error_message
            ))
    
    async def detect_environment(self) -> EnvironmentInfo:
        """
        Detect the current environment and what's installed.
        
        Returns:
            EnvironmentInfo with details about game and framework installations
        """
        env = EnvironmentInfo()
        
        # Detect macOS version and architecture
        try:
            result = subprocess.run(['sw_vers', '-productVersion'], capture_output=True, text=True)
            if result.returncode == 0:
                env.macos_version = result.stdout.strip()
        except Exception:
            pass
        
        try:
            result = subprocess.run(['uname', '-m'], capture_output=True, text=True)
            if result.returncode == 0:
                env.is_apple_silicon = 'arm64' in result.stdout.lower()
        except Exception:
            pass
        
        # Detect game installation
        installations = await detect_game_installations()
        if installations:
            env.game_detected = True
            env.game_path = Path(installations[0]['path'])
            env.game_version = installations[0].get('version')
            env.game_launcher = installations[0].get('launcher')
            self.game_path = env.game_path
        else:
            env.issues.append("Cyberpunk 2077 installation not found")
            env.setup_needed = True
            return env
        
        # Check framework installations
        manager = await self._get_framework_manager()
        
        try:
            red4ext_status = await manager.check_status('red4ext')
            env.red4ext_installed = red4ext_status.installed and red4ext_status.healthy
            env.red4ext_version = red4ext_status.version
            if not env.red4ext_installed:
                env.issues.append("RED4ext not installed or unhealthy")
        except Exception as e:
            env.issues.append(f"Failed to check RED4ext: {e}")
        
        try:
            tweakxl_status = await manager.check_status('tweakxl')
            env.tweakxl_installed = tweakxl_status.installed and tweakxl_status.healthy
            env.tweakxl_version = tweakxl_status.version
        except Exception:
            pass
        
        try:
            archivexl_status = await manager.check_status('archivexl')
            env.archivexl_installed = archivexl_status.installed and archivexl_status.healthy
            env.archivexl_version = archivexl_status.version
        except Exception:
            pass
        
        # Check for Frida Gadget
        if env.game_path:
            frida_path = env.game_path / "red4ext" / "FridaGadget.dylib"
            env.frida_gadget_installed = frida_path.exists()
            if not env.frida_gadget_installed and env.red4ext_installed:
                env.issues.append("Frida Gadget not installed (required for hooking)")
        
        # Check for launch script
        if env.game_path:
            launch_script = env.game_path / "launch_red4ext.sh"
            env.launch_script_exists = launch_script.exists()
        
        # Check for redscript
        if env.game_path:
            # Check common redscript locations
            redscript_paths = [
                env.game_path / "engine" / "tools" / "scc",
                env.game_path / "r6" / "scripts",
            ]
            if any(p.exists() for p in redscript_paths):
                env.redscript_installed = True
        
        # Determine if setup is needed
        env.setup_needed = not (
            env.game_detected and 
            env.red4ext_installed and 
            env.frida_gadget_installed and
            env.launch_script_exists
        )
        
        return env
    
    async def check_setup_status(self) -> SetupStatus:
        """
        Quick check if setup is needed.
        
        Returns:
            SetupStatus indicating current state
        """
        env = await self.detect_environment()
        
        if not env.game_detected:
            return SetupStatus.NEEDS_SETUP
        
        if env.setup_needed:
            return SetupStatus.NEEDS_SETUP
        
        return SetupStatus.COMPLETED
    
    async def run_setup(
        self, 
        options: SetupOptions,
        on_progress: Optional[ProgressCallback] = None
    ) -> SetupResult:
        """
        Run the complete setup process.
        
        Args:
            options: Setup configuration options
            on_progress: Callback for progress updates
            
        Returns:
            SetupResult with installation outcome
        """
        self._progress_callback = on_progress
        self._cancelled = False
        start_time = datetime.now()
        
        installed = []
        failed = []
        warnings = []
        
        # Calculate total steps
        total_steps = 2  # detect + verify
        if options.install_red4ext:
            total_steps += 1
        if options.install_tweakxl:
            total_steps += 1
        if options.install_archivexl:
            total_steps += 1
        if options.create_launch_script:
            total_steps += 1
        
        current_step = 0
        
        try:
            # Step 1: Detect environment
            current_step += 1
            self._report_progress(
                SetupStep.DETECT_GAME, current_step, total_steps,
                0.0, "Detecting game installation..."
            )
            
            env = await self.detect_environment()
            
            if not env.game_detected:
                return SetupResult(
                    success=False,
                    status=SetupStatus.FAILED,
                    message="Cyberpunk 2077 installation not found",
                    environment=env
                )
            
            # Use provided game path or detected one
            if options.game_path:
                self.game_path = options.game_path
            elif env.game_path:
                self.game_path = env.game_path
            
            self._report_progress(
                SetupStep.DETECT_GAME, current_step, total_steps,
                1.0, f"Game found at {self.game_path}"
            )
            
            if self._cancelled:
                return SetupResult(
                    success=False,
                    status=SetupStatus.FAILED,
                    message="Setup cancelled by user"
                )
            
            # Get framework manager
            manager = await self._get_framework_manager()
            
            # Step 2: Install RED4ext
            if options.install_red4ext:
                current_step += 1
                self._report_progress(
                    SetupStep.INSTALL_RED4EXT, current_step, total_steps,
                    0.0, "Installing RED4ext mod loader..."
                )
                
                try:
                    result = await manager.install('red4ext')
                    if result.success:
                        installed.append('red4ext')
                        self._report_progress(
                            SetupStep.INSTALL_RED4EXT, current_step, total_steps,
                            1.0, f"RED4ext {result.version} installed"
                        )
                    else:
                        failed.append('red4ext')
                        warnings.append(f"RED4ext installation failed: {result.message}")
                        self._report_progress(
                            SetupStep.INSTALL_RED4EXT, current_step, total_steps,
                            1.0, result.message, is_error=True
                        )
                except Exception as e:
                    failed.append('red4ext')
                    warnings.append(f"RED4ext installation error: {e}")
                
                if self._cancelled:
                    return SetupResult(
                        success=False,
                        status=SetupStatus.FAILED,
                        message="Setup cancelled by user",
                        installed_frameworks=installed
                    )
            
            # Step 3: Install TweakXL
            if options.install_tweakxl:
                current_step += 1
                self._report_progress(
                    SetupStep.INSTALL_TWEAKXL, current_step, total_steps,
                    0.0, "Installing TweakXL..."
                )
                
                try:
                    result = await manager.install('tweakxl')
                    if result.success:
                        installed.append('tweakxl')
                        self._report_progress(
                            SetupStep.INSTALL_TWEAKXL, current_step, total_steps,
                            1.0, f"TweakXL {result.version} installed"
                        )
                    else:
                        failed.append('tweakxl')
                        warnings.append(f"TweakXL installation failed: {result.message}")
                except Exception as e:
                    failed.append('tweakxl')
                    warnings.append(f"TweakXL installation error: {e}")
                
                if self._cancelled:
                    return SetupResult(
                        success=False,
                        status=SetupStatus.FAILED,
                        message="Setup cancelled by user",
                        installed_frameworks=installed
                    )
            
            # Step 4: Install ArchiveXL
            if options.install_archivexl:
                current_step += 1
                self._report_progress(
                    SetupStep.INSTALL_ARCHIVEXL, current_step, total_steps,
                    0.0, "Installing ArchiveXL..."
                )
                
                try:
                    result = await manager.install('archivexl')
                    if result.success:
                        installed.append('archivexl')
                        self._report_progress(
                            SetupStep.INSTALL_ARCHIVEXL, current_step, total_steps,
                            1.0, f"ArchiveXL {result.version} installed"
                        )
                    else:
                        failed.append('archivexl')
                        warnings.append(f"ArchiveXL installation failed: {result.message}")
                except Exception as e:
                    failed.append('archivexl')
                    warnings.append(f"ArchiveXL installation error: {e}")
            
            # Step 5: Create launch script
            if options.create_launch_script:
                current_step += 1
                self._report_progress(
                    SetupStep.CREATE_LAUNCHER, current_step, total_steps,
                    0.0, "Creating launch script..."
                )
                
                try:
                    await self._create_launch_script()
                    self._report_progress(
                        SetupStep.CREATE_LAUNCHER, current_step, total_steps,
                        1.0, "Launch script created"
                    )
                except Exception as e:
                    warnings.append(f"Failed to create launch script: {e}")
            
            # Step 6: Verify installation
            current_step += 1
            self._report_progress(
                SetupStep.VERIFY, current_step, total_steps,
                0.0, "Verifying installation..."
            )
            
            verification = await self.verify_setup()
            
            self._report_progress(
                SetupStep.VERIFY, current_step, total_steps,
                1.0, f"Verification complete: {verification.checks_passed}/{verification.checks_passed + verification.checks_failed} checks passed"
            )
            
            # Final result
            duration = (datetime.now() - start_time).total_seconds()
            
            # Determine success
            success = 'red4ext' in installed and len(failed) == 0
            
            if success:
                self._report_progress(
                    SetupStep.COMPLETE, current_step, total_steps,
                    1.0, "Setup completed successfully!"
                )
            
            # Re-detect environment after setup
            final_env = await self.detect_environment()
            
            return SetupResult(
                success=success,
                status=SetupStatus.COMPLETED if success else SetupStatus.FAILED,
                message="Setup completed successfully" if success else f"Setup completed with issues: {', '.join(failed)} failed",
                environment=final_env,
                installed_frameworks=installed,
                failed_frameworks=failed,
                warnings=warnings,
                duration_seconds=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return SetupResult(
                success=False,
                status=SetupStatus.FAILED,
                message=f"Setup failed: {str(e)}",
                installed_frameworks=installed,
                failed_frameworks=failed,
                warnings=warnings,
                duration_seconds=duration
            )
        finally:
            self._progress_callback = None
    
    async def _create_launch_script(self):
        """Create the launch script for running the game with mods"""
        if not self.game_path:
            raise RuntimeError("Game path not set")
        
        launch_script = self.game_path / "launch_red4ext.sh"
        red4ext_dir = self.game_path / "red4ext"
        
        # Find the game binary
        game_app = None
        for item in self.game_path.iterdir():
            if item.suffix == ".app":
                game_app = item
                break
        
        if not game_app:
            game_app = self.game_path / "Cyberpunk2077.app"
        
        game_binary = game_app / "Contents" / "MacOS" / "Cyberpunk2077"
        
        script_content = f'''#!/bin/bash
# RED4ext macOS Launcher
# Generated by macOS Mod Manager

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
RED4EXT_DIR="$SCRIPT_DIR/red4ext"
GAME_BINARY="$SCRIPT_DIR/{game_app.name}/Contents/MacOS/Cyberpunk2077"

echo "=== RED4ext macOS Launcher ==="
echo "Game: $GAME_BINARY"

# Check if RED4ext exists
if [ ! -f "$RED4EXT_DIR/RED4ext.dylib" ]; then
    echo "ERROR: RED4ext.dylib not found!"
    echo "Please run the mod manager setup first."
    exit 1
fi

# Build injection list
INJECT_LIBS="$RED4EXT_DIR/RED4ext.dylib"

# Add Frida Gadget if present
if [ -f "$RED4EXT_DIR/FridaGadget.dylib" ]; then
    INJECT_LIBS="$INJECT_LIBS:$RED4EXT_DIR/FridaGadget.dylib"
    echo "Frida Gadget: Enabled"
fi

# Compile REDscript if compiler exists
if [ -x "$SCRIPT_DIR/engine/tools/scc" ]; then
    echo "Compiling REDscript..."
    "$SCRIPT_DIR/engine/tools/scc" -compile "$SCRIPT_DIR/r6/scripts" 2>&1 || echo "REDscript compilation skipped"
fi

# Process input mappings if available
if [ -x "$SCRIPT_DIR/engine/tools/inputloader.pl" ]; then
    "$SCRIPT_DIR/engine/tools/inputloader.pl" 2>&1 || true
fi

echo "Injecting: $INJECT_LIBS"
echo "Launching game..."

# Set injection environment and launch
export DYLD_INSERT_LIBRARIES="$INJECT_LIBS"
export DYLD_FORCE_FLAT_NAMESPACE=1
exec "$GAME_BINARY" "$@"
'''
        
        launch_script.write_text(script_content)
        launch_script.chmod(0o755)
    
    async def verify_setup(self) -> VerificationResult:
        """
        Verify the setup is complete and working.
        
        Returns:
            VerificationResult with detailed check results
        """
        checks = []
        issues = []
        recommendations = []
        
        if not self.game_path:
            env = await self.detect_environment()
            if env.game_path:
                self.game_path = env.game_path
        
        if not self.game_path:
            return VerificationResult(
                success=False,
                checks_passed=0,
                checks_failed=1,
                checks=[{"name": "Game Detection", "passed": False, "message": "Game not found"}],
                issues=["Cyberpunk 2077 installation not detected"]
            )
        
        # Check 1: Game installation
        game_exists = self.game_path.exists()
        checks.append({
            "name": "Game Installation",
            "passed": game_exists,
            "message": f"Game found at {self.game_path}" if game_exists else "Game directory not found"
        })
        if not game_exists:
            issues.append("Game installation not found")
        
        # Check 2: RED4ext directory
        red4ext_dir = self.game_path / "red4ext"
        red4ext_exists = red4ext_dir.exists()
        checks.append({
            "name": "RED4ext Directory",
            "passed": red4ext_exists,
            "message": "red4ext/ directory exists" if red4ext_exists else "red4ext/ directory missing"
        })
        if not red4ext_exists:
            issues.append("RED4ext directory not created")
        
        # Check 3: RED4ext.dylib
        red4ext_dylib = red4ext_dir / "RED4ext.dylib"
        dylib_exists = red4ext_dylib.exists()
        checks.append({
            "name": "RED4ext.dylib",
            "passed": dylib_exists,
            "message": "RED4ext.dylib present" if dylib_exists else "RED4ext.dylib missing"
        })
        if not dylib_exists:
            issues.append("RED4ext.dylib not installed")
        
        # Check 4: Dylib code signature
        if dylib_exists:
            try:
                result = subprocess.run(
                    ['codesign', '-v', str(red4ext_dylib)],
                    capture_output=True, text=True
                )
                signed = result.returncode == 0
                checks.append({
                    "name": "Code Signature (RED4ext)",
                    "passed": signed,
                    "message": "Valid signature" if signed else "Invalid or missing signature"
                })
                if not signed:
                    recommendations.append("Run 'codesign -s - RED4ext.dylib' to ad-hoc sign")
            except Exception:
                checks.append({
                    "name": "Code Signature (RED4ext)",
                    "passed": False,
                    "message": "Could not verify signature"
                })
        
        # Check 5: Frida Gadget
        frida_gadget = red4ext_dir / "FridaGadget.dylib"
        frida_exists = frida_gadget.exists()
        checks.append({
            "name": "Frida Gadget",
            "passed": frida_exists,
            "message": "FridaGadget.dylib present" if frida_exists else "FridaGadget.dylib missing"
        })
        if not frida_exists:
            recommendations.append("Install Frida Gadget for full functionality")
        
        # Check 6: Plugins directory
        plugins_dir = red4ext_dir / "plugins"
        plugins_exists = plugins_dir.exists()
        checks.append({
            "name": "Plugins Directory",
            "passed": plugins_exists,
            "message": "plugins/ directory exists" if plugins_exists else "plugins/ directory missing"
        })
        
        # Check 7: TweakXL (optional)
        tweakxl_dylib = plugins_dir / "TweakXL" / "TweakXL.dylib"
        tweakxl_exists = tweakxl_dylib.exists() if plugins_exists else False
        checks.append({
            "name": "TweakXL Plugin",
            "passed": tweakxl_exists,
            "message": "TweakXL.dylib present" if tweakxl_exists else "TweakXL not installed (optional)"
        })
        
        # Check 8: ArchiveXL (optional)
        archivexl_dylib = plugins_dir / "ArchiveXL" / "ArchiveXL.dylib"
        archivexl_exists = archivexl_dylib.exists() if plugins_exists else False
        checks.append({
            "name": "ArchiveXL Plugin",
            "passed": archivexl_exists,
            "message": "ArchiveXL.dylib present" if archivexl_exists else "ArchiveXL not installed (optional)"
        })
        
        # Check 9: Launch script
        launch_script = self.game_path / "launch_red4ext.sh"
        script_exists = launch_script.exists()
        checks.append({
            "name": "Launch Script",
            "passed": script_exists,
            "message": "launch_red4ext.sh present" if script_exists else "Launch script missing"
        })
        if not script_exists:
            issues.append("Launch script not created")
        
        # Check 10: Launch script executable
        if script_exists:
            import os
            executable = os.access(launch_script, os.X_OK)
            checks.append({
                "name": "Launch Script Executable",
                "passed": executable,
                "message": "Script is executable" if executable else "Script not executable"
            })
            if not executable:
                recommendations.append("Run 'chmod +x launch_red4ext.sh'")
        
        # Calculate results
        passed = sum(1 for c in checks if c['passed'])
        failed = len(checks) - passed
        
        # Determine overall success (core requirements)
        core_passed = all([
            game_exists,
            red4ext_exists,
            dylib_exists,
            script_exists
        ])
        
        return VerificationResult(
            success=core_passed,
            checks_passed=passed,
            checks_failed=failed,
            checks=checks,
            issues=issues,
            recommendations=recommendations
        )
    
    def cancel(self):
        """Cancel the current setup operation"""
        self._cancelled = True


async def get_setup_status() -> Dict[str, Any]:
    """
    Quick helper to get setup status for API.
    
    Returns:
        Dict with status information
    """
    wizard = SetupWizard()
    try:
        env = await wizard.detect_environment()
        status = await wizard.check_setup_status()
        
        return {
            "status": status.value,
            "game_detected": env.game_detected,
            "game_path": str(env.game_path) if env.game_path else None,
            "red4ext_installed": env.red4ext_installed,
            "tweakxl_installed": env.tweakxl_installed,
            "archivexl_installed": env.archivexl_installed,
            "setup_needed": env.setup_needed,
            "issues": env.issues,
        }
    finally:
        await wizard.close()
