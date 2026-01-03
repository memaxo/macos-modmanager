#!/usr/bin/env python3
"""
Persistent Metal Profiler Runner for Cyberpunk 2077 macOS

Attaches Frida to the game and keeps the profiler running,
collecting and displaying real-time performance data.
"""

import sys
import signal
import time
from pathlib import Path

import frida

SCRIPT_PATH = Path(__file__).parent / "frida" / "metal_profiler.js"

def on_message(message, data):
    """Handle messages from the Frida script."""
    if message['type'] == 'send':
        payload = message['payload']
        if isinstance(payload, dict) and payload.get('type') == 'report':
            report = payload['data']
            print("\n" + "=" * 70)
            print("📊 METAL PROFILER REPORT")
            print("=" * 70)
            perf = report.get('performance', {})
            print(f"FPS: {perf.get('fps', 'N/A')} | Frame: {perf.get('avgFrameTimeMs', 'N/A')}ms | P99: {perf.get('p99FrameTimeMs', 'N/A')}ms")
            
            upscale = report.get('upscaling', {})
            print(f"Upscaling: {upscale.get('type', 'none')} | Calls: {upscale.get('calls', 0)} | Avg: {upscale.get('avgTimeMs', 0)}ms")
            
            rt = report.get('rayTracing', {})
            print(f"Ray Tracing: AccelStructs: {rt.get('accelerationStructures', 0)} | Dispatches: {rt.get('dispatches', 0)}")
            
            mem = report.get('memory', {})
            print(f"Memory: Buffers: {mem.get('bufferMB', 0)}MB | Textures: {mem.get('texturesAllocated', 0)}")
            
            storage = mem.get('storageModes', {})
            print(f"Storage Modes: Shared:{storage.get('shared', 0)} Managed:{storage.get('managed', 0)} Private:{storage.get('private', 0)}")
            
            bottlenecks = report.get('bottlenecks', [])
            if bottlenecks:
                print("\n⚠️  BOTTLENECKS:")
                for b in bottlenecks:
                    print(f"   [{b.get('severity', '?').upper()}] {b.get('type', '?')}: {b.get('message', '?')}")
            
            print("=" * 70)
    elif message['type'] == 'error':
        print(f"❌ Error: {message.get('description', message)}")
    else:
        print(f"[Frida] {message}")


def main():
    print("=" * 70)
    print("🎮 Cyberpunk 2077 macOS Metal Profiler")
    print("=" * 70)
    
    # Find game process
    print("\n🔍 Looking for Cyberpunk 2077 process...")
    
    try:
        device = frida.get_local_device()
        processes = [p for p in device.enumerate_processes() if 'Cyberpunk' in p.name]
        
        if not processes:
            print("❌ Cyberpunk 2077 not running!")
            print("   Launch the game first, then run this profiler.")
            sys.exit(1)
        
        process = processes[0]
        print(f"✅ Found: {process.name} (PID: {process.pid})")
        
    except Exception as e:
        print(f"❌ Error finding process: {e}")
        sys.exit(1)
    
    # Load script
    if not SCRIPT_PATH.exists():
        print(f"❌ Script not found: {SCRIPT_PATH}")
        sys.exit(1)
    
    script_code = SCRIPT_PATH.read_text()
    print(f"📜 Loaded profiler script: {SCRIPT_PATH.name}")
    
    # Attach to process
    print(f"\n🔗 Attaching to PID {process.pid}...")
    
    try:
        session = device.attach(process.pid)
        script = session.create_script(script_code)
        script.on('message', on_message)
        script.load()
        
        print("✅ Profiler attached and running!")
        print("\n" + "=" * 70)
        print("📈 Collecting performance data... (Press Ctrl+C to stop)")
        print("=" * 70)
        
        # Keep running until interrupted
        def signal_handler(sig, frame):
            print("\n\n🛑 Stopping profiler...")
            script.unload()
            session.detach()
            print("✅ Profiler detached cleanly")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Keep alive
        while True:
            time.sleep(1)
            
    except frida.ProcessNotFoundError:
        print(f"❌ Process {process.pid} not found (game may have closed)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error attaching: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
