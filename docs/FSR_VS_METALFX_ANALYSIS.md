# FSR vs MetalFX Analysis - Cyberpunk 2077 macOS

## Critical Finding: AAPL Optimizations Are for Ray Tracing, NOT Upscaling

After deep binary analysis, I've discovered that the Apple-specific optimizations we found are **entirely for ray tracing**, not for upscaling:

### AAPL Optimizations (Ray Tracing Only)

```
Ray Tracing Buffers:
├── aaplBucketsBuffer
├── aaplHitRayIndexBuffer
├── aaplMissRayIndexBuffer
├── aaplPayloadBuffer
├── aaplRayBuffer (Position, Direction, Radiance, Throughput, Flags, HitDistance)
├── aaplTracingAttributesBuffer
└── aaplRayLocalLightsInfos

ReSTIRGI Specific:
├── m_aaplReSTIRGIDiffuseBinOutputBuffer
├── m_aaplReSTIRGIDiffuseOuputBuffer
├── m_aaplReSTIRGISpecularBinOutputBuffer
└── m_aaplReSTIRGISpecularOuputBuffer

Denoising Shaders:
├── DenoisingRayTracingShaderMaskAAPL
├── DenoisingPathTracingShaderMaskAAPL
├── DenoisingRtxdiShaderMaskAAPL
└── DenoisingShaderPreferenceAAPL

Optimization Flags:
├── EnableReferenceAAPLOptim
└── UseAAPLOptimPass
```

**Conclusion**: `EnableReferenceAAPLOptim` and `UseAAPLOptimPass` affect **ray tracing performance**, not upscaling. Using MetalFX vs FSR will NOT change whether these optimizations are active.

---

## FSR vs MetalFX: Separate Implementations

### Key Discovery: They Are Independent

The game has **completely separate implementations** for FSR and MetalFX:

| Upscaler | Enable Flag | CustomData Type | Render Node |
|----------|-------------|-----------------|-------------|
| FSR 2.x | `m_FSR2Enabled` | `FSR2CustomData` | `CRenderNode_ApplyFSR2` |
| FSR 3.x | `m_FSR3Enabled` | `FSR3CustomData` | `CRenderNode_ApplyFSR3` |
| MetalFX | `m_MFXEnabled` | `MFXCustomData` | `CRenderNode_ApplyMFX` |

They are **mutually exclusive** - you use one or the other, not both simultaneously.

### Why FSR Might Feel Smoother

#### FSR Has Explicit Frame Pacing Infrastructure

Binary analysis shows FSR has comprehensive synchronization:

```
FSR Synchronization System:
├── FSR CompositionFence      - Synchronizes composition
├── FSR GameFence             - Syncs with game render
├── FSR InterpolationFence    - Frame generation sync
├── FSR PresentFence          - Presentation timing
├── FSR PresentQueue          - Dedicated present queue
├── FSR ReplacementBufferFence - Buffer swap sync
└── FSR Interpolation Async Queue - Async frame gen
```

#### MetalFX Has NO Visible Synchronization

No equivalent fences or queues found for MetalFX:
- Relies on Metal's internal synchronization
- May have hidden overhead from system-level wrapping
- Less direct integration with game render loop

### Theoretical Explanation

```
┌─────────────────────────────────────────────────────────────────┐
│                    FSR Implementation                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Game Render → FSR CompositionFence → FSR Compute → FSR Present │
│       │              │                     │              │     │
│       └──────────────┴─────────────────────┴──────────────┘     │
│                    Tight Integration                             │
│              Explicit Async Queues & Fences                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    MetalFX Implementation                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Game Render → MFX Wrapper → MTLFXTemporalScaler → Metal Present│
│       │              │              │                    │      │
│       │              │              │                    │      │
│       │         Framework Boundary  │                    │      │
│       │              │              │                    │      │
│       └──────────────┘              └────────────────────┘      │
│                                                                  │
│  Less direct integration - relies on Metal's internal sync      │
│  Potential overhead from framework crossing                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Matters

1. **FSR is more directly integrated** with the game's render pipeline
2. **MetalFX adds an abstraction layer** that may introduce micro-stutter
3. **FSR's explicit fences** allow tighter frame pacing control
4. **MetalFX relies on Metal system** synchronization which may not be optimized for this specific game

---

## Recommendations Based on Analysis

### For Smoothest Gameplay

| Priority | Recommendation | Reason |
|----------|----------------|--------|
| 1 | **Try FSR 2/3 over MetalFX** | Better frame pacing infrastructure |
| 2 | Enable RT only if AAPL opts work | AAPL optimizations are for RT, not upscaling |
| 3 | Use FSR 3 Frame Gen cautiously | Extra interpolation fences may help or hurt |

### For Best Visual Quality

| Priority | Recommendation | Reason |
|----------|----------------|--------|
| 1 | MetalFX or FSR at same quality | Should look identical |
| 2 | Enable sharpening (0.3-0.5) | Both support sharpening |

### For Ray Tracing

| Priority | Recommendation | Reason |
|----------|----------------|--------|
| 1 | Enable RT if using M3/M4 | Hardware RT + AAPL optimizations |
| 2 | Check if EnableReferenceAAPLOptim is on | This affects RT performance |
| 3 | RT Reflections > RT Shadows | Shadows are most expensive |

---

## Verification Steps

To confirm which upscaler is actually performing better for you:

### 1. Enable In-Game Stats Overlay
Look for `Overlay/Stats/GPUTime` and `GPU time: %1.2fms` in the overlay.

### 2. Compare Same Settings
- Set identical quality level (e.g., "Balanced" on both)
- Set identical sharpening
- Measure average frame time, not just FPS

### 3. Test Frame Pacing
Watch for:
- Micro-stutter (brief hitches)
- Frame time consistency (should be steady, not spikey)
- Input lag feel

### 4. Run Frida Probe
Use the `aapl_optimization_probe.js` script to see which upscaler is actually being called and their timing.

---

## Technical Details

### FSR Frame Generation Logging
```
FSR3 FPS: %1.2f (injected frames : %d)
Frame index, Frame time (ms), FSR3 Frame Generation (ms), CPU memory (MB), GPU memory (MB)
```

### MetalFX API Calls
```objc
MTLFXTemporalScaler
MTLFXSpatialScaler
newTemporalScalerWithDevice:
newSpatialScalerWithDevice:
encodeToCommandBuffer:
```

### Config Variables
```
m_FSR2Enabled, m_FSR2Quality, m_FSR2Sharpness
m_FSR3Enabled, m_FSR3Quality, m_FSR3Sharpness, m_FSR3FrameGenEnabled
m_MFXEnabled, m_MFXQuality, m_MFXSharpness
m_upscalingType  // Master selector
```

---

## Summary

| Question | Answer |
|----------|--------|
| Do AAPL opts affect upscaling? | **NO** - They're for ray tracing only |
| Is MetalFX required for AAPL opts? | **NO** - Independent systems |
| Why does FSR feel smoother? | Better frame pacing via explicit fences/queues |
| Should I use FSR over MetalFX? | **Try it** - binary analysis suggests FSR has tighter integration |
| What do AAPL opts actually do? | Optimize ray buffer management and denoising |

---

*Analysis based on Cyberpunk 2077 macOS binary (arm64, 151MB)*
*Last updated: December 2024*
