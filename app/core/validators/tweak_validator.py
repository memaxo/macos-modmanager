"""
TweakXL Tweak Validator

Validates .yaml/.yml tweak files for syntax errors.
"""

import re
from pathlib import Path
from typing import List

from app.core.validation_engine import (
    Validator,
    ValidationCheckResult,
    ValidationIssue,
    ValidationCategory,
    ValidationSeverity,
)


class TweakValidator(Validator):
    """
    Validates TweakXL tweak files (.yaml/.yml).
    
    Checks for:
    - YAML syntax errors
    - Invalid tweak structure
    - Common mistakes
    """
    
    name = "TweakXL Tweaks"
    category = ValidationCategory.TWEAK
    
    async def validate(self, game_path: Path) -> ValidationCheckResult:
        issues: List[ValidationIssue] = []
        files_checked = 0
        
        tweaks_dir = game_path / "r6" / "tweaks"
        
        if not tweaks_dir.exists():
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=True,
                message="No tweaks directory (OK if no TweakXL mods)",
                issues=[]
            )
        
        # Find all yaml files
        yaml_files = list(tweaks_dir.rglob("*.yaml")) + list(tweaks_dir.rglob("*.yml"))
        
        if not yaml_files:
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=True,
                message="No tweak files found",
                issues=[]
            )
        
        for yaml_file in yaml_files:
            try:
                content = yaml_file.read_text(encoding='utf-8', errors='ignore')
                file_issues = self._check_yaml(yaml_file, content)
                issues.extend(file_issues)
                files_checked += 1
            except Exception as e:
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    f"Could Not Read: {yaml_file.name}",
                    str(e),
                    file_path=str(yaml_file)
                ))
        
        error_count = sum(1 for i in issues if i.severity == ValidationSeverity.ERROR)
        passed = error_count == 0
        
        return ValidationCheckResult(
            name=self.name,
            category=self.category,
            passed=passed,
            message=f"Checked {files_checked} tweak files" if passed else f"Found {error_count} errors in tweaks",
            issues=issues
        )
    
    def _check_yaml(self, file_path: Path, content: str) -> List[ValidationIssue]:
        """Check a YAML file for issues"""
        issues = []
        lines = content.split('\n')
        
        # Try to parse with PyYAML if available
        try:
            import yaml
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                # Extract line number if available
                line_num = None
                if hasattr(e, 'problem_mark') and e.problem_mark:
                    line_num = e.problem_mark.line + 1
                
                issues.append(self.create_issue(
                    ValidationSeverity.ERROR,
                    f"YAML Syntax Error: {file_path.name}",
                    str(e),
                    file_path=str(file_path),
                    line_number=line_num
                ))
                return issues
        except ImportError:
            # PyYAML not available, do basic checks
            pass
        
        # Basic syntax checks
        indent_stack = [0]
        prev_indent = 0
        
        for line_num, line in enumerate(lines, 1):
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                continue
            
            # Check indentation
            indent = len(line) - len(line.lstrip())
            
            # Check for tabs (YAML prefers spaces)
            if '\t' in line:
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    "Tab Character Found",
                    "YAML files should use spaces, not tabs",
                    file_path=str(file_path),
                    line_number=line_num,
                    suggestion="Replace tabs with spaces"
                ))
            
            # Check for inconsistent indentation
            if indent > prev_indent and (indent - prev_indent) not in [2, 4]:
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    "Inconsistent Indentation",
                    f"Unexpected indent increase of {indent - prev_indent} spaces",
                    file_path=str(file_path),
                    line_number=line_num,
                    suggestion="Use consistent 2 or 4 space indentation"
                ))
            
            prev_indent = indent
            
            # Check for common YAML mistakes
            stripped = line.strip()
            
            # Missing colon after key
            if re.match(r'^[\w\.\$]+\s+\w', stripped) and ':' not in stripped:
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    "Possible Missing Colon",
                    "Line may be missing ':' after key",
                    file_path=str(file_path),
                    line_number=line_num,
                    suggestion="Add ':' after the key name"
                ))
            
            # Unquoted special characters
            if re.search(r':\s*[{}\[\]&*!|>]', stripped):
                # This might be intentional, but warn
                pass
        
        return issues
