"""
FOMOD Installer Parser

Parses FOMOD installer XML files (info.xml and ModuleConfig.xml) to extract
mod installation options, steps, groups, and file mappings.

FOMOD spec: https://stepmodifications.org/wiki/Guide:FOMOD
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class GroupType(Enum):
    """FOMOD group selection types"""
    SELECT_EXACTLY_ONE = "SelectExactlyOne"
    SELECT_AT_MOST_ONE = "SelectAtMostOne"
    SELECT_AT_LEAST_ONE = "SelectAtLeastOne"
    SELECT_ALL = "SelectAll"
    SELECT_ANY = "SelectAny"


class PluginType(Enum):
    """FOMOD plugin type descriptors"""
    REQUIRED = "Required"
    OPTIONAL = "Optional"
    RECOMMENDED = "Recommended"
    NOT_USABLE = "NotUsable"
    COULD_BE_USABLE = "CouldBeUsable"


class ConditionOperator(Enum):
    """Operators for combining conditions"""
    AND = "And"
    OR = "Or"


@dataclass
class FomodFileMapping:
    """Represents a file/folder to be installed"""
    source: str
    destination: str
    priority: int = 0
    is_folder: bool = False
    always_install: bool = False
    install_if_usable: bool = False


@dataclass
class FomodConditionFlag:
    """A condition flag that can be set by plugins"""
    name: str
    value: str


@dataclass
class FomodCondition:
    """Represents a condition for visibility or file installation"""
    flag_name: Optional[str] = None
    flag_value: Optional[str] = None
    file_path: Optional[str] = None
    game_version: Optional[str] = None
    operator: ConditionOperator = ConditionOperator.AND
    sub_conditions: List["FomodCondition"] = field(default_factory=list)
    
    def evaluate(self, flags: Dict[str, str], installed_files: List[str] = None) -> bool:
        """Evaluate this condition against current flags and files"""
        results = []
        
        # Check flag condition
        if self.flag_name is not None:
            current_value = flags.get(self.flag_name, "")
            results.append(current_value == self.flag_value)
        
        # Check file condition
        if self.file_path is not None and installed_files is not None:
            results.append(self.file_path in installed_files)
        
        # Evaluate sub-conditions
        for sub in self.sub_conditions:
            results.append(sub.evaluate(flags, installed_files))
        
        if not results:
            return True
        
        if self.operator == ConditionOperator.AND:
            return all(results)
        else:
            return any(results)


@dataclass
class FomodPlugin:
    """Represents a selectable option/plugin in a group"""
    name: str
    description: str = ""
    image: Optional[str] = None
    files: List[FomodFileMapping] = field(default_factory=list)
    condition_flags: List[FomodConditionFlag] = field(default_factory=list)
    type_descriptor: PluginType = PluginType.OPTIONAL
    condition: Optional[FomodCondition] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "description": self.description,
            "image": self.image,
            "type": self.type_descriptor.value,
            "has_files": len(self.files) > 0
        }


@dataclass
class FomodGroup:
    """Represents a group of plugins within a step"""
    name: str
    type: GroupType = GroupType.SELECT_ANY
    plugins: List[FomodPlugin] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "type": self.type.value,
            "plugins": [p.to_dict() for p in self.plugins],
            "is_radio": self.type in [GroupType.SELECT_EXACTLY_ONE, GroupType.SELECT_AT_MOST_ONE],
            "is_required": self.type in [GroupType.SELECT_EXACTLY_ONE, GroupType.SELECT_AT_LEAST_ONE],
            "allow_none": self.type == GroupType.SELECT_AT_MOST_ONE,
            "select_all": self.type == GroupType.SELECT_ALL
        }


@dataclass
class FomodStep:
    """Represents an installation step/page"""
    name: str
    groups: List[FomodGroup] = field(default_factory=list)
    visible_condition: Optional[FomodCondition] = None
    
    def is_visible(self, flags: Dict[str, str]) -> bool:
        """Check if this step should be visible"""
        if self.visible_condition is None:
            return True
        return self.visible_condition.evaluate(flags)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "groups": [g.to_dict() for g in self.groups]
        }


@dataclass
class FomodInfo:
    """Parsed info.xml data"""
    name: str = "Unknown Mod"
    author: str = ""
    version: str = ""
    description: str = ""
    website: str = ""
    groups: List[str] = field(default_factory=list)


@dataclass
class FomodConfig:
    """Complete FOMOD configuration"""
    info: FomodInfo
    module_name: str = ""
    required_files: List[FomodFileMapping] = field(default_factory=list)
    steps: List[FomodStep] = field(default_factory=list)
    conditional_file_installs: List[Tuple[FomodCondition, List[FomodFileMapping]]] = field(default_factory=list)
    fomod_path: Optional[Path] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "info": {
                "name": self.info.name,
                "author": self.info.author,
                "version": self.info.version,
                "description": self.info.description,
                "website": self.info.website
            },
            "module_name": self.module_name,
            "steps": [s.to_dict() for s in self.steps],
            "total_steps": len(self.steps),
            "has_required_files": len(self.required_files) > 0
        }


class FomodParseError(Exception):
    """Exception raised when FOMOD parsing fails"""
    pass


class FomodParser:
    """Parses FOMOD installer XML files"""
    
    def __init__(self):
        self.namespaces = {}
    
    def parse(self, fomod_dir: Path) -> FomodConfig:
        """Parse FOMOD configuration from a directory containing fomod files
        
        Args:
            fomod_dir: Path to directory containing fomod/ModuleConfig.xml
            
        Returns:
            FomodConfig with parsed data
        """
        # Find fomod directory (case insensitive)
        fomod_path = self._find_fomod_dir(fomod_dir)
        if fomod_path is None:
            raise FomodParseError(f"No fomod directory found in {fomod_dir}")
        
        # Parse info.xml
        info = self._parse_info_xml(fomod_path)
        
        # Parse ModuleConfig.xml
        config = self._parse_module_config(fomod_path, info)
        config.fomod_path = fomod_path
        
        return config
    
    def _find_fomod_dir(self, base_dir: Path) -> Optional[Path]:
        """Find the fomod directory (case insensitive)"""
        for item in base_dir.iterdir():
            if item.is_dir() and item.name.lower() == "fomod":
                return item
        return None
    
    def _parse_info_xml(self, fomod_path: Path) -> FomodInfo:
        """Parse info.xml file"""
        info = FomodInfo()
        
        info_path = fomod_path / "info.xml"
        if not info_path.exists():
            # Try case insensitive
            for f in fomod_path.iterdir():
                if f.name.lower() == "info.xml":
                    info_path = f
                    break
        
        if not info_path.exists():
            return info
        
        try:
            tree = self._parse_xml_file(info_path)
            root = tree.getroot()
            
            # Parse elements
            name_elem = root.find(".//Name") or root.find(".//name")
            if name_elem is not None and name_elem.text:
                info.name = name_elem.text.strip()
            
            author_elem = root.find(".//Author") or root.find(".//author")
            if author_elem is not None and author_elem.text:
                info.author = author_elem.text.strip()
            
            version_elem = root.find(".//Version") or root.find(".//version")
            if version_elem is not None and version_elem.text:
                info.version = version_elem.text.strip()
            
            desc_elem = root.find(".//Description") or root.find(".//description")
            if desc_elem is not None and desc_elem.text:
                info.description = desc_elem.text.strip()
            
            website_elem = root.find(".//Website") or root.find(".//website")
            if website_elem is not None and website_elem.text:
                info.website = website_elem.text.strip()
            
        except Exception as e:
            logger.warning(f"Failed to parse info.xml: {e}")
        
        return info
    
    def _parse_module_config(self, fomod_path: Path, info: FomodInfo) -> FomodConfig:
        """Parse ModuleConfig.xml file"""
        config_path = fomod_path / "ModuleConfig.xml"
        if not config_path.exists():
            # Try case insensitive
            for f in fomod_path.iterdir():
                if f.name.lower() == "moduleconfig.xml":
                    config_path = f
                    break
        
        if not config_path.exists():
            raise FomodParseError(f"ModuleConfig.xml not found in {fomod_path}")
        
        try:
            tree = self._parse_xml_file(config_path)
            root = tree.getroot()
            
            config = FomodConfig(info=info)
            
            # Parse module name
            module_name = root.find(".//moduleName")
            if module_name is not None and module_name.text:
                config.module_name = module_name.text.strip()
                if not config.info.name or config.info.name == "Unknown Mod":
                    config.info.name = config.module_name
            
            # Parse required install files
            required_files = root.find(".//requiredInstallFiles")
            if required_files is not None:
                config.required_files = self._parse_file_list(required_files)
            
            # Parse install steps
            install_steps = root.find(".//installSteps")
            if install_steps is not None:
                config.steps = self._parse_install_steps(install_steps)
            
            # Parse conditional file installs
            conditional_installs = root.find(".//conditionalFileInstalls")
            if conditional_installs is not None:
                config.conditional_file_installs = self._parse_conditional_installs(conditional_installs)
            
            return config
            
        except FomodParseError:
            raise
        except Exception as e:
            raise FomodParseError(f"Failed to parse ModuleConfig.xml: {e}")
    
    def _parse_xml_file(self, path: Path) -> ET.ElementTree:
        """Parse an XML file, handling different encodings"""
        # Try UTF-8 first (most common)
        try:
            return ET.parse(path)
        except ET.ParseError:
            pass
        
        # Try reading with explicit encoding detection
        try:
            with open(path, 'rb') as f:
                content = f.read()
            
            # Check for BOM or encoding declaration
            if content.startswith(b'\xff\xfe') or content.startswith(b'\xfe\xff'):
                # UTF-16
                text = content.decode('utf-16')
            elif b'encoding="UTF-16"' in content or b"encoding='UTF-16'" in content:
                text = content.decode('utf-16')
            else:
                # Try UTF-8 with BOM
                text = content.decode('utf-8-sig')
            
            return ET.ElementTree(ET.fromstring(text))
        except Exception as e:
            raise FomodParseError(f"Failed to parse XML file {path}: {e}")
    
    def _parse_file_list(self, element: ET.Element) -> List[FomodFileMapping]:
        """Parse a list of file/folder elements"""
        files = []
        
        for child in element:
            tag = child.tag.lower()
            if tag in ["file", "folder"]:
                source = child.get("source", "")
                destination = child.get("destination", source)
                priority = int(child.get("priority", "0"))
                always_install = child.get("alwaysInstall", "false").lower() == "true"
                install_if_usable = child.get("installIfUsable", "false").lower() == "true"
                
                files.append(FomodFileMapping(
                    source=source,
                    destination=destination,
                    priority=priority,
                    is_folder=(tag == "folder"),
                    always_install=always_install,
                    install_if_usable=install_if_usable
                ))
        
        return files
    
    def _parse_install_steps(self, element: ET.Element) -> List[FomodStep]:
        """Parse installSteps element"""
        steps = []
        
        for step_elem in element.findall(".//installStep"):
            step_name = step_elem.get("name", "Installation")
            step = FomodStep(name=step_name)
            
            # Parse visibility condition
            visible = step_elem.find("visible")
            if visible is not None:
                step.visible_condition = self._parse_condition(visible)
            
            # Parse option groups
            groups_elem = step_elem.find("optionalFileGroups")
            if groups_elem is not None:
                step.groups = self._parse_groups(groups_elem)
            
            steps.append(step)
        
        return steps
    
    def _parse_groups(self, element: ET.Element) -> List[FomodGroup]:
        """Parse optionalFileGroups element"""
        groups = []
        
        for group_elem in element.findall("group"):
            group_name = group_elem.get("name", "Options")
            group_type_str = group_elem.get("type", "SelectAny")
            
            # Parse group type
            try:
                group_type = GroupType(group_type_str)
            except ValueError:
                group_type = GroupType.SELECT_ANY
            
            group = FomodGroup(name=group_name, type=group_type)
            
            # Parse plugins
            plugins_elem = group_elem.find("plugins")
            if plugins_elem is not None:
                group.plugins = self._parse_plugins(plugins_elem)
            
            groups.append(group)
        
        return groups
    
    def _parse_plugins(self, element: ET.Element) -> List[FomodPlugin]:
        """Parse plugins element"""
        plugins = []
        
        for plugin_elem in element.findall("plugin"):
            plugin_name = plugin_elem.get("name", "Option")
            plugin = FomodPlugin(name=plugin_name)
            
            # Parse description
            desc_elem = plugin_elem.find("description")
            if desc_elem is not None and desc_elem.text:
                plugin.description = desc_elem.text.strip()
            
            # Parse image
            image_elem = plugin_elem.find("image")
            if image_elem is not None:
                plugin.image = image_elem.get("path")
            
            # Parse type descriptor
            type_elem = plugin_elem.find("typeDescriptor")
            if type_elem is not None:
                type_dep = type_elem.find("type")
                if type_dep is not None:
                    type_name = type_dep.get("name", "Optional")
                    try:
                        plugin.type_descriptor = PluginType(type_name)
                    except ValueError:
                        plugin.type_descriptor = PluginType.OPTIONAL
            
            # Parse files
            files_elem = plugin_elem.find("files")
            if files_elem is not None:
                plugin.files = self._parse_file_list(files_elem)
            
            # Parse condition flags (flags this plugin sets when selected)
            flags_elem = plugin_elem.find("conditionFlags")
            if flags_elem is not None:
                plugin.condition_flags = self._parse_condition_flags(flags_elem)
            
            plugins.append(plugin)
        
        return plugins
    
    def _parse_condition_flags(self, element: ET.Element) -> List[FomodConditionFlag]:
        """Parse conditionFlags element"""
        flags = []
        
        for flag_elem in element.findall("flag"):
            name = flag_elem.get("name", "")
            value = flag_elem.text or ""
            if name:
                flags.append(FomodConditionFlag(name=name, value=value.strip()))
        
        return flags
    
    def _parse_condition(self, element: ET.Element) -> Optional[FomodCondition]:
        """Parse a condition element (visible, dependencies, etc.)"""
        # Check for composite conditions
        for composite_tag in ["dependencies", "moduleDependencies"]:
            deps = element.find(composite_tag)
            if deps is not None:
                return self._parse_composite_condition(deps)
        
        # Check for flag dependencies
        flag_deps = element.find("flagDependency")
        if flag_deps is not None:
            return FomodCondition(
                flag_name=flag_deps.get("flag"),
                flag_value=flag_deps.get("value")
            )
        
        return None
    
    def _parse_composite_condition(self, element: ET.Element) -> FomodCondition:
        """Parse a composite condition with multiple sub-conditions"""
        operator_str = element.get("operator", "And")
        try:
            operator = ConditionOperator(operator_str)
        except ValueError:
            operator = ConditionOperator.AND
        
        condition = FomodCondition(operator=operator)
        
        # Parse flag dependencies
        for flag_dep in element.findall("flagDependency"):
            sub_condition = FomodCondition(
                flag_name=flag_dep.get("flag"),
                flag_value=flag_dep.get("value")
            )
            condition.sub_conditions.append(sub_condition)
        
        # Parse file dependencies
        for file_dep in element.findall("fileDependency"):
            sub_condition = FomodCondition(
                file_path=file_dep.get("file")
            )
            condition.sub_conditions.append(sub_condition)
        
        # Parse nested dependencies
        for nested_deps in element.findall("dependencies"):
            nested = self._parse_composite_condition(nested_deps)
            condition.sub_conditions.append(nested)
        
        return condition
    
    def _parse_conditional_installs(
        self, 
        element: ET.Element
    ) -> List[Tuple[FomodCondition, List[FomodFileMapping]]]:
        """Parse conditionalFileInstalls element"""
        result = []
        
        patterns = element.find("patterns")
        if patterns is None:
            return result
        
        for pattern in patterns.findall("pattern"):
            deps = pattern.find("dependencies")
            files = pattern.find("files")
            
            if deps is not None and files is not None:
                condition = self._parse_composite_condition(deps)
                file_list = self._parse_file_list(files)
                result.append((condition, file_list))
        
        return result
    
    def resolve_files(
        self,
        config: FomodConfig,
        choices: Dict[str, Any],
        base_dir: Path
    ) -> List[Tuple[Path, Path]]:
        """Resolve which files to install based on user choices
        
        Args:
            config: The parsed FOMOD configuration
            choices: User choices in the format:
                {
                    "type": "fomod",
                    "options": [
                        {
                            "name": "Step Name",
                            "groups": [
                                {
                                    "name": "Group Name",
                                    "choices": [
                                        {"name": "Plugin Name", "idx": 0}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            base_dir: Base directory containing extracted mod files
        
        Returns:
            List of (source_path, destination_path) tuples
        """
        files_to_install: List[Tuple[Path, Path]] = []
        flags: Dict[str, str] = {}
        
        # Always install required files
        for file_mapping in config.required_files:
            source = base_dir / file_mapping.source
            dest_path = file_mapping.destination
            if source.exists():
                files_to_install.append((source, Path(dest_path)))
        
        # Process choices
        options = choices.get("options", [])
        
        for step_idx, step in enumerate(config.steps):
            if step_idx >= len(options):
                continue
            
            step_choices = options[step_idx]
            
            for group in step.groups:
                # Find matching group in choices
                group_choices = None
                for g in step_choices.get("groups", []):
                    if g.get("name") == group.name:
                        group_choices = g
                        break
                
                if group_choices is None:
                    continue
                
                selected_plugins = group_choices.get("choices", [])
                
                for selected in selected_plugins:
                    plugin_idx = selected.get("idx", 0)
                    if plugin_idx < len(group.plugins):
                        plugin = group.plugins[plugin_idx]
                        
                        # Set condition flags
                        for flag in plugin.condition_flags:
                            flags[flag.name] = flag.value
                        
                        # Add files from this plugin
                        for file_mapping in plugin.files:
                            source = base_dir / file_mapping.source
                            dest_path = file_mapping.destination
                            if source.exists():
                                files_to_install.append((source, Path(dest_path)))
        
        # Process conditional file installs
        for condition, file_list in config.conditional_file_installs:
            if condition.evaluate(flags):
                for file_mapping in file_list:
                    source = base_dir / file_mapping.source
                    dest_path = file_mapping.destination
                    if source.exists():
                        files_to_install.append((source, Path(dest_path)))
        
        return files_to_install


def detect_fomod(extracted_dir: Path) -> bool:
    """Check if an extracted mod directory contains a FOMOD installer"""
    for item in extracted_dir.iterdir():
        if item.is_dir() and item.name.lower() == "fomod":
            module_config = item / "ModuleConfig.xml"
            if module_config.exists():
                return True
            # Case insensitive check
            for f in item.iterdir():
                if f.name.lower() == "moduleconfig.xml":
                    return True
    return False
