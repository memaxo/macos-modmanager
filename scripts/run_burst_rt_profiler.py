#!/usr/bin/env python3
"""
Burst RT Profiler Runner
Phase 1, Week 2: Run burst RT profiler for short capture windows
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import frida
    # Verify we got the real frida
    if not hasattr(frida, 'attach'):
        print(f"❌ Wrong frida module loaded from: {getattr(frida, '__file__', 'unknown')}")
        sys.exit(1)
except ImportError as e:
    print(f"❌ Frida not available: {e}")
    print("   Install with: pip install frida")
    sys.exit(1)

from app.core.gpu_profiler import GPUProfiler


async def run_burst_rt_profiling(duration_seconds: int = 10, scenario: str = "unknown"):
    """Run burst RT profiling for specified duration."""
    print("="*70)
    print("BURST RT PROFILER")
    print(f"Scenario: {scenario}")
    print(f"Duration: {duration_seconds} seconds")
    print("="*70)
    
    # Find game process
    profiler = GPUProfiler()
    pid = await profiler._find_game_process()
    if not pid:
        print("❌ Cyberpunk 2077 not running!")
        return None
    
    print(f"✓ Found process: PID {pid}\n")
    
    # Load burst RT profiler script
    script_path = Path(__file__).parent / "frida_scripts" / "burst_rt_profiler.js"
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return None
    
    script_content = script_path.read_text()
    
    # Attach and load script
    print("🚀 Attaching Frida and loading burst RT profiler...")
    try:
        session = await asyncio.to_thread(frida.attach, pid)
        script = session.create_script(script_content)
        
        rt_reports = []
        
        def on_message(message, data):
            if message.get('type') == 'send':
                payload = message.get('payload', {})
                if payload.get('type') == 'rt_stats':
                    rt_reports.append({
                        'timestamp': datetime.now().isoformat(),
                        'data': payload.get('data', {})
                    })
        
        script.on('message', on_message)
        script.load()
        
        print("✓ Script loaded\n")
        
        # Enable RT profiling (use camelCase to match JS exports)
        print(f"📊 Enabling RT profiling for {duration_seconds} seconds...")
        result = script.exports_sync.enableRTProfiling({'durationSeconds': duration_seconds})
        print(f"✓ {result.get('status', 'unknown')}\n")
        
        # Wait for duration + buffer
        print("⏳ Collecting RT data...")
        await asyncio.sleep(duration_seconds + 2)  # Extra 2s buffer
        
        # Get final stats
        final_stats = script.exports_sync.getRTStats()
        
        # Disable profiling
        disable_result = script.exports_sync.disableRTProfiling()
        
        # Unload and detach
        script.unload()
        session.detach()
        
        print("\n✓ Profiling complete\n")
        
        # Compile results
        results = {
            'scenario': scenario,
            'duration_seconds': duration_seconds,
            'timestamp': datetime.now().isoformat(),
            'final_stats': final_stats,
            'reports': rt_reports,
            'summary': disable_result.get('report', {}) if disable_result else {}
        }
        
        return results
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Burst RT Profiler')
    parser.add_argument('--duration', type=int, default=10, help='Duration in seconds (max 15)')
    parser.add_argument('--scenario', type=str, default='unknown', help='Scenario name')
    parser.add_argument('--output', type=str, help='Output JSON file path')
    
    args = parser.parse_args()
    
    duration = min(args.duration, 15)  # Safety limit
    
    result = await run_burst_rt_profiling(duration, args.scenario)
    
    if result:
        # Print summary
        print("="*70)
        print("RT PROFILING RESULTS")
        print("="*70)
        
        final = result.get('final_stats', {})
        if final.get('status') == 'active' or 'acceleration_structures' in final:
            accel = final.get('acceleration_structures', {})
            print(f"\nAcceleration Structures:")
            print(f"  Created: {accel.get('created', 0)}")
            print(f"  Built: {accel.get('built', 0)}")
            print(f"  Refitted: {accel.get('refitted', 0)}")
            print(f"  Avg Build Time: {accel.get('avg_build_time_ms', '0')}ms")
            print(f"  Avg Refit Time: {accel.get('avg_refit_time_ms', '0')}ms")
            
            nodes = final.get('render_nodes', {})
            if any(nodes.values()):
                print(f"\nRT Render Nodes:")
                for node, count in nodes.items():
                    if count > 0:
                        print(f"  {node}: {count} calls")
        
        # Save to file
        output_file = Path(args.output) if args.output else (
            Path(__file__).parent.parent / "docs" / f"burst_rt_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
