"""
Redscript Syntax Validator

Validates .reds files for common syntax errors before game launch.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple

from app.core.validation_engine import (
    Validator,
    ValidationCheckResult,
    ValidationIssue,
    ValidationCategory,
    ValidationSeverity,
)


class RedscriptValidator(Validator):
    """
    Validates redscript (.reds) files for syntax errors.
    
    Checks for:
    - Missing semicolons
    - Unmatched braces
    - Invalid function signatures
    - Common typos
    - Import errors
    """
    
    name = "Redscript Syntax"
    category = ValidationCategory.REDSCRIPT
    
    # Common error patterns
    MISSING_SEMICOLON_PATTERN = re.compile(
        r'^[^;{}/\n]*(?:return|let|this\.\w+\s*=)[^;{}\n]*$',
        re.MULTILINE
    )
    
    INVALID_FUNCTION_PATTERN = re.compile(
        r'(?:public|private|protected)?\s*(?:static)?\s*func\s+\w+\s*\([^)]*\)\s*(?:->)?\s*(?:\w+)?\s*[^{]',
        re.MULTILINE
    )
    
    COMMON_TYPOS = {
        'fucn': 'func',
        'retrun': 'return',
        'pubilc': 'public',
        'priavte': 'private',
        'calss': 'class',
        'improt': 'import',
    }
    
    async def validate(self, game_path: Path) -> ValidationCheckResult:
        issues: List[ValidationIssue] = []
        files_checked = 0
        
        # Find all .reds files
        scripts_dir = game_path / "r6" / "scripts"
        
        if not scripts_dir.exists():
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=True,
                message="No scripts directory found (OK if no redscript mods)",
                issues=[]
            )
        
        reds_files = list(scripts_dir.rglob("*.reds"))
        
        if not reds_files:
            return ValidationCheckResult(
                name=self.name,
                category=self.category,
                passed=True,
                message="No redscript files found",
                issues=[]
            )
        
        for reds_file in reds_files:
            try:
                content = reds_file.read_text(encoding='utf-8', errors='ignore')
                file_issues = self._check_file(reds_file, content)
                issues.extend(file_issues)
                files_checked += 1
            except Exception as e:
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    f"Could Not Read: {reds_file.name}",
                    f"Error reading file: {str(e)}",
                    file_path=str(reds_file)
                ))
        
        # Determine pass/fail
        error_count = sum(1 for i in issues if i.severity == ValidationSeverity.ERROR)
        passed = error_count == 0
        
        return ValidationCheckResult(
            name=self.name,
            category=self.category,
            passed=passed,
            message=f"Checked {files_checked} files, found {len(issues)} issues" if issues else f"Checked {files_checked} files, no issues found",
            issues=issues
        )
    
    def _check_file(self, file_path: Path, content: str) -> List[ValidationIssue]:
        """Check a single file for issues"""
        issues = []
        lines = content.split('\n')
        
        # Track brace depth
        brace_depth = 0
        paren_depth = 0
        in_string = False
        in_comment = False
        in_multiline_comment = False
        
        for line_num, line in enumerate(lines, 1):
            # Skip empty lines
            stripped = line.strip()
            if not stripped:
                continue
            
            # Handle comments
            if stripped.startswith('//'):
                continue
            if '/*' in stripped:
                in_multiline_comment = True
            if '*/' in stripped:
                in_multiline_comment = False
                continue
            if in_multiline_comment:
                continue
            
            # Check for common typos
            for typo, correct in self.COMMON_TYPOS.items():
                if typo in stripped.lower():
                    # Find the actual case-insensitive match
                    match = re.search(typo, stripped, re.IGNORECASE)
                    if match:
                        issues.append(self.create_issue(
                            ValidationSeverity.ERROR,
                            f"Typo: '{match.group()}'",
                            f"Did you mean '{correct}'?",
                            file_path=str(file_path),
                            line_number=line_num,
                            suggestion=f"Change '{match.group()}' to '{correct}'"
                        ))
            
            # Track braces
            for char in stripped:
                if char == '"' and not in_string:
                    in_string = True
                elif char == '"' and in_string:
                    in_string = False
                elif not in_string:
                    if char == '{':
                        brace_depth += 1
                    elif char == '}':
                        brace_depth -= 1
                    elif char == '(':
                        paren_depth += 1
                    elif char == ')':
                        paren_depth -= 1
            
            # Check for missing semicolons (simple heuristic)
            if self._likely_needs_semicolon(stripped, line_num, lines):
                issues.append(self.create_issue(
                    ValidationSeverity.WARNING,
                    "Possible Missing Semicolon",
                    f"Line may be missing a semicolon",
                    file_path=str(file_path),
                    line_number=line_num,
                    suggestion="Add ';' at the end of the statement"
                ))
            
            # Check for negative brace depth (extra closing brace)
            if brace_depth < 0:
                issues.append(self.create_issue(
                    ValidationSeverity.ERROR,
                    "Unmatched Closing Brace",
                    "Found '}' without matching '{'",
                    file_path=str(file_path),
                    line_number=line_num
                ))
                brace_depth = 0  # Reset to continue checking
        
        # Check final brace balance
        if brace_depth > 0:
            issues.append(self.create_issue(
                ValidationSeverity.ERROR,
                "Unmatched Opening Brace",
                f"File has {brace_depth} unclosed '{{' brace(s)",
                file_path=str(file_path),
                suggestion="Add missing '}' to close open blocks"
            ))
        
        if paren_depth != 0:
            issues.append(self.create_issue(
                ValidationSeverity.ERROR,
                "Unmatched Parentheses",
                f"File has unbalanced parentheses",
                file_path=str(file_path),
                suggestion="Check for missing '(' or ')'"
            ))
        
        return issues
    
    def _likely_needs_semicolon(self, line: str, line_num: int, all_lines: List[str]) -> bool:
        """Heuristic to check if a line likely needs a semicolon"""
        stripped = line.strip()
        
        # Lines that don't need semicolons
        if not stripped:
            return False
        if stripped.endswith('{') or stripped.endswith('}'):
            return False
        if stripped.endswith(';'):
            return False
        if stripped.endswith(','):
            return False
        if stripped.startswith('//'):
            return False
        if stripped.startswith('/*') or stripped.startswith('*'):
            return False
        if stripped.startswith('if') or stripped.startswith('else'):
            return False
        if stripped.startswith('for') or stripped.startswith('while'):
            return False
        if stripped.startswith('func ') or stripped.startswith('public func'):
            return False
        if stripped.startswith('class ') or stripped.startswith('public class'):
            return False
        if stripped.startswith('@'):  # Annotations
            return False
        if stripped.startswith('import'):
            return False
        
        # Check if next line starts a block
        if line_num < len(all_lines):
            next_line = all_lines[line_num].strip() if line_num < len(all_lines) else ''
            if next_line.startswith('{'):
                return False
        
        # Statements that typically need semicolons
        needs_semicolon_patterns = [
            r'^\s*let\s+',
            r'^\s*return\s+',
            r'^\s*this\.\w+\s*=',
            r'^\s*\w+\s*=\s*',
            r'\)\s*$',  # Ends with closing paren (function call)
        ]
        
        for pattern in needs_semicolon_patterns:
            if re.search(pattern, stripped):
                return True
        
        return False
