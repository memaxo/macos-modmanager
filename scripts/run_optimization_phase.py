#!/usr/bin/env python3
"""
Master Optimization Phase Runner
Executes complete optimization phases with automated workflows
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class OptimizationPhaseRunner:
    """Runs optimization phases with automated workflows."""
    
    def __init__(self):
        self.results_dir = Path(__file__).parent.parent / "docs" / "optimization_results"
        self.results_dir.mkdir(exist_ok=True, parents=True)
    
    async def run_phase1_week1(self):
        """Phase 1, Week 1: Extended baseline profiling."""
        print("="*70)
        print("PHASE 1, WEEK 1: Extended Baseline Profiling")
        print("="*70)
        
        from scripts.extended_baseline_profiler import ExtendedBaselineProfiler
        
        profiler = ExtendedBaselineProfiler()
        await profiler.run_all_scenarios()
        
        print("\n✓ Phase 1, Week 1 complete")
    
    async def run_phase1_week2(self):
        """Phase 1, Week 2: Burst RT profiler."""
        print("="*70)
        print("PHASE 1, WEEK 2: Burst RT Profiler")
        print("="*70)
        
        print("\nRunning burst RT profiler in different scenarios...")
        print("(This requires manual interaction - game must be running)\n")
        
        scenarios = [
            ("Static Scene", 10),
            ("Dynamic Scene", 10),
            ("RT-Heavy Scene", 10),
        ]
        
        from scripts.run_burst_rt_profiler import run_burst_rt_profiling
        
        results = []
        for scenario, duration in scenarios:
            print(f"\n📊 Scenario: {scenario}")
            print("   Navigate to scenario location, then press ENTER...")
            try:
                await asyncio.to_thread(input)
            except (EOFError, KeyboardInterrupt):
                break
            
            result = await run_burst_rt_profiling(duration, scenario)
            if result:
                results.append(result)
        
        if results:
            output_file = self.results_dir / f"phase1_week2_burst_rt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n✓ Results saved to: {output_file}")
        
        print("\n✓ Phase 1, Week 2 complete")
    
    async def run_phase2_week3(self):
        """Phase 2, Week 3: Command buffer profiling."""
        print("="*70)
        print("PHASE 2, WEEK 3: Command Buffer Profiling")
        print("="*70)
        
        from scripts.command_buffer_profiler import CommandBufferProfiler
        
        profiler = CommandBufferProfiler()
        result = await profiler.profile_command_buffers(duration_minutes=5)
        
        if result:
            output_file = self.results_dir / f"phase2_week3_cmd_buffer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\n✓ Results saved to: {output_file}")
        
        print("\n✓ Phase 2, Week 3 complete")
    
    async def run_rt_feature_benchmark(self):
        """RT feature toggle benchmarking."""
        print("="*70)
        print("RT FEATURE TOGGLE BENCHMARKING")
        print("="*70)
        
        from scripts.rt_feature_toggle_benchmark import RTFeatureBenchmark
        
        benchmark = RTFeatureBenchmark()
        await benchmark.run_all_benchmarks()
        
        print("\n✓ RT feature benchmarking complete")
    
    async def run_all_phases(self):
        """Run all phases sequentially."""
        print("="*70)
        print("COMPLETE OPTIMIZATION PLAN EXECUTION")
        print("="*70)
        print("\nThis will run all phases sequentially.")
        print("Each phase may require manual interaction.")
        print("\nPress ENTER to start, or Ctrl+C to cancel...")
        
        try:
            await asyncio.to_thread(input)
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled")
            return
        
        phases = [
            ("Phase 1, Week 1: Extended Baseline", self.run_phase1_week1),
            ("Phase 1, Week 1: RT Feature Benchmark", self.run_rt_feature_benchmark),
            ("Phase 1, Week 2: Burst RT Profiler", self.run_phase1_week2),
            ("Phase 2, Week 3: Command Buffer Profiling", self.run_phase2_week3),
        ]
        
        for phase_name, phase_func in phases:
            print(f"\n{'='*70}")
            print(f"STARTING: {phase_name}")
            print(f"{'='*70}\n")
            
            try:
                await phase_func()
            except KeyboardInterrupt:
                print(f"\n⚠️  {phase_name} interrupted by user")
                print("Continue to next phase? (y/n): ", end='')
                try:
                    response = await asyncio.to_thread(input)
                    if response.strip().lower() != 'y':
                        break
                except (EOFError, KeyboardInterrupt):
                    break
            except Exception as e:
                print(f"\n❌ Error in {phase_name}: {e}")
                import traceback
                traceback.print_exc()
                print("\nContinue to next phase? (y/n): ", end='')
                try:
                    response = await asyncio.to_thread(input)
                    if response.strip().lower() != 'y':
                        break
                except (EOFError, KeyboardInterrupt):
                    break
        
        print("\n" + "="*70)
        print("OPTIMIZATION PLAN EXECUTION COMPLETE")
        print("="*70)
        print(f"\nResults saved to: {self.results_dir}")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Optimization Phase Runner')
    parser.add_argument('phase', nargs='?', choices=[
        'phase1-week1', 'phase1-week2', 'phase2-week3',
        'rt-benchmark', 'all'
    ], default='all', help='Phase to run')
    
    args = parser.parse_args()
    
    runner = OptimizationPhaseRunner()
    
    if args.phase == 'phase1-week1':
        await runner.run_phase1_week1()
    elif args.phase == 'phase1-week2':
        await runner.run_phase1_week2()
    elif args.phase == 'phase2-week3':
        await runner.run_phase2_week3()
    elif args.phase == 'rt-benchmark':
        await runner.run_rt_feature_benchmark()
    elif args.phase == 'all':
        await runner.run_all_phases()


if __name__ == "__main__":
    asyncio.run(main())
