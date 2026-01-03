"""
API endpoints for GPU/CPU/Memory profiler.

Provides real-time performance analysis for MetalFX, FSR,
and ray tracing optimization investigation.
"""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.game_detector import detect_cyberpunk_installations
from app.core.gpu_profiler import GPUProfiler, ProfilerReport, analyze_binary, get_profiler

router = APIRouter(prefix="/api/profiler", tags=["profiler"])


class ProfilerStatus(BaseModel):
    """Profiler status response."""
    available: bool
    state: str
    frida_installed: bool
    current_fps: float = 0
    current_frame_time_ms: float = 0
    upscaling_time_ms: float = 0
    ray_tracing_time_ms: float = 0
    memory_mb: float = 0
    command_buffers: int = 0


class BinaryAnalysis(BaseModel):
    """Binary analysis response."""
    fsr_symbols_count: int
    metalfx_detected: bool
    ray_tracing_detected: bool
    metal_frameworks: list[str]
    has_fsr: bool
    analysis_summary: str


class OptimizationRecommendation(BaseModel):
    """Optimization recommendation."""
    category: str
    severity: str  # low, medium, high
    title: str
    description: str
    potential_gain: str


@router.get("/status", response_model=ProfilerStatus)
async def get_profiler_status():
    """Get current profiler status and stats."""
    profiler = get_profiler()
    stats = profiler.get_current_stats()
    
    fps = float(stats.get('fps', 0)) if stats.get('fps') else 0
    
    return ProfilerStatus(
        available=profiler.is_available,
        state=profiler.state.value,
        frida_installed=profiler._frida_available,
        current_fps=fps,
        current_frame_time_ms=float(stats.get('avgFrameTimeMs', 0)),
        upscaling_time_ms=float(stats.get('upscalingTimeMs', 0)),
        ray_tracing_time_ms=float(stats.get('rayTracingTimeMs', 0)),
        memory_mb=float(stats.get('memoryAllocatedMB', 0)),
        command_buffers=int(stats.get('commandBuffers', 0))
    )


@router.post("/start")
async def start_profiler(pid: int = None):
    """
    Start GPU profiler.
    
    Args:
        pid: Optional process ID (auto-detect if not provided)
    """
    profiler = get_profiler()
    
    if not profiler.is_available:
        raise HTTPException(
            status_code=503,
            detail="Frida Python bindings not available. Install with: pip install frida"
        )
    
    success = await profiler.start(pid)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to start profiler. Is Cyberpunk 2077 running?"
        )
    
    msg = "Profiler attached to game process"
    if profiler.state.value == "running":
        # start() is idempotent; indicate whether we were already running
        msg = "Profiler running"
    return {"status": "started", "message": msg}


@router.post("/stop")
async def stop_profiler():
    """Stop GPU profiler and get report."""
    profiler = get_profiler()
    report = await profiler.stop()
    
    if report is None:
        return {"status": "stopped", "report": None}
    
    return {
        "status": "stopped",
        "report": {
            "total_frames": report.total_frames,
            "avg_fps": round(report.avg_fps, 1),
            "avg_frame_time_ms": round(report.avg_frame_time_ms, 2),
            "min_fps": round(report.min_fps, 1),
            "max_fps": round(report.max_fps, 1),
            "percentile_99_frame_time": round(report.percentile_99_frame_time, 2),
            "percentile_95_frame_time": round(report.percentile_95_frame_time, 2),
            "avg_upscaling_ms": round(report.avg_upscaling_ms, 2),
            "avg_raytracing_ms": round(report.avg_raytracing_ms, 2),
            "bottleneck_analysis": report.bottleneck_analysis,
            "recommendations": report.recommendations
        }
    }


@router.get("/stream")
async def stream_stats():
    """Stream real-time profiler stats via SSE."""
    profiler = get_profiler()
    
    async def generate():
        while profiler.state.value == "running":
            stats = profiler.get_current_stats()
            yield f"data: {json.dumps(stats)}\n\n"
            await asyncio.sleep(0.1)  # 10 updates per second
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analyze-binary", response_model=BinaryAnalysis)
async def analyze_game_binary():
    """Analyze game binary for FSR/MetalFX symbols."""
    installations = await detect_cyberpunk_installations()
    
    if not installations:
        raise HTTPException(
            status_code=404,
            detail="Cyberpunk 2077 installation not found"
        )
    
    # Use the first installation found
    game_path = Path(installations[0]['path'])
    
    # Find the actual binary
    binary_path = game_path / "Cyberpunk 2077.app" / "Contents" / "MacOS" / "Cyberpunk2077"
    if not binary_path.exists():
        binary_path = game_path / "Cyberpunk2077.app" / "Contents" / "MacOS" / "Cyberpunk2077"
    if not binary_path.exists():
        binary_path = game_path / "Cyberpunk2077"
    
    if not binary_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Cyberpunk 2077 binary not found"
        )
    
    results = await analyze_binary(binary_path)
    
    # Generate summary
    summary_parts = []
    if results['analysis'].get('has_metalfx'):
        summary_parts.append("MetalFX upscaling detected (FSR-based)")
    if results['analysis'].get('has_fsr'):
        summary_parts.append(f"Found {len(results['fsr_symbols'])} FSR-related symbols")
    if results['analysis'].get('has_raytracing'):
        summary_parts.append("Metal ray tracing APIs in use")
    
    if not summary_parts:
        summary_parts.append("No FSR/MetalFX symbols found in exports (may be statically linked)")
    
    return BinaryAnalysis(
        fsr_symbols_count=len(results['fsr_symbols']),
        metalfx_detected=results['analysis'].get('has_metalfx', False),
        ray_tracing_detected=results['analysis'].get('has_raytracing', False),
        metal_frameworks=results['metal_frameworks'],
        has_fsr=results['analysis'].get('has_fsr', False),
        analysis_summary="; ".join(summary_parts)
    )


@router.get("/recommendations", response_model=list[OptimizationRecommendation])
async def get_optimization_recommendations():
    """
    Get optimization recommendations based on current profiling data
    and known MetalFX/FSR optimization opportunities.
    """
    profiler = get_profiler()
    stats_history = profiler.get_stats_history()
    
    recommendations = []
    
    # Always include these general recommendations
    recommendations.append(OptimizationRecommendation(
        category="MetalFX/FSR",
        severity="medium",
        title="MetalFX Buffer Storage Mode",
        description=(
            "MetalFX (FSR-based) may not be using optimal buffer storage modes for "
            "Apple Silicon's unified memory. Using MTLResourceStorageModeShared could "
            "eliminate unnecessary CPU-GPU memory copies."
        ),
        potential_gain="5-15% improvement in upscaling performance"
    ))
    
    recommendations.append(OptimizationRecommendation(
        category="MetalFX/FSR",
        severity="high",
        title="FSR Quality vs Performance Balance",
        description=(
            "FSR Quality presets may not be optimally tuned for Apple Silicon GPU. "
            "Experiment with FSR2/FSR3 quality settings. Lower quality with higher "
            "sharpening can sometimes look better than high quality with artifacts."
        ),
        potential_gain="20-40% FPS improvement at minimal visual cost"
    ))
    
    recommendations.append(OptimizationRecommendation(
        category="Ray Tracing",
        severity="high",
        title="Ray Traced Shadows Overhead",
        description=(
            "Ray traced shadows are typically the highest-cost RT effect. "
            "Disabling rayTracedSunShadows and rayTracedLocalShadows in favor of "
            "screen-space shadows can significantly improve performance while "
            "maintaining visual quality."
        ),
        potential_gain="30-50% FPS improvement when RT is bottleneck"
    ))
    
    recommendations.append(OptimizationRecommendation(
        category="Path Tracing",
        severity="high",
        title="Path Tracing Software Fallback",
        description=(
            "Path tracing on Apple Silicon may use software BVH traversal instead of "
            "Metal's hardware-accelerated ray tracing. This is a known limitation. "
            "Consider disabling rayTracedPathTracingEnabled for significantly "
            "better performance."
        ),
        potential_gain="100-200% FPS improvement (path tracing is extremely expensive)"
    ))
    
    recommendations.append(OptimizationRecommendation(
        category="Memory",
        severity="medium",
        title="Unified Memory Optimization",
        description=(
            "Apple Silicon's unified memory architecture should allow zero-copy "
            "operations between CPU and GPU. If the game is using separate "
            "buffers with copy operations, this is suboptimal. Profile memory "
            "allocation patterns to identify opportunities."
        ),
        potential_gain="Variable - depends on current implementation"
    ))
    
    recommendations.append(OptimizationRecommendation(
        category="Command Buffer",
        severity="low",
        title="Command Buffer Batching",
        description=(
            "Submitting many small command buffers causes GPU idle time between "
            "submissions. Modern Metal best practices suggest batching related "
            "work into fewer, larger command buffers."
        ),
        potential_gain="5-10% improvement in GPU utilization"
    ))
    
    # Add dynamic recommendations based on profiling data
    if stats_history:
        avg_frame_time = sum(s.frame_time_ms for s in stats_history) / len(stats_history)
        avg_upscaling = sum(s.upscaling_time_ms for s in stats_history) / len(stats_history)
        
        if avg_frame_time > 0 and avg_upscaling / avg_frame_time > 0.25:
            recommendations.insert(0, OptimizationRecommendation(
                category="DETECTED",
                severity="high",
                title="High Upscaling Overhead Detected",
                description=(
                    f"Upscaling is consuming {(avg_upscaling/avg_frame_time)*100:.1f}% of frame time. "
                    "This indicates MetalFX/FSR may have optimization issues. "
                    "Try lowering FSR quality or investigate buffer allocation patterns."
                ),
                potential_gain="Significant - this is likely your primary bottleneck"
            ))
    
    return recommendations


@router.get("/frida-script")
async def get_frida_script():
    """
    Get the Frida profiler script for manual use.
    
    This allows advanced users to run the profiler manually with:
    frida -p <pid> -l gpu_profiler.js
    """
    from app.core.gpu_profiler import METAL_PROFILER_SCRIPT
    
    return {
        "script": METAL_PROFILER_SCRIPT,
        "usage": "frida -p $(pgrep Cyberpunk2077) -l gpu_profiler.js --no-pause"
    }


# ============================================================================
# FSR vs MetalFX Comparison
# ============================================================================

# Global comparison instance
_upscaler_comparison = None

def get_upscaler_comparison():
    """Get or create upscaler comparison instance."""
    global _upscaler_comparison
    if _upscaler_comparison is None:
        from app.core.gpu_profiler import UpscalerComparison
        _upscaler_comparison = UpscalerComparison()
    return _upscaler_comparison


@router.post("/upscaler-comparison/run")
async def run_upscaler_comparison(duration: int = 30):
    """
    Run FSR vs MetalFX frame pacing comparison.
    
    This performs live analysis of frame timing to compare upscaler performance.
    Based on binary analysis showing:
    - FSR has 6 explicit sync fences (CompositionFence, PresentFence, etc.)
    - MetalFX relies on Metal's internal synchronization
    
    Args:
        duration: Analysis duration in seconds (default 30)
    
    Returns:
        UpscalerComparisonResult with frame pacing analysis
    """
    comparison = get_upscaler_comparison()
    
    result = await comparison.run_comparison(duration)
    
    if result:
        return {
            "status": "success",
            "data": result.to_dict()
        }
    
    return {
        "status": "error",
        "message": "Failed to run comparison. Ensure game is running and Frida is installed."
    }


@router.get("/upscaler-comparison/results")
async def get_comparison_results():
    """
    Get all upscaler comparison results.
    
    Returns stored results from previous comparisons for side-by-side analysis.
    """
    comparison = get_upscaler_comparison()
    
    return {
        "results": {
            name: result.to_dict() for name, result in comparison.results.items()
        },
        "comparison": comparison.compare_results() if len(comparison.results) >= 2 else None
    }


@router.get("/upscaler-comparison/insights")
async def get_upscaler_insights():
    """
    Get insights about FSR vs MetalFX based on binary analysis.
    
    Returns technical findings from reverse engineering the game binary.
    """
    return {
        "title": "FSR vs MetalFX: Technical Analysis",
        "key_finding": (
            "Binary analysis reveals FSR has explicit frame pacing infrastructure "
            "that MetalFX lacks. This may explain why FSR feels smoother."
        ),
        "fsr_sync_primitives": [
            {"name": "FSR CompositionFence", "purpose": "Coordinates frame composition"},
            {"name": "FSR GameFence", "purpose": "Syncs with game render loop"},
            {"name": "FSR InterpolationFence", "purpose": "Frame generation sync"},
            {"name": "FSR PresentFence", "purpose": "Presentation timing control"},
            {"name": "FSR PresentQueue", "purpose": "Dedicated presentation queue"},
            {"name": "FSR ReplacementBufferFence", "purpose": "Double/triple buffer sync"},
            {"name": "FSR Interpolation Async Queue", "purpose": "Async frame generation"}
        ],
        "metalfx_sync_primitives": [
            {"name": "None visible", "purpose": "Relies on Metal internal sync"}
        ],
        "aapl_optimization_note": (
            "IMPORTANT: The AAPL optimizations (EnableReferenceAAPLOptim, UseAAPLOptimPass) "
            "affect RAY TRACING, not upscaling. These optimizations improve ray buffer management "
            "and denoising - they are independent of MetalFX vs FSR choice."
        ),
        "recommendation": (
            "Based on binary evidence, FSR2/FSR3 is recommended over MetalFX for potentially "
            "smoother frame pacing. FSR's explicit async queues and fences allow tighter "
            "control over frame delivery timing."
        )
    }


@router.get("/frame-timing-analyzer-script")
async def get_frame_timing_script():
    """
    Get the specialized frame timing analyzer Frida script.
    
    This script provides detailed frame pacing analysis including:
    - Frame delta measurements
    - Stall detection
    - Drawable acquisition timing
    - FSR/MetalFX detection
    
    Usage:
        frida -U -n Cyberpunk2077 -l frame_timing_analyzer.js
    """
    script_path = Path(__file__).parent.parent.parent / "scripts" / "frida" / "frame_timing_analyzer.js"
    
    if script_path.exists():
        return {
            "script": script_path.read_text(),
            "usage": "frida -U -n Cyberpunk2077 -l frame_timing_analyzer.js",
            "description": (
                "Comprehensive frame timing analyzer that measures frame pacing quality "
                "and compares FSR vs MetalFX synchronization behavior."
            )
        }
    
    return {
        "status": "error",
        "message": "Script not found. Check scripts/frida/frame_timing_analyzer.js"
    }
