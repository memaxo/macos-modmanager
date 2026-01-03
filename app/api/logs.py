"""
Log API Endpoints

Provides endpoints for log streaming, retrieval, and management.
"""

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional, List
import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.core.log_streamer import LogStreamer, LogFilters, LogLevel, LogSource, get_log_file_paths
from app.core.error_detector import ErrorDetector

router = APIRouter()

# Singleton instances
_streamer: Optional[LogStreamer] = None
_detector: Optional[ErrorDetector] = None


def get_streamer() -> LogStreamer:
    global _streamer
    if _streamer is None:
        _streamer = LogStreamer()
    return _streamer


def get_detector() -> ErrorDetector:
    global _detector
    if _detector is None:
        patterns_file = Path(__file__).parent.parent.parent / "data" / "error_patterns.json"
        _detector = ErrorDetector(patterns_file if patterns_file.exists() else None)
    return _detector


@router.get("/stream")
async def stream_logs(
    request: Request,
    level: Optional[str] = Query(None, description="Filter by log level (error, warning, info, debug)"),
    source: Optional[str] = Query(None, description="Filter by source (red4ext, tweakxl, archivexl, redscript)"),
    search: Optional[str] = Query(None, description="Search string"),
):
    """
    Stream logs via Server-Sent Events (SSE).
    
    Connect to this endpoint to receive real-time log updates.
    """
    streamer = get_streamer()
    
    # Build filters
    filters = LogFilters()
    if level:
        try:
            filters.levels = {LogLevel(level)}
        except ValueError:
            pass
    if source:
        try:
            filters.sources = {LogSource(source)}
        except ValueError:
            pass
    if search:
        filters.search = search
    
    async def event_generator():
        try:
            async for line in streamer.stream(filters, include_buffer=True):
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                data = {
                    "timestamp": line.timestamp.isoformat(),
                    "level": line.level.value,
                    "source": line.source.value,
                    "message": line.message,
                    "file_path": line.file_path,
                    "line_number": line.line_number,
                }
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            streamer.stop()
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/recent")
async def get_recent_logs(
    lines: int = Query(100, ge=1, le=1000, description="Number of lines to retrieve"),
):
    """Get recent log lines from all sources"""
    streamer = get_streamer()
    detector = get_detector()
    
    log_lines = await streamer.get_recent(lines)
    
    # Detect errors
    detected_errors = []
    for line in log_lines:
        errors = detector.detect(line)
        for error in errors:
            detected_errors.append({
                "title": error.title,
                "description": error.description,
                "suggestion": error.suggestion,
                "severity": error.pattern.severity.value,
                "category": error.pattern.category.value,
                "line_number": line.line_number,
                "file_path": line.file_path,
            })
    
    return {
        "lines": [
            {
                "timestamp": line.timestamp.isoformat(),
                "level": line.level.value,
                "source": line.source.value,
                "message": line.message,
                "file_path": line.file_path,
                "line_number": line.line_number,
            }
            for line in log_lines
        ],
        "detected_errors": detected_errors,
        "stats": {
            "total": len(log_lines),
            "errors": sum(1 for l in log_lines if l.level == LogLevel.ERROR),
            "warnings": sum(1 for l in log_lines if l.level == LogLevel.WARNING),
        }
    }


@router.get("/errors")
async def get_errors_only(
    lines: int = Query(50, ge=1, le=500, description="Number of error lines to retrieve"),
):
    """Get only error log lines"""
    streamer = get_streamer()
    detector = get_detector()
    
    error_lines = await streamer.get_errors_only(lines)
    
    # Detect and categorize errors
    detected_errors = []
    for line in error_lines:
        errors = detector.detect(line)
        if errors:
            for error in errors:
                detected_errors.append({
                    "title": error.title,
                    "description": error.description,
                    "suggestion": error.suggestion,
                    "severity": error.pattern.severity.value,
                    "category": error.pattern.category.value,
                    "raw_message": line.message,
                    "timestamp": line.timestamp.isoformat(),
                })
        else:
            # Unrecognized error
            detected_errors.append({
                "title": "Unknown Error",
                "description": line.message[:200],
                "suggestion": None,
                "severity": "error",
                "category": "unknown",
                "raw_message": line.message,
                "timestamp": line.timestamp.isoformat(),
            })
    
    return {
        "errors": detected_errors,
        "total": len(detected_errors),
    }


@router.get("/files")
async def get_log_files():
    """Get list of log files and their status"""
    files = await get_log_file_paths()
    return {"files": files}


@router.post("/export")
async def export_logs():
    """Export all logs to a downloadable format"""
    streamer = get_streamer()
    log_lines = await streamer.get_recent(5000)
    
    # Build export content
    lines = []
    lines.append("=" * 80)
    lines.append("Cyberpunk 2077 macOS Mod Manager - Log Export")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("=" * 80)
    lines.append("")
    
    for line in log_lines:
        lines.append(f"[{line.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] [{line.source.value.upper()}] [{line.level.value.upper()}] {line.message}")
    
    content = "\n".join(lines)
    
    return {
        "content": content,
        "filename": f"cyberpunk_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        "lines": len(log_lines),
    }


@router.delete("/clear")
async def clear_logs():
    """Clear all log files"""
    streamer = get_streamer()
    await streamer.clear_logs()
    return {"status": "success", "message": "Logs cleared"}


@router.get("/analyze")
async def analyze_logs():
    """Analyze recent logs for issues"""
    streamer = get_streamer()
    detector = get_detector()
    
    log_lines = await streamer.get_recent(500)
    
    # Detect all errors
    all_errors = detector.detect_in_batch(log_lines)
    summary = detector.get_error_summary(all_errors)
    
    # Group by pattern
    by_pattern = {}
    for error in all_errors:
        pattern_id = error.pattern.id
        if pattern_id not in by_pattern:
            by_pattern[pattern_id] = {
                "title": error.pattern.title,
                "category": error.pattern.category.value,
                "severity": error.pattern.severity.value,
                "count": 0,
                "examples": [],
            }
        by_pattern[pattern_id]["count"] += 1
        if len(by_pattern[pattern_id]["examples"]) < 3:
            by_pattern[pattern_id]["examples"].append({
                "message": error.log_line.message[:200],
                "suggestion": error.suggestion,
            })
    
    return {
        "summary": summary,
        "issues_by_type": list(by_pattern.values()),
        "total_lines_analyzed": len(log_lines),
    }
