"""
Cyberpunk 2077 macOS Settings Optimizer

Based on binary analysis findings, provides optimized configuration
recommendations for MetalFX, FSR, and ray tracing settings.

Key findings from binary analysis:
- Game has dual FSR/MetalFX paths
- Apple-specific optimizations exist (EnableReferenceAAPLOptim, UseAAPLOptimPass)
- AAPL buffer systems for ray tracing
- Multiple denoiser configurations
"""

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MacModel(Enum):
    """Mac model categories for optimization profiles."""
    M1_BASE = "m1_base"      # M1, M1 Pro 8-core
    M1_PRO = "m1_pro"        # M1 Pro 10-core, M1 Max
    M2_BASE = "m2_base"      # M2
    M2_PRO = "m2_pro"        # M2 Pro, M2 Max
    M3_BASE = "m3_base"      # M3
    M3_PRO = "m3_pro"        # M3 Pro, M3 Max
    M4_BASE = "m4_base"      # M4
    M4_PRO = "m4_pro"        # M4 Pro, M4 Max
    UNKNOWN = "unknown"


class PerformanceTarget(Enum):
    """Performance target presets."""
    QUALITY = "quality"           # Best visuals, 30fps target
    BALANCED = "balanced"         # Good visuals, 45fps target
    PERFORMANCE = "performance"   # Playable, 60fps target
    ULTRA_PERF = "ultra_performance"  # Maximum FPS


@dataclass
class OptimizedSettings:
    """Container for optimized game settings."""
    # Upscaling
    # Note: FSR recommended over MetalFX based on binary analysis showing
    # FSR has better frame pacing (explicit fences/async queues)
    upscaling_type: str = "fsr2"  # fsr2, fsr3, metalfx, native
    upscaling_quality: int = 2       # 0=Ultra Quality, 1=Quality, 2=Balanced, 3=Performance, 4=Ultra Perf
    sharpening: float = 0.5          # 0.0-1.0
    frame_generation: bool = False
    
    # Ray Tracing
    ray_tracing_enabled: bool = False
    rt_reflections: bool = False
    rt_shadows_global: bool = False
    rt_shadows_local: bool = False
    rt_ambient_occlusion: bool = False
    rt_lighting_quality: int = 0     # 0=Off, 1=Low, 2=Medium, 3=High
    path_tracing: bool = False
    
    # Denoising
    nrd_enabled: bool = True
    denoising_concurrent: bool = True
    
    # Apple-specific (theoretical - may require game modification)
    aapl_optim_enabled: bool = True
    aapl_optim_pass: bool = True
    
    # General
    resolution_scale: float = 1.0
    vsync: bool = True
    
    # Metadata
    profile_name: str = ""
    estimated_fps: str = ""
    visual_quality: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'upscaling': {
                'type': self.upscaling_type,
                'quality': self.upscaling_quality,
                'sharpening': self.sharpening,
                'frame_generation': self.frame_generation,
            },
            'ray_tracing': {
                'enabled': self.ray_tracing_enabled,
                'reflections': self.rt_reflections,
                'shadows_global': self.rt_shadows_global,
                'shadows_local': self.rt_shadows_local,
                'ambient_occlusion': self.rt_ambient_occlusion,
                'lighting_quality': self.rt_lighting_quality,
                'path_tracing': self.path_tracing,
            },
            'denoising': {
                'nrd_enabled': self.nrd_enabled,
                'concurrent': self.denoising_concurrent,
            },
            'apple_optimizations': {
                'aapl_optim_enabled': self.aapl_optim_enabled,
                'aapl_optim_pass': self.aapl_optim_pass,
            },
            'general': {
                'resolution_scale': self.resolution_scale,
                'vsync': self.vsync,
            },
            'metadata': {
                'profile_name': self.profile_name,
                'estimated_fps': self.estimated_fps,
                'visual_quality': self.visual_quality,
            }
        }


class SettingsOptimizer:
    """
    Generates optimized settings for Cyberpunk 2077 on macOS
    based on hardware detection and performance targets.
    """
    
    # Optimization profiles based on binary analysis
    PROFILES = {
        # M1 Base - Limited GPU, aim for playability
        # Using FSR for better frame pacing based on binary analysis
        (MacModel.M1_BASE, PerformanceTarget.QUALITY): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=2,  # Balanced
            sharpening=0.5,
            frame_generation=False,
            ray_tracing_enabled=False,
            profile_name="M1 Quality (FSR2)",
            estimated_fps="25-35",
            visual_quality="Good",
        ),
        (MacModel.M1_BASE, PerformanceTarget.PERFORMANCE): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=4,  # Ultra Performance
            sharpening=0.7,
            frame_generation=False,
            ray_tracing_enabled=False,
            resolution_scale=0.8,
            profile_name="M1 Performance (FSR2)",
            estimated_fps="40-55",
            visual_quality="Acceptable",
        ),
        
        # M1 Pro/Max - Can handle some RT
        (MacModel.M1_PRO, PerformanceTarget.QUALITY): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=1,  # Quality
            sharpening=0.4,
            frame_generation=False,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=False,
            rt_shadows_local=False,
            rt_lighting_quality=1,
            profile_name="M1 Pro/Max Quality (FSR2 + RT)",
            estimated_fps="30-40",
            visual_quality="Very Good",
        ),
        (MacModel.M1_PRO, PerformanceTarget.PERFORMANCE): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=3,  # Performance
            sharpening=0.6,
            frame_generation=False,
            ray_tracing_enabled=False,
            profile_name="M1 Pro/Max Performance (FSR2)",
            estimated_fps="50-65",
            visual_quality="Good",
        ),
        
        # M2 Base
        (MacModel.M2_BASE, PerformanceTarget.QUALITY): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=1,
            sharpening=0.4,
            frame_generation=False,
            ray_tracing_enabled=False,
            profile_name="M2 Quality (FSR2)",
            estimated_fps="30-40",
            visual_quality="Good",
        ),
        (MacModel.M2_BASE, PerformanceTarget.PERFORMANCE): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=3,
            sharpening=0.6,
            frame_generation=False,
            ray_tracing_enabled=False,
            profile_name="M2 Performance (FSR2)",
            estimated_fps="45-60",
            visual_quality="Good",
        ),
        
        # M2 Pro/Max - Good RT capability
        (MacModel.M2_PRO, PerformanceTarget.QUALITY): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=0,  # Ultra Quality
            sharpening=0.3,
            frame_generation=False,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=True,
            rt_shadows_local=False,
            rt_lighting_quality=2,
            profile_name="M2 Pro/Max Quality (FSR2 + RT)",
            estimated_fps="35-45",
            visual_quality="Excellent",
        ),
        (MacModel.M2_PRO, PerformanceTarget.BALANCED): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=2,
            sharpening=0.5,
            frame_generation=False,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=False,
            rt_shadows_local=False,
            rt_lighting_quality=1,
            profile_name="M2 Pro/Max Balanced (FSR2 + RT)",
            estimated_fps="45-55",
            visual_quality="Very Good",
        ),
        (MacModel.M2_PRO, PerformanceTarget.PERFORMANCE): OptimizedSettings(
            upscaling_type="fsr2",
            upscaling_quality=3,
            sharpening=0.6,
            frame_generation=False,
            ray_tracing_enabled=False,
            profile_name="M2 Pro/Max Performance (FSR2)",
            estimated_fps="60-75",
            visual_quality="Good",
        ),
        
        # M3 Base - Hardware RT support
        (MacModel.M3_BASE, PerformanceTarget.QUALITY): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=1,
            sharpening=0.4,
            frame_generation=False,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=False,
            rt_lighting_quality=1,
            profile_name="M3 Quality (FSR3 + RT)",
            estimated_fps="35-45",
            visual_quality="Very Good",
        ),
        (MacModel.M3_BASE, PerformanceTarget.PERFORMANCE): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=3,
            sharpening=0.5,
            frame_generation=False,
            ray_tracing_enabled=False,
            profile_name="M3 Performance (FSR3)",
            estimated_fps="55-70",
            visual_quality="Good",
        ),
        
        # M3 Pro/Max - Best RT performance
        (MacModel.M3_PRO, PerformanceTarget.QUALITY): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=0,
            sharpening=0.3,
            frame_generation=True,  # FSR3 Frame Gen
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=True,
            rt_shadows_local=True,
            rt_ambient_occlusion=True,
            rt_lighting_quality=3,
            profile_name="M3 Pro/Max Quality (FSR3 + RT + FrameGen)",
            estimated_fps="40-55",
            visual_quality="Excellent",
        ),
        (MacModel.M3_PRO, PerformanceTarget.BALANCED): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=1,
            sharpening=0.4,
            frame_generation=True,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=True,
            rt_shadows_local=False,
            rt_lighting_quality=2,
            profile_name="M3 Pro/Max Balanced (FSR3 + RT + FrameGen)",
            estimated_fps="55-70",
            visual_quality="Very Good",
        ),
        (MacModel.M3_PRO, PerformanceTarget.PERFORMANCE): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=2,
            sharpening=0.5,
            frame_generation=True,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=False,
            rt_shadows_local=False,
            rt_lighting_quality=1,
            profile_name="M3 Pro/Max Performance (FSR3 + FrameGen)",
            estimated_fps="70-90",
            visual_quality="Good",
        ),
        
        # M4 - Latest generation
        (MacModel.M4_BASE, PerformanceTarget.QUALITY): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=1,
            sharpening=0.4,
            frame_generation=True,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=True,
            rt_lighting_quality=2,
            profile_name="M4 Quality (FSR3 + RT + FrameGen)",
            estimated_fps="45-55",
            visual_quality="Excellent",
        ),
        (MacModel.M4_BASE, PerformanceTarget.PERFORMANCE): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=2,
            sharpening=0.5,
            frame_generation=True,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_lighting_quality=1,
            profile_name="M4 Performance (FSR3 + FrameGen)",
            estimated_fps="65-80",
            visual_quality="Very Good",
        ),
        
        # M4 Pro/Max
        (MacModel.M4_PRO, PerformanceTarget.QUALITY): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=0,
            sharpening=0.3,
            frame_generation=True,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=True,
            rt_shadows_local=True,
            rt_ambient_occlusion=True,
            rt_lighting_quality=3,
            path_tracing=False,  # Still too expensive
            profile_name="M4 Pro/Max Quality (FSR3 + Full RT)",
            estimated_fps="50-65",
            visual_quality="Maximum",
        ),
        (MacModel.M4_PRO, PerformanceTarget.BALANCED): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=1,
            sharpening=0.4,
            frame_generation=True,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=True,
            rt_shadows_local=True,
            rt_lighting_quality=2,
            profile_name="M4 Pro/Max Balanced (FSR3 + RT)",
            estimated_fps="65-80",
            visual_quality="Excellent",
        ),
        (MacModel.M4_PRO, PerformanceTarget.PERFORMANCE): OptimizedSettings(
            upscaling_type="fsr3",
            upscaling_quality=2,
            sharpening=0.5,
            frame_generation=True,
            ray_tracing_enabled=True,
            rt_reflections=True,
            rt_shadows_global=False,
            rt_lighting_quality=1,
            profile_name="M4 Pro/Max Performance (FSR3 + FrameGen)",
            estimated_fps="80-100",
            visual_quality="Very Good",
        ),
    }
    
    def __init__(self):
        self.detected_model: MacModel = MacModel.UNKNOWN
        self.gpu_cores: int = 0
        self.memory_gb: int = 0
        self._detect_hardware()
    
    def _detect_hardware(self):
        """Detect Mac hardware configuration."""
        try:
            # Get chip info
            result = subprocess.run(
                ['sysctl', '-n', 'machdep.cpu.brand_string'],
                capture_output=True,
                text=True,
                timeout=5
            )
            chip_string = result.stdout.strip().lower()
            
            # Get memory
            mem_result = subprocess.run(
                ['sysctl', '-n', 'hw.memsize'],
                capture_output=True,
                text=True,
                timeout=5
            )
            self.memory_gb = int(int(mem_result.stdout.strip()) / (1024**3))
            
            # Get GPU cores (approximate from model)
            gpu_result = subprocess.run(
                ['system_profiler', 'SPDisplaysDataType', '-json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Determine Mac model
            if 'm4' in chip_string:
                if 'max' in chip_string or 'pro' in chip_string:
                    self.detected_model = MacModel.M4_PRO
                    self.gpu_cores = 40 if 'max' in chip_string else 20
                else:
                    self.detected_model = MacModel.M4_BASE
                    self.gpu_cores = 10
            elif 'm3' in chip_string:
                if 'max' in chip_string or 'pro' in chip_string:
                    self.detected_model = MacModel.M3_PRO
                    self.gpu_cores = 40 if 'max' in chip_string else 18
                else:
                    self.detected_model = MacModel.M3_BASE
                    self.gpu_cores = 10
            elif 'm2' in chip_string:
                if 'max' in chip_string or 'pro' in chip_string or 'ultra' in chip_string:
                    self.detected_model = MacModel.M2_PRO
                    self.gpu_cores = 38 if 'max' in chip_string else 19
                else:
                    self.detected_model = MacModel.M2_BASE
                    self.gpu_cores = 10
            elif 'm1' in chip_string:
                if 'max' in chip_string or 'pro' in chip_string or 'ultra' in chip_string:
                    self.detected_model = MacModel.M1_PRO
                    self.gpu_cores = 32 if 'max' in chip_string else 16
                else:
                    self.detected_model = MacModel.M1_BASE
                    self.gpu_cores = 8
            else:
                self.detected_model = MacModel.UNKNOWN
                
        except Exception as e:
            print(f"Hardware detection failed: {e}")
            self.detected_model = MacModel.UNKNOWN
    
    def get_hardware_info(self) -> dict:
        """Get detected hardware information."""
        return {
            'model': self.detected_model.value,
            'model_display': self.detected_model.name.replace('_', ' '),
            'gpu_cores': self.gpu_cores,
            'memory_gb': self.memory_gb,
        }
    
    def get_recommended_settings(
        self, 
        target: PerformanceTarget = PerformanceTarget.BALANCED
    ) -> OptimizedSettings:
        """Get recommended settings for detected hardware and target."""
        
        # Try exact match first
        key = (self.detected_model, target)
        if key in self.PROFILES:
            return self.PROFILES[key]
        
        # Fall back to balanced if specific target not found
        key = (self.detected_model, PerformanceTarget.BALANCED)
        if key in self.PROFILES:
            settings = self.PROFILES[key]
            settings.profile_name = f"{self.detected_model.name} {target.value}"
            return settings
        
        # Default conservative settings
        return OptimizedSettings(
            upscaling_type="metalfx",
            upscaling_quality=3,
            sharpening=0.5,
            frame_generation=False,
            ray_tracing_enabled=False,
            profile_name="Conservative Default",
            estimated_fps="Variable",
            visual_quality="Good",
        )
    
    def get_all_profiles_for_hardware(self) -> list[OptimizedSettings]:
        """Get all available profiles for detected hardware."""
        profiles = []
        for target in PerformanceTarget:
            key = (self.detected_model, target)
            if key in self.PROFILES:
                profiles.append(self.PROFILES[key])
        
        # If no profiles found, return defaults
        if not profiles:
            for target in [PerformanceTarget.QUALITY, PerformanceTarget.BALANCED, PerformanceTarget.PERFORMANCE]:
                profiles.append(self.get_recommended_settings(target))
        
        return profiles
    
    def generate_optimization_report(self) -> dict:
        """Generate a comprehensive optimization report."""
        hardware = self.get_hardware_info()
        profiles = self.get_all_profiles_for_hardware()
        
        # Binary analysis insights
        insights = [
            {
                'title': 'FSR vs MetalFX: FSR Has Better Frame Pacing',
                'finding': 'Binary analysis shows FSR has explicit synchronization (CompositionFence, GameFence, PresentQueue, Async Queues) while MetalFX relies on Metal internal sync',
                'recommendation': 'Try FSR 2/3 over MetalFX for potentially smoother gameplay - FSR is more directly integrated with game render loop',
                'impact': 'Medium - may reduce micro-stutter',
            },
            {
                'title': 'AAPL Optimizations Are for Ray Tracing ONLY',
                'finding': 'EnableReferenceAAPLOptim and UseAAPLOptimPass affect ray tracing buffers (aaplRayBuffer, aaplBucketsBuffer, ReSTIRGI), NOT upscaling',
                'recommendation': 'These optimizations are independent of MetalFX/FSR choice - they only matter if ray tracing is enabled',
                'impact': 'High for RT users, None for non-RT users',
            },
            {
                'title': 'Ray Tracing Overhead',
                'finding': 'RT shadows are most expensive, reflections less so',
                'recommendation': 'Disable RT shadows first for performance, keep reflections if possible',
                'impact': 'High (30-50% FPS difference)',
            },
            {
                'title': 'Path Tracing',
                'finding': 'Path tracing is extremely expensive on all Mac hardware',
                'recommendation': 'Avoid path tracing except for screenshots on high-end M3/M4 Pro/Max',
                'impact': 'Very High (100-200% FPS difference)',
            },
            {
                'title': 'FSR 3 Frame Generation',
                'finding': 'Frame generation is available but adds latency',
                'recommendation': 'Enable on M3/M4 series for higher frame rates, disable for lower input lag',
                'impact': 'Medium (20-40% FPS increase, ~10ms latency increase)',
            },
            {
                'title': 'Denoising Configuration',
                'finding': 'NRD with Apple-specific shaders available',
                'recommendation': 'Keep denoising enabled with concurrent dispatch for best quality/performance',
                'impact': 'Low',
            },
        ]
        
        return {
            'hardware': hardware,
            'profiles': [p.to_dict() for p in profiles],
            'insights': insights,
            'generated_at': str(Path(__file__).stat().st_mtime),
        }


# Singleton instance
_optimizer_instance: Optional[SettingsOptimizer] = None


def get_optimizer() -> SettingsOptimizer:
    """Get or create optimizer instance."""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = SettingsOptimizer()
    return _optimizer_instance
