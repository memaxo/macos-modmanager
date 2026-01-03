"""
Plugin Dependency Validator

Validates RED4ext plugin dependencies using otool.
"""

import subprocess
import re
from pathlib import Path
from typing import List, Dict, Set

from app.core.validation_engine import (
    Validator,
    ValidationCheckResult,
    ValidationIssue,
    ValidationCategory,
    ValidationSeverity,
)


class PluginDependencyValidator(Validator):
    """
    Validates RED4ext plugin dependencies.
    
    Uses otool to check:
    - Missing dynamic library dependencies
    - Invalid library paths
    - Architecture mismatches
    """
    
    name = "Plugin Dependencies"
    category = ValidationCategory.PLUGIN
    
    # System libraries that are expected to exist
    SYSTEM_LIBS = {
        '/usr/lib/',
        '/System/Library/',
        '@rpath/',
        '@loader_path/',
        '@executable_path/',
    }
    
    async def validate(self, game_path: Path) -> ValidationCheckResult:
        issues: List[ValidationIssue] = []
        plugins_checked = 0
        
        plugins_dir = game_path / "red4ext" / "plugins"
        
        if not plugins_dir.exists():
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=True,
                message="No plugins directory",
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
            plugin_issues = await self._check_plugin(dylib)
            issues.extend(plugin_issues)
            plugins_checked += 1
        
        error_count = sum(1 for i in issues if i.severity == ValidationSeverity.ERROR)
        passed = error_count == 0
        
        return ValidationCheckResult(
            name=self.name,
            category=self.category,
            passed=passed,
            message=f"Checked {plugins_checked} plugins" if passed else f"Found issues in {error_count} plugins",
            issues=issues
        )
    
    async def _check_plugin(self, dylib_path: Path) -> List[ValidationIssue]:
        """Check a single plugin for dependency issues"""
        issues = []
        plugin_name = dylib_path.name
        
        # Run otool -L to get dependencies
        try:
            result = subprocess.run(
                ['otool', '-L', str(dylib_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    f"Cannot Analyze: {plugin_name}",
                    f"otool failed: {result.stderr}",
                    file_path=str(dylib_path)
                ))
                return issues
            
            # Parse otool output
            deps = self._parse_otool_output(result.stdout)
            
            for dep_path, dep_info in deps.items():
                # Skip the library itself
                if plugin_name in dep_path:
                    continue
                
                # Check if it's a system library (should always exist)
                is_system = any(dep_path.startswith(prefix) for prefix in self.SYSTEM_LIBS)
                
                if not is_system:
                    # Check if the dependency exists
                    if dep_path.startswith('/') and not Path(dep_path).exists():
                        issues.append(self.create_issue(
                            ValidationSeverity.ERROR,
                            f"Missing Dependency: {plugin_name}",
                            f"Required library not found: {dep_path}",
                            file_path=str(dylib_path),
                            suggestion="Reinstall the plugin or install the missing dependency"
                        ))
            
        except subprocess.TimeoutExpired:
            issues.append(self.create_issue(
                ValidationSeverity.WARNING,
                f"Analysis Timeout: {plugin_name}",
                "Dependency analysis timed out",
                file_path=str(dylib_path)
            ))
        except Exception as e:
            issues.append(self.create_issue(
                ValidationSeverity.WARNING,
                f"Analysis Error: {plugin_name}",
                str(e),
                file_path=str(dylib_path)
            ))
        
        # Check architecture
        arch_issues = await self._check_architecture(dylib_path)
        issues.extend(arch_issues)
        
        return issues
    
    def _parse_otool_output(self, output: str) -> Dict[str, Dict]:
        """Parse otool -L output into a dictionary"""
        deps = {}
        
        for line in output.split('\n'):
            line = line.strip()
            if not line or line.endswith(':'):
                continue
            
            # Format: /path/to/lib.dylib (compatibility version X, current version Y)
            match = re.match(r'(.+?)\s*\((.+)\)', line)
            if match:
                path = match.group(1).strip()
                version_info = match.group(2)
                deps[path] = {'version_info': version_info}
            elif line:
                deps[line] = {}
        
        return deps
    
    async def _check_architecture(self, dylib_path: Path) -> List[ValidationIssue]:
        """Check if the plugin has the correct architecture"""
        issues = []
        plugin_name = dylib_path.name
        
        try:
            result = subprocess.run(
                ['file', str(dylib_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout.lower()
                
                # Check for ARM64 (Apple Silicon)
                if 'arm64' not in output and 'x86_64' in output:
                    issues.append(self.create_issue(
                        ValidationSeverity.WARNING,
                        f"x86_64 Only: {plugin_name}",
                        "Plugin is x86_64 only, may run slower under Rosetta",
                        file_path=str(dylib_path),
                        suggestion="Look for an ARM64 native version of the plugin"
                    ))
                elif 'arm64' not in output and 'x86_64' not in output:
                    issues.append(self.create_issue(
                        ValidationSeverity.ERROR,
                        f"Invalid Architecture: {plugin_name}",
                        "Plugin does not appear to be a valid macOS binary",
                        file_path=str(dylib_path)
                    ))
                    
        except Exception:
            pass
        
        return issues
