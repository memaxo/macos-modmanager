/**
 * Apple Optimization Probe for Cyberpunk 2077 macOS
 * 
 * This script probes the game's Apple-specific optimizations discovered
 * in binary analysis to determine:
 * 1. Whether AAPL optimizations are enabled
 * 2. Which upscaling path (FSR vs MetalFX) is active
 * 3. Ray tracing buffer allocation patterns
 * 4. Denoiser configuration
 * 
 * Usage:
 *   frida -p $(pgrep Cyberpunk2077) -l aapl_optimization_probe.js --no-pause
 * 
 * @version 1.0.0
 */

'use strict';

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
    // Safe continuous mode defaults:
    // - no sync scanning
    // - no console spam
    // - minimal hooks + compact send() payloads
    safeMode: true,

    logLevel: 0,  // 0=errors, 1=info, 2=debug, 3=trace
    probeInterval: 2000,  // ms between status checks

    outputConsole: false,

    trackUpscaling: true,
    trackRayTracing: false,
    trackAAPL: true,
    trackDenoising: false,

    // Heavy / risky operations (disabled by default)
    enableConfigScan: false,
};

// ============================================================================
// State Tracking
// ============================================================================

const state = {
    // Upscaling
    upscaling: {
        fsr2Active: false,
        fsr3Active: false,
        mfxActive: false,
        fsr2Calls: 0,
        fsr3Calls: 0,
        mfxCalls: 0,
        lastUpscaler: null,
    },
    
    // Apple optimizations
    aapl: {
        optimEnabled: null,  // null = unknown, true/false = detected
        optimPassUsed: false,
        bucketsBufferAllocated: false,
        rayBufferAllocated: false,
        payloadBufferAllocated: false,
        aaplBufferCount: 0,
    },
    
    // Ray tracing
    rayTracing: {
        accelerationStructures: 0,
        rtxdiCalls: 0,
        restirgiCalls: 0,
        reflectionCalls: 0,
        shadowCalls: 0,
    },
    
    // Denoising
    denoising: {
        nrdEnabled: null,
        aaplShaderPreference: null,
        concurrentDispatch: null,
    },
};

// ============================================================================
// Logging
// ============================================================================

function log(level, ...args) {
    if (!CONFIG.outputConsole) return;
    if (level <= CONFIG.logLevel) {
        const prefix = ['[ERR]', '[INF]', '[DBG]', '[TRC]'][level] || '[???]';
        console.log(`[AAPL-Probe]${prefix}`, ...args);
    }
}

const logError = (...args) => log(0, ...args);
const logInfo = (...args) => log(1, ...args);
const logDebug = (...args) => log(2, ...args);
const logTrace = (...args) => log(3, ...args);

// ============================================================================
// Memory Pattern Scanning
// ============================================================================

function scanForString(pattern) {
    const gameModule = Process.findModuleByName('Cyberpunk2077');
    if (!gameModule) return [];
    
    const results = [];
    const patternBytes = pattern.split('').map(c => c.charCodeAt(0).toString(16).padStart(2, '0')).join(' ');
    
    Memory.scan(gameModule.base, gameModule.size, patternBytes, {
        onMatch: (address, size) => {
            results.push(address);
        },
        onComplete: () => {}
    });
    
    return results;
}

// ============================================================================
// Render Node Hooking
// ============================================================================

function hookRenderNodes() {
    const gameModule = Process.findModuleByName('Cyberpunk2077');
    if (!gameModule) {
        logError('Game module not found');
        return;
    }
    
    logInfo('Setting up render node hooks...');
    
    // Search for render node function addresses
    const exports = gameModule.enumerateExports();
    
    // FSR2 render node
    const fsr2Exports = exports.filter(e => 
        e.name.includes('ApplyFSR2') && e.type === 'function'
    );
    fsr2Exports.forEach(exp => {
        try {
            Interceptor.attach(exp.address, {
                onEnter: function(args) {
                    state.upscaling.fsr2Calls++;
                    state.upscaling.fsr2Active = true;
                    state.upscaling.lastUpscaler = 'FSR2';
                    logTrace('FSR2 upscaling active');
                }
            });
            logDebug(`Hooked FSR2: ${exp.name}`);
        } catch (e) {
            logTrace(`Failed to hook ${exp.name}: ${e.message}`);
        }
    });
    
    // FSR3 render node
    const fsr3Exports = exports.filter(e => 
        e.name.includes('ApplyFSR3') && e.type === 'function'
    );
    fsr3Exports.forEach(exp => {
        try {
            Interceptor.attach(exp.address, {
                onEnter: function(args) {
                    state.upscaling.fsr3Calls++;
                    state.upscaling.fsr3Active = true;
                    state.upscaling.lastUpscaler = 'FSR3';
                    logTrace('FSR3 upscaling active');
                }
            });
            logDebug(`Hooked FSR3: ${exp.name}`);
        } catch (e) {
            logTrace(`Failed to hook ${exp.name}: ${e.message}`);
        }
    });
    
    // MetalFX render node
    const mfxExports = exports.filter(e => 
        e.name.includes('ApplyMFX') && e.type === 'function'
    );
    mfxExports.forEach(exp => {
        try {
            Interceptor.attach(exp.address, {
                onEnter: function(args) {
                    state.upscaling.mfxCalls++;
                    state.upscaling.mfxActive = true;
                    state.upscaling.lastUpscaler = 'MetalFX';
                    logTrace('MetalFX upscaling active');
                }
            });
            logDebug(`Hooked MetalFX: ${exp.name}`);
        } catch (e) {
            logTrace(`Failed to hook ${exp.name}: ${e.message}`);
        }
    });
    
    // Ray tracing render nodes
    const rtExports = exports.filter(e => 
        e.name.includes('RenderRayTraced') && e.type === 'function'
    );
    rtExports.forEach(exp => {
        try {
            Interceptor.attach(exp.address, {
                onEnter: function(args) {
                    if (exp.name.includes('RTXDI')) {
                        state.rayTracing.rtxdiCalls++;
                    } else if (exp.name.includes('ReSTIRGI')) {
                        state.rayTracing.restirgiCalls++;
                    } else if (exp.name.includes('Reflection')) {
                        state.rayTracing.reflectionCalls++;
                    } else if (exp.name.includes('Shadow')) {
                        state.rayTracing.shadowCalls++;
                    }
                }
            });
            logDebug(`Hooked RT: ${exp.name}`);
        } catch (e) {}
    });
    
    logInfo(`Hooked ${fsr2Exports.length} FSR2, ${fsr3Exports.length} FSR3, ${mfxExports.length} MFX, ${rtExports.length} RT nodes`);
}

// ============================================================================
// MetalFX ObjC Hooking
// ============================================================================

function hookMetalFX() {
    if (!ObjC.available) {
        logError('ObjC not available for MetalFX hooks');
        return;
    }
    
    logInfo('Setting up MetalFX ObjC hooks...');
    
    // MTLFXTemporalScaler
    if (ObjC.classes.MTLFXTemporalScaler) {
        const scaler = ObjC.classes.MTLFXTemporalScaler;
        const methods = scaler.$ownMethods || [];
        
        methods.forEach(method => {
            if (method.includes('encodeToCommandBuffer')) {
                try {
                    Interceptor.attach(scaler[method].implementation, {
                        onEnter: function(args) {
                            state.upscaling.mfxCalls++;
                            state.upscaling.mfxActive = true;
                            state.upscaling.lastUpscaler = 'MetalFX-Temporal';
                            logTrace('MetalFX Temporal Scaler encoding');
                        }
                    });
                    logDebug(`Hooked MTLFXTemporalScaler.${method}`);
                } catch (e) {}
            }
        });
    }
    
    // MTLFXSpatialScaler
    if (ObjC.classes.MTLFXSpatialScaler) {
        const scaler = ObjC.classes.MTLFXSpatialScaler;
        const methods = scaler.$ownMethods || [];
        
        methods.forEach(method => {
            if (method.includes('encodeToCommandBuffer')) {
                try {
                    Interceptor.attach(scaler[method].implementation, {
                        onEnter: function(args) {
                            state.upscaling.mfxCalls++;
                            state.upscaling.mfxActive = true;
                            state.upscaling.lastUpscaler = 'MetalFX-Spatial';
                            logTrace('MetalFX Spatial Scaler encoding');
                        }
                    });
                    logDebug(`Hooked MTLFXSpatialScaler.${method}`);
                } catch (e) {}
            }
        });
    }
}

// ============================================================================
// AAPL Buffer Tracking
// ============================================================================

function hookAAPLBuffers() {
    const gameModule = Process.findModuleByName('Cyberpunk2077');
    if (!gameModule) return;
    
    logInfo('Setting up AAPL buffer tracking...');
    
    const exports = gameModule.enumerateExports();
    
    // Look for aapl-prefixed buffer allocations
    const aaplExports = exports.filter(e => 
        e.name.toLowerCase().includes('aapl') && e.type === 'function'
    );
    
    aaplExports.forEach(exp => {
        try {
            Interceptor.attach(exp.address, {
                onEnter: function(args) {
                    state.aapl.aaplBufferCount++;
                    
                    const name = exp.name.toLowerCase();
                    if (name.includes('bucket')) {
                        state.aapl.bucketsBufferAllocated = true;
                    } else if (name.includes('raybuffer') || name.includes('ray_buffer')) {
                        state.aapl.rayBufferAllocated = true;
                    } else if (name.includes('payload')) {
                        state.aapl.payloadBufferAllocated = true;
                    }
                    
                    logDebug(`AAPL buffer operation: ${exp.name}`);
                }
            });
        } catch (e) {}
    });
    
    logInfo(`Found ${aaplExports.length} AAPL-prefixed exports`);
}

// ============================================================================
// Configuration Value Probing
// ============================================================================

function probeConfigValues() {
    if (CONFIG.safeMode || !CONFIG.enableConfigScan) return;
    const gameModule = Process.findModuleByName('Cyberpunk2077');
    if (!gameModule) return;
    
    logInfo('Probing configuration values...');
    
    // Search for configuration strings in memory
    // These are data symbols that store configuration state
    
    const configPatterns = [
        { pattern: 'EnableReferenceAAPLOptim', key: 'aaplOptim' },
        { pattern: 'UseAAPLOptimPass', key: 'aaplPass' },
        { pattern: 'EnableNRD', key: 'nrd' },
        { pattern: 'DenoisingConcurrentDispatch', key: 'concurrentDenoising' },
    ];
    
    configPatterns.forEach(({ pattern, key }) => {
        try {
            const results = Memory.scanSync(
                gameModule.base, 
                gameModule.size,
                pattern.split('').map(c => c.charCodeAt(0).toString(16).padStart(2, '0')).join(' ')
            );
            
            if (results.length > 0) {
                logDebug(`Found ${pattern} at ${results.length} locations`);
                
                // Try to read nearby memory for boolean value
                results.forEach(result => {
                    try {
                        // Check bytes after the string for a boolean flag
                        const afterString = result.address.add(pattern.length);
                        const padding = 8 - (pattern.length % 8); // Align to 8 bytes
                        const valueAddr = afterString.add(padding);
                        
                        // Read potential boolean value
                        const possibleBool = valueAddr.readU8();
                        logTrace(`${pattern}: possible value at +${padding}: ${possibleBool}`);
                    } catch (e) {}
                });
            }
        } catch (e) {
            logTrace(`Error scanning for ${pattern}: ${e.message}`);
        }
    });
}

// ============================================================================
// Metal Acceleration Structure Tracking
// ============================================================================

function hookAccelerationStructures() {
    if (CONFIG.safeMode) return;
    if (!ObjC.available) return;
    
    logInfo('Setting up acceleration structure tracking...');
    
    const resolver = new ApiResolver('objc');
    
    // Hook acceleration structure creation
    const accelMatches = resolver.enumerateMatches('-[* newAccelerationStructureWithDescriptor:]');
    accelMatches.forEach(match => {
        if (!match.name.includes('MTL')) return;
        
        try {
            Interceptor.attach(match.address, {
                onEnter: function(args) {
                    state.rayTracing.accelerationStructures++;
                    logTrace('Acceleration structure created');
                }
            });
            logDebug(`Hooked accel struct: ${match.name}`);
        } catch (e) {}
    });
}

// ============================================================================
// Status Reporter
// ============================================================================

function printStatus() {
    if (CONFIG.outputConsole) {
        console.log('\n' + '═'.repeat(70));
        console.log('║ CYBERPUNK 2077 macOS - APPLE OPTIMIZATION STATUS');
        console.log('═'.repeat(70));
    }
    
    // Upscaling status
    if (CONFIG.outputConsole) {
        console.log('\n┌─ UPSCALING ─────────────────────────────────────────────────────────┐');
        console.log(`│ Active Upscaler: ${state.upscaling.lastUpscaler || 'NONE DETECTED'}`);
        console.log(`│ FSR2 Calls: ${state.upscaling.fsr2Calls}  |  FSR3 Calls: ${state.upscaling.fsr3Calls}  |  MetalFX Calls: ${state.upscaling.mfxCalls}`);
        console.log(`│ FSR2 Active: ${state.upscaling.fsr2Active ? '✓' : '✗'}  |  FSR3 Active: ${state.upscaling.fsr3Active ? '✓' : '✗'}  |  MFX Active: ${state.upscaling.mfxActive ? '✓' : '✗'}`);
        console.log('└─────────────────────────────────────────────────────────────────────┘');
    }
    
    // Apple optimizations
    if (CONFIG.outputConsole) {
        console.log('\n┌─ APPLE OPTIMIZATIONS ───────────────────────────────────────────────┐');
        console.log(`│ EnableReferenceAAPLOptim: ${state.aapl.optimEnabled === null ? '? UNKNOWN' : (state.aapl.optimEnabled ? '✓ ENABLED' : '✗ DISABLED')}`);
        console.log(`│ UseAAPLOptimPass: ${state.aapl.optimPassUsed ? '✓ IN USE' : '? NOT DETECTED'}`);
        console.log(`│ AAPL Buffer Operations: ${state.aapl.aaplBufferCount}`);
        console.log(`│   - Buckets Buffer: ${state.aapl.bucketsBufferAllocated ? '✓' : '✗'}`);
        console.log(`│   - Ray Buffer: ${state.aapl.rayBufferAllocated ? '✓' : '✗'}`);
        console.log(`│   - Payload Buffer: ${state.aapl.payloadBufferAllocated ? '✓' : '✗'}`);
        console.log('└─────────────────────────────────────────────────────────────────────┘');
    }
    
    // Ray tracing
    if (CONFIG.outputConsole) {
        console.log('\n┌─ RAY TRACING ───────────────────────────────────────────────────────┐');
        console.log(`│ Acceleration Structures: ${state.rayTracing.accelerationStructures}`);
        console.log(`│ RTXDI Calls: ${state.rayTracing.rtxdiCalls}  |  ReSTIRGI Calls: ${state.rayTracing.restirgiCalls}`);
        console.log(`│ Reflection Calls: ${state.rayTracing.reflectionCalls}  |  Shadow Calls: ${state.rayTracing.shadowCalls}`);
        console.log('└─────────────────────────────────────────────────────────────────────┘');
    }
    
    // Denoising
    if (CONFIG.outputConsole) {
        console.log('\n┌─ DENOISING ─────────────────────────────────────────────────────────┐');
        console.log(`│ NRD Enabled: ${state.denoising.nrdEnabled === null ? '? UNKNOWN' : (state.denoising.nrdEnabled ? '✓' : '✗')}`);
        console.log(`│ AAPL Shader Preference: ${state.denoising.aaplShaderPreference || '? UNKNOWN'}`);
        console.log(`│ Concurrent Dispatch: ${state.denoising.concurrentDispatch === null ? '? UNKNOWN' : (state.denoising.concurrentDispatch ? '✓' : '✗')}`);
        console.log('└─────────────────────────────────────────────────────────────────────┘');
    }
    
    // Analysis
    if (CONFIG.outputConsole) console.log('\n┌─ ANALYSIS ──────────────────────────────────────────────────────────┐');
    
    if (state.upscaling.mfxCalls > 0 && state.upscaling.fsr2Calls === 0 && state.upscaling.fsr3Calls === 0) {
        if (CONFIG.outputConsole) console.log('│ ✓ Using MetalFX exclusively (optimal for macOS)');
    } else if (state.upscaling.fsr2Calls > 0 || state.upscaling.fsr3Calls > 0) {
        if (CONFIG.outputConsole) console.log('│ ⚠ Using FSR directly instead of MetalFX - investigate settings');
    } else {
        if (CONFIG.outputConsole) console.log('│ ? No upscaling detected yet - may need more gameplay');
    }
    
    if (state.aapl.aaplBufferCount > 0) {
        if (CONFIG.outputConsole) console.log('│ ✓ Apple-specific buffer management is ACTIVE');
    } else {
        if (CONFIG.outputConsole) console.log('│ ⚠ No AAPL buffer operations detected - may not be optimized');
    }
    
    if (state.rayTracing.shadowCalls > state.rayTracing.reflectionCalls * 2) {
        if (CONFIG.outputConsole) console.log('│ ⚠ High RT shadow overhead - consider disabling for performance');
    }
    
    if (CONFIG.outputConsole) {
        console.log('└─────────────────────────────────────────────────────────────────────┘');
        console.log('\n' + '═'.repeat(70) + '\n');
    }
    
    // Send JSON for mod manager integration
    send({
        type: 'aapl_status',
        data: {
            upscaling: state.upscaling,
            aapl: state.aapl,
            rayTracing: state.rayTracing,
            denoising: state.denoising,
            timestamp: new Date().toISOString(),
        }
    });
}

// ============================================================================
// Memory Watch for Runtime Config Changes
// ============================================================================

function watchConfigChanges() {
    logInfo('Setting up configuration watchers...');
    
    // This would require finding the actual memory addresses of config variables
    // For now, we'll poll the render node calls to infer configuration
}

// ============================================================================
// Entry Point
// ============================================================================

if (CONFIG.outputConsole) {
    console.log('\n' + '═'.repeat(70));
    console.log('║ CYBERPUNK 2077 macOS - APPLE OPTIMIZATION PROBE v1.0');
    console.log('║ Analyzing AAPL optimizations, FSR/MetalFX paths, and RT performance');
    console.log('═'.repeat(70) + '\n');
}

// Check prerequisites
if (!ObjC.available) {
    logError('Objective-C runtime not available');
} else {
    logInfo('Objective-C runtime available');
}

const gameModule = Process.findModuleByName('Cyberpunk2077');
if (gameModule) {
    logInfo(`Game module found: ${gameModule.base} (${(gameModule.size / 1024 / 1024).toFixed(1)}MB)`);
} else {
    logError('Game module not found!');
}

let intervalId = null;

// Install hooks (safeMode keeps the surface minimal)
if (CONFIG.trackUpscaling) {
    hookRenderNodes();
    hookMetalFX();
}

if (CONFIG.trackAAPL) {
    hookAAPLBuffers();
}

if (CONFIG.trackRayTracing) {
    hookAccelerationStructures();
}

probeConfigValues();
watchConfigChanges();

// Start periodic status reports
intervalId = setInterval(printStatus, CONFIG.probeInterval);

if (CONFIG.outputConsole) {
    console.log('\n' + '═'.repeat(70));
    console.log('║ Probe installed - monitoring started');
    console.log('║ Status reports every ' + (CONFIG.probeInterval / 1000) + ' seconds');
    console.log('║ Play the game to generate data...');
    console.log('═'.repeat(70) + '\n');
}

// Initial status
setTimeout(printStatus, 1000);

Script.bindExitHandler(function() {
    try {
        if (intervalId !== null) {
            clearInterval(intervalId);
            intervalId = null;
        }
        // final status snapshot
        printStatus();
    } catch (e) {}
});

rpc.exports = {
    start: function() {
        if (intervalId === null) intervalId = setInterval(printStatus, CONFIG.probeInterval);
        return true;
    },
    stop: function() {
        if (intervalId !== null) {
            clearInterval(intervalId);
            intervalId = null;
        }
        return true;
    },
    status: function() { return state; },
    setconfig: function(cfg) {
        if (cfg && typeof cfg === 'object') {
            if (typeof cfg.probeInterval === 'number') CONFIG.probeInterval = cfg.probeInterval;
            if (typeof cfg.outputConsole === 'boolean') CONFIG.outputConsole = cfg.outputConsole;
            if (typeof cfg.logLevel === 'number') CONFIG.logLevel = cfg.logLevel;
            if (typeof cfg.safeMode === 'boolean') CONFIG.safeMode = cfg.safeMode;
            if (typeof cfg.enableConfigScan === 'boolean') CONFIG.enableConfigScan = cfg.enableConfigScan;
        }
        return CONFIG;
    },
};
