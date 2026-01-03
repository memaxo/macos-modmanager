# Frida Profiler Stress Testing (macOS)

This project’s Frida instrumentation is designed to run in **safe continuous mode** during gameplay. The most important regressions to catch are:

- attach/detach instability over repeated runs
- “backpressure” style freezes (too much output / heavy work in render hooks)
- accumulating overhead (hook explosions, runaway timers)

## Prerequisites

- Cyberpunk 2077 running (native macOS build)
- `frida` Python bindings installed in the mod manager environment
  - `pip install frida`

## Repeat attach/detach stress test

Use the dev harness:

```bash
PYTHONPATH=. python scripts/run_profiler_stress.py --cycles 50 --run-seconds 5 --sleep-seconds 1
```

### What to watch

- **Failures**: any non-zero failures indicates attach/detach instability.
- **Attach time drift**: attach time should remain stable. A rising max/avg suggests contention or leaked resources.
- **Game responsiveness**: the game should never “freeze” while the profiler is active.

## Soak test (long continuous run)

You can approximate a soak test by running fewer cycles with longer run duration:

```bash
PYTHONPATH=. python scripts/run_profiler_stress.py --cycles 3 --run-seconds 600 --sleep-seconds 5
```

### Metrics to monitor during soak

- FPS stability (no sudden collapse when hooks are active)
- CPU usage changes when toggling start/stop
- Any crash/hang on stop (detach)

