/**
 * Advanced Metal/MetalFX/FSR Profiler for Cyberpunk 2077 macOS
 * 
 * This script provides deep instrumentation of the Metal rendering pipeline,
 * MetalFX upscaling (FSR-based), and ray tracing to identify optimization
 * opportunities on Apple Silicon.
 * 
 * Theory: Path tracing and ray tracing are unoptimized for macOS, and there are
 * real performance gains if MetalFX/AMD FSR/Apple Silicon GPU were optimized.
 * 
 * Usage:
 *   frida -p $(pgrep Cyberpunk2077) -l metal_profiler.js --no-pause
 * 
 * @version 1.0.0
 * @author Cyberpunk 2077 macOS Modding Project
 */

'use strict';

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
    // Safe defaults for continuous gameplay profiling:
    // - minimal hooks
    // - no console spam
    // - low reporting cadence
    safeMode: true,

    logLevel: 0,  // 0=off, 1=info, 2=debug, 3=trace
    
    // Profiling features
    profileMemory: false,
    profileUpscaling: false,
    profileRayTracing: false,
    profileCommandBuffers: true,
    profileShaders: false,
    
    // Sampling
    reportIntervalMs: 1000,
    keepHistory: 240,  // frames
    
    // Output
    outputJson: true,
    outputConsole: false,

    // Heavy startup analysis
    runBinaryAnalysisOnStart: false,
};

// ============================================================================
// Logging
// ============================================================================

function log(level, ...args) {
    if (!CONFIG.outputConsole) return;
    if (level <= CONFIG.logLevel) {
        const prefix = ['[ERR]', '[INF]', '[DBG]', '[TRC]'][level] || '[???]';
        console.log(`[MetalProfiler]${prefix}`, ...args);
    }
}

const logError = (...args) => log(0, ...args);
const logInfo = (...args) => log(1, ...args);
const logDebug = (...args) => log(2, ...args);
const logTrace = (...args) => log(3, ...args);

// ============================================================================
// Stats Collection
// ============================================================================

function makeRingBuffer(size) {
    return {
        buf: new Array(size).fill(0),
        idx: 0,
        count: 0,
        sum: 0,
        sumSq: 0,
    };
}

function rbAdd(rb, value) {
    const old = rb.count < rb.buf.length ? 0 : rb.buf[rb.idx];
    rb.buf[rb.idx] = value;
    rb.idx = (rb.idx + 1) % rb.buf.length;
    rb.count = Math.min(rb.count + 1, rb.buf.length);
    rb.sum += value - old;
    rb.sumSq += (value * value) - (old * old);
}

function rbAvg(rb) {
    return rb.count > 0 ? rb.sum / rb.count : 0;
}

function rbStd(rb) {
    if (rb.count <= 1) return 0;
    const mean = rb.sum / rb.count;
    const variance = Math.max(0, (rb.sumSq / rb.count) - (mean * mean));
    return Math.sqrt(variance);
}

function rbValues(rb) {
    // Return values in chronological order (O(n); used only in reporter)
    const out = [];
    for (let i = 0; i < rb.count; i++) {
        const idx = (rb.idx - rb.count + i + rb.buf.length) % rb.buf.length;
        out.push(rb.buf[idx]);
    }
    return out;
}

const stats = {
    // Frame timing
    frames: {
        count: 0,
        rb: makeRingBuffer(CONFIG.keepHistory),
        lastTime: 0,
    },
    
    // Command buffers
    commandBuffers: {
        count: 0,
        bytesEncoded: 0,
        types: {},  // render, compute, blit
    },
    
    // Memory
    memory: {
        buffersAllocated: 0,
        bufferBytes: 0,
        texturesAllocated: 0,
        textureBytes: 0,
        storageModes: {
            shared: 0,
            managed: 0,
            private: 0,
            memoryless: 0,
        },
    },
    
    // Upscaling
    upscaling: {
        calls: 0,
        totalTimeMs: 0,
        inputResolutions: {},
        outputResolutions: {},
        scalerType: null,  // spatial or temporal
    },
    
    // Ray tracing
    rayTracing: {
        accelerationStructures: 0,
        intersectionFunctions: 0,
        dispatchCalls: 0,
        totalTimeMs: 0,
    },
    
    // Shaders
    shaders: {
        compiled: 0,
        pipelineStates: 0,
        computePipelines: 0,
    },
};

// ============================================================================
// Metal Resource Options Decoder
// ============================================================================

const MTLResourceOptions = {
    decodeStorageMode: (options) => {
        const mode = (options >> 4) & 0xF;
        switch (mode) {
            case 0: return 'shared';
            case 1: return 'managed';
            case 2: return 'private';
            case 3: return 'memoryless';
            default: return `unknown(${mode})`;
        }
    },
    
    decodeCPUCacheMode: (options) => {
        const mode = options & 0xF;
        return mode === 0 ? 'default' : 'writeCombined';
    },
    
    decodeHazardTracking: (options) => {
        const mode = (options >> 8) & 0x3;
        switch (mode) {
            case 0: return 'default';
            case 1: return 'untracked';
            case 2: return 'tracked';
            default: return `unknown(${mode})`;
        }
    },
};

// ============================================================================
// ObjC Resolver Helpers
// ============================================================================

function findMethods(pattern) {
    if (!ObjC.available) return [];
    
    const resolver = new ApiResolver('objc');
    try {
        return resolver.enumerateMatches(pattern);
    } catch (e) {
        logError(`Failed to resolve pattern ${pattern}:`, e.message);
        return [];
    }
}

function hookObjCMethod(pattern, callbacks) {
    const matches = findMethods(pattern);
    matches.forEach(match => {
        try {
            Interceptor.attach(match.address, callbacks);
            logDebug(`Hooked: ${match.name}`);
        } catch (e) {
            logTrace(`Failed to hook ${match.name}:`, e.message);
        }
    });
    return matches.length;
}

// ============================================================================
// Command Buffer Profiling
// ============================================================================

function profileCommandBuffers() {
    if (!CONFIG.profileCommandBuffers) return;
    logInfo('Setting up command buffer profiling...');
    
    // Track command buffer creation
    hookObjCMethod('-[* makeCommandBuffer*]', {
        onLeave: function(retval) {
            stats.commandBuffers.count++;
        }
    });
    
    // Track commit
    hookObjCMethod('-[* commit]', {
        onEnter: function(args) {
            const self = ObjC.Object(args[0]);
            if (self.$className && self.$className.includes('CommandBuffer')) {
                logTrace('CommandBuffer commit');
            }
        }
    });
    
    // Track render encoders
    hookObjCMethod('-[* renderCommandEncoderWithDescriptor:]', {
        onLeave: function(retval) {
            stats.commandBuffers.types.render = (stats.commandBuffers.types.render || 0) + 1;
        }
    });
    
    // Track compute encoders
    hookObjCMethod('-[* computeCommandEncoder*]', {
        onLeave: function(retval) {
            stats.commandBuffers.types.compute = (stats.commandBuffers.types.compute || 0) + 1;
        }
    });
    
    // Track blit encoders
    hookObjCMethod('-[* blitCommandEncoder*]', {
        onLeave: function(retval) {
            stats.commandBuffers.types.blit = (stats.commandBuffers.types.blit || 0) + 1;
        }
    });
}

// ============================================================================
// Memory Allocation Profiling
// ============================================================================

function profileMemory() {
    if (!CONFIG.profileMemory) return;
    logInfo('Setting up memory profiling...');
    
    // Hook buffer allocation with length and options
    const bufferMatches = findMethods('-[* newBufferWithLength:options:]');
    bufferMatches.forEach(match => {
        if (!match.name.includes('MTL')) return;
        
        try {
            Interceptor.attach(match.address, {
                onEnter: function(args) {
                    const length = args[2].toInt32();
                    const options = args[3].toInt32();
                    
                    stats.memory.buffersAllocated++;
                    stats.memory.bufferBytes += length;
                    
                    const storageMode = MTLResourceOptions.decodeStorageMode(options);
                    stats.memory.storageModes[storageMode] = 
                        (stats.memory.storageModes[storageMode] || 0) + 1;
                    
                    logTrace(`Buffer: ${length} bytes, storage: ${storageMode}`);
                    
                    // Optimization check: Warn about non-optimal storage modes
                    if (length > 1024 * 1024 && storageMode === 'managed') {
                        logDebug(`⚠️ Large managed buffer (${(length/1024/1024).toFixed(1)}MB) - consider shared or private`);
                    }
                }
            });
        } catch (e) {}
    });
    
    // Hook texture allocation
    hookObjCMethod('-[* newTextureWithDescriptor:]', {
        onEnter: function(args) {
            stats.memory.texturesAllocated++;
            // Would need to read descriptor for size
            stats.memory.textureBytes += 1024 * 1024; // Estimate
        }
    });
}

// ============================================================================
// MetalFX Upscaling Profiling
// ============================================================================

function profileUpscaling() {
    if (!CONFIG.profileUpscaling) return;
    logInfo('Setting up MetalFX/FSR upscaling profiling...');
    
    // MTLFXSpatialScaler
    if (ObjC.classes.MTLFXSpatialScaler) {
        logInfo('Found MTLFXSpatialScaler - MetalFX Spatial Upscaling available');
        stats.upscaling.scalerType = 'spatial';
        
        const scaler = ObjC.classes.MTLFXSpatialScaler;
        const methods = scaler.$ownMethods || [];
        
        methods.forEach(method => {
            if (method.includes('encodeToCommandBuffer')) {
                try {
                    Interceptor.attach(scaler[method].implementation, {
                        onEnter: function(args) {
                            this.startTime = Date.now();
                            stats.upscaling.calls++;
                        },
                        onLeave: function(retval) {
                            const duration = Date.now() - this.startTime;
                            stats.upscaling.totalTimeMs += duration;
                            logTrace(`Spatial upscale: ${duration}ms`);
                        }
                    });
                    logDebug(`Hooked MTLFXSpatialScaler.${method}`);
                } catch (e) {
                    logError(`Failed to hook spatial scaler:`, e.message);
                }
            }
        });
    }
    
    // MTLFXTemporalScaler
    if (ObjC.classes.MTLFXTemporalScaler) {
        logInfo('Found MTLFXTemporalScaler - MetalFX Temporal Upscaling (FSR-based) available');
        stats.upscaling.scalerType = 'temporal';
        
        const scaler = ObjC.classes.MTLFXTemporalScaler;
        const methods = scaler.$ownMethods || [];
        
        methods.forEach(method => {
            if (method.includes('encodeToCommandBuffer')) {
                try {
                    Interceptor.attach(scaler[method].implementation, {
                        onEnter: function(args) {
                            this.startTime = Date.now();
                            stats.upscaling.calls++;
                        },
                        onLeave: function(retval) {
                            const duration = Date.now() - this.startTime;
                            stats.upscaling.totalTimeMs += duration;
                            logTrace(`Temporal upscale (FSR): ${duration}ms`);
                        }
                    });
                    logDebug(`Hooked MTLFXTemporalScaler.${method}`);
                } catch (e) {
                    logError(`Failed to hook temporal scaler:`, e.message);
                }
            }
        });
    }
    
    // Look for FSR functions directly in game binary
    const gameModule = Process.findModuleByName('Cyberpunk2077');
    if (gameModule) {
        const exports = gameModule.enumerateExports();
        const fsrExports = exports.filter(e => 
            e.name.toLowerCase().includes('fsr') ||
            e.name.toLowerCase().includes('fidelity')
        );
        
        if (fsrExports.length > 0) {
            logInfo(`Found ${fsrExports.length} FSR-related exports in game binary`);
            fsrExports.forEach(exp => {
                logDebug(`  - ${exp.name} @ ${exp.address}`);
            });
        }
    }
}

// ============================================================================
// Ray Tracing Profiling
// ============================================================================

function profileRayTracing() {
    if (!CONFIG.profileRayTracing) return;
    logInfo('Setting up ray tracing profiling...');
    
    // Acceleration structure creation
    hookObjCMethod('-[* newAccelerationStructureWithDescriptor:]', {
        onEnter: function(args) {
            this.startTime = Date.now();
        },
        onLeave: function(retval) {
            stats.rayTracing.accelerationStructures++;
            const duration = Date.now() - this.startTime;
            stats.rayTracing.totalTimeMs += duration;
            logTrace(`AccelStruct created: ${duration}ms`);
        }
    });
    
    // Acceleration structure with size
    hookObjCMethod('-[* newAccelerationStructureWithSize:]', {
        onEnter: function(args) {
            const size = args[2].toInt32();
            logTrace(`AccelStruct allocation: ${(size/1024/1024).toFixed(1)}MB`);
        },
        onLeave: function(retval) {
            stats.rayTracing.accelerationStructures++;
        }
    });
    
    // Intersection function tables
    hookObjCMethod('-[* newIntersectionFunctionTableWithDescriptor:]', {
        onLeave: function(retval) {
            stats.rayTracing.intersectionFunctions++;
        }
    });
    
    // Ray tracing compute dispatch
    hookObjCMethod('-[* dispatchRaysWithAcceleration*]', {
        onEnter: function(args) {
            this.startTime = Date.now();
            stats.rayTracing.dispatchCalls++;
        },
        onLeave: function(retval) {
            const duration = Date.now() - this.startTime;
            stats.rayTracing.totalTimeMs += duration;
        }
    });
    
    // Indirect ray dispatch
    hookObjCMethod('-[* useResource:usage:stages:]', {
        onEnter: function(args) {
            // Check if this is an acceleration structure
            const obj = ObjC.Object(args[2]);
            if (obj.$className && obj.$className.includes('Acceleration')) {
                logTrace('AccelStruct bound for ray tracing');
            }
        }
    });
}

// ============================================================================
// Shader Profiling
// ============================================================================

function profileShaders() {
    if (!CONFIG.profileShaders) return;
    logInfo('Setting up shader profiling...');
    
    // Track shader compilation
    hookObjCMethod('-[* newFunctionWithName:]', {
        onLeave: function(retval) {
            stats.shaders.compiled++;
        }
    });
    
    // Track render pipeline creation
    hookObjCMethod('-[* newRenderPipelineStateWithDescriptor:*]', {
        onEnter: function(args) {
            this.startTime = Date.now();
        },
        onLeave: function(retval) {
            stats.shaders.pipelineStates++;
            const duration = Date.now() - this.startTime;
            if (duration > 10) {
                logDebug(`Slow pipeline creation: ${duration}ms`);
            }
        }
    });
    
    // Track compute pipeline creation
    hookObjCMethod('-[* newComputePipelineStateWithFunction:*]', {
        onEnter: function(args) {
            this.startTime = Date.now();
        },
        onLeave: function(retval) {
            stats.shaders.computePipelines++;
            const duration = Date.now() - this.startTime;
            if (duration > 10) {
                logDebug(`Slow compute pipeline: ${duration}ms`);
            }
        }
    });
}

// ============================================================================
// Frame Timing
// ============================================================================

function profileFrameTiming() {
    logInfo('Setting up frame timing...');

    // Safe-mode: avoid broad ApiResolver scans. Hook known command buffer classes if available.
    if (!ObjC.available) return;
    const candidates = [
        '_MTLCommandBuffer',
        'MTLIOAccelCommandBuffer',
        'MTLDebugCommandBuffer',
        'MTLToolsCommandBuffer',
    ];

    for (const className of candidates) {
        try {
            const cls = ObjC.classes[className];
            if (!cls) continue;
            const m = cls['- presentDrawable:'];
            if (!m) continue;
            Interceptor.attach(m.implementation, {
                onEnter: function() {
                    const now = Date.now();
                    if (stats.frames.lastTime > 0) {
                        rbAdd(stats.frames.rb, now - stats.frames.lastTime);
                    }
                    stats.frames.lastTime = now;
                    stats.frames.count++;
                }
            });
            return;
        } catch (e) {}
    }

    // Fallback to drawable acquisition as a frame boundary signal
    try {
        const layer = ObjC.classes.CAMetalLayer;
        if (layer && layer['- nextDrawable']) {
            Interceptor.attach(layer['- nextDrawable'].implementation, {
                onLeave: function() {
                    const now = Date.now();
                    if (stats.frames.lastTime > 0) {
                        rbAdd(stats.frames.rb, now - stats.frames.lastTime);
                    }
                    stats.frames.lastTime = now;
                    stats.frames.count++;
                }
            });
        }
    } catch (e) {}
}

// ============================================================================
// Stats Reporter
// ============================================================================

function calculateStats() {
    const avgFrameTime = rbAvg(stats.frames.rb);
    const fps = avgFrameTime > 0 ? 1000 / avgFrameTime : 0;

    // Percentiles computed off the ring buffer snapshot (report-time only)
    const times = rbValues(stats.frames.rb);
    const sortedTimes = times.sort((a, b) => a - b);
    const p99 = sortedTimes[Math.floor(sortedTimes.length * 0.99)] || 0;
    const p95 = sortedTimes[Math.floor(sortedTimes.length * 0.95)] || 0;
    
    // Bottleneck analysis
    const bottlenecks = [];
    
    if (stats.upscaling.calls > 0 && avgFrameTime > 0) {
        const upscaleRatio = (stats.upscaling.totalTimeMs / stats.upscaling.calls) / avgFrameTime;
        if (upscaleRatio > 0.25) {
            bottlenecks.push({
                type: 'upscaling',
                severity: 'high',
                message: `MetalFX/FSR consuming ${(upscaleRatio * 100).toFixed(0)}% of frame time`
            });
        }
    }
    
    if (stats.rayTracing.totalTimeMs > 0 && avgFrameTime > 0) {
        const rtRatio = (stats.rayTracing.totalTimeMs / Math.max(stats.rayTracing.dispatchCalls, 1)) / avgFrameTime;
        if (rtRatio > 0.3) {
            bottlenecks.push({
                type: 'rayTracing',
                severity: 'high',
                message: `Ray tracing consuming ${(rtRatio * 100).toFixed(0)}% of frame time`
            });
        }
    }
    
    if (stats.memory.storageModes.managed > stats.memory.storageModes.shared * 2) {
        bottlenecks.push({
            type: 'memory',
            severity: 'medium',
            message: 'Many managed buffers - consider shared for Apple Silicon unified memory'
        });
    }
    
    if (stats.commandBuffers.types.blit > stats.commandBuffers.types.render * 0.5) {
        bottlenecks.push({
            type: 'bandwidth',
            severity: 'medium',
            message: 'High blit encoder usage suggests unnecessary copies'
        });
    }
    
    return {
        timestamp: new Date().toISOString(),
        performance: {
            fps: fps.toFixed(1),
            avgFrameTimeMs: avgFrameTime.toFixed(2),
            p99FrameTimeMs: p99.toFixed(2),
            p95FrameTimeMs: p95.toFixed(2),
            frameCount: stats.frames.count,
        },
        upscaling: {
            enabled: stats.upscaling.scalerType !== null,
            type: stats.upscaling.scalerType,
            calls: stats.upscaling.calls,
            avgTimeMs: stats.upscaling.calls > 0 
                ? (stats.upscaling.totalTimeMs / stats.upscaling.calls).toFixed(2) 
                : 0,
        },
        rayTracing: {
            accelerationStructures: stats.rayTracing.accelerationStructures,
            dispatches: stats.rayTracing.dispatchCalls,
            avgTimeMs: stats.rayTracing.dispatchCalls > 0
                ? (stats.rayTracing.totalTimeMs / stats.rayTracing.dispatchCalls).toFixed(2)
                : 0,
        },
        memory: {
            buffersAllocated: stats.memory.buffersAllocated,
            bufferMB: (stats.memory.bufferBytes / 1024 / 1024).toFixed(1),
            texturesAllocated: stats.memory.texturesAllocated,
            storageModes: stats.memory.storageModes,
        },
        commandBuffers: {
            total: stats.commandBuffers.count,
            byType: stats.commandBuffers.types,
        },
        shaders: {
            compiled: stats.shaders.compiled,
            renderPipelines: stats.shaders.pipelineStates,
            computePipelines: stats.shaders.computePipelines,
        },
        bottlenecks: bottlenecks,
    };
}

function startReporter() {
    setInterval(() => {
        const report = calculateStats();
        
        if (CONFIG.outputJson) {
            send({ type: 'report', data: report });
        }
        
        if (CONFIG.outputConsole) {
            console.log('\n' + '='.repeat(60));
            console.log(`[MetalProfiler] Performance Report`);
            console.log('='.repeat(60));
            console.log(`FPS: ${report.performance.fps} | Frame: ${report.performance.avgFrameTimeMs}ms | P99: ${report.performance.p99FrameTimeMs}ms`);
            console.log(`Upscaling: ${report.upscaling.type || 'none'} | Calls: ${report.upscaling.calls} | Avg: ${report.upscaling.avgTimeMs}ms`);
            console.log(`RayTracing: AccelStructs: ${report.rayTracing.accelerationStructures} | Dispatches: ${report.rayTracing.dispatches}`);
            console.log(`Memory: Buffers: ${report.memory.bufferMB}MB | Textures: ${report.memory.texturesAllocated}`);
            console.log(`Storage: Shared:${report.memory.storageModes.shared} Managed:${report.memory.storageModes.managed} Private:${report.memory.storageModes.private}`);
            
            if (report.bottlenecks.length > 0) {
                console.log('\n⚠️ BOTTLENECKS DETECTED:');
                report.bottlenecks.forEach(b => {
                    console.log(`  [${b.severity.toUpperCase()}] ${b.type}: ${b.message}`);
                });
            }
            console.log('='.repeat(60) + '\n');
        }
        
        // Reset per-interval counters
        stats.commandBuffers.count = 0;
        stats.commandBuffers.types = {};
        stats.upscaling.calls = 0;
        stats.upscaling.totalTimeMs = 0;
        stats.rayTracing.dispatchCalls = 0;
        stats.rayTracing.totalTimeMs = 0;
        
    }, CONFIG.reportIntervalMs);
}

// ============================================================================
// Binary Analysis
// ============================================================================

function analyzeBinary() {
    logInfo('Analyzing game binary for optimization opportunities...');
    
    const gameModule = Process.findModuleByName('Cyberpunk2077');
    if (!gameModule) {
        logError('Game module not found');
        return;
    }
    
    logInfo(`Game module: ${gameModule.name} @ ${gameModule.base}`);
    logInfo(`Size: ${(gameModule.size / 1024 / 1024).toFixed(1)}MB`);
    
    // Enumerate exports
    const exports = gameModule.enumerateExports();
    
    // Categorize exports
    const categories = {
        fsr: [],
        metal: [],
        raytracing: [],
        rendering: [],
    };
    
    exports.forEach(exp => {
        const name = exp.name.toLowerCase();
        if (name.includes('fsr') || name.includes('fidelity') || name.includes('upscal')) {
            categories.fsr.push(exp);
        }
        if (name.includes('metal') || name.includes('mtl')) {
            categories.metal.push(exp);
        }
        if (name.includes('raytrac') || name.includes('accel') || name.includes('bvh')) {
            categories.raytracing.push(exp);
        }
        if (name.includes('render') || name.includes('draw') || name.includes('shader')) {
            categories.rendering.push(exp);
        }
    });
    
    console.log('\n' + '='.repeat(60));
    console.log('[MetalProfiler] Binary Analysis Results');
    console.log('='.repeat(60));
    console.log(`FSR/Upscaling symbols: ${categories.fsr.length}`);
    console.log(`Metal symbols: ${categories.metal.length}`);
    console.log(`Ray tracing symbols: ${categories.raytracing.length}`);
    console.log(`Rendering symbols: ${categories.rendering.length}`);
    
    if (categories.fsr.length > 0) {
        console.log('\nFSR/Upscaling exports:');
        categories.fsr.slice(0, 10).forEach(e => console.log(`  - ${e.name}`));
        if (categories.fsr.length > 10) console.log(`  ... and ${categories.fsr.length - 10} more`);
    }
    
    console.log('='.repeat(60) + '\n');
}

// ============================================================================
// Entry Point
// ============================================================================

if (CONFIG.outputConsole) {
    console.log('\n' + '='.repeat(60));
    console.log('[MetalProfiler] Advanced Metal/FSR Profiler v1.0');
    console.log('[MetalProfiler] Cyberpunk 2077 macOS Optimization Research');
    console.log('='.repeat(60) + '\n');
}

// Check ObjC availability
if (!ObjC.available) {
    logError('Objective-C runtime not available!');
} else {
    logInfo('Objective-C runtime available');
    
    // Check for MetalFX classes
    const metalFXClasses = ['MTLFXSpatialScaler', 'MTLFXTemporalScaler', 'MTLFXSpatialScalerDescriptor', 'MTLFXTemporalScalerDescriptor'];
    metalFXClasses.forEach(cls => {
        if (ObjC.classes[cls]) {
            logInfo(`Found: ${cls}`);
        }
    });
}

// Run binary analysis first
if (!CONFIG.safeMode && CONFIG.runBinaryAnalysisOnStart) {
    analyzeBinary();
}

// Set up profilers (safe mode keeps hook surface minimal)
profileFrameTiming();
if (!CONFIG.safeMode) {
    profileCommandBuffers();
    profileMemory();
    profileUpscaling();
    profileRayTracing();
    profileShaders();
}

// Start periodic reporter
startReporter();

if (CONFIG.outputConsole) {
    console.log('\n' + '='.repeat(60));
    console.log('[MetalProfiler] Profiler initialized - collecting data...');
    console.log('[MetalProfiler] Reports will be generated every ' + CONFIG.reportIntervalMs + 'ms');
    console.log('='.repeat(60) + '\n');
}
