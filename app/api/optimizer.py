"""
API endpoints for Cyberpunk 2077 macOS Settings Optimizer.

Provides hardware detection and optimized settings recommendations
based on binary analysis findings.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.settings_optimizer import (
    OptimizedSettings,
    PerformanceTarget,
    SettingsOptimizer,
    get_optimizer,
)

router = APIRouter(prefix="/api/optimizer", tags=["optimizer"])


class HardwareInfo(BaseModel):
    """Hardware information response."""
    model: str
    model_display: str
    gpu_cores: int
    memory_gb: int


class SettingsProfile(BaseModel):
    """Optimized settings profile."""
    profile_name: str
    estimated_fps: str
    visual_quality: str
    upscaling: dict
    ray_tracing: dict
    denoising: dict
    apple_optimizations: dict
    general: dict


class OptimizationInsight(BaseModel):
    """Binary analysis insight."""
    title: str
    finding: str
    recommendation: str
    impact: str


class OptimizationReport(BaseModel):
    """Complete optimization report."""
    hardware: HardwareInfo
    profiles: list[dict]
    insights: list[OptimizationInsight]


@router.get("/hardware", response_model=HardwareInfo)
async def get_hardware_info():
    """
    Detect and return Mac hardware information.
    
    Returns:
        HardwareInfo with detected Mac model, GPU cores, and memory
    """
    optimizer = get_optimizer()
    info = optimizer.get_hardware_info()
    
    return HardwareInfo(
        model=info['model'],
        model_display=info['model_display'],
        gpu_cores=info['gpu_cores'],
        memory_gb=info['memory_gb']
    )


@router.get("/recommended")
async def get_recommended_settings(
    target: str = "balanced"
):
    """
    Get recommended settings for detected hardware.
    
    Args:
        target: Performance target (quality, balanced, performance, ultra_performance)
    
    Returns:
        OptimizedSettings with recommended configuration
    """
    optimizer = get_optimizer()
    
    # Parse target
    try:
        perf_target = PerformanceTarget(target.lower())
    except ValueError:
        perf_target = PerformanceTarget.BALANCED
    
    settings = optimizer.get_recommended_settings(perf_target)
    
    return settings.to_dict()


@router.get("/profiles")
async def get_all_profiles():
    """
    Get all available optimization profiles for detected hardware.
    
    Returns:
        List of all available profiles
    """
    optimizer = get_optimizer()
    profiles = optimizer.get_all_profiles_for_hardware()
    
    return [p.to_dict() for p in profiles]


@router.get("/report", response_model=OptimizationReport)
async def get_optimization_report():
    """
    Get comprehensive optimization report with hardware info,
    all profiles, and binary analysis insights.
    
    Returns:
        Complete optimization report
    """
    optimizer = get_optimizer()
    report = optimizer.generate_optimization_report()
    
    return OptimizationReport(
        hardware=HardwareInfo(**report['hardware']),
        profiles=report['profiles'],
        insights=[OptimizationInsight(**i) for i in report['insights']]
    )


@router.get("/quick-tips")
async def get_quick_tips():
    """
    Get quick optimization tips based on binary analysis.
    
    Returns:
        List of actionable tips
    """
    optimizer = get_optimizer()
    hardware = optimizer.get_hardware_info()
    
    tips = []
    
    # Model-specific tips
    if 'm1' in hardware['model'].lower():
        tips.append({
            'priority': 'high',
            'tip': 'Disable all ray tracing for best performance on M1',
            'reason': 'M1 lacks hardware RT acceleration'
        })
        tips.append({
            'priority': 'medium',
            'tip': 'Use MetalFX Performance or Ultra Performance mode',
            'reason': 'M1 GPU needs render resolution reduction'
        })
    
    if 'm2' in hardware['model'].lower():
        if 'pro' in hardware['model'].lower():
            tips.append({
                'priority': 'medium',
                'tip': 'RT Reflections are playable, RT Shadows are expensive',
                'reason': 'M2 Pro/Max have decent RT performance'
            })
        else:
            tips.append({
                'priority': 'high',
                'tip': 'Disable ray tracing or use only RT Reflections',
                'reason': 'Base M2 has limited RT capability'
            })
    
    if 'm3' in hardware['model'].lower() or 'm4' in hardware['model'].lower():
        tips.append({
            'priority': 'low',
            'tip': 'Enable FSR 3 Frame Generation for smoother gameplay',
            'reason': 'M3/M4 series handle frame interpolation well'
        })
        tips.append({
            'priority': 'medium',
            'tip': 'RT Medium or RT High presets are recommended',
            'reason': 'M3/M4 have hardware ray tracing support'
        })
    
    # Universal tips from binary analysis
    tips.extend([
        {
            'priority': 'high',
            'tip': 'Try FSR over MetalFX for smoother gameplay',
            'reason': 'Binary analysis shows FSR has explicit frame pacing (fences, async queues) while MetalFX relies on Metal internal sync'
        },
        {
            'priority': 'high',
            'tip': 'AAPL optimizations only affect Ray Tracing',
            'reason': 'EnableReferenceAAPLOptim improves RT buffer management, not upscaling'
        },
        {
            'priority': 'medium',
            'tip': 'Disable Path Tracing (RT Overdrive)',
            'reason': 'Path tracing is extremely expensive on all Mac hardware'
        },
        {
            'priority': 'low',
            'tip': 'Keep NRD denoising enabled',
            'reason': 'Denoiser has Apple-specific shader variants (DenoisingShaderPreferenceAAPL)'
        },
        {
            'priority': 'info',
            'tip': 'FSR has 6 explicit sync fences, MetalFX has none visible',
            'reason': 'FSR: CompositionFence, GameFence, PresentFence, InterpolationFence, PresentQueue, Async Queue'
        },
    ])
    
    return {'hardware': hardware, 'tips': tips}


@router.get("/comparison")
async def compare_settings(
    current_upscaling: str = "metalfx",
    current_upscaling_quality: int = 2,
    current_rt_enabled: bool = False,
    current_rt_shadows: bool = False
):
    """
    Compare current settings against recommended.
    
    Args:
        current_upscaling: Current upscaling type
        current_upscaling_quality: Current quality level (0-4)
        current_rt_enabled: Whether RT is enabled
        current_rt_shadows: Whether RT shadows are enabled
    
    Returns:
        Comparison analysis with improvement suggestions
    """
    optimizer = get_optimizer()
    recommended = optimizer.get_recommended_settings(PerformanceTarget.BALANCED)
    
    improvements = []
    potential_fps_gain = 0
    
    # Analyze upscaling - Note: FSR now recommended over MetalFX based on binary analysis
    if current_upscaling.lower() == 'metalfx':
        improvements.append({
            'setting': 'Upscaling Type',
            'current': current_upscaling,
            'recommended': 'FSR2 or FSR3',
            'reason': 'FSR has explicit frame pacing (6 sync fences/queues) for smoother gameplay; MetalFX relies on Metal internal sync',
            'estimated_impact': 'Potentially smoother frame pacing, reduced micro-stutter'
        })
    
    # Analyze quality level for hardware
    hardware = optimizer.get_hardware_info()
    if 'm1' in hardware['model'].lower() and current_upscaling_quality < 3:
        improvements.append({
            'setting': 'Upscaling Quality',
            'current': current_upscaling_quality,
            'recommended': 3,
            'reason': 'M1 benefits from lower render resolution',
            'estimated_impact': '20-40% performance improvement'
        })
        potential_fps_gain += 30
    
    # Analyze RT settings
    if current_rt_enabled and 'm1' in hardware['model'].lower():
        improvements.append({
            'setting': 'Ray Tracing',
            'current': 'Enabled',
            'recommended': 'Disabled',
            'reason': 'M1 lacks hardware RT - significant performance cost',
            'estimated_impact': '30-50% performance improvement'
        })
        potential_fps_gain += 40
    
    if current_rt_shadows and current_rt_enabled:
        improvements.append({
            'setting': 'RT Shadows',
            'current': 'Enabled',
            'recommended': 'Disabled (keep RT Reflections)',
            'reason': 'RT Shadows are most expensive, reflections are cheaper',
            'estimated_impact': '20-30% performance improvement'
        })
        potential_fps_gain += 25
    
    return {
        'current_settings': {
            'upscaling': current_upscaling,
            'upscaling_quality': current_upscaling_quality,
            'rt_enabled': current_rt_enabled,
            'rt_shadows': current_rt_shadows,
        },
        'recommended_settings': recommended.to_dict(),
        'improvements': improvements,
        'potential_fps_gain_percent': min(potential_fps_gain, 100),
        'hardware': hardware,
    }
