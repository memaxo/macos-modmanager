# GPU/CPU/Memory Profiler Exploration for Cyberpunk 2077 macOS

## Executive Summary

**Theory**: Path tracing and ray tracing are unoptimized for macOS, and there are real performance gains possible if MetalFX/AMD FSR/Apple Silicon GPU were properly optimized.

**Key Insight**: MetalFX is built on AMD's FidelityFX Super Resolution (FSR) technology under an MIT license. Apple has wrapped FSR in their proprietary MetalFX framework but hasn't necessarily optimized it for Apple Silicon's unified memory architecture.

## Current State of Upscaling in Cyberpunk 2077 macOS

### Available Technologies
Based on SDK analysis, the game supports:

| Technology | SDK Field | Status |
|------------|-----------|--------|
| FSR 1.0 | `FSREnabled`, `FSRQuality` | Available |
| FSR 2.x | `FSR2Enabled`, `FSR2Quality`, `FSR2Sharpness` | Available |
| FSR 3.x | `FSR3Enabled`, `FSR3Quality`, `FSR3Sharpness`, `FSR3FrameGenEnabled` | Available |
| FSR 4.x | `FSR4Enabled`, `FSR4Quality`, `FSR4Sharpness` | Available |
| MetalFX | Wrapped FSR implementation | macOS only |
| DLSS/XeSS | Windows-only | N/A on macOS |

### Ray Tracing Data Structures Found

```cpp
// From RED4ext.SDK analysis:
struct BenchmarkSummary {
    // Upscaling
    uint8_t upscalingType;           // 0x184
    uint8_t frameGenerationType;     // 0x185
    
    // FSR variants
    bool FSR2Enabled;                // 0x1A8
    int32_t FSR2Quality;             // 0x1AC
    float FSR2Sharpness;             // 0x1B0
    
    bool FSR3Enabled;                // 0x1B4
    int32_t FSR3Quality;             // 0x1B8
    float FSR3Sharpness;             // 0x1BC
    bool FSR3FrameGenEnabled;        // 0x1C0
    
    bool FSR4Enabled;                // 0x1C1
    int32_t FSR4Quality;             // 0x1C4
    float FSR4Sharpness;             // 0x1C8
    
    // Ray Tracing
    bool rayTracingEnabled;          // 0x1F0
    bool rayTracedReflections;       // 0x1F1
    bool rayTracedSunShadows;        // 0x1F2
    bool rayTracedLocalShadows;      // 0x1F3
    int32_t rayTracedLightingQuality; // 0x1F4
    bool rayTracedPathTracingEnabled; // 0x1F8
};
```

## Potential Optimization Targets

### 1. MetalFX/FSR Integration Points

MetalFX wraps AMD FSR, but there are several potential inefficiencies:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Current Flow (Suspected)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Game Render → FSR Upscale → MetalFX Wrapper → Metal Present    │
│       │              │              │                │          │
│       │              │              │                │          │
│       ▼              ▼              ▼                ▼          │
│  [GPU Memory]  [CPU Copy?]   [GPU Memory]     [Display]         │
│                                                                  │
│  ISSUE: Potential unnecessary memory copies between FSR         │
│         compute and MetalFX presentation                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Optimized Flow (Target)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Game Render → FSR Upscale (Metal Compute) → Metal Present      │
│       │              │                              │           │
│       ▼              ▼                              ▼           │
│  [Unified Memory - Zero Copy Throughout]       [Display]        │
│                                                                  │
│  GOAL: Leverage Apple Silicon unified memory for zero-copy      │
│        upscaling pipeline                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Ray Tracing Inefficiencies

Ray tracing on Apple Silicon likely uses software raytracing or Metal's limited RT capabilities:

- **BVH Construction**: Acceleration structures may not be optimized for Apple GPU architecture
- **Ray-Triangle Intersection**: Software fallback instead of hardware acceleration
- **Denoising**: May be using generic denoiser instead of optimized Apple Neural Engine

### 3. Memory Bandwidth Bottlenecks

Apple Silicon has unified memory but:
- Default buffer allocations may use wrong storage mode
- Texture mipmaps may not be optimally streamed
- Command buffer scheduling may cause GPU stalls

## Proposed Frida Hooks for Profiling

### Target Libraries to Hook

```javascript
// Metal Framework
const metalLib = 'Metal';
// Possible FSR/MetalFX implementation
const gameLib = 'Cyberpunk2077';

// Key Metal APIs to profile
const metalHooks = {
    // Command buffer timing
    'MTLCommandBuffer_commit': 'Track GPU work submission',
    'MTLCommandBuffer_waitUntilCompleted': 'Detect CPU/GPU sync points',
    
    // Render pass tracking
    'MTLRenderCommandEncoder_endEncoding': 'Render pass completion',
    'MTLComputeCommandEncoder_endEncoding': 'Compute pass completion',
    
    // Memory allocation
    'MTLDevice_newBufferWithLength': 'Track buffer allocations',
    'MTLDevice_newTextureWithDescriptor': 'Track texture allocations',
    
    // Upscaling detection
    'MTLFXSpatialScaler': 'MetalFX spatial upscaling',
    'MTLFXTemporalScaler': 'MetalFX temporal upscaling',
};
```

### Specific Hook Targets

```javascript
// FSR-related function signatures to find in binary
const fsrSignatures = [
    // FSR 2.0 context creation
    'ffxFsr2ContextCreate',
    'ffxFsr2ContextDispatch',
    'ffxFsr2ContextDestroy',
    
    // FSR 3.0 frame interpolation
    'ffxFsr3ContextCreate',
    'ffxFsr3UpscalerContextDispatch',
    'ffxFrameInterpolationDispatch',
    
    // AMD GPUOpen common
    'ffxCreateContext',
    'ffxDispatch',
];

// MetalFX specific
const metalFXSignatures = [
    'MTLFXSpatialScalerDescriptor',
    'MTLFXTemporalScalerDescriptor',
    'encodeToCommandBuffer',
];
```

## Profiler Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GPU Profiler Architecture                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Frida Instrumentation                    │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │ │
│  │  │  Metal   │  │   FSR    │  │  Memory  │  │   CPU    │   │ │
│  │  │  Hooks   │  │  Hooks   │  │  Hooks   │  │  Timing  │   │ │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │ │
│  │       │             │             │             │          │ │
│  │       └─────────────┴─────────────┴─────────────┘          │ │
│  │                          │                                  │ │
│  └──────────────────────────┼──────────────────────────────────┘ │
│                             ▼                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   Data Collection Layer                     │ │
│  │                                                             │ │
│  │  • Frame timing (CPU + GPU)                                 │ │
│  │  • Memory allocation patterns                               │ │
│  │  • Upscaling pass duration                                  │ │
│  │  • Ray tracing kernel times                                 │ │
│  │  • Command buffer utilization                               │ │
│  │                                                             │ │
│  └─────────────────────────┬───────────────────────────────────┘ │
│                            ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   Analysis Engine                           │ │
│  │                                                             │ │
│  │  • Bottleneck detection                                     │ │
│  │  • Memory bandwidth analysis                                │ │
│  │  • GPU/CPU sync point identification                        │ │
│  │  • Optimization recommendations                             │ │
│  │                                                             │ │
│  └─────────────────────────┬───────────────────────────────────┘ │
│                            ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   Mod Manager UI                            │ │
│  │                                                             │ │
│  │  Real-time graphs, flame charts, recommendations            │ │
│  │                                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Binary Analysis Strategy

### Step 1: Identify FSR/MetalFX Symbols

```bash
# Find FSR-related symbols in game binary
nm -gU "/path/to/Cyberpunk2077" | grep -i "fsr\|fidelity\|upscal\|metalfx"

# Check linked frameworks
otool -L "/path/to/Cyberpunk2077" | grep -i "metal\|fsr"

# Dump Objective-C classes (MetalFX uses ObjC)
class-dump "/path/to/Cyberpunk2077" | grep -A 20 "MTLFX"
```

### Step 2: Find Render Pipeline Functions

```javascript
// Frida script to enumerate game functions
const gameModule = Process.getModuleByName('Cyberpunk2077');

Memory.scan(gameModule.base, gameModule.size, 'FF 83 ?? ?? ?? ?? 48 89', {
    onMatch: (address, size) => {
        // Analyze potential render loop functions
        console.log('Potential render function at:', address);
    }
});

// Search for FSR string references
Memory.scanSync(gameModule.base, gameModule.size, 'FSR'.split('').map(c => c.charCodeAt(0).toString(16)).join(' '));
```

### Step 3: Hook MetalFX Temporal Scaler

```javascript
// Hook MetalFX upscaling
if (ObjC.available) {
    const MTLFXTemporalScaler = ObjC.classes.MTLFXTemporalScaler;
    
    if (MTLFXTemporalScaler) {
        Interceptor.attach(MTLFXTemporalScaler['- encodeToCommandBuffer:'].implementation, {
            onEnter: function(args) {
                this.startTime = Date.now();
                send({ type: 'metalfx_start', time: this.startTime });
            },
            onLeave: function(retval) {
                const duration = Date.now() - this.startTime;
                send({ type: 'metalfx_end', duration: duration });
            }
        });
    }
}
```

## Potential Optimizations to Test

### 1. Buffer Storage Mode Optimization

```javascript
// Hook buffer creation to analyze storage modes
Interceptor.attach(ObjC.classes.MTLDevice['- newBufferWithLength:options:'].implementation, {
    onEnter: function(args) {
        const length = args[2].toInt32();
        const options = args[3].toInt32();
        
        // MTLResourceStorageModeShared = 0
        // MTLResourceStorageModeManaged = 1  
        // MTLResourceStorageModePrivate = 2
        
        const storageMode = (options >> 4) & 0xF;
        
        send({
            type: 'buffer_alloc',
            size: length,
            storageMode: storageMode,
            // Shared mode on Apple Silicon = optimal for unified memory
            optimal: storageMode === 0 || storageMode === 2
        });
    }
});
```

### 2. Command Buffer Batching Analysis

```javascript
// Track command buffer submission patterns
let commandBufferCount = 0;
let lastFrameTime = Date.now();

Interceptor.attach(ObjC.classes.MTLCommandBuffer['- commit'].implementation, {
    onEnter: function(args) {
        commandBufferCount++;
        
        const now = Date.now();
        if (now - lastFrameTime > 16) { // New frame (60fps)
            send({
                type: 'frame_stats',
                commandBuffers: commandBufferCount,
                frameTime: now - lastFrameTime
            });
            commandBufferCount = 0;
            lastFrameTime = now;
        }
    }
});
```

### 3. GPU Timestamp Profiling

```javascript
// Use Metal's GPU timestamps for accurate timing
const sampleTimestamps = ObjC.classes.MTLDevice['- sampleTimestamps:gpuTimestamp:'];

function profileGPUWork(device, workBlock) {
    const cpuStart = Memory.alloc(8);
    const gpuStart = Memory.alloc(8);
    const cpuEnd = Memory.alloc(8);
    const gpuEnd = Memory.alloc(8);
    
    // Sample before
    device.sampleTimestamps_(cpuStart, gpuStart);
    
    workBlock();
    
    // Sample after
    device.sampleTimestamps_(cpuEnd, gpuEnd);
    
    return {
        cpuDuration: cpuEnd.readU64().sub(cpuStart.readU64()),
        gpuDuration: gpuEnd.readU64().sub(gpuStart.readU64())
    };
}
```

## Expected Findings & Optimization Opportunities

### Hypothesis 1: Unnecessary Memory Copies
**Theory**: FSR output may be copied to a separate MetalFX buffer before presentation.
**Test**: Hook `MTLBlitCommandEncoder` to detect copy operations after FSR dispatch.
**Optimization**: Use shared buffers between FSR compute and presentation.

### Hypothesis 2: Suboptimal Upscaler Quality Settings
**Theory**: Default FSR quality settings may not match Apple Silicon's performance profile.
**Test**: Compare frame times at different `FSR*Quality` settings.
**Optimization**: Tune quality/performance balance for M1/M2/M3 chips.

### Hypothesis 3: Ray Tracing Software Fallback
**Theory**: RT is using software implementation instead of Metal's accelerated RT.
**Test**: Profile `MTLAccelerationStructure` usage and ray intersection kernel times.
**Optimization**: Implement Metal's ray tracing APIs if not already used.

### Hypothesis 4: Command Buffer Fragmentation
**Theory**: Too many small command buffers cause GPU idle time.
**Test**: Count command buffers per frame and measure GPU utilization.
**Optimization**: Batch related work into fewer, larger command buffers.

## Implementation Phases

### Phase 1: Binary Analysis (1-2 weeks)
- [ ] Dump game symbols and identify FSR/MetalFX entry points
- [ ] Map memory layout of upscaling-related structures
- [ ] Document render pipeline flow

### Phase 2: Basic Profiler (2-3 weeks)
- [ ] Create Frida hooks for Metal API
- [ ] Build data collection infrastructure
- [ ] Integrate with mod manager UI

### Phase 3: Advanced Analysis (3-4 weeks)
- [ ] GPU timestamp profiling
- [ ] Memory bandwidth analysis
- [ ] Bottleneck detection algorithms

### Phase 4: Optimization Testing (2-3 weeks)
- [ ] Test buffer storage mode changes
- [ ] Experiment with command buffer batching
- [ ] Validate upscaler quality tuning

## Resources

### Apple Documentation
- [Metal Best Practices Guide](https://developer.apple.com/library/archive/documentation/3DDrawing/Conceptual/MTLBestPracticesGuide/)
- [MetalFX Documentation](https://developer.apple.com/documentation/metalfx/)
- [GPU Programming Guide](https://developer.apple.com/metal/)

### AMD FSR
- [FSR GitHub Repository](https://github.com/GPUOpen-Effects/FidelityFX-FSR)
- [FSR 3 Source Code](https://github.com/GPUOpen-Effects/FidelityFX-FSR3)

### Frida Resources
- [Frida JavaScript API](https://frida.re/docs/javascript-api/)
- [Objective-C Bridge](https://frida.re/docs/ios/#objc-available)

## Next Steps

1. **Binary Analysis**: Run `nm` and `otool` on game binary to find FSR symbols
2. **Prototype Hooks**: Create basic Metal API hooks to validate approach
3. **Integrate with Mod Manager**: Add profiler UI to the dashboard
4. **Community Testing**: Gather data from different Mac configurations

---

*Document created for Cyberpunk 2077 macOS Modding Project*
*Last updated: December 2024*
