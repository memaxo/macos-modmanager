#!/usr/bin/env python3
"""
Quick RT Profiler Starter
Attaches safe-continuous profiler to running Cyberpunk 2077 process.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.gpu_profiler import get_profiler


async def main():
    print("=" * 70)
    print("RT Profiler - Safe Continuous Mode")
    print("=" * 70)
    
    profiler = get_profiler()
    
    if not profiler.is_available:
        print("❌ Frida not available. Install with: pip install frida")
        return 1
    
    print("\n🔍 Looking for Cyberpunk 2077 process...")
    pid = await profiler._find_game_process()
    
    if pid is None:
        print("❌ Cyberpunk 2077 not running!")
        print("   Start the game first, then run this script again.")
        return 1
    
    print(f"✓ Found process: PID {pid}")
    print("\n🚀 Starting profiler (safe-continuous mode)...")
    
    success = await profiler.start(pid)
    
    if not success:
        print("❌ Failed to attach profiler")
        return 1
    
    print("✓ Profiler attached successfully!")
    print("\n" + "=" * 70)
    print("PROFILER RUNNING")
    print("=" * 70)
    print("\n📊 Stats will be collected in safe-continuous mode:")
    print("   - Frame timing (ring buffers)")
    print("   - Command buffer counts")
    print("   - Basic Metal API hooks")
    print("\n⚠️  Heavy RT hooks are DISABLED by default")
    print("   (to avoid game freezes)")
    print("\n📈 View stats:")
    print("   - API: http://localhost:8000/api/profiler/status")
    print("   - Stream: http://localhost:8000/api/profiler/stream")
    print("\n⏹️  Press Ctrl+C to stop profiling and generate report...")
    print("=" * 70 + "\n")
    
    try:
        # Keep running and show periodic stats
        import time
        while True:
            await asyncio.sleep(5)
            stats = profiler.get_current_stats()
            if stats:
                fps = stats.get('fps', 'N/A')
                frame_time = stats.get('avgFrameTimeMs', 'N/A')
                cmd_buffers = stats.get('commandBuffers', 0)
                print(f"[{time.strftime('%H:%M:%S')}] FPS: {fps} | Frame: {frame_time}ms | CmdBuffers: {cmd_buffers}")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\n⏹️  Stopping profiler...")
        try:
            report = await profiler.stop()
        except Exception as e:
            print(f"⚠️  Error during stop: {e}")
            report = None
        
        if report:
            print("\n" + "=" * 70)
            print("PROFILER REPORT")
            print("=" * 70)
            print(f"Total Frames: {report.total_frames}")
            print(f"Avg FPS: {report.avg_fps:.1f}")
            print(f"Avg Frame Time: {report.avg_frame_time_ms:.2f}ms")
            print(f"P99 Frame Time: {report.percentile_99_frame_time:.2f}ms")
            print(f"P95 Frame Time: {report.percentile_95_frame_time:.2f}ms")
            print(f"Min FPS: {report.min_fps:.1f} | Max FPS: {report.max_fps:.1f}")
            
            if report.avg_upscaling_ms > 0:
                print(f"\nUpscaling:")
                print(f"  Avg Time: {report.avg_upscaling_ms:.2f}ms")
            
            if report.avg_raytracing_ms > 0:
                print(f"\nRay Tracing:")
                print(f"  Avg Time: {report.avg_raytracing_ms:.2f}ms")
            
            if report.recommendations:
                print(f"\nRecommendations:")
                for rec in report.recommendations:
                    print(f"  - {rec}")
        
        print("\n✓ Profiler stopped")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
