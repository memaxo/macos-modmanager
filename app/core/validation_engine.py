"""
Validation Engine for Pre-Launch Checks

Runs validation checks before game launch to catch configuration
errors and prevent wasted debugging time.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Protocol
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

from app.core.game_detector import detect_game_installations
from app.config import settings


class ValidationSeverity(str, Enum):
    """Severity level of validation issues"""
    ERROR = "error"      # Blocks launch
    WARNING = "warning"  # Warns but allows launch
    INFO = "info"        # Informational only


class ValidationCategory(str, Enum):
    """Category of validation check"""
    FRAMEWORK = "framework"
    PLUGIN = "plugin"
    REDSCRIPT = "redscript"
    TWEAK = "tweak"
    ARCHIVE = "archive"
    SYSTEM = "system"


@dataclass
class ValidationIssue:
    """A validation issue found during checks"""
    category: ValidationCategory
    severity: ValidationSeverity
    title: str
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None
    auto_fix_available: bool = False
    auto_fix_action: Optional[str] = None


@dataclass
class ValidationCheckResult:
    """Result of a single validation check"""
    name: str
    category: ValidationCategory
    passed: bool
    message: str
    issues: List[ValidationIssue] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class ValidationReport:
    """Complete validation report"""
    success: bool  # No errors (warnings ok)
    can_launch: bool  # Can proceed with launch
    total_checks: int
    passed_checks: int
    failed_checks: int
    error_count: int
    warning_count: int
    info_count: int
    checks: List[ValidationCheckResult] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    duration_ms: float = 0.0


class Validator(ABC):
    """Base class for validators"""
    
    name: str = "Base Validator"
    category: ValidationCategory = ValidationCategory.SYSTEM
    
    @abstractmethod
    async def validate(self, game_path: Path) -> ValidationCheckResult:
        """Run validation check"""
        pass
    
    def create_issue(
        self,
        severity: ValidationSeverity,
        title: str,
        message: str,
        **kwargs
    ) -> ValidationIssue:
        """Helper to create an issue"""
        return ValidationIssue(
            category=self.category,
            severity=severity,
            title=title,
            message=message,
            **kwargs
        )


class RED4extValidator(Validator):
    """Validates RED4ext installation"""
    
    name = "RED4ext Installation"
    category = ValidationCategory.FRAMEWORK
    
    async def validate(self, game_path: Path) -> ValidationCheckResult:
        issues = []
        
        red4ext_dir = game_path / "red4ext"
        red4ext_dylib = red4ext_dir / "RED4ext.dylib"
        
        # Check directory exists
        if not red4ext_dir.exists():
            issues.append(self.create_issue(
                ValidationSeverity.ERROR,
                "RED4ext Not Installed",
                "The red4ext directory does not exist",
                suggestion="Run the setup wizard to install RED4ext"
            ))
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=False,
                message="RED4ext not installed",
                issues=issues
            )
        
        # Check dylib exists
        if not red4ext_dylib.exists():
            issues.append(self.create_issue(
                ValidationSeverity.ERROR,
                "RED4ext.dylib Missing",
                "RED4ext.dylib not found in red4ext directory",
                suggestion="Reinstall RED4ext using the setup wizard"
            ))
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=False,
                message="RED4ext.dylib missing",
                issues=issues
            )
        
        # Check file size (basic corruption check)
        if red4ext_dylib.stat().st_size < 10000:
            issues.append(self.create_issue(
                ValidationSeverity.ERROR,
                "RED4ext.dylib Corrupted",
                "RED4ext.dylib appears to be corrupted (file too small)",
                suggestion="Reinstall RED4ext"
            ))
        
        # Check code signature
        try:
            result = subprocess.run(
                ['codesign', '-v', str(red4ext_dylib)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    "Code Signature Invalid",
                    "RED4ext.dylib is not properly signed",
                    suggestion="Run: codesign -s - " + str(red4ext_dylib),
                    auto_fix_available=True,
                    auto_fix_action="codesign"
                ))
        except Exception:
            issues.append(self.create_issue(
                ValidationSeverity.INFO,
                "Signature Check Skipped",
                "Could not verify code signature"
            ))
        
        # Check Frida Gadget
        frida_gadget = red4ext_dir / "FridaGadget.dylib"
        if not frida_gadget.exists():
            issues.append(self.create_issue(
                ValidationSeverity.WARNING,
                "Frida Gadget Missing",
                "FridaGadget.dylib not found - some hooks may not work",
                suggestion="Reinstall RED4ext with Frida Gadget"
            ))
        
        passed = not any(i.severity == ValidationSeverity.ERROR for i in issues)
        
        return ValidationCheckResult(
            name=self.name,
            category=self.category,
            passed=passed,
            message="RED4ext installation OK" if passed else "RED4ext installation has issues",
            issues=issues
        )


class PluginValidator(Validator):
    """Validates RED4ext plugins"""
    
    name = "Plugin Loadability"
    category = ValidationCategory.PLUGIN
    
    async def validate(self, game_path: Path) -> ValidationCheckResult:
        issues = []
        
        plugins_dir = game_path / "red4ext" / "plugins"
        
        if not plugins_dir.exists():
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=True,
                message="No plugins directory (OK if no plugins installed)",
                issues=[]
            )
        
        # Find all dylib files
        dylib_files = list(plugins_dir.rglob("*.dylib"))
        
        if not dylib_files:
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=True,
                message="No plugins installed",
                issues=[]
            )
        
        for dylib in dylib_files:
            # Check file exists and readable
            if not dylib.is_file():
                continue
            
            # Check file size
            if dylib.stat().st_size < 1000:
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    f"Plugin May Be Corrupted: {dylib.name}",
                    f"Plugin file {dylib.name} is suspiciously small",
                    file_path=str(dylib)
                ))
                continue
            
            # Check code signature
            try:
                result = subprocess.run(
                    ['codesign', '-v', str(dylib)],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode != 0:
                    issues.append(self.create_issue(
                        ValidationSeverity.WARNING,
                        f"Plugin Not Signed: {dylib.name}",
                        f"Plugin {dylib.name} is not properly signed",
                        file_path=str(dylib),
                        suggestion=f"Run: codesign -s - {dylib}",
                        auto_fix_available=True,
                        auto_fix_action="codesign"
                    ))
            except Exception:
                pass
            
            # Check dependencies with otool
            try:
                result = subprocess.run(
                    ['otool', '-L', str(dylib)],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    # Look for missing dependencies
                    for line in result.stdout.split('\n'):
                        if 'not found' in line.lower():
                            issues.append(self.create_issue(
                                ValidationSeverity.ERROR,
                                f"Missing Dependency: {dylib.name}",
                                f"Plugin {dylib.name} has missing dependencies",
                                file_path=str(dylib),
                                suggestion="Reinstall the plugin or check for missing libraries"
                            ))
            except Exception:
                pass
        
        passed = not any(i.severity == ValidationSeverity.ERROR for i in issues)
        
        return ValidationCheckResult(
            name=self.name,
            category=self.category,
            passed=passed,
            message=f"Checked {len(dylib_files)} plugins" if passed else "Some plugins have issues",
            issues=issues
        )


class LaunchScriptValidator(Validator):
    """Validates launch script"""
    
    name = "Launch Script"
    category = ValidationCategory.SYSTEM
    
    async def validate(self, game_path: Path) -> ValidationCheckResult:
        issues = []
        
        launch_script = game_path / "launch_red4ext.sh"
        
        if not launch_script.exists():
            issues.append(self.create_issue(
                ValidationSeverity.ERROR,
                "Launch Script Missing",
                "launch_red4ext.sh not found",
                suggestion="Run the setup wizard to create the launch script"
            ))
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=False,
                message="Launch script missing",
                issues=issues
            )
        
        # Check executable
        import os
        if not os.access(launch_script, os.X_OK):
            issues.append(self.create_issue(
                ValidationSeverity.WARNING,
                "Launch Script Not Executable",
                "launch_red4ext.sh is not executable",
                suggestion="Run: chmod +x launch_red4ext.sh",
                auto_fix_available=True,
                auto_fix_action="chmod"
            ))
        
        # Check script content
        content = launch_script.read_text()
        
        if 'DYLD_INSERT_LIBRARIES' not in content:
            issues.append(self.create_issue(
                ValidationSeverity.WARNING,
                "Launch Script May Be Outdated",
                "Launch script may not properly inject RED4ext",
                suggestion="Regenerate the launch script"
            ))
        
        passed = not any(i.severity == ValidationSeverity.ERROR for i in issues)
        
        return ValidationCheckResult(
            name=self.name,
            category=self.category,
            passed=passed,
            message="Launch script OK" if passed else "Launch script has issues",
            issues=issues
        )


class GameBinaryValidator(Validator):
    """Validates game binary"""
    
    name = "Game Binary"
    category = ValidationCategory.SYSTEM
    
    async def validate(self, game_path: Path) -> ValidationCheckResult:
        issues = []
        
        # Find game app bundle
        game_app = None
        for item in game_path.iterdir():
            if item.suffix == ".app" and "Cyberpunk" in item.name:
                game_app = item
                break
        
        if not game_app:
            issues.append(self.create_issue(
                ValidationSeverity.ERROR,
                "Game App Not Found",
                "Could not find Cyberpunk2077.app",
                suggestion="Verify game installation via Steam/GOG"
            ))
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=False,
                message="Game binary not found",
                issues=issues
            )
        
        # Check binary exists
        game_binary = game_app / "Contents" / "MacOS" / "Cyberpunk2077"
        
        if not game_binary.exists():
            issues.append(self.create_issue(
                ValidationSeverity.ERROR,
                "Game Binary Missing",
                "Cyberpunk2077 executable not found in app bundle",
                suggestion="Verify game integrity via Steam/GOG"
            ))
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=False,
                message="Game binary missing",
                issues=issues
            )
        
        # Check architecture (should be ARM64 for Apple Silicon)
        try:
            result = subprocess.run(
                ['file', str(game_binary)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                if 'arm64' not in result.stdout.lower() and 'x86_64' not in result.stdout.lower():
                    issues.append(self.create_issue(
                        ValidationSeverity.WARNING,
                        "Unknown Architecture",
                        "Could not determine game binary architecture"
                    ))
        except Exception:
            pass
        
        passed = not any(i.severity == ValidationSeverity.ERROR for i in issues)
        
        return ValidationCheckResult(
            name=self.name,
            category=self.category,
            passed=passed,
            message="Game binary OK" if passed else "Game binary has issues",
            issues=issues
        )


class ValidationEngine:
    """
    Orchestrates validation checks before game launch.
    
    Runs multiple validators and aggregates results into a comprehensive report.
    """
    
    def __init__(self, game_path: Optional[Path] = None):
        self.game_path = game_path
        self.validators: List[Validator] = [
            GameBinaryValidator(),
            RED4extValidator(),
            PluginValidator(),
            LaunchScriptValidator(),
        ]
    
    async def _get_game_path(self) -> Path:
        """Get game path if not set"""
        if self.game_path:
            return self.game_path
        
        installations = await detect_game_installations()
        if not installations:
            raise RuntimeError("Cyberpunk 2077 installation not found")
        
        self.game_path = Path(installations[0]['path'])
        return self.game_path
    
    def add_validator(self, validator: Validator):
        """Add a custom validator"""
        self.validators.append(validator)
    
    async def run_all(self) -> ValidationReport:
        """Run all validation checks"""
        import time
        start = time.time()
        
        game_path = await self._get_game_path()
        
        checks: List[ValidationCheckResult] = []
        all_issues: List[ValidationIssue] = []
        
        for validator in self.validators:
            check_start = time.time()
            try:
                result = await validator.validate(game_path)
                result.duration_ms = (time.time() - check_start) * 1000
                checks.append(result)
                all_issues.extend(result.issues)
            except Exception as e:
                checks.append(ValidationCheckResult(
                    name=validator.name,
                    category=validator.category,
                    passed=False,
                    message=f"Validator error: {str(e)}",
                    issues=[ValidationIssue(
                        category=validator.category,
                        severity=ValidationSeverity.ERROR,
                        title="Validation Error",
                        message=str(e)
                    )],
                    duration_ms=(time.time() - check_start) * 1000
                ))
        
        # Count results
        passed = sum(1 for c in checks if c.passed)
        failed = len(checks) - passed
        
        errors = sum(1 for i in all_issues if i.severity == ValidationSeverity.ERROR)
        warnings = sum(1 for i in all_issues if i.severity == ValidationSeverity.WARNING)
        infos = sum(1 for i in all_issues if i.severity == ValidationSeverity.INFO)
        
        duration = (time.time() - start) * 1000
        
        return ValidationReport(
            success=errors == 0,
            can_launch=errors == 0,  # Can launch if no errors
            total_checks=len(checks),
            passed_checks=passed,
            failed_checks=failed,
            error_count=errors,
            warning_count=warnings,
            info_count=infos,
            checks=checks,
            issues=all_issues,
            duration_ms=duration
        )
    
    async def run_critical_only(self) -> ValidationReport:
        """Run only critical validators (faster)"""
        # For now, same as run_all but could be optimized
        return await self.run_all()
    
    @staticmethod
    def get_fix_suggestions(issue: ValidationIssue) -> List[Dict[str, Any]]:
        """Get fix suggestions for an issue"""
        suggestions = []
        
        if issue.suggestion:
            suggestions.append({
                "description": issue.suggestion,
                "auto_fix": issue.auto_fix_available,
                "action": issue.auto_fix_action,
            })
        
        # Add common fixes based on category
        if issue.category == ValidationCategory.FRAMEWORK:
            suggestions.append({
                "description": "Run the setup wizard to reinstall frameworks",
                "auto_fix": False,
                "action": None,
            })
        
        return suggestions
    
    async def apply_fix(self, issue: ValidationIssue) -> bool:
        """Attempt to auto-fix an issue"""
        if not issue.auto_fix_available or not issue.auto_fix_action:
            return False
        
        try:
            if issue.auto_fix_action == "codesign" and issue.file_path:
                result = subprocess.run(
                    ['codesign', '-s', '-', issue.file_path],
                    capture_output=True, timeout=30
                )
                return result.returncode == 0
            
            if issue.auto_fix_action == "chmod" and issue.file_path:
                result = subprocess.run(
                    ['chmod', '+x', issue.file_path],
                    capture_output=True, timeout=10
                )
                return result.returncode == 0
            
        except Exception:
            pass
        
        return False
