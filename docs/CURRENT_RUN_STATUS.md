# Current Optimization Run Status
**Started:** 2026-01-01

---

## ✅ Currently Running

### 1. Continuous RT Profiler (Background)
**Script:** `scripts/start_rt_profiler.py`  
**Status:** Running in background  
**Mode:** Safe-continuous  
**Duration:** Until stopped (Ctrl+C)

**What it's collecting:**
- Frame timing (FPS, frame times)
- Command buffer counts
- Basic Metal API hooks
- Real-time stats every 5 seconds

**View stats:**
- API: `http://localhost:8000/api/profiler/status`
- Stream: `http://localhost:8000/api/profiler/stream`

---

## 📊 Ready to Run (Interactive)

### 2. Extended Baseline Profiler
**Script:** `scripts/extended_baseline_profiler.py`  
**Status:** Ready (requires in-game navigation)  
**Duration:** 30 minutes total (6 scenarios × 5 minutes)

**To run:**
```bash
cd /Users/jackmazac/Development/macos-modmanager
python3 scripts/extended_baseline_profiler.py
```

**What it does:**
- Prompts you to navigate to each scenario
- Collects 5 minutes of data per scenario
- Saves results to `docs/baseline_profiling_results.json`

**Scenarios:**
1. Dense Urban (Corpo Plaza)
2. City Center
3. Open World (Badlands)
4. Interior Space (Apartment)
5. Interior Space (Shop)
6. Combat Scenario

---

### 3. Burst RT Profiler
**Script:** `scripts/run_burst_rt_profiler.py`  
**Status:** Ready (quick 10-second captures)  
**Duration:** 10 seconds per scenario

**To run:**
```bash
cd /Users/jackmazac/Development/macos-modmanager
python3 scripts/run_burst_rt_profiler.py --duration 10 --scenario "Static Scene"
```

**What it does:**
- Captures RT-specific metrics for 10 seconds
- Tracks acceleration structure operations
- Safe mode with auto-disable timeout
- Saves results to `docs/burst_rt_results_*.json`

**Recommended scenarios:**
- Static Scene (minimal movement)
- Dynamic Scene (many moving objects)
- RT-Heavy Scene (many reflective surfaces)

---

### 4. RT Feature Toggle Benchmark
**Script:** `scripts/rt_feature_toggle_benchmark.py`  
**Status:** Ready (requires RT feature toggling)  
**Duration:** ~40 minutes (4 features × 10 minutes)

**To run:**
```bash
cd /Users/jackmazac/Development/macos-modmanager
python3 scripts/rt_feature_toggle_benchmark.py
```

**What it does:**
- Tests each RT feature ON/OFF
- Measures FPS impact per feature
- Generates feature impact matrix
- Saves results to `docs/rt_feature_benchmark_results.json`

**Features tested:**
1. RT Shadows
2. RT Reflections
3. RT Global Illumination
4. Path Tracing

---

### 5. Command Buffer Profiler
**Script:** `scripts/command_buffer_profiler.py`  
**Status:** Ready (automatic, no interaction)  
**Duration:** 5 minutes

**To run:**
```bash
cd /Users/jackmazac/Development/macos-modmanager
python3 scripts/command_buffer_profiler.py --duration 5
```

**What it does:**
- Analyzes command buffer creation patterns
- Calculates fragmentation metrics
- Identifies optimization opportunities
- Saves results to `docs/command_buffer_analysis_*.json`

---

## 🎮 Recommended Execution Order

### Quick Start (5 minutes)
1. **Command Buffer Profiler** - Run automatically, no interaction needed
2. **Burst RT Profiler** - Quick 10-second captures

### Full Baseline (30-40 minutes)
1. **Extended Baseline Profiler** - Navigate to scenarios as prompted
2. **RT Feature Benchmark** - Toggle RT features as prompted

### Complete Run (1-2 hours)
1. Start continuous profiler (already running)
2. Run extended baseline profiler
3. Run RT feature benchmark
4. Run burst RT profiler (multiple scenarios)
5. Run command buffer profiler

---

## 📈 Current Data Collection

The continuous profiler is currently collecting:
- Real-time FPS
- Frame times
- Command buffer counts
- Basic Metal API metrics

**To view live stats:**
```bash
curl http://localhost:8000/api/profiler/status
```

**To stop profiler:**
- Find the background process and kill it, or
- Use API: `curl -X POST http://localhost:8000/api/profiler/stop`

---

## 📝 Next Steps

1. **Let continuous profiler run** while you play (collects baseline data)
2. **Run command buffer profiler** (5 minutes, automatic)
3. **Run burst RT profiler** (10 seconds, quick captures)
4. **Run extended baseline** when ready (30 minutes, interactive)

---

**Status:** Continuous profiler running, ready for additional phases  
**Game Status:** Running (PID 97152)
