#!/usr/bin/env python3
"""
RT Feature Toggle Benchmarking
Phase 1, Week 1: Measure impact of each RT feature independently
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.gpu_profiler import get_profiler


class RTFeatureBenchmark:
    """Benchmarks RT features by toggling them on/off."""
    
    def __init__(self):
        self.profiler = get_profiler()
        self.results = []
    
    async def benchmark_feature(self, feature_name: str, duration_minutes: int = 5) -> dict:
        """Benchmark a single RT feature."""
        print(f"\n{'='*70}")
        print(f"BENCHMARKING: {feature_name}")
        print(f"{'='*70}\n")
        
        # Test with feature OFF
        print(f"📊 Testing with {feature_name} OFF...")
        print("   Please disable this feature in game settings")
        print("   Navigate to a consistent location")
        print("   Press ENTER when ready, or 'skip' to skip this feature")
        
        try:
            user_input = await asyncio.to_thread(input)
            if user_input.strip().lower() == 'skip':
                return None
        except (EOFError, KeyboardInterrupt):
            return None
        
        pid = await self.profiler._find_game_process()
        if not pid:
            print("❌ Game not running!")
            return None
        
        # Profile OFF state
        await self.profiler.start(pid)
        off_samples = []
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        print(f"📊 Collecting data (OFF state)...")
        try:
            while time.time() < end_time:
                await asyncio.sleep(5)
                stats = self.profiler.get_current_stats()
                if stats:
                    off_samples.append({
                        'timestamp': datetime.now().isoformat(),
                        **stats
                    })
                    fps = stats.get('fps', 'N/A')
                    print(f"  [{time.strftime('%H:%M:%S')}] FPS: {fps}")
        except KeyboardInterrupt:
            pass
        
        off_report = await self.profiler.stop()
        
        # Test with feature ON
        print(f"\n📊 Testing with {feature_name} ON...")
        print("   Please enable this feature in game settings")
        print("   Stay in the same location")
        print("   Press ENTER when ready")
        
        try:
            await asyncio.to_thread(input)
        except (EOFError, KeyboardInterrupt):
            return None
        
        # Profile ON state
        await self.profiler.start(pid)
        on_samples = []
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        print(f"📊 Collecting data (ON state)...")
        try:
            while time.time() < end_time:
                await asyncio.sleep(5)
                stats = self.profiler.get_current_stats()
                if stats:
                    on_samples.append({
                        'timestamp': datetime.now().isoformat(),
                        **stats
                    })
                    fps = stats.get('fps', 'N/A')
                    print(f"  [{time.strftime('%H:%M:%S')}] FPS: {fps}")
        except KeyboardInterrupt:
            pass
        
        on_report = await self.profiler.stop()
        
        # Calculate impact
        if off_samples and on_samples:
            off_fps = [float(s.get('fps', 0)) for s in off_samples if s.get('fps') and s.get('fps') != 'N/A']
            on_fps = [float(s.get('fps', 0)) for s in on_samples if s.get('fps') and s.get('fps') != 'N/A']
            
            if off_fps and on_fps:
                avg_off_fps = sum(off_fps) / len(off_fps)
                avg_on_fps = sum(on_fps) / len(on_fps)
                fps_delta = avg_on_fps - avg_off_fps
                fps_delta_percent = (fps_delta / avg_off_fps * 100) if avg_off_fps > 0 else 0
                
                result = {
                    'feature': feature_name,
                    'duration_minutes': duration_minutes,
                    'off_state': {
                        'avg_fps': avg_off_fps,
                        'samples': len(off_samples),
                        'profiler_report': {
                            'total_frames': off_report.total_frames if off_report else 0,
                            'avg_fps': off_report.avg_fps if off_report else 0,
                            'avg_frame_time_ms': off_report.avg_frame_time_ms if off_report else 0,
                        } if off_report else None
                    },
                    'on_state': {
                        'avg_fps': avg_on_fps,
                        'samples': len(on_samples),
                        'profiler_report': {
                            'total_frames': on_report.total_frames if on_report else 0,
                            'avg_fps': on_report.avg_fps if on_report else 0,
                            'avg_frame_time_ms': on_report.avg_frame_time_ms if on_report else 0,
                        } if on_report else None
                    },
                    'impact': {
                        'fps_delta': fps_delta,
                        'fps_delta_percent': fps_delta_percent,
                        'performance_cost': abs(fps_delta_percent) if fps_delta_percent < 0 else 0
                    }
                }
                
                print(f"\n✓ Benchmark complete:")
                print(f"  OFF: {avg_off_fps:.1f} FPS")
                print(f"  ON:  {avg_on_fps:.1f} FPS")
                print(f"  Impact: {fps_delta:+.1f} FPS ({fps_delta_percent:+.1f}%)")
                
                return result
        
        return None
    
    async def run_all_benchmarks(self):
        """Run benchmarks for all RT features."""
        features = [
            "RT Shadows",
            "RT Reflections",
            "RT Global Illumination",
            "Path Tracing",
        ]
        
        print("="*70)
        print("RT FEATURE TOGGLE BENCHMARKING")
        print("Phase 1, Week 1: Measure impact of each RT feature")
        print("="*70)
        
        if not self.profiler.is_available:
            print("❌ Frida not available")
            return
        
        results = []
        for feature in features:
            result = await self.benchmark_feature(feature, duration_minutes=5)
            if result:
                results.append(result)
            
            print("\nContinue to next feature? (y/n): ", end='')
            try:
                response = await asyncio.to_thread(input)
                if response.strip().lower() != 'y':
                    break
            except (EOFError, KeyboardInterrupt):
                break
        
        # Save results
        if results:
            output_file = Path(__file__).parent.parent / "docs" / "rt_feature_benchmark_results.json"
            output_file.parent.mkdir(exist_ok=True)
            
            # Sort by performance cost (highest first)
            results.sort(key=lambda x: x['impact']['performance_cost'], reverse=True)
            
            summary = {
                'timestamp': datetime.now().isoformat(),
                'features_tested': len(results),
                'results': results,
                'ranking': [
                    {
                        'feature': r['feature'],
                        'performance_cost_percent': r['impact']['performance_cost'],
                        'fps_delta': r['impact']['fps_delta']
                    }
                    for r in results
                ]
            }
            
            with open(output_file, 'w') as f:
                json.dump(summary, f, indent=2)
            
            print(f"\n{'='*70}")
            print("BENCHMARKING COMPLETE")
            print(f"{'='*70}")
            print(f"Features tested: {len(results)}")
            print(f"Results saved to: {output_file}")
            
            print("\n📊 Feature Impact Ranking (Highest Cost First):")
            for i, r in enumerate(results, 1):
                print(f"{i}. {r['feature']}: {r['impact']['performance_cost']:.1f}% cost ({r['impact']['fps_delta']:+.1f} FPS)")


async def main():
    benchmark = RTFeatureBenchmark()
    await benchmark.run_all_benchmarks()


if __name__ == "__main__":
    asyncio.run(main())
