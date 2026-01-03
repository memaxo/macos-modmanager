"""
Error Detection Engine

Analyzes log lines to detect and categorize errors.
Provides fix suggestions based on pattern matching.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from app.core.log_streamer import LogLine, LogLevel, LogSource


class ErrorCategory(str, Enum):
    """Categories of errors"""
    REDSCRIPT = "redscript"
    PLUGIN = "plugin"
    TWEAK = "tweak"
    ARCHIVE = "archive"
    FRAMEWORK = "framework"
    GAME = "game"
    UNKNOWN = "unknown"


@dataclass
class ErrorPattern:
    """A pattern for detecting errors"""
    id: str
    regex: str
    category: ErrorCategory
    severity: LogLevel
    title: str
    description: str
    suggestion: Optional[str] = None
    extract_groups: List[str] = field(default_factory=list)  # Named capture groups
    
    _compiled: Optional[re.Pattern] = field(default=None, repr=False)
    
    def compile(self):
        """Compile the regex pattern"""
        if self._compiled is None:
            self._compiled = re.compile(self.regex, re.IGNORECASE | re.MULTILINE)
        return self._compiled


@dataclass 
class DetectedError:
    """An error detected in the logs"""
    pattern: ErrorPattern
    log_line: LogLine
    match_groups: Dict[str, str]
    title: str
    description: str
    suggestion: Optional[str]
    context: List[str] = field(default_factory=list)


class ErrorDetector:
    """
    Detects and categorizes errors from log lines.
    
    Uses regex pattern matching to identify known error types
    and provide helpful fix suggestions.
    """
    
    def __init__(self, patterns_file: Optional[Path] = None):
        self.patterns: List[ErrorPattern] = []
        self._load_builtin_patterns()
        
        if patterns_file and patterns_file.exists():
            self._load_patterns_from_file(patterns_file)
    
    def _load_builtin_patterns(self):
        """Load built-in error patterns"""
        builtin = [
            # Redscript errors
            ErrorPattern(
                id="reds_syntax_error",
                regex=r"(?:syntax\s+)?error.*\.reds.*line\s+(\d+)",
                category=ErrorCategory.REDSCRIPT,
                severity=LogLevel.ERROR,
                title="Redscript Syntax Error",
                description="Syntax error in redscript file at line {1}",
                suggestion="Check the redscript file for syntax errors at the specified line",
                extract_groups=["line"]
            ),
            ErrorPattern(
                id="reds_undefined",
                regex=r"undefined\s+(?:function|class|variable|type)\s+['\"]?(\w+)['\"]?",
                category=ErrorCategory.REDSCRIPT,
                severity=LogLevel.ERROR,
                title="Undefined Reference",
                description="Undefined reference to '{1}'",
                suggestion="Check if the function/class/variable '{1}' is properly imported or defined",
                extract_groups=["name"]
            ),
            ErrorPattern(
                id="reds_compile_failed",
                regex=r"(?:redscript|scc)\s+compilation?\s+failed",
                category=ErrorCategory.REDSCRIPT,
                severity=LogLevel.ERROR,
                title="Redscript Compilation Failed",
                description="Redscript compilation failed",
                suggestion="Check redscript.log for detailed error messages"
            ),
            
            # Plugin errors
            ErrorPattern(
                id="plugin_load_failed",
                regex=r"failed\s+to\s+load\s+(?:plugin|module)\s+['\"]?([^'\"]+)['\"]?",
                category=ErrorCategory.PLUGIN,
                severity=LogLevel.ERROR,
                title="Plugin Load Failed",
                description="Failed to load plugin '{1}'",
                suggestion="Check if the plugin is properly installed and compatible with your game version",
                extract_groups=["plugin"]
            ),
            ErrorPattern(
                id="plugin_missing_dep",
                regex=r"(?:missing|cannot\s+find)\s+(?:dependency|library)\s+['\"]?([^'\"]+)['\"]?",
                category=ErrorCategory.PLUGIN,
                severity=LogLevel.ERROR,
                title="Missing Dependency",
                description="Missing dependency '{1}'",
                suggestion="Install the required dependency or reinstall the plugin",
                extract_groups=["dep"]
            ),
            ErrorPattern(
                id="plugin_api_mismatch",
                regex=r"(?:api|version)\s+(?:mismatch|incompatible)",
                category=ErrorCategory.PLUGIN,
                severity=LogLevel.ERROR,
                title="API Version Mismatch",
                description="Plugin API version mismatch",
                suggestion="Update the plugin to a version compatible with your RED4ext"
            ),
            ErrorPattern(
                id="dylib_signature",
                regex=r"(?:code\s+signature|codesign)\s+(?:invalid|failed)",
                category=ErrorCategory.PLUGIN,
                severity=LogLevel.ERROR,
                title="Code Signature Invalid",
                description="Plugin dylib has invalid code signature",
                suggestion="Run 'codesign -s - <path>' to ad-hoc sign the plugin"
            ),
            
            # TweakXL errors
            ErrorPattern(
                id="tweak_parse_error",
                regex=r"(?:yaml|tweak)\s+(?:parse|syntax)\s+error.*?['\"]?([^'\"]+\.ya?ml)['\"]?",
                category=ErrorCategory.TWEAK,
                severity=LogLevel.ERROR,
                title="Tweak Parse Error",
                description="Failed to parse tweak file '{1}'",
                suggestion="Check YAML syntax in the specified file",
                extract_groups=["file"]
            ),
            ErrorPattern(
                id="tweak_invalid_value",
                regex=r"invalid\s+(?:value|type)\s+(?:for|in)\s+['\"]?(\w+)['\"]?",
                category=ErrorCategory.TWEAK,
                severity=LogLevel.ERROR,
                title="Invalid Tweak Value",
                description="Invalid value for tweak '{1}'",
                suggestion="Check the expected value type for this tweak",
                extract_groups=["tweak"]
            ),
            
            # ArchiveXL errors
            ErrorPattern(
                id="archive_not_found",
                regex=r"(?:archive|resource)\s+not\s+found.*?['\"]?([^'\"]+)['\"]?",
                category=ErrorCategory.ARCHIVE,
                severity=LogLevel.ERROR,
                title="Archive Not Found",
                description="Archive or resource not found: '{1}'",
                suggestion="Check if the archive file exists and is properly installed",
                extract_groups=["archive"]
            ),
            ErrorPattern(
                id="archive_corrupt",
                regex=r"(?:archive|resource)\s+(?:corrupt|invalid|damaged)",
                category=ErrorCategory.ARCHIVE,
                severity=LogLevel.ERROR,
                title="Corrupt Archive",
                description="Archive file is corrupt or invalid",
                suggestion="Re-download and reinstall the mod"
            ),
            
            # Framework errors
            ErrorPattern(
                id="red4ext_init_failed",
                regex=r"red4ext\s+(?:initialization|init)\s+failed",
                category=ErrorCategory.FRAMEWORK,
                severity=LogLevel.ERROR,
                title="RED4ext Init Failed",
                description="RED4ext failed to initialize",
                suggestion="Check if RED4ext is properly installed and the game is compatible"
            ),
            ErrorPattern(
                id="hook_failed",
                regex=r"(?:hook|detour)\s+(?:failed|error)",
                category=ErrorCategory.FRAMEWORK,
                severity=LogLevel.ERROR,
                title="Hook Failed",
                description="Failed to install function hook",
                suggestion="This may indicate a game version mismatch or conflict with another mod"
            ),
            ErrorPattern(
                id="frida_error",
                regex=r"frida.*(?:error|failed)",
                category=ErrorCategory.FRAMEWORK,
                severity=LogLevel.ERROR,
                title="Frida Error",
                description="Frida Gadget error",
                suggestion="Check if FridaGadget.dylib is properly configured"
            ),
            
            # General warnings
            ErrorPattern(
                id="deprecation_warning",
                regex=r"deprecat(?:ed|ion).*?['\"]?(\w+)['\"]?",
                category=ErrorCategory.UNKNOWN,
                severity=LogLevel.WARNING,
                title="Deprecation Warning",
                description="Deprecated feature usage: '{1}'",
                suggestion="Update the mod to use the newer API",
                extract_groups=["feature"]
            ),
            ErrorPattern(
                id="performance_warning",
                regex=r"(?:performance|slow|lag)\s+(?:warning|issue)",
                category=ErrorCategory.GAME,
                severity=LogLevel.WARNING,
                title="Performance Warning",
                description="Performance issue detected",
                suggestion="Consider disabling some mods or adjusting game settings"
            ),
        ]
        
        self.patterns.extend(builtin)
        
        # Compile all patterns
        for pattern in self.patterns:
            pattern.compile()
    
    def _load_patterns_from_file(self, file_path: Path):
        """Load patterns from JSON file"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            for p in data.get('patterns', []):
                pattern = ErrorPattern(
                    id=p['id'],
                    regex=p['regex'],
                    category=ErrorCategory(p.get('category', 'unknown')),
                    severity=LogLevel(p.get('severity', 'error')),
                    title=p['title'],
                    description=p['description'],
                    suggestion=p.get('suggestion'),
                    extract_groups=p.get('extract_groups', [])
                )
                pattern.compile()
                self.patterns.append(pattern)
        except Exception as e:
            print(f"Error loading patterns from {file_path}: {e}")
    
    def detect(self, log_line: LogLine) -> List[DetectedError]:
        """
        Detect errors in a log line.
        
        Args:
            log_line: The log line to analyze
            
        Returns:
            List of detected errors
        """
        errors = []
        
        for pattern in self.patterns:
            match = pattern._compiled.search(log_line.message)
            if match:
                # Extract groups
                groups = {}
                if match.groups():
                    for i, group in enumerate(match.groups(), 1):
                        groups[str(i)] = group or ""
                        if i <= len(pattern.extract_groups):
                            groups[pattern.extract_groups[i-1]] = group or ""
                
                # Format description and suggestion
                description = pattern.description
                suggestion = pattern.suggestion
                
                for key, value in groups.items():
                    description = description.replace(f"{{{key}}}", value)
                    if suggestion:
                        suggestion = suggestion.replace(f"{{{key}}}", value)
                
                errors.append(DetectedError(
                    pattern=pattern,
                    log_line=log_line,
                    match_groups=groups,
                    title=pattern.title,
                    description=description,
                    suggestion=suggestion
                ))
        
        return errors
    
    def detect_in_batch(self, log_lines: List[LogLine]) -> List[DetectedError]:
        """Detect errors in a batch of log lines"""
        all_errors = []
        for line in log_lines:
            errors = self.detect(line)
            all_errors.extend(errors)
        return all_errors
    
    def get_error_summary(self, errors: List[DetectedError]) -> Dict[str, Any]:
        """Get summary statistics of detected errors"""
        by_category = {}
        by_severity = {}
        
        for error in errors:
            cat = error.pattern.category.value
            sev = error.pattern.severity.value
            
            by_category[cat] = by_category.get(cat, 0) + 1
            by_severity[sev] = by_severity.get(sev, 0) + 1
        
        return {
            "total": len(errors),
            "by_category": by_category,
            "by_severity": by_severity,
            "unique_patterns": len(set(e.pattern.id for e in errors))
        }
