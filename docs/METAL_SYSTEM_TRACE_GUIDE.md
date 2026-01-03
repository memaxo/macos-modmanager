# Metal System Trace Capture Guide
## Phase 1, Week 1: GPU Timeline Analysis

This guide explains how to capture and analyze Metal System Traces for Cyberpunk 2077 on macOS.

---

## Prerequisites

- **Xcode** installed (for Instruments)
- **Cyberpunk 2077** running
- **Admin privileges** (for system-level profiling)

---

## Step 1: Launch Instruments

1. Open **Xcode**
2. Go to **Xcode → Open Developer Tool → Instruments**
3. Select **Metal System Trace** template

---

## Step 2: Configure Capture

1. **Select Target Process:**
   - Click the target dropdown (top-left)
   - Select **Cyberpunk2077** process
   - If not listed, click "Choose Target..." and browse to:
     ```
     ~/Library/Application Support/Steam/steamapps/common/Cyberpunk 2077/Cyberpunk2077.app
     ```

2. **Configure Recording:**
   - **Duration:** 30 seconds (recommended for initial capture)
   - **Options:**
     - ✅ Enable "GPU Counters"
     - ✅ Enable "Shader Profiling"
     - ✅ Enable "Command Buffer Profiling"

---

## Step 3: Capture Timeline

1. **Start Recording:**
   - Click the **Record** button (red circle)
   - Navigate to a consistent location in-game
   - Let it record for 30 seconds
   - Click **Stop**

2. **Save Trace:**
   - File → Save
   - Name: `cyberpunk_metaltrace_YYYYMMDD_HHMMSS.trace`
   - Location: `docs/traces/`

---

## Step 4: Analyze GPU Timeline

### Key Metrics to Examine

#### 1. GPU Utilization
- **Location:** GPU Timeline → GPU Utilization
- **Look for:**
  - GPU idle time between command buffer submissions
  - GPU busy percentage (target: >90%)
  - Pipeline stalls

#### 2. Command Buffer Submissions
- **Location:** GPU Timeline → Command Buffers
- **Look for:**
  - Number of command buffers per frame
  - Time between submissions
  - Buffer fragmentation patterns

#### 3. Render Passes
- **Location:** GPU Timeline → Render Passes
- **Look for:**
  - Longest render passes
  - RT-specific passes (if identifiable)
  - Pass dependencies

#### 4. Ray Tracing Operations
- **Location:** GPU Timeline → Ray Tracing (if available)
- **Look for:**
  - Acceleration structure builds/refits
  - Ray dispatch operations
  - RT pass timing

---

## Step 5: Export Analysis

### Export Metrics

1. **Select Time Range:**
   - Click and drag on timeline to select 5-10 second window
   - Focus on representative gameplay (not menu/loading)

2. **Export Statistics:**
   - Right-click timeline → Export Statistics
   - Save as CSV: `metaltrace_stats_YYYYMMDD_HHMMSS.csv`

### Key Statistics to Extract

- **GPU Utilization:**
  - Average GPU busy %
  - GPU idle time per frame
  - Pipeline stall count

- **Command Buffers:**
  - Total command buffers in time range
  - Average buffers per frame
  - Time between submissions

- **Render Passes:**
  - Pass execution time
  - Pass dependencies
  - Longest passes

---

## Step 6: Correlate with Frida Profiler

1. **Run Frida Profiler Simultaneously:**
   ```bash
   python scripts/start_rt_profiler.py
   ```

2. **Match Time Ranges:**
   - Note timestamps from both tools
   - Correlate Frida frame times with GPU timeline
   - Match command buffer counts

3. **Cross-Reference:**
   - Frida: CPU-side metrics (FPS, frame times)
   - Instruments: GPU-side metrics (GPU utilization, passes)
   - Identify bottlenecks (CPU vs GPU bound)

---

## Automation Script

For automated capture, use this script:

```bash
#!/bin/bash
# capture_metaltrace.sh

GAME_PID=$(pgrep -f Cyberpunk2077)
if [ -z "$GAME_PID" ]; then
    echo "Game not running!"
    exit 1
fi

# Launch Instruments with Metal System Trace
open -a Instruments --args \
    -t "Metal System Trace" \
    -p "$GAME_PID" \
    -D "docs/traces/cyberpunk_metaltrace_$(date +%Y%m%d_%H%M%S).trace"
```

---

## Analysis Checklist

- [ ] GPU utilization >90% during gameplay
- [ ] Command buffers <2 per frame
- [ ] GPU idle time <5% of frame time
- [ ] No pipeline stalls detected
- [ ] RT passes identified and timed
- [ ] Longest render passes documented
- [ ] Correlated with Frida profiler data

---

## Troubleshooting

### Instruments Can't Attach
- **Solution:** Grant Terminal/Xcode Full Disk Access in System Preferences
- **Solution:** Run Instruments with sudo (not recommended)

### No GPU Timeline Visible
- **Solution:** Ensure Metal System Trace template is selected
- **Solution:** Check that game is using Metal (not OpenGL/Vulkan)

### Trace File Too Large
- **Solution:** Reduce capture duration to 10-15 seconds
- **Solution:** Disable shader profiling if not needed

---

## Expected Results

Based on current baseline (44 FPS, 3.4 buffers/frame):

- **GPU Utilization:** Likely <80% (due to fragmentation)
- **Command Buffers:** ~3.4 per frame (confirmed)
- **GPU Idle Time:** Significant gaps between submissions
- **RT Passes:** Should be identifiable in timeline

---

## Next Steps

After capturing trace:

1. **Analyze GPU Timeline** for bottlenecks
2. **Export Statistics** for quantitative analysis
3. **Correlate with Frida Data** for complete picture
4. **Document Findings** in Phase 2 analysis report

---

**Related Documents:**
- `RT_OPTIMIZATION_PHASED_PLAN.md` - Full optimization plan
- `PROFILER_RUN_ANALYSIS.md` - Baseline performance analysis
- `RT_REVERSE_ENGINEERING_REPORT.md` - RT architecture analysis
