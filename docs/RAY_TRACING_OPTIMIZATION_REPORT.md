# Ray/Path Tracing Optimization Diagnostics Report

**Generated:** 2026-01-01  
**Status:** Baseline established, ready for runtime profiling

---

## Executive Summary

The Cyberpunk 2077 macOS binary contains **174 ray tracing symbols** and **8 FSR symbols**, indicating significant RT infrastructure. The game is **not currently running**, so runtime profiling requires starting the game first.

**Key Finding:** Binary analysis confirms RT support exists, but we need **Metal System Trace captures** to determine if it's using **Metal hardware RT APIs** or **software RT in compute shaders**. This distinction determines the optimization strategy.

---

## Binary Analysis Results

### Symbol Detection

| Category | Count | Status |
|----------|-------|--------|
| **Ray Tracing Symbols** | 174 | ✅ Detected |
| **FSR Symbols** | 8 | ✅ Detected |
| **MetalFX Symbols** | 0 | ⚠️ Not found in exports |
| **Metal Frameworks** | 2 | ✅ Linked |

### Sample Ray Tracing Symbols

The binary contains RT-related symbols including:
- `PoolRaytrace` memory pools
- `GPUM_Buffer_Ray*` GPU buffer types
- RT-specific render node infrastructure

**Interpretation:** The game has RT infrastructure, but symbol names suggest it may be using **custom RT abstractions** rather than direct Metal RT API calls. This needs verification via Instruments.

### Sample FSR Symbols

- `CRenderNode_ApplyFSR2` / `CRenderNode_ApplyFSR3` render nodes
- `FSR2CustomData` / `FSR3CustomData` type hashes

**Interpretation:** FSR is integrated as render nodes, which aligns with the frame timing analyzer's hook targets.

---

## Profiler Status

- ✅ **Frida Python bindings:** Available (v16.7.19)
- ✅ **Profiler module:** Importable and functional
- ⚠️ **Game process:** Not running (attach test skipped)

---

## Next Steps for Ray/Path Tracing Optimization

### Phase 1: Confirm RT Implementation Type (CRITICAL)

**Goal:** Determine if RT uses Metal hardware acceleration or software compute.

**Action Items:**
1. **Start Cyberpunk 2077** and load into gameplay
2. **Enable ray tracing** in graphics settings
3. **Capture Metal System Trace** (Xcode → Instruments → Metal System Trace):
   - Look for `dispatchRays` calls → indicates **hardware RT**
   - Look for compute shader dispatches with RT-like names → indicates **software RT**
   - Check acceleration structure creation/build frequency

**Expected Outcome:** Clear answer: "Hardware RT" or "Software RT" → determines optimization approach

---

### Phase 2: Create Burst RT Profiler (High Priority)

**Goal:** Add opt-in RT hooks for short capture windows without destabilizing gameplay.

**Implementation Plan:**
1. Extend `scripts/frida/metal_profiler.js` with RT-specific hooks:
   ```javascript
   // Opt-in RT profiling (disabled by default)
   CONFIG.profileRayTracing = false;  // Safe default
   
   // When enabled, hook:
   // - Acceleration structure creation/build/refit
   // - Ray dispatch calls (dispatchRays or compute equivalents)
   // - Denoiser passes
   ```

2. Add `rpc.exports.enableRTProfiling()` / `disableRTProfiling()` for runtime toggle

3. Capture window: 5-15 seconds max to avoid instability

**Metrics to Collect:**
- Acceleration structure creation count per frame
- Acceleration structure build/refit time
- Ray dispatch count and timing
- Denoiser pass count and timing
- RT buffer allocation patterns

---

### Phase 3: Benchmark RT Feature Toggles (High Priority)

**Goal:** Identify which RT features have the highest cost/benefit ratio.

**Test Matrix:**

| Feature | Baseline (OFF) | Test (ON) | Measure |
|---------|----------------|-----------|---------|
| RT Shadows | FPS, P99 | FPS, P99 | Delta |
| RT Reflections | FPS, P99 | FPS, P99 | Delta |
| Path Tracing | FPS, P99 | FPS, P99 | Delta |
| Denoiser Quality | Low | High | Delta |

**Execution:**
1. Use safe-continuous profiler to establish baseline (RT OFF)
2. Enable one RT feature at a time
3. Capture 30-60 seconds of gameplay
4. Compare metrics

**Expected Outcome:** Rank RT features by performance impact → prioritize optimizations

---

### Phase 4: Apple Silicon Specific Optimizations (Medium Priority)

**Goal:** Verify and optimize Apple-specific RT paths.

**Checks:**

1. **AAPL Optimization Flags** (from `aapl_optimization_probe.js`):
   - `EnableReferenceAAPLOptim` - should be enabled
   - `UseAAPLOptimPass` - should be enabled
   - Verify at runtime (not just binary presence)

2. **RT Buffer Storage Modes:**
   - Use `StorageModePrivate` for RT buffers (no CPU access needed)
   - Avoid `StorageModeManaged` (causes CPU-GPU copies)
   - Profile with `metal_profiler.js` memory hooks

3. **Async Compute Queue Usage:**
   - RT/denoise should run on async compute queue
   - Check Metal System Trace for queue overlap/contention

---

## Implementation Priority

1. **IMMEDIATE:** Start game, capture Metal System Trace → confirm RT type
2. **HIGH:** Build burst RT profiler → collect RT-specific metrics
3. **HIGH:** Run RT feature toggle benchmarks → identify bottlenecks
4. **MEDIUM:** Verify AAPL optimizations → Apple Silicon tuning
5. **LOW:** Long-term: optimize based on findings

---

## Risk Mitigation

- **Burst profiler only:** RT hooks disabled by default to prevent freezes
- **Short capture windows:** 5-15 seconds max per capture
- **Safe-continuous baseline:** Use existing safe profiler for comparison
- **Instruments first:** Use Apple's tools before heavy Frida hooks

---

## Success Criteria

- ✅ Binary analysis complete (this report)
- ⏳ RT implementation type confirmed (requires game + Instruments)
- ⏳ Burst RT profiler functional (requires implementation)
- ⏳ RT feature benchmarks complete (requires game + profiler)
- ⏳ Optimization recommendations actionable (requires data)

---

## Notes

- **MetalFX symbols not found:** May be statically linked or using different naming. Frame timing analyzer can detect via ObjC class presence (`MTLFXTemporalScaler`).
- **174 RT symbols:** High count suggests extensive RT infrastructure. Need to determine if it's hardware-accelerated or software-based.
- **Profiler ready:** Safe-continuous mode is functional and ready for baseline measurements once game is running.

---

**Next Action:** Start Cyberpunk 2077, enable RT, capture Metal System Trace to confirm implementation type.
