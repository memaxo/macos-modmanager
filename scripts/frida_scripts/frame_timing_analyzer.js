/**
 * Frame Timing Analyzer for Cyberpunk 2077 macOS
 * 
 * Measures frame pacing quality and compares FSR vs MetalFX synchronization.
 * 
 * Usage:
 *   frida -U -n Cyberpunk2077 -l frame_timing_analyzer.js
 * 
 * @version 1.0.0
 * @author macOS Mod Manager Team
 */

'use strict';

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
    // Ring buffer window size (kept small to avoid heavy aggregation cost)
    maxSamples: 240,
    
    // Target frame times (ms)
    targetFrameTimes: {
        60: 16.67,
        30: 33.33,
        120: 8.33
    },
    
    // Stall thresholds (ms) (used for counters only; no per-stall logging)
    stallThresholdMs: {
        minor: 20,
        major: 33,
        severe: 50
    },

    // Reporting cadence (timer-driven; never from within render hooks)
    reportIntervalMs: 1000,

    // Enable optional console logs (off by default for safety)
    verbose: false,
};

// ============================================================================
// Timing Data Storage
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

const state = {
    reporting: true,
    hookedPresent: false,
    frameCount: 0,
    lastFrameMark: 0,

    // Ring buffers
    frameDeltas: makeRingBuffer(CONFIG.maxSamples),
    drawableAcquire: makeRingBuffer(CONFIG.maxSamples),
    metalfxEncode: makeRingBuffer(CONFIG.maxSamples),

    // Counters
    stallCount: { minor: 0, major: 0, severe: 0 },
    drawableStallCount: 0,
    metalfxCalls: 0,

    // Detection (safe-only: no memory scanning)
    upscaler: {
        metalfxDetected: false,
        fsrDetected: false,
        fsrVersion: 'unknown',
    },

    sessionStartTime: Date.now(),
    minFps: Infinity,
    maxFps: 0,

    intervalId: null,
};

// ============================================================================
// Utility Functions
// ============================================================================

function log(level, message, data) {
    const prefix = `[FrameAnalyzer][${level}]`;
    if (data) {
        console.log(`${prefix} ${message}`, JSON.stringify(data));
    } else {
        console.log(`${prefix} ${message}`);
    }
}

function logInfo(msg, data) { log('INFO', msg, data); }
function logDebug(msg, data) { if (CONFIG.verbose) log('DEBUG', msg, data); }
function logWarn(msg, data) { log('WARN', msg, data); }

function safeDetectUpscaler() {
    // Safe continuous mode: avoid module scans. Best-effort MetalFX detection.
    if (!ObjC.available) return;
    if (ObjC.classes.MTLFXTemporalScaler || ObjC.classes.MTLFXSpatialScaler) {
        state.upscaler.metalfxDetected = true;
    }
    // FSR detection is intentionally left as unknown in safe mode.
}

// ============================================================================
// Hook Implementations
// ============================================================================

/**
 * Hook CAMetalLayer.nextDrawable to measure drawable acquisition time
 */
function hookNextDrawable() {
    try {
        const CAMetalLayer = ObjC.classes.CAMetalLayer;
        if (!CAMetalLayer) {
            logWarn('CAMetalLayer not found');
            return false;
        }
        
        const selector = '- nextDrawable';
        const method = CAMetalLayer[selector];
        if (!method) {
            logWarn('nextDrawable method not found');
            return false;
        }
        
        Interceptor.attach(method.implementation, {
            onEnter: function(args) {
                this.startTime = Date.now();
            },
            onLeave: function(retval) {
                const duration = Date.now() - this.startTime;

                rbAdd(state.drawableAcquire, duration);

                // Detect drawable stalls (counters only)
                if (duration > CONFIG.stallThresholdMs.minor) {
                    state.drawableStallCount++;
                }

                // Fallback frame boundary when presentDrawable hook isn't available
                if (!state.hookedPresent) {
                    const now = Date.now();
                    if (state.lastFrameMark > 0) {
                        const delta = now - state.lastFrameMark;
                        rbAdd(state.frameDeltas, delta);
                        state.frameCount++;
                        const fps = 1000 / delta;
                        state.minFps = Math.min(state.minFps, fps);
                        state.maxFps = Math.max(state.maxFps, fps);
                        classifyFrameDelta(delta);
                    }
                    state.lastFrameMark = now;
                }
            }
        });
        
        logInfo('Hooked CAMetalLayer.nextDrawable');
        return true;
    } catch (e) {
        logWarn(`Failed to hook nextDrawable: ${e}`);
        return false;
    }
}

/**
 * Hook MTLCommandBuffer commit/present to measure frame timing
 */
function hookCommandBufferPresent() {
    if (!ObjC.available) return false;

    // Avoid enumerateLoadedClasses (too expensive + hooks explode). Instead, try known command buffer classes.
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
            const selector = '- presentDrawable:';
            const method = cls[selector];
            if (!method) continue;

            Interceptor.attach(method.implementation, {
                onEnter: function() {
                    const now = Date.now();
                    if (state.lastFrameMark > 0) {
                        const delta = now - state.lastFrameMark;
                        rbAdd(state.frameDeltas, delta);
                        state.frameCount++;
                        const fps = 1000 / delta;
                        state.minFps = Math.min(state.minFps, fps);
                        state.maxFps = Math.max(state.maxFps, fps);
                        classifyFrameDelta(delta);
                    }
                    state.lastFrameMark = now;
                }
            });

            state.hookedPresent = true;
            logInfo(`Hooked presentDrawable on ${className}`);
            return true;
        } catch (e) {
            // ignore
        }
    }

    logWarn('No presentDrawable hook installed (falling back to nextDrawable frame boundary)');
    return false;
}

/**
 * Hook MTLFXTemporalScaler to detect MetalFX usage and timing
 */
function hookMetalFXScaler() {
    try {
        if (!ObjC.available) return;

        const scalerClasses = ['MTLFXTemporalScaler', 'MTLFXSpatialScaler', '_MTLFXTemporalScaler'];
        scalerClasses.forEach(className => {
            try {
                const cls = ObjC.classes[className];
                if (!cls) return;
                const methods = cls.$ownMethods || [];
                methods.forEach(m => {
                    if (!m.includes('encodeToCommandBuffer')) return;
                    try {
                        Interceptor.attach(cls[m].implementation, {
                            onEnter: function() {
                                this.t0 = Date.now();
                            },
                            onLeave: function() {
                                const dt = Date.now() - this.t0;
                                rbAdd(state.metalfxEncode, dt);
                                state.metalfxCalls++;
                                state.upscaler.metalfxDetected = true;
                            }
                        });
                    } catch (e) {}
                });
            } catch (e) {}
        });
    } catch (e) {
        logWarn(`Failed to hook MetalFX: ${e}`);
    }
}

function classifyFrameDelta(deltaMs) {
    if (deltaMs > CONFIG.stallThresholdMs.severe) state.stallCount.severe++;
    else if (deltaMs > CONFIG.stallThresholdMs.major) state.stallCount.major++;
    else if (deltaMs > CONFIG.stallThresholdMs.minor) state.stallCount.minor++;
}

// ============================================================================
// Reporting
// ============================================================================

function generateReport() {
    const avgFrame = rbAvg(state.frameDeltas);
    const stdFrame = rbStd(state.frameDeltas);
    const avgDrawable = rbAvg(state.drawableAcquire);
    const avgMfx = rbAvg(state.metalfxEncode);
    
    // Calculate frame pacing quality (0-100)
    // Perfect pacing = low stdDev relative to avg
    const targetFrameTime = CONFIG.targetFrameTimes[60];
    const pacingQuality = avgFrame > 0 ? Math.max(0, 100 - (stdFrame / targetFrameTime * 100)) : 0;
    const avgFps = avgFrame > 0 ? (1000 / avgFrame) : 0;
    
    const report = {
        // Summary
        summary: {
            frameCount: state.frameCount,
            sessionDuration: ((Date.now() - state.sessionStartTime) / 1000).toFixed(1) + 's',
            avgFps: avgFps.toFixed(1),
            fpsRange: `${state.minFps === Infinity ? 0 : state.minFps.toFixed(1)} - ${state.maxFps.toFixed(1)}`,
            framePacingQuality: pacingQuality.toFixed(1) + '%'
        },
        
        // Frame timing
        frameTiming: {
            avgFrameTime: avgFrame.toFixed(2) + 'ms',
            stdDev: stdFrame.toFixed(2) + 'ms',
        },
        
        // Stalls
        stalls: {
            minor: state.stallCount.minor,
            major: state.stallCount.major,
            severe: state.stallCount.severe,
            drawableStalls: state.drawableStallCount
        },
        
        // Drawable acquisition
        drawableAcquisition: {
            avgTime: avgDrawable.toFixed(2) + 'ms',
        },
        
        // Upscaler info
        upscaler: {
            metalfxDetected: state.upscaler.metalfxDetected,
            metalfxCalls: state.metalfxCalls,
            metalfxAvgTime: avgMfx.toFixed(2) + 'ms',
            fsrDetected: state.upscaler.fsrDetected,
            fsrVersion: state.upscaler.fsrVersion
        }
    };

    // Send to mod manager if connected (compact payload; no console spam)
    if (state.reporting) {
        send({
            type: 'frameTimingReport',
            data: report
        });
    }
    
    return report;
}

// ============================================================================
// Interactive Commands
// ============================================================================

// Handle messages from mod manager
recv('command', function(message) {
    const cmd = message.command;
    
    switch (cmd) {
        case 'report':
            // force report even if reporting is paused
            state.reporting = true;
            generateReport();
            break;
            
        case 'reset':
            resetStats();
            logInfo('Stats reset');
            break;
            
        case 'setVerbose':
            CONFIG.verbose = message.value;
            logInfo(`Verbose mode: ${CONFIG.verbose}`);
            break;
            
        default:
            logWarn(`Unknown command: ${cmd}`);
    }
});

function resetStats() {
    state.frameCount = 0;
    state.lastFrameMark = 0;
    state.frameDeltas = makeRingBuffer(CONFIG.maxSamples);
    state.drawableAcquire = makeRingBuffer(CONFIG.maxSamples);
    state.metalfxEncode = makeRingBuffer(CONFIG.maxSamples);
    state.stallCount = { minor: 0, major: 0, severe: 0 };
    state.drawableStallCount = 0;
    state.metalfxCalls = 0;
    state.sessionStartTime = Date.now();
    state.minFps = Infinity;
    state.maxFps = 0;
}

// ============================================================================
// Initialization
// ============================================================================

function initialize() {
    if (CONFIG.verbose) {
        console.log('[FrameAnalyzer] Initializing (safe continuous mode)...');
    }
    
    // Install hooks
    hookNextDrawable();
    hookCommandBufferPresent();
    hookMetalFXScaler();
    safeDetectUpscaler();

    if (state.intervalId === null) {
        state.intervalId = setInterval(generateReport, CONFIG.reportIntervalMs);
    }
}

// Handle script unload
Script.bindExitHandler(function() {
    try {
        if (state.intervalId !== null) {
            clearInterval(state.intervalId);
            state.intervalId = null;
        }
        generateReport();
    } catch (e) {}
});

// Start
initialize();

// Optional RPC control (works when run under frida-python)
rpc.exports = {
    start: function() {
        state.reporting = true;
        if (state.intervalId === null) {
            state.intervalId = setInterval(generateReport, CONFIG.reportIntervalMs);
        }
        return true;
    },
    stop: function() {
        state.reporting = false;
        if (state.intervalId !== null) {
            clearInterval(state.intervalId);
            state.intervalId = null;
        }
        return true;
    },
    report: function() { return generateReport(); },
    reset: function() { resetStats(); return true; },
    setverbose: function(v) { CONFIG.verbose = !!v; return CONFIG.verbose; },
};
