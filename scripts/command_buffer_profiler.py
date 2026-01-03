#!/usr/bin/env python3
"""
Command Buffer Deep Profiler
Phase 2, Week 3: Deep command buffer pattern analysis
"""

import asyncio
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.gpu_profiler import get_profiler


class CommandBufferProfiler:
    """Profiles command buffer creation patterns and GPU timeline."""
    
    def __init__(self):
        self.profiler = get_profiler()
        self.buffer_events = []
        self.buffer_patterns = defaultdict(list)
    
    async def profile_command_buffers(self, duration_minutes: int = 5):
        """Profile command buffer creation patterns."""
        print("="*70)
        print("COMMAND BUFFER DEEP PROFILER")
        print("Phase 2, Week 3: Deep command buffer pattern analysis")
        print("="*70)
        
        if not self.profiler.is_available:
            print("❌ Frida not available")
            return None
        
        pid = await self.profiler._find_game_process()
        if not pid:
            print("❌ Cyberpunk 2077 not running!")
            return None
        
        print(f"✓ Found process: PID {pid}\n")
        print("📊 Starting command buffer profiling...")
        print("   This will track command buffer creation patterns\n")
        
        # Start profiler
        await self.profiler.start(pid)
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        samples = []
        
        print(f"⏳ Collecting data for {duration_minutes} minutes...")
        print("   (Press Ctrl+C to stop early)\n")
        
        try:
            last_cmd_buffer_count = 0
            while time.time() < end_time:
                await asyncio.sleep(1)  # Sample every second for finer granularity
                stats = self.profiler.get_current_stats()
                if stats:
                    current_cmd_buffers = stats.get('commandBuffers', 0)
                    cmd_buffer_delta = current_cmd_buffers - last_cmd_buffer_count
                    last_cmd_buffer_count = current_cmd_buffers
                    
                    sample = {
                        'timestamp': datetime.now().isoformat(),
                        'elapsed_seconds': time.time() - start_time,
                        'command_buffers_total': current_cmd_buffers,
                        'command_buffers_per_second': cmd_buffer_delta,
                        'fps': stats.get('fps', 0),
                        'frame_time_ms': stats.get('avgFrameTimeMs', 0),
                    }
                    samples.append(sample)
                    
                    if len(samples) % 10 == 0:
                        fps = stats.get('fps', 'N/A')
                        cmd_bufs = stats.get('commandBuffers', 0)
                        print(f"  [{time.strftime('%H:%M:%S')}] FPS: {fps} | CmdBuffers: {cmd_bufs} | Delta: {cmd_buffer_delta}/s")
        except KeyboardInterrupt:
            print("\n⚠️  Stopped early by user")
        
        report = await self.profiler.stop()
        
        # Analyze patterns
        if samples:
            # Calculate per-frame command buffer rate
            fps_values = [float(s.get('fps', 0)) for s in samples if s.get('fps') and s.get('fps') != 'N/A']
            cmd_buffer_rates = [s.get('command_buffers_per_second', 0) for s in samples]
            
            avg_fps = sum(fps_values) / len(fps_values) if fps_values else 0
            avg_cmd_buffer_rate = sum(cmd_buffer_rates) / len(cmd_buffer_rates) if cmd_buffer_rates else 0
            cmd_buffers_per_frame = avg_cmd_buffer_rate / avg_fps if avg_fps > 0 else 0
            
            # Identify patterns
            high_buffer_samples = [s for s in samples if s.get('command_buffers_per_second', 0) > avg_cmd_buffer_rate * 1.5]
            low_buffer_samples = [s for s in samples if s.get('command_buffers_per_second', 0) < avg_cmd_buffer_rate * 0.5]
            
            result = {
                'timestamp': datetime.now().isoformat(),
                'duration_minutes': duration_minutes,
                'samples_collected': len(samples),
                'analysis': {
                    'average_fps': avg_fps,
                    'average_cmd_buffer_rate_per_second': avg_cmd_buffer_rate,
                    'command_buffers_per_frame': cmd_buffers_per_frame,
                    'target_buffers_per_frame': 1.0,
                    'fragmentation_ratio': cmd_buffers_per_frame / 1.0 if cmd_buffers_per_frame > 0 else 0,
                },
                'patterns': {
                    'high_buffer_periods': len(high_buffer_samples),
                    'low_buffer_periods': len(low_buffer_samples),
                    'variance': {
                        'min_cmd_buffer_rate': min(cmd_buffer_rates) if cmd_buffer_rates else 0,
                        'max_cmd_buffer_rate': max(cmd_buffer_rates) if cmd_buffer_rates else 0,
                        'std_dev': self._calculate_std_dev(cmd_buffer_rates) if cmd_buffer_rates else 0,
                    }
                },
                'profiler_report': {
                    'total_frames': report.total_frames if report else 0,
                    'avg_fps': report.avg_fps if report else 0,
                    'avg_frame_time_ms': report.avg_frame_time_ms if report else 0,
                } if report else None,
                'samples': samples[:200]  # Keep first 200 samples
            }
            
            print(f"\n{'='*70}")
            print("COMMAND BUFFER ANALYSIS")
            print(f"{'='*70}")
            print(f"\nAverage FPS: {avg_fps:.1f}")
            print(f"Average CmdBuffer Rate: {avg_cmd_buffer_rate:.1f}/second")
            print(f"Command Buffers per Frame: {cmd_buffers_per_frame:.2f}")
            print(f"Target: <1.0 buffers/frame")
            print(f"Fragmentation Ratio: {result['analysis']['fragmentation_ratio']:.2f}x")
            
            if cmd_buffers_per_frame > 2.0:
                print(f"\n⚠️  HIGH FRAGMENTATION DETECTED")
                print(f"   Current: {cmd_buffers_per_frame:.2f} buffers/frame")
                print(f"   Target: <1.0 buffers/frame")
                print(f"   Potential Gain: 5-15% FPS improvement")
            
            return result
        
        return None
    
    def _calculate_std_dev(self, values):
        """Calculate standard deviation."""
        if not values:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Command Buffer Profiler')
    parser.add_argument('--duration', type=int, default=5, help='Duration in minutes')
    parser.add_argument('--output', type=str, help='Output JSON file path')
    
    args = parser.parse_args()
    
    profiler = CommandBufferProfiler()
    result = await profiler.profile_command_buffers(args.duration)
    
    if result:
        output_file = Path(args.output) if args.output else (
            Path(__file__).parent.parent / "docs" / f"command_buffer_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
