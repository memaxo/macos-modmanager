#!/usr/bin/env python3
"""
Extended Baseline Profiler
Phase 1, Week 1: Collect 30+ minutes of gameplay data across different scenarios
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.gpu_profiler import get_profiler


class ExtendedBaselineProfiler:
    """Collects extended baseline performance data across scenarios."""
    
    def __init__(self):
        self.profiler = get_profiler()
        self.scenarios = []
        self.results = []
    
    async def run_scenario(self, name: str, duration_minutes: int = 5) -> Dict:
        """Run profiling for a specific scenario."""
        print(f"\n{'='*70}")
        print(f"SCENARIO: {name}")
        print(f"Duration: {duration_minutes} minutes")
        print(f"{'='*70}\n")
        
        print("⏳ Waiting for you to navigate to scenario location...")
        print("   Press ENTER when ready, or type 'skip' to skip this scenario")
        
        # Wait for user confirmation
        try:
            user_input = await asyncio.to_thread(input)
            if user_input.strip().lower() == 'skip':
                return None
        except (EOFError, KeyboardInterrupt):
            return None
        
        # Start profiling
        pid = await self.profiler._find_game_process()
        if not pid:
            print("❌ Game not running!")
            return None
        
        print(f"🚀 Starting profiler for {duration_minutes} minutes...")
        success = await self.profiler.start(pid)
        if not success:
            print("❌ Failed to start profiler")
            return None
        
        # Collect data
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        samples = []
        
        print(f"📊 Collecting data... (Press Ctrl+C to stop early)")
        
        try:
            while time.time() < end_time:
                await asyncio.sleep(5)
                stats = self.profiler.get_current_stats()
                if stats:
                    sample = {
                        'timestamp': datetime.now().isoformat(),
                        'elapsed_seconds': time.time() - start_time,
                        **stats
                    }
                    samples.append(sample)
                    fps = stats.get('fps', 'N/A')
                    frame_time = stats.get('avgFrameTimeMs', 'N/A')
                    cmd_buffers = stats.get('commandBuffers', 0)
                    print(f"  [{time.strftime('%H:%M:%S')}] FPS: {fps} | Frame: {frame_time}ms | CmdBuffers: {cmd_buffers}")
        except KeyboardInterrupt:
            print("\n⚠️  Stopped early by user")
        
        # Stop profiling
        report = await self.profiler.stop()
        
        # Calculate statistics
        if samples:
            fps_values = [float(s.get('fps', 0)) for s in samples if s.get('fps') and s.get('fps') != 'N/A']
            frame_times = [float(s.get('avgFrameTimeMs', 0)) for s in samples if s.get('avgFrameTimeMs') and s.get('avgFrameTimeMs') != 'N/A']
            cmd_buffer_counts = [int(s.get('commandBuffers', 0)) for s in samples]
            
            scenario_result = {
                'scenario': name,
                'duration_minutes': duration_minutes,
                'samples_collected': len(samples),
                'statistics': {
                    'fps': {
                        'avg': sum(fps_values) / len(fps_values) if fps_values else 0,
                        'min': min(fps_values) if fps_values else 0,
                        'max': max(fps_values) if fps_values else 0,
                    },
                    'frame_time_ms': {
                        'avg': sum(frame_times) / len(frame_times) if frame_times else 0,
                        'min': min(frame_times) if frame_times else 0,
                        'max': max(frame_times) if frame_times else 0,
                    },
                    'command_buffers': {
                        'avg_per_5s': sum(cmd_buffer_counts) / len(cmd_buffer_counts) if cmd_buffer_counts else 0,
                        'total': sum(cmd_buffer_counts),
                    }
                },
                'profiler_report': {
                    'total_frames': report.total_frames if report else 0,
                    'avg_fps': report.avg_fps if report else 0,
                    'avg_frame_time_ms': report.avg_frame_time_ms if report else 0,
                    'percentile_99_frame_time': report.percentile_99_frame_time if report else 0,
                    'percentile_95_frame_time': report.percentile_95_frame_time if report else 0,
                } if report else None,
                'samples': samples[:100]  # Keep first 100 samples for detail
            }
            
            print(f"\n✓ Scenario complete: {len(samples)} samples collected")
            return scenario_result
        
        return None
    
    async def run_all_scenarios(self):
        """Run all baseline scenarios."""
        scenarios = [
            ("Dense Urban (Corpo Plaza)", 5),
            ("City Center", 5),
            ("Open World (Badlands)", 5),
            ("Interior Space (Apartment)", 5),
            ("Interior Space (Shop)", 5),
            ("Combat Scenario", 5),
        ]
        
        print("="*70)
        print("EXTENDED BASELINE PROFILER")
        print("Phase 1, Week 1: Collect 30+ minutes of gameplay data")
        print("="*70)
        
        if not self.profiler.is_available:
            print("❌ Frida not available. Install with: pip install frida")
            return
        
        pid = await self.profiler._find_game_process()
        if not pid:
            print("❌ Cyberpunk 2077 not running!")
            print("   Start the game first, then run this script again.")
            return
        
        print(f"✓ Found game process: PID {pid}\n")
        
        results = []
        for name, duration in scenarios:
            result = await self.run_scenario(name, duration)
            if result:
                results.append(result)
            
            # Ask if user wants to continue
            if result:
                print("\nContinue to next scenario? (y/n): ", end='')
                try:
                    response = await asyncio.to_thread(input)
                    if response.strip().lower() != 'y':
                        break
                except (EOFError, KeyboardInterrupt):
                    break
        
        # Save results
        if results:
            output_file = Path(__file__).parent.parent / "docs" / "baseline_profiling_results.json"
            output_file.parent.mkdir(exist_ok=True)
            
            summary = {
                'timestamp': datetime.now().isoformat(),
                'total_scenarios': len(results),
                'total_duration_minutes': sum(r['duration_minutes'] for r in results),
                'scenarios': results
            }
            
            with open(output_file, 'w') as f:
                json.dump(summary, f, indent=2)
            
            print(f"\n{'='*70}")
            print("BASELINE PROFILING COMPLETE")
            print(f"{'='*70}")
            print(f"Scenarios completed: {len(results)}")
            print(f"Total duration: {sum(r['duration_minutes'] for r in results)} minutes")
            print(f"Results saved to: {output_file}")
            
            # Print summary
            print("\n📊 Summary Statistics:")
            for result in results:
                stats = result['statistics']
                print(f"\n{result['scenario']}:")
                print(f"  Avg FPS: {stats['fps']['avg']:.1f}")
                print(f"  Avg Frame Time: {stats['frame_time_ms']['avg']:.2f}ms")
                print(f"  Avg CmdBuffers/5s: {stats['command_buffers']['avg_per_5s']:.0f}")


async def main():
    profiler = ExtendedBaselineProfiler()
    await profiler.run_all_scenarios()


if __name__ == "__main__":
    asyncio.run(main())
