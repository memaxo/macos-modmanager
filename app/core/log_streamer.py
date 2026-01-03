"""
Log Streaming Service

Provides real-time log streaming via Server-Sent Events (SSE).
Watches multiple log files and streams new lines to clients.
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import deque

from app.core.game_detector import detect_game_installations
from app.config import settings


class LogLevel(str, Enum):
    """Log severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogSource(str, Enum):
    """Log sources"""
    RED4EXT = "red4ext"
    TWEAKXL = "tweakxl"
    ARCHIVEXL = "archivexl"
    REDSCRIPT = "redscript"
    GAME = "game"
    UNKNOWN = "unknown"


@dataclass
class LogLine:
    """A parsed log line"""
    timestamp: datetime
    level: LogLevel
    source: LogSource
    message: str
    raw: str
    file_path: str
    line_number: int


@dataclass
class LogFilters:
    """Filters for log streaming"""
    levels: Optional[Set[LogLevel]] = None
    sources: Optional[Set[LogSource]] = None
    search: Optional[str] = None


class LogFileWatcher:
    """Watches a single log file for changes"""
    
    def __init__(self, file_path: Path, source: LogSource):
        self.file_path = file_path
        self.source = source
        self._last_position = 0
        self._last_size = 0
        self._line_number = 0
    
    def check_for_new_lines(self) -> List[LogLine]:
        """Check for new lines in the file"""
        lines = []
        
        if not self.file_path.exists():
            return lines
        
        try:
            current_size = self.file_path.stat().st_size
            
            # Check for log rotation (file got smaller)
            if current_size < self._last_size:
                self._last_position = 0
                self._line_number = 0
            
            self._last_size = current_size
            
            if current_size <= self._last_position:
                return lines
            
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self._last_position)
                new_content = f.read()
                self._last_position = f.tell()
            
            for raw_line in new_content.split('\n'):
                if raw_line.strip():
                    self._line_number += 1
                    parsed = self._parse_line(raw_line)
                    lines.append(parsed)
        
        except Exception:
            pass
        
        return lines
    
    def _parse_line(self, raw: str) -> LogLine:
        """Parse a raw log line"""
        level = LogLevel.INFO
        timestamp = datetime.now()
        
        # Detect log level from content
        raw_lower = raw.lower()
        if '[error]' in raw_lower or 'error:' in raw_lower:
            level = LogLevel.ERROR
        elif '[warn]' in raw_lower or 'warning:' in raw_lower:
            level = LogLevel.WARNING
        elif '[debug]' in raw_lower:
            level = LogLevel.DEBUG
        
        # Try to extract timestamp
        # Common format: [2024-01-15 10:30:45]
        import re
        ts_match = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]', raw)
        if ts_match:
            try:
                timestamp = datetime.strptime(ts_match.group(1), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        
        return LogLine(
            timestamp=timestamp,
            level=level,
            source=self.source,
            message=raw.strip(),
            raw=raw,
            file_path=str(self.file_path),
            line_number=self._line_number
        )


class LogStreamer:
    """
    Streams logs from multiple sources via Server-Sent Events.
    
    Features:
    - Real-time log streaming
    - Multiple log file watching
    - Log rotation handling
    - Buffer for late joiners
    """
    
    BUFFER_SIZE = 100  # Keep last N lines for late joiners
    
    def __init__(self, game_path: Optional[Path] = None):
        self.game_path = game_path
        self._watchers: Dict[str, LogFileWatcher] = {}
        self._buffer: deque[LogLine] = deque(maxlen=self.BUFFER_SIZE)
        self._running = False
    
    async def _get_game_path(self) -> Optional[Path]:
        """Get game path if not set"""
        if self.game_path:
            return self.game_path
        
        installations = await detect_game_installations()
        if installations:
            self.game_path = Path(installations[0]['path'])
        
        return self.game_path
    
    def _setup_watchers(self):
        """Set up file watchers for all log files"""
        if not self.game_path:
            return
        
        log_files = {
            # RED4ext logs
            self.game_path / "red4ext" / "logs" / "red4ext.log": LogSource.RED4EXT,
            self.game_path / "red4ext" / "red4ext.log": LogSource.RED4EXT,
            
            # Plugin logs
            self.game_path / "red4ext" / "plugins" / "TweakXL" / "TweakXL.log": LogSource.TWEAKXL,
            self.game_path / "red4ext" / "plugins" / "ArchiveXL" / "ArchiveXL.log": LogSource.ARCHIVEXL,
            
            # Redscript logs
            self.game_path / "r6" / "logs" / "redscript.log": LogSource.REDSCRIPT,
            self.game_path / "r6" / "cache" / "redscript.log": LogSource.REDSCRIPT,
        }
        
        for file_path, source in log_files.items():
            if file_path.exists() or file_path.parent.exists():
                self._watchers[str(file_path)] = LogFileWatcher(file_path, source)
    
    async def stream(
        self, 
        filters: Optional[LogFilters] = None,
        include_buffer: bool = True
    ) -> AsyncGenerator[LogLine, None]:
        """
        Stream log lines as they appear.
        
        Args:
            filters: Optional filters to apply
            include_buffer: Whether to include buffered lines first
            
        Yields:
            LogLine objects as they appear
        """
        await self._get_game_path()
        self._setup_watchers()
        self._running = True
        
        # First, yield buffered lines if requested
        if include_buffer:
            for line in self._buffer:
                if self._matches_filters(line, filters):
                    yield line
        
        # Then stream new lines
        while self._running:
            for watcher in self._watchers.values():
                new_lines = watcher.check_for_new_lines()
                for line in new_lines:
                    self._buffer.append(line)
                    if self._matches_filters(line, filters):
                        yield line
            
            # Small delay to prevent busy-waiting
            await asyncio.sleep(0.1)
    
    def _matches_filters(self, line: LogLine, filters: Optional[LogFilters]) -> bool:
        """Check if a line matches the given filters"""
        if not filters:
            return True
        
        if filters.levels and line.level not in filters.levels:
            return False
        
        if filters.sources and line.source not in filters.sources:
            return False
        
        if filters.search and filters.search.lower() not in line.message.lower():
            return False
        
        return True
    
    async def get_recent(self, lines: int = 100) -> List[LogLine]:
        """
        Get recent log lines from all sources.
        
        Args:
            lines: Maximum number of lines to return
            
        Returns:
            List of recent LogLine objects
        """
        await self._get_game_path()
        self._setup_watchers()
        
        all_lines: List[LogLine] = []
        
        # Check all watchers for current content
        for watcher in self._watchers.values():
            if watcher.file_path.exists():
                try:
                    content = watcher.file_path.read_text(encoding='utf-8', errors='ignore')
                    for i, raw_line in enumerate(content.split('\n')[-lines:], 1):
                        if raw_line.strip():
                            all_lines.append(watcher._parse_line(raw_line))
                except Exception:
                    pass
        
        # Sort by timestamp and return last N
        all_lines.sort(key=lambda x: x.timestamp)
        return all_lines[-lines:]
    
    async def get_errors_only(self, lines: int = 50) -> List[LogLine]:
        """Get only error log lines"""
        recent = await self.get_recent(lines * 10)  # Get more to filter
        errors = [l for l in recent if l.level == LogLevel.ERROR]
        return errors[-lines:]
    
    def stop(self):
        """Stop the log streamer"""
        self._running = False
    
    async def clear_logs(self):
        """Clear all log files"""
        await self._get_game_path()
        
        if not self.game_path:
            return
        
        log_dirs = [
            self.game_path / "red4ext" / "logs",
            self.game_path / "r6" / "logs",
            self.game_path / "r6" / "cache",
        ]
        
        for log_dir in log_dirs:
            if log_dir.exists():
                for log_file in log_dir.glob("*.log"):
                    try:
                        log_file.write_text("")
                    except Exception:
                        pass
        
        # Clear buffer
        self._buffer.clear()
        
        # Reset watchers
        for watcher in self._watchers.values():
            watcher._last_position = 0
            watcher._last_size = 0
            watcher._line_number = 0


async def get_log_file_paths(game_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Get list of log files and their status"""
    if not game_path:
        installations = await detect_game_installations()
        if installations:
            game_path = Path(installations[0]['path'])
        else:
            return []
    
    log_locations = [
        ("RED4ext Main", game_path / "red4ext" / "logs" / "red4ext.log"),
        ("RED4ext Alt", game_path / "red4ext" / "red4ext.log"),
        ("TweakXL", game_path / "red4ext" / "plugins" / "TweakXL" / "TweakXL.log"),
        ("ArchiveXL", game_path / "red4ext" / "plugins" / "ArchiveXL" / "ArchiveXL.log"),
        ("Redscript", game_path / "r6" / "logs" / "redscript.log"),
    ]
    
    results = []
    for name, path in log_locations:
        info = {
            "name": name,
            "path": str(path),
            "exists": path.exists(),
            "size": 0,
            "modified": None,
        }
        
        if path.exists():
            stat = path.stat()
            info["size"] = stat.st_size
            info["modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
        
        results.append(info)
    
    return results
