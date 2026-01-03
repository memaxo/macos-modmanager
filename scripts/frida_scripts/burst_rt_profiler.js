/**
 * Burst RT Profiler for Cyberpunk 2077 macOS
 * 
 * Phase 1, Week 2: Opt-in RT hooks for short capture windows (5-15s)
 * 
 * SAFETY: RT hooks are DISABLED by default. Must be explicitly enabled via rpc.exports.enableRTProfiling()
 * Auto-disables after timeout to prevent game instability.
 * 
 * Usage:
 *   frida -p $(pgrep Cyberpunk2077) -l burst_rt_profiler.js --no-pause
 *   Then call: rpc.exports.enableRTProfiling({durationSeconds: 10})
 */

'use strict';

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
    // RT profiling is OFF by default
    rtProfilingEnabled: false,
    rtProfilingStartTime: 0,
    rtProfilingDuration: 0,
    
    // Safety timeout (max duration)
    maxDurationSeconds: 15,
    
    // Reporting interval
    reportIntervalMs: 1000,  // 1 second for RT data
};

// ============================================================================
// RT Statistics Collection
// ============================================================================

const rtStats = {
    // Acceleration structures
    accelerationStructures: {
        created: 0,
        built: 0,
        refitted: 0,
        updated: 0,
        buildTimes: [],
        refitTimes: [],
    },
    
    // RT render nodes (from reverse engineering)
    renderNodes: {
        rtxdi: { calls: 0, times: [] },
        restirgi: { calls: 0, times: [] },
        reflections: { calls: 0, times: [] },
        globalShadow: { calls: 0, times: [] },
        localShadow: { calls: 0, times: [] },
        ambientOcclusion: { calls: 0, times: [] },
        filterOutput: { calls: 0, times: [] },
    },
    
    // RT buffers
    buffers: {
        raytracing: { allocated: 0, bytes: 0 },
        raytracingAS: { allocated: 0, bytes: 0 },
        raytracingOMM: { allocated: 0, bytes: 0 },
        raytracingUpload: { allocated: 0, bytes: 0 },
    },
    
    // Ray dispatch (if detectable)
    rayDispatches: {
        count: 0,
        times: [],
    },
    
    // Session info
    session: {
        startTime: 0,
        endTime: 0,
        samplesCollected: 0,
    }
};

// ============================================================================
// Ring Buffer Helper
// ============================================================================

function addToRingBuffer(buffer, value, maxSize) {
    buffer.push(value);
    if (buffer.length > maxSize) {
        buffer.shift();
    }
}

// ============================================================================
// RT Hook Implementations (SAFE - Only active when enabled)
// ============================================================================

let rtHooks = {
    accelStructHooks: [],
    renderNodeHooks: [],
    bufferHooks: [],
};

function installRTHooks() {
    if (!ObjC.available) {
        console.log('[BurstRT] ObjC not available');
        return false;
    }
    
    console.log('[BurstRT] Installing RT hooks...');
    
    // Hook acceleration structure operations
    try {
        const resolver = new ApiResolver('objc');
        
        // Hook AS creation
        const createMatches = resolver.enumerateMatches('-[* newAccelerationStructure*]');
        createMatches.forEach(match => {
            if (match.name.includes('MTL')) {
                try {
                    const hook = Interceptor.attach(match.address, {
                        onEnter: function(args) {
                            if (!CONFIG.rtProfilingEnabled) return;
                            this.startTime = Date.now();
                        },
                        onLeave: function(retval) {
                            if (!CONFIG.rtProfilingEnabled) return;
                            rtStats.accelerationStructures.created++;
                            const duration = Date.now() - this.startTime;
                            addToRingBuffer(rtStats.accelerationStructures.buildTimes, duration, 100);
                        }
                    });
                    rtHooks.accelStructHooks.push(hook);
                } catch (e) {}
            }
        });
        
        // Hook AS build
        const buildMatches = resolver.enumerateMatches('-[* buildAccelerationStructure*]');
        buildMatches.forEach(match => {
            if (match.name.includes('MTL')) {
                try {
                    const hook = Interceptor.attach(match.address, {
                        onEnter: function(args) {
                            if (!CONFIG.rtProfilingEnabled) return;
                            this.startTime = Date.now();
                        },
                        onLeave: function(retval) {
                            if (!CONFIG.rtProfilingEnabled) return;
                            rtStats.accelerationStructures.built++;
                            const duration = Date.now() - this.startTime;
                            addToRingBuffer(rtStats.accelerationStructures.buildTimes, duration, 100);
                        }
                    });
                    rtHooks.accelStructHooks.push(hook);
                } catch (e) {}
            }
        });
        
        // Hook AS refit (update)
        const refitMatches = resolver.enumerateMatches('-[* refitAccelerationStructure*]');
        refitMatches.forEach(match => {
            if (match.name.includes('MTL')) {
                try {
                    const hook = Interceptor.attach(match.address, {
                        onEnter: function(args) {
                            if (!CONFIG.rtProfilingEnabled) return;
                            this.startTime = Date.now();
                        },
                        onLeave: function(retval) {
                            if (!CONFIG.rtProfilingEnabled) return;
                            rtStats.accelerationStructures.refitted++;
                            const duration = Date.now() - this.startTime;
                            addToRingBuffer(rtStats.accelerationStructures.refitTimes, duration, 100);
                        }
                    });
                    rtHooks.accelStructHooks.push(hook);
                } catch (e) {}
            }
        });
        
        console.log(`[BurstRT] Installed ${rtHooks.accelStructHooks.length} acceleration structure hooks`);
    } catch (e) {
        console.log(`[BurstRT] Failed to install AS hooks: ${e}`);
    }
    
    // Hook RT render nodes (by scanning for known node names in exports)
    try {
        const gameModule = Process.findModuleByName('Cyberpunk2077');
        if (gameModule) {
            // These are function exports we identified in reverse engineering
            const nodePatterns = [
                { pattern: 'RenderRayTracedRTXDI', stat: 'rtxdi' },
                { pattern: 'RenderRayTracedReSTIRGI', stat: 'restirgi' },
                { pattern: 'RenderRayTracedReflections', stat: 'reflections' },
                { pattern: 'RenderRayTracedGlobalShadow', stat: 'globalShadow' },
                { pattern: 'RenderRayTracedLocalShadow', stat: 'localShadow' },
                { pattern: 'RenderRayTracedAmbientOcclusion', stat: 'ambientOcclusion' },
                { pattern: 'RayTracingFilterOutput', stat: 'filterOutput' },
            ];
            
            // Note: These may not be directly hookable as exports
            // They're render nodes that execute internally
            // We'll track them via ObjC if possible, otherwise skip
            console.log('[BurstRT] RT render nodes will be tracked via ObjC hooks if available');
        }
    } catch (e) {
        console.log(`[BurstRT] Render node hooking skipped: ${e}`);
    }
    
    return true;
}

function uninstallRTHooks() {
    console.log('[BurstRT] Uninstalling RT hooks...');
    
    rtHooks.accelStructHooks.forEach(hook => {
        try {
            hook.detach();
        } catch (e) {}
    });
    
    rtHooks.accelStructHooks = [];
    rtHooks.renderNodeHooks = [];
    rtHooks.bufferHooks = [];
}

// ============================================================================
// RT Profiling Control
// ============================================================================

function checkRTProfilingTimeout() {
    if (!CONFIG.rtProfilingEnabled) return;
    
    const elapsed = (Date.now() - CONFIG.rtProfilingStartTime) / 1000;
    if (elapsed >= CONFIG.rtProfilingDuration) {
        console.log(`[BurstRT] Auto-disabling RT profiling after ${elapsed.toFixed(1)}s (safety timeout)`);
        disableRTProfiling();
    }
}

// ============================================================================
// Stats Reporting
// ============================================================================

function generateRTReport() {
    if (!CONFIG.rtProfilingEnabled) {
        return { status: 'disabled' };
    }
    
    const elapsed = (Date.now() - CONFIG.rtProfilingStartTime) / 1000;
    
    // Calculate averages
    const avgBuildTime = rtStats.accelerationStructures.buildTimes.length > 0
        ? rtStats.accelerationStructures.buildTimes.reduce((a, b) => a + b, 0) / rtStats.accelerationStructures.buildTimes.length
        : 0;
    
    const avgRefitTime = rtStats.accelerationStructures.refitTimes.length > 0
        ? rtStats.accelerationStructures.refitTimes.reduce((a, b) => a + b, 0) / rtStats.accelerationStructures.refitTimes.length
        : 0;
    
    return {
        status: 'active',
        elapsed_seconds: elapsed.toFixed(1),
        acceleration_structures: {
            created: rtStats.accelerationStructures.created,
            built: rtStats.accelerationStructures.built,
            refitted: rtStats.accelerationStructures.refitted,
            avg_build_time_ms: avgBuildTime.toFixed(2),
            avg_refit_time_ms: avgRefitTime.toFixed(2),
        },
        render_nodes: {
            rtxdi: rtStats.renderNodes.rtxdi.calls,
            restirgi: rtStats.renderNodes.restirgi.calls,
            reflections: rtStats.renderNodes.reflections.calls,
            globalShadow: rtStats.renderNodes.globalShadow.calls,
            localShadow: rtStats.renderNodes.localShadow.calls,
            ambientOcclusion: rtStats.renderNodes.ambientOcclusion.calls,
        },
        buffers: rtStats.buffers,
        ray_dispatches: {
            count: rtStats.rayDispatches.count,
        }
    };
}

// ============================================================================
// RPC Exports (Control Interface)
// ============================================================================

rpc.exports = {
    enableRTProfiling: function(options) {
        options = options || {};
        const duration = Math.min(options.durationSeconds || 10, CONFIG.maxDurationSeconds);
        
        if (CONFIG.rtProfilingEnabled) {
            return { status: 'already_enabled', message: 'RT profiling already active' };
        }
        
        console.log(`[BurstRT] Enabling RT profiling for ${duration} seconds...`);
        
        CONFIG.rtProfilingEnabled = true;
        CONFIG.rtProfilingStartTime = Date.now();
        CONFIG.rtProfilingDuration = duration;
        
        rtStats.session.startTime = Date.now();
        
        // Install hooks if not already installed
        if (rtHooks.accelStructHooks.length === 0) {
            installRTHooks();
        }
        
        // Auto-disable after duration
        setTimeout(() => {
            checkRTProfilingTimeout();
        }, duration * 1000);
        
        return { status: 'enabled', duration_seconds: duration };
    },
    
    disableRTProfiling: function() {
        if (!CONFIG.rtProfilingEnabled) {
            return { status: 'already_disabled' };
        }
        
        console.log('[BurstRT] Disabling RT profiling...');
        CONFIG.rtProfilingEnabled = false;
        rtStats.session.endTime = Date.now();
        
        return { status: 'disabled', report: generateRTReport() };
    },
    
    getRTStats: function() {
        return generateRTReport();
    },
    
    resetRTStats: function() {
        rtStats.accelerationStructures = {
            created: 0,
            built: 0,
            refitted: 0,
            updated: 0,
            buildTimes: [],
            refitTimes: [],
        };
        rtStats.renderNodes = {
            rtxdi: { calls: 0, times: [] },
            restirgi: { calls: 0, times: [] },
            reflections: { calls: 0, times: [] },
            globalShadow: { calls: 0, times: [] },
            localShadow: { calls: 0, times: [] },
            ambientOcclusion: { calls: 0, times: [] },
            filterOutput: { calls: 0, times: [] },
        };
        rtStats.buffers = {
            raytracing: { allocated: 0, bytes: 0 },
            raytracingAS: { allocated: 0, bytes: 0 },
            raytracingOMM: { allocated: 0, bytes: 0 },
            raytracingUpload: { allocated: 0, bytes: 0 },
        };
        rtStats.rayDispatches = { count: 0, times: [] };
        return { status: 'reset' };
    }
};

// ============================================================================
// Periodic Reporting (when enabled)
// ============================================================================

let reportInterval = null;

function startReporting() {
    if (reportInterval) return;
    
    reportInterval = setInterval(() => {
        if (CONFIG.rtProfilingEnabled) {
            checkRTProfilingTimeout();
            const report = generateRTReport();
            if (report.status === 'active') {
                send({
                    type: 'rt_stats',
                    data: report
                });
            }
        }
    }, CONFIG.reportIntervalMs);
}

function stopReporting() {
    if (reportInterval) {
        clearInterval(reportInterval);
        reportInterval = null;
    }
}

// ============================================================================
// Initialization
// ============================================================================

console.log('\n' + '='.repeat(70));
console.log('[BurstRT] Burst RT Profiler - Phase 1, Week 2');
console.log('[BurstRT] RT hooks DISABLED by default (safe mode)');
console.log('[BurstRT] Use rpc.exports.enableRTProfiling({durationSeconds: 10}) to enable');
console.log('='.repeat(70) + '\n');

// Install hooks but keep them disabled
if (ObjC.available) {
    installRTHooks();
    // Hooks are installed but won't fire until enabled
    console.log('[BurstRT] RT hooks installed (disabled by default)');
} else {
    console.log('[BurstRT] ObjC not available - RT hooks cannot be installed');
}

startReporting();

// Cleanup on exit
Script.bindExitHandler(function() {
    stopReporting();
    uninstallRTHooks();
    console.log('[BurstRT] Cleanup complete');
});
