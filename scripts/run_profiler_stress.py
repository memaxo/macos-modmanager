"""
Dev stress harness for the Frida-based GPUProfiler.

This is intended for manual validation on a machine where Cyberpunk 2077 is running.

What this catches:
- attach/detach stability regressions
- leaks/backpressure regressions (indirectly via increasing attach time / failures)
- "double start" or rapid toggling issues

Example:
  python scripts/run_profiler_stress.py --cycles 50 --run-seconds 5 --sleep-seconds 1
"""

import argparse
import asyncio
import time

from app.core.gpu_profiler import get_profiler


async def run(cycles: int, run_seconds: float, sleep_seconds: float) -> int:
    profiler = get_profiler()

    if not profiler.is_available:
        print("ERROR: profiler is not available (missing frida python bindings?).")
        return 2

    failures = 0
    attach_times: list[float] = []
    detach_times: list[float] = []

    for i in range(1, cycles + 1):
        t0 = time.time()
        ok = await profiler.start()
        t1 = time.time()

        attach_dt = t1 - t0
        attach_times.append(attach_dt)

        if not ok:
            failures += 1
            print(f"[{i}/{cycles}] start FAILED (attach_dt={attach_dt:.3f}s)")
            # backoff a bit in case the target is in a transient state
            await asyncio.sleep(max(1.0, sleep_seconds))
            continue

        print(f"[{i}/{cycles}] started (attach_dt={attach_dt:.3f}s)")
        await asyncio.sleep(run_seconds)

        t2 = time.time()
        _ = await profiler.stop()
        t3 = time.time()

        detach_dt = t3 - t2
        detach_times.append(detach_dt)

        print(f"[{i}/{cycles}] stopped (detach_dt={detach_dt:.3f}s)")
        await asyncio.sleep(sleep_seconds)

    if attach_times:
        print("")
        print(f"attach avg: {sum(attach_times)/len(attach_times):.3f}s, max: {max(attach_times):.3f}s")
    if detach_times:
        print(f"detach avg: {sum(detach_times)/len(detach_times):.3f}s, max: {max(detach_times):.3f}s")

    print(f"failures: {failures}/{cycles}")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=50)
    parser.add_argument("--run-seconds", type=float, default=5.0)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    args = parser.parse_args()

    raise SystemExit(asyncio.run(run(args.cycles, args.run_seconds, args.sleep_seconds)))


if __name__ == "__main__":
    main()

