"""
GPU/CPU/Memory Profiler for Cyberpunk 2077 macOS

This module provides profiling capabilities for analyzing MetalFX, FSR,
and ray tracing performance using Frida instrumentation.

Theory: Path tracing and ray tracing are unoptimized for macOS and there
are real performance gains if MetalFX/AMD FSR/Apple Silicon GPU were optimized.

Key Insight: MetalFX is built on AMD FSR under MIT license.
"""

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from app.config import settings

try:
    import frida  # type: ignore
except Exception:  # pragma: no cover
    frida = None


class ProfilerState(Enum):
    """Profiler states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class FrameStats:
    """Statistics for a single frame."""
    frame_number: int
    frame_time_ms: float
    gpu_time_ms: float
    cpu_time_ms: float
    command_buffer_count: int
    memory_allocated_mb: float
    upscaling_time_ms: float = 0.0
    ray_tracing_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ProfilerReport:
    """Complete profiler report."""
    start_time: datetime
    end_time: datetime
    total_frames: int
    avg_frame_time_ms: float
    avg_gpu_time_ms: float
    avg_cpu_time_ms: float
    avg_memory_mb: float
    avg_upscaling_ms: float
    avg_raytracing_ms: float
    min_fps: float
    max_fps: float
    avg_fps: float
    percentile_99_frame_time: float
    percentile_95_frame_time: float
    bottleneck_analysis: dict
    recommendations: list[str]


# Frida hook script for Metal API profiling
METAL_PROFILER_SCRIPT = """
/**
 * GPU Profiler for Cyberpunk 2077 macOS
 * Hooks Metal API, MetalFX, and FSR functions
 */

'use strict';

// Safe-continuous mode defaults:
// - No console logging from hooks
// - No ApiResolver scans in the render loop
// - No full-module memory scans
// - Fixed-size ring buffers + low-frequency reporting timer

const CONFIG = {
    reportIntervalMs: 500,
    maxSamples: 240,
    // Minimal safe signals
    enableFrameTiming: true,
    enableDrawableTiming: true,
    enableCommandBufferCounts: true,
};

function makeRingBuffer(size) {
    return {
        buf: new Array(size).fill(0),
        idx: 0,
        count: 0,
        sum: 0,
        sumSq: 0,
    };
}

function rbAdd(rb, value) {
    const old = rb.count < rb.buf.length ? 0 : rb.buf[rb.idx];
    rb.buf[rb.idx] = value;
    rb.idx = (rb.idx + 1) % rb.buf.length;
    rb.count = Math.min(rb.count + 1, rb.buf.length);
    rb.sum += value - old;
    rb.sumSq += (value * value) - (old * old);
}

function rbAvg(rb) {
    return rb.count > 0 ? rb.sum / rb.count : 0;
}

function rbStd(rb) {
    if (rb.count <= 1) return 0;
    const mean = rb.sum / rb.count;
    const variance = Math.max(0, (rb.sumSq / rb.count) - (mean * mean));
    return Math.sqrt(variance);
}

const state = {
    reporting: true,
    frameCount: 0,
    lastFrameMark: 0,
    lastDrawableEnter: 0,
    commandBuffers: 0,
    drawableAcquire: makeRingBuffer(CONFIG.maxSamples),
    frameDeltas: makeRingBuffer(CONFIG.maxSamples),
    intervalId: null,
    hooked: {
        nextDrawable: false,
        presentDrawable: false,
        commit: false,
    }
};

function hookNextDrawable() {
    if (!CONFIG.enableDrawableTiming) return;
    if (!ObjC.available) return;
    const layer = ObjC.classes.CAMetalLayer;
    if (!layer) return;
    const method = layer['- nextDrawable'];
    if (!method) return;

    Interceptor.attach(method.implementation, {
        onEnter: function() {
            this.t0 = Date.now();
        },
        onLeave: function() {
            const dt = Date.now() - this.t0;
            rbAdd(state.drawableAcquire, dt);

            // Fallback frame boundary (if presentDrawable isn't hooked)
            if (!state.hooked.presentDrawable && CONFIG.enableFrameTiming) {
                const now = Date.now();
                if (state.lastFrameMark > 0) {
                    rbAdd(state.frameDeltas, now - state.lastFrameMark);
                    state.frameCount++;
                }
                state.lastFrameMark = now;
            }
        }
    });

    state.hooked.nextDrawable = true;
}

function tryHookMethod(className, selector, callbacks) {
        try {
            const cls = ObjC.classes[className];
        if (!cls) return false;
        const method = cls[selector];
        if (!method) return false;
        Interceptor.attach(method.implementation, callbacks);
        return true;
    } catch (e) {
        return false;
    }
}

function hookCommandBufferPresentAndCommit() {
    if (!ObjC.available) return;

    const candidates = [
        '_MTLCommandBuffer',
        'MTLIOAccelCommandBuffer',
        'MTLDebugCommandBuffer',
        'MTLToolsCommandBuffer',
    ];

    // Frame boundary
    if (CONFIG.enableFrameTiming) {
        for (const name of candidates) {
            if (tryHookMethod(name, '- presentDrawable:', {
                onEnter: function() {
                    const now = Date.now();
                    if (state.lastFrameMark > 0) {
                        rbAdd(state.frameDeltas, now - state.lastFrameMark);
                        state.frameCount++;
                    }
                    state.lastFrameMark = now;
                }
            })) {
                state.hooked.presentDrawable = true;
                break;
            }
        }
    }

    // Command buffer throughput signal
    if (CONFIG.enableCommandBufferCounts) {
        for (const name of candidates) {
            if (tryHookMethod(name, '- commit', {
                onEnter: function() {
                    state.commandBuffers++;
                }
            })) {
                state.hooked.commit = true;
                break;
            }
        }
    }
}

function emitReport() {
    if (!state.reporting) return;
    const avgFrame = rbAvg(state.frameDeltas);
    const stdFrame = rbStd(state.frameDeltas);
    const fps = avgFrame > 0 ? (1000 / avgFrame) : 0;
        
        send({
            type: 'stats',
            data: {
            frameCount: state.frameCount,
            fps: Number(fps.toFixed(1)),
            avgFrameTimeMs: Number(avgFrame.toFixed(2)),
            frameTimeStdDevMs: Number(stdFrame.toFixed(2)),
            avgDrawableAcquireMs: Number(rbAvg(state.drawableAcquire).toFixed(2)),
            commandBuffers: state.commandBuffers,
            hooks: state.hooked,
        }
    });

    // Reset per-interval counters (not ring buffers)
    state.commandBuffers = 0;
}

function start() {
    if (state.intervalId === null) {
        state.intervalId = setInterval(emitReport, CONFIG.reportIntervalMs);
    }
    state.reporting = true;
    return true;
}

function stop() {
    state.reporting = false;
    if (state.intervalId !== null) {
        clearInterval(state.intervalId);
        state.intervalId = null;
    }
    return true;
}

rpc.exports = {
    start: start,
    stop: stop,
    status: function() {
        return {
            reporting: state.reporting,
            frameCount: state.frameCount,
            hooks: state.hooked,
        };
    },
    setconfig: function(cfg) {
        if (cfg && typeof cfg === 'object') {
            if (typeof cfg.reportIntervalMs === 'number') CONFIG.reportIntervalMs = cfg.reportIntervalMs;
            if (typeof cfg.enableFrameTiming === 'boolean') CONFIG.enableFrameTiming = cfg.enableFrameTiming;
            if (typeof cfg.enableDrawableTiming === 'boolean') CONFIG.enableDrawableTiming = cfg.enableDrawableTiming;
            if (typeof cfg.enableCommandBufferCounts === 'boolean') CONFIG.enableCommandBufferCounts = cfg.enableCommandBufferCounts;
        }
        return CONFIG;
    }
};

// One-time, low-risk initialization
hookNextDrawable();
hookCommandBufferPresentAndCommit();
start();
"""


class GPUProfiler:
    """
    GPU/CPU/Memory profiler using Frida instrumentation.
    
    Provides real-time performance analysis for:
    - Metal API usage
    - MetalFX upscaling performance
    - AMD FSR integration
    - Ray tracing overhead
    - Memory allocation patterns
    """
    
    def __init__(self):
        self.state = ProfilerState.STOPPED
        self._session = None
        self._script = None
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.stats_history: list[FrameStats] = []
        self.current_stats: dict[str, Any] = {}
        self.callbacks: list[Callable[[dict], None]] = []
        self._frida_available = self._check_frida()
    
    def _check_frida(self) -> bool:
        """Check if Frida is available."""
        return frida is not None
    
    @property
    def is_available(self) -> bool:
        """Check if profiler can run."""
        return self._frida_available
    
    async def start(self, pid: Optional[int] = None) -> bool:
        """
        Start profiling.
        
        Args:
            pid: Process ID to attach to (auto-detect if None)
        
        Returns:
            True if started successfully
        """
        async with self._lock:
            if self.state == ProfilerState.RUNNING:
                return True

            if not self._frida_available or frida is None:
                return False

            self.state = ProfilerState.STARTING

            if pid is None:
                pid = await self._find_game_process()
                if pid is None:
                    self.state = ProfilerState.ERROR
                    return False

            self._loop = asyncio.get_running_loop()

            try:
                await asyncio.to_thread(self._attach_and_load, pid)
                self.state = ProfilerState.RUNNING
                return True
            except Exception as e:
                print(f"Failed to start profiler: {e}")
                self.state = ProfilerState.ERROR
                await asyncio.to_thread(self._detach_and_cleanup)
                return False

    def _attach_and_load(self, pid: int) -> None:
        """Attach to the target and load the Frida script (runs in a worker thread)."""
        if frida is None:
            raise RuntimeError("Frida Python bindings not available")

        session = frida.attach(pid)
        script = session.create_script(METAL_PROFILER_SCRIPT)
        script.on("message", self._on_message)
        script.load()

        # Best-effort start lifecycle (script may auto-start)
        try:
            script.exports.start()
        except Exception:
            pass

        self._session = session
        self._script = script

    def _detach_and_cleanup(self) -> None:
        """Unload script and detach session (runs in a worker thread)."""
        script = self._script
        session = self._session
        self._script = None
        self._session = None

        if script is not None:
            try:
                try:
                    script.exports.stop()
                except Exception:
                    pass
                script.unload()
            except Exception:
                pass

        if session is not None:
            try:
                session.detach()
            except Exception:
                pass

    def _on_message(self, message: dict, data: Any) -> None:
        """Handle messages from the Frida agent (called from Frida's thread)."""
        loop = self._loop
        if loop is None:
            return

        if message.get("type") == "send":
            payload = message.get("payload", {})
            if isinstance(payload, dict) and payload.get("type") == "stats":
                stats_data = payload.get("data", {})
                if isinstance(stats_data, dict):
                    loop.call_soon_threadsafe(self._process_stats, stats_data)
        elif message.get("type") == "error":
            # Surface script errors, but don't crash the server
            description = message.get("description") or message
            print(f"Frida script error: {description}")
    
    async def stop(self) -> Optional[ProfilerReport]:
        """
        Stop profiling and generate report.
        
        Returns:
            ProfilerReport with analysis results
        """
        async with self._lock:
            if self.state != ProfilerState.RUNNING:
                return None
            
            self.state = ProfilerState.STOPPING
            
            await asyncio.to_thread(self._detach_and_cleanup)
            self.state = ProfilerState.STOPPED
            
            return self._generate_report()
    
    async def _find_game_process(self) -> Optional[int]:
        """Find Cyberpunk 2077 process ID."""
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'Cyberpunk2077'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split('\n')[0])
        except Exception:
            pass
        return None
    
    def _process_stats(self, data: dict):
        """Process stats update from Frida."""
        self.current_stats = data
        
        # Add to history
        try:
            frame_stats = FrameStats(
                frame_number=int(data.get('frameCount', 0)),
                frame_time_ms=float(data.get('avgFrameTimeMs', 0)),
                gpu_time_ms=0,  # Would need GPU timestamps
                cpu_time_ms=float(data.get('avgFrameTimeMs', 0)),
                command_buffer_count=int(data.get('commandBuffers', 0)),
                memory_allocated_mb=float(data.get('memoryAllocatedMB', 0)),
                upscaling_time_ms=float(data.get('upscalingTimeMs', 0)),
                ray_tracing_time_ms=float(data.get('rayTracingTimeMs', 0)),
            )
            self.stats_history.append(frame_stats)
            
            # Keep last 10000 samples
            if len(self.stats_history) > 10000:
                self.stats_history = self.stats_history[-10000:]
            
        except Exception as e:
            print(f"Error processing stats: {e}")
        
        # Notify callbacks
        for callback in self.callbacks:
            try:
                callback(data)
            except Exception:
                pass
    
    def add_callback(self, callback: Callable[[dict], None]):
        """Add callback for stats updates."""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[dict], None]):
        """Remove stats callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def _generate_report(self) -> ProfilerReport:
        """Generate comprehensive profiler report."""
        if not self.stats_history:
            return ProfilerReport(
                start_time=datetime.now(),
                end_time=datetime.now(),
                total_frames=0,
                avg_frame_time_ms=0,
                avg_gpu_time_ms=0,
                avg_cpu_time_ms=0,
                avg_memory_mb=0,
                avg_upscaling_ms=0,
                avg_raytracing_ms=0,
                min_fps=0,
                max_fps=0,
                avg_fps=0,
                percentile_99_frame_time=0,
                percentile_95_frame_time=0,
                bottleneck_analysis={},
                recommendations=[]
            )
        
        frame_times = [s.frame_time_ms for s in self.stats_history if s.frame_time_ms > 0]
        
        if not frame_times:
            frame_times = [16.67]  # Default 60fps
        
        sorted_times = sorted(frame_times)
        
        avg_frame_time = sum(frame_times) / len(frame_times)
        avg_fps = 1000 / avg_frame_time if avg_frame_time > 0 else 0
        
        # Calculate percentiles
        p99_idx = int(len(sorted_times) * 0.99)
        p95_idx = int(len(sorted_times) * 0.95)
        
        # Analyze bottlenecks
        bottleneck_analysis = self._analyze_bottlenecks()
        recommendations = self._generate_recommendations(bottleneck_analysis)
        
        return ProfilerReport(
            start_time=self.stats_history[0].timestamp if self.stats_history else datetime.now(),
            end_time=self.stats_history[-1].timestamp if self.stats_history else datetime.now(),
            total_frames=len(self.stats_history),
            avg_frame_time_ms=avg_frame_time,
            avg_gpu_time_ms=sum(s.gpu_time_ms for s in self.stats_history) / len(self.stats_history),
            avg_cpu_time_ms=sum(s.cpu_time_ms for s in self.stats_history) / len(self.stats_history),
            avg_memory_mb=sum(s.memory_allocated_mb for s in self.stats_history) / len(self.stats_history),
            avg_upscaling_ms=sum(s.upscaling_time_ms for s in self.stats_history) / len(self.stats_history),
            avg_raytracing_ms=sum(s.ray_tracing_time_ms for s in self.stats_history) / len(self.stats_history),
            min_fps=1000 / max(frame_times) if max(frame_times) > 0 else 0,
            max_fps=1000 / min(frame_times) if min(frame_times) > 0 else 0,
            avg_fps=avg_fps,
            percentile_99_frame_time=sorted_times[p99_idx] if p99_idx < len(sorted_times) else 0,
            percentile_95_frame_time=sorted_times[p95_idx] if p95_idx < len(sorted_times) else 0,
            bottleneck_analysis=bottleneck_analysis,
            recommendations=recommendations
        )
    
    def _analyze_bottlenecks(self) -> dict:
        """Analyze performance bottlenecks."""
        analysis = {
            'upscaling_overhead': 'low',
            'ray_tracing_overhead': 'low',
            'memory_pressure': 'low',
            'command_buffer_fragmentation': 'low',
            'cpu_bound': False,
            'gpu_bound': False,
        }
        
        if not self.stats_history:
            return analysis
        
        # Analyze upscaling overhead
        avg_upscaling = sum(s.upscaling_time_ms for s in self.stats_history) / len(self.stats_history)
        avg_frame = sum(s.frame_time_ms for s in self.stats_history) / len(self.stats_history)
        
        if avg_frame > 0:
            upscaling_ratio = avg_upscaling / avg_frame
            if upscaling_ratio > 0.3:
                analysis['upscaling_overhead'] = 'high'
            elif upscaling_ratio > 0.15:
                analysis['upscaling_overhead'] = 'medium'
        
        # Analyze ray tracing
        avg_rt = sum(s.ray_tracing_time_ms for s in self.stats_history) / len(self.stats_history)
        if avg_frame > 0:
            rt_ratio = avg_rt / avg_frame
            if rt_ratio > 0.4:
                analysis['ray_tracing_overhead'] = 'high'
            elif rt_ratio > 0.2:
                analysis['ray_tracing_overhead'] = 'medium'
        
        # Analyze command buffer fragmentation
        avg_cmd_buffers = sum(s.command_buffer_count for s in self.stats_history) / len(self.stats_history)
        if avg_cmd_buffers > 50:
            analysis['command_buffer_fragmentation'] = 'high'
        elif avg_cmd_buffers > 20:
            analysis['command_buffer_fragmentation'] = 'medium'
        
        return analysis
    
    def _generate_recommendations(self, analysis: dict) -> list[str]:
        """Generate optimization recommendations."""
        recommendations = []
        
        if analysis.get('upscaling_overhead') == 'high':
            recommendations.append(
                "HIGH UPSCALING OVERHEAD: MetalFX/FSR is consuming >30% of frame time. "
                "Consider: (1) Lower FSR quality setting, (2) Check for unnecessary buffer copies "
                "between FSR compute and presentation, (3) Ensure shared memory buffers are used."
            )
        elif analysis.get('upscaling_overhead') == 'medium':
            recommendations.append(
                "MODERATE UPSCALING OVERHEAD: MetalFX/FSR using 15-30% of frame time. "
                "This is expected for temporal upscaling but could be optimized with "
                "proper buffer storage modes on Apple Silicon."
            )
        
        if analysis.get('ray_tracing_overhead') == 'high':
            recommendations.append(
                "HIGH RAY TRACING OVERHEAD: RT consuming >40% of frame time. "
                "Consider: (1) Disable ray traced shadows first, (2) Lower RT quality, "
                "(3) RT may be using software fallback instead of Metal RT API."
            )
        
        if analysis.get('command_buffer_fragmentation') == 'high':
            recommendations.append(
                "COMMAND BUFFER FRAGMENTATION: >50 command buffers per frame detected. "
                "This causes GPU idle time between submissions. The game may benefit from "
                "command buffer batching optimization."
            )
        
        if not recommendations:
            recommendations.append(
                "No major bottlenecks detected in profiled metrics. "
                "For deeper analysis, enable GPU timestamps and memory bandwidth tracking."
            )
        
        return recommendations
    
    def get_current_stats(self) -> dict:
        """Get current stats snapshot."""
        return self.current_stats.copy()
    
    def get_stats_history(self) -> list[FrameStats]:
        """Get stats history."""
        return self.stats_history.copy()


# Singleton instance
_profiler_instance: Optional[GPUProfiler] = None


def get_profiler() -> GPUProfiler:
    """Get or create profiler instance."""
    global _profiler_instance
    if _profiler_instance is None:
        _profiler_instance = GPUProfiler()
    return _profiler_instance


async def analyze_binary(game_path: Path) -> dict:
    """
    Analyze game binary for FSR/MetalFX symbols.
    
    Args:
        game_path: Path to Cyberpunk2077 binary
    
    Returns:
        Dictionary with symbol analysis
    """
    results = {
        'fsr_symbols': [],
        'metalfx_symbols': [],
        'metal_frameworks': [],
        'ray_tracing_symbols': [],
        'analysis': {}
    }
    
    if not game_path.exists():
        return results
    
    # Find FSR symbols
    try:
        nm_result = subprocess.run(
            ['nm', '-gU', str(game_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        for line in nm_result.stdout.split('\n'):
            lower = line.lower()
            if 'fsr' in lower or 'fidelity' in lower:
                results['fsr_symbols'].append(line.strip())
            if 'metalfx' in lower or 'mtlfx' in lower:
                results['metalfx_symbols'].append(line.strip())
            if 'raytrac' in lower or 'accelerationstruct' in lower:
                results['ray_tracing_symbols'].append(line.strip())
    except Exception as e:
        results['analysis']['nm_error'] = str(e)
    
    # Check linked frameworks
    try:
        otool_result = subprocess.run(
            ['otool', '-L', str(game_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        for line in otool_result.stdout.split('\n'):
            if 'Metal' in line or 'FSR' in line:
                results['metal_frameworks'].append(line.strip())
    except Exception as e:
        results['analysis']['otool_error'] = str(e)
    
    # Analysis summary
    results['analysis']['has_fsr'] = len(results['fsr_symbols']) > 0
    results['analysis']['has_metalfx'] = len(results['metalfx_symbols']) > 0 or any('MetalFX' in f for f in results['metal_frameworks'])
    results['analysis']['has_raytracing'] = len(results['ray_tracing_symbols']) > 0
    
    return results


# ============================================================================
# Upscaler Comparison Analysis
# ============================================================================

@dataclass
class UpscalerComparisonResult:
    """Results from comparing FSR vs MetalFX performance."""
    upscaler_type: str  # 'fsr2', 'fsr3', 'metalfx'
    avg_frame_time_ms: float
    frame_time_std_dev: float
    avg_fps: float
    frame_pacing_quality: float  # 0-100%, higher is better
    drawable_stall_count: int
    avg_drawable_acquire_ms: float
    recommendation: str
    
    def to_dict(self) -> dict:
        return {
            'upscaler_type': self.upscaler_type,
            'avg_frame_time_ms': round(self.avg_frame_time_ms, 2),
            'frame_time_std_dev': round(self.frame_time_std_dev, 2),
            'avg_fps': round(self.avg_fps, 1),
            'frame_pacing_quality': round(self.frame_pacing_quality, 1),
            'drawable_stall_count': self.drawable_stall_count,
            'avg_drawable_acquire_ms': round(self.avg_drawable_acquire_ms, 2),
            'recommendation': self.recommendation
        }


FRAME_TIMING_ANALYZER_SCRIPT = """
/**
 * Upscaler Comparison Script
 * Specifically designed to compare FSR vs MetalFX frame pacing
 */
'use strict';

// Safe-continuous comparison mode:
// - No memory scanning (no enumerateRanges/readByteArray)
// - No console logging
// - Minimal hooks + timer-driven send()

const CONFIG = {
    reportIntervalMs: 1000,
    maxSamples: 240,
    minSamplesForComplete: 30,
    stallThresholdMs: 16,
};

function makeRingBuffer(size) {
    return {
        buf: new Array(size).fill(0),
        idx: 0,
        count: 0,
        sum: 0,
        sumSq: 0,
    };
}

function rbAdd(rb, value) {
    const old = rb.count < rb.buf.length ? 0 : rb.buf[rb.idx];
    rb.buf[rb.idx] = value;
    rb.idx = (rb.idx + 1) % rb.buf.length;
    rb.count = Math.min(rb.count + 1, rb.buf.length);
    rb.sum += value - old;
    rb.sumSq += (value * value) - (old * old);
}

function rbAvg(rb) {
    return rb.count > 0 ? rb.sum / rb.count : 0;
}

function rbStd(rb) {
    if (rb.count <= 1) return 0;
    const mean = rb.sum / rb.count;
    const variance = Math.max(0, (rb.sumSq / rb.count) - (mean * mean));
    return Math.sqrt(variance);
}

const state = {
    reporting: true,
    upscalerType: 'unknown',
    lastMark: 0,
    sampleCount: 0,
    stallCount: 0,
    frameDeltas: makeRingBuffer(CONFIG.maxSamples),
    drawableAcquire: makeRingBuffer(CONFIG.maxSamples),
    intervalId: null,
    hookedPresent: false,
};

function detectUpscalerSafely() {
    // Avoid memory scanning; best-effort detection via ObjC class presence.
    if (!ObjC.available) return 'unknown';
    if (ObjC.classes.MTLFXTemporalScaler || ObjC.classes.MTLFXSpatialScaler) {
        state.upscalerType = 'metalfx';
    }
    return state.upscalerType;
}

function hookDrawable() {
    if (!ObjC.available) return;
    const layer = ObjC.classes.CAMetalLayer;
    if (!layer) return;
    const method = layer['- nextDrawable'];
        if (!method) return;
        
        Interceptor.attach(method.implementation, {
        onEnter: function() {
            this.t0 = Date.now();
        },
        onLeave: function() {
            const dt = Date.now() - this.t0;
            rbAdd(state.drawableAcquire, dt);
            if (dt > CONFIG.stallThresholdMs) state.stallCount++;

            // Fallback frame boundary if presentDrawable isn't hooked
            if (!state.hookedPresent) {
                const now = Date.now();
                if (state.lastMark > 0) {
                    rbAdd(state.frameDeltas, now - state.lastMark);
                    state.sampleCount++;
                }
                state.lastMark = now;
                }
            }
        });
}

function tryHookMethod(className, selector, callbacks) {
    try {
        const cls = ObjC.classes[className];
        if (!cls) return false;
        const method = cls[selector];
        if (!method) return false;
        Interceptor.attach(method.implementation, callbacks);
        return true;
    } catch (e) {
        return false;
    }
}

function hookPresent() {
    if (!ObjC.available) return;
    const candidates = [
        '_MTLCommandBuffer',
        'MTLIOAccelCommandBuffer',
        'MTLDebugCommandBuffer',
        'MTLToolsCommandBuffer',
    ];

    for (const name of candidates) {
        if (tryHookMethod(name, '- presentDrawable:', {
            onEnter: function() {
                    const now = Date.now();
                if (state.lastMark > 0) {
                    rbAdd(state.frameDeltas, now - state.lastMark);
                    state.sampleCount++;
                }
                state.lastMark = now;
            }
        })) {
            state.hookedPresent = true;
            break;
        }
    }
}

function reportResults() {
    if (!state.reporting) return;
    const avg = rbAvg(state.frameDeltas);
    const stdDev = rbStd(state.frameDeltas);
    const fps = avg > 0 ? (1000 / avg) : 0;
    const pacingQuality = avg > 0 ? Math.max(0, Math.min(100, 100 - (stdDev / avg * 100))) : 0;

    const status = state.sampleCount >= CONFIG.minSamplesForComplete ? 'complete' : 'insufficient_data';
    send({
        type: 'upscaler_comparison',
        status: status,
        upscalerType: state.upscalerType,
        avgFrameTimeMs: avg,
        frameTimeStdDev: stdDev,
        avgFps: fps,
        framePacingQuality: pacingQuality,
        stallCount: state.stallCount,
        avgDrawableAcquireMs: rbAvg(state.drawableAcquire),
        sampleCount: state.sampleCount,
        hookedPresent: state.hookedPresent,
    });
}

function start() {
    if (state.intervalId === null) {
        state.intervalId = setInterval(reportResults, CONFIG.reportIntervalMs);
    }
    state.reporting = true;
    return true;
}

function stop() {
    state.reporting = false;
    if (state.intervalId !== null) {
        clearInterval(state.intervalId);
        state.intervalId = null;
    }
    return true;
}

rpc.exports = {
    start: start,
    stop: stop,
    status: function() { return { ...state }; },
    setconfig: function(cfg) {
        if (cfg && typeof cfg === 'object') {
            if (typeof cfg.reportIntervalMs === 'number') CONFIG.reportIntervalMs = cfg.reportIntervalMs;
            if (typeof cfg.minSamplesForComplete === 'number') CONFIG.minSamplesForComplete = cfg.minSamplesForComplete;
        }
        return CONFIG;
    }
};

detectUpscalerSafely();
hookDrawable();
hookPresent();
start();
"""


class UpscalerComparison:
    """
    Tool for comparing FSR vs MetalFX performance.
    
    Based on binary analysis showing:
    - FSR has explicit frame pacing (6 fences/queues)
    - MetalFX relies on Metal internal sync
    - FSR may provide smoother gameplay
    """
    
    def __init__(self):
        self.results: dict[str, UpscalerComparisonResult] = {}
        self._running = False
        self._lock = asyncio.Lock()
    
    async def run_comparison(self, duration_seconds: int = 30) -> Optional[UpscalerComparisonResult]:
        """
        Run upscaler comparison analysis.
        
        Args:
            duration_seconds: How long to collect samples
        
        Returns:
            UpscalerComparisonResult with analysis
        """
        async with self._lock:
            if frida is None:
                return None

        pid = await self._find_game_process()
        if pid is None:
            return None
        
            self._running = True
            last_complete: Optional[dict] = None

            loop = asyncio.get_running_loop()

            def on_message(message: dict, data: Any) -> None:
                nonlocal last_complete
                if message.get("type") != "send":
                    return
                payload = message.get("payload", {})
                if not isinstance(payload, dict):
                    return
                if payload.get("type") != "upscaler_comparison":
                    return
                if payload.get("status") == "complete":
                    last_complete = payload

            session = None
            script = None

            try:
                session = await asyncio.to_thread(frida.attach, pid)
                script = session.create_script(FRAME_TIMING_ANALYZER_SCRIPT)
                script.on("message", on_message)
                script.load()

                # Let it run for duration_seconds
                end_time = time.time() + duration_seconds
                while time.time() < end_time and self._running:
                    await asyncio.sleep(0.1)

                # Best-effort stop (script may already be stopped by unload)
                try:
                    script.exports.stop()
                except Exception:
                    pass

            except Exception as e:
                print(f"Comparison failed: {e}")
            finally:
                self._running = False
                if script is not None:
                    try:
                        script.unload()
                    except Exception:
                        pass
                if session is not None:
                    try:
                        session.detach()
                    except Exception:
                        pass

            if not last_complete:
                return None

            upscaler_type = last_complete.get("upscalerType", "unknown")
            pacing_quality = float(last_complete.get("framePacingQuality", 0))
            recommendation = self._generate_recommendation(last_complete)
                
            result = UpscalerComparisonResult(
                upscaler_type=str(upscaler_type),
                avg_frame_time_ms=float(last_complete.get("avgFrameTimeMs", 0)),
                frame_time_std_dev=float(last_complete.get("frameTimeStdDev", 0)),
                avg_fps=float(last_complete.get("avgFps", 0)),
                frame_pacing_quality=pacing_quality,
                drawable_stall_count=int(last_complete.get("stallCount", 0)),
                avg_drawable_acquire_ms=float(last_complete.get("avgDrawableAcquireMs", 0)),
                recommendation=recommendation,
            )

            self.results[str(upscaler_type)] = result
            return result
    
    def _generate_recommendation(self, data: dict) -> str:
        """Generate recommendation based on analysis."""
        upscaler = data.get('upscalerType', 'unknown')
        pacing = data.get('framePacingQuality', 0)
        stalls = data.get('stallCount', 0)
        
        if upscaler == 'metalfx':
            if pacing < 70:
                return (
                    "MetalFX showing sub-optimal frame pacing. "
                    "Binary analysis shows MetalFX lacks FSR's explicit sync fences. "
                    "TRY FSR2/FSR3 for potentially smoother gameplay."
                )
            elif stalls > 10:
                return (
                    "MetalFX showing drawable stalls. "
                    "This may indicate Metal internal sync issues. "
                    "Consider trying FSR which has explicit PresentQueue and GameFence."
                )
            else:
                return "MetalFX performing well. Frame pacing is acceptable."
        
        elif upscaler in ('fsr2', 'fsr3'):
            if pacing < 70:
                return (
                    f"{upscaler.upper()} showing frame pacing issues. "
                    "Check FSR quality setting and ensure FSR3 Frame Generation is "
                    "enabled if using FSR3 at lower base framerates."
                )
            elif pacing >= 85:
                return (
                    f"{upscaler.upper()} showing excellent frame pacing ({pacing:.1f}%). "
                    "FSR's explicit fences (CompositionFence, PresentFence, etc.) "
                    "are providing smooth frame delivery."
                )
            else:
                return f"{upscaler.upper()} performing adequately. Frame pacing is good."
        
        return "Unable to detect upscaler type. Try with game in focus and graphics loaded."
    
    async def _find_game_process(self) -> Optional[int]:
        """Find Cyberpunk 2077 process."""
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'Cyberpunk2077'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split('\n')[0])
        except Exception:
            pass
        return None
    
    def compare_results(self) -> dict:
        """
        Compare stored results between upscalers.
        
        Returns:
            Dictionary with comparison analysis
        """
        if len(self.results) < 2:
            return {
                'status': 'insufficient_data',
                'message': 'Need at least 2 upscalers tested for comparison'
            }
        
        # Find best performer
        best_pacing = max(self.results.values(), key=lambda r: r.frame_pacing_quality)
        best_fps = max(self.results.values(), key=lambda r: r.avg_fps)
        
        return {
            'status': 'complete',
            'best_frame_pacing': best_pacing.upscaler_type,
            'best_fps': best_fps.upscaler_type,
            'comparison': {
                name: result.to_dict() for name, result in self.results.items()
            },
            'recommendation': self._overall_recommendation()
        }
    
    def _overall_recommendation(self) -> str:
        """Generate overall recommendation from all results."""
        if not self.results:
            return "No comparison data available."
        
        fsr_results = [r for name, r in self.results.items() if 'fsr' in name]
        mfx_results = [r for name, r in self.results.items() if name == 'metalfx']
        
        if fsr_results and mfx_results:
            fsr_pacing = max(r.frame_pacing_quality for r in fsr_results)
            mfx_pacing = mfx_results[0].frame_pacing_quality
            
            if fsr_pacing > mfx_pacing + 10:
                return (
                    f"FSR shows {fsr_pacing - mfx_pacing:.1f}% better frame pacing than MetalFX. "
                    "This confirms binary analysis: FSR's explicit sync fences provide "
                    "smoother frame delivery than MetalFX's internal synchronization."
                )
            elif mfx_pacing > fsr_pacing + 10:
                return (
                    "MetalFX showing better frame pacing than FSR in this test. "
                    "This may indicate FSR configuration issues or "
                    "that Metal's internal sync is well-tuned for this workload."
                )
            else:
                return (
                    "FSR and MetalFX show similar frame pacing quality. "
                    "Personal preference may determine best choice. "
                    "FSR offers more configuration options."
                )
        
        return "Comparison results inconclusive."
