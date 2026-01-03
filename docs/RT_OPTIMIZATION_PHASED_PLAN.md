# Ray Tracing Optimization Phased Plan
## Cyberpunk 2077 macOS Apple Silicon Performance Optimization

**Created:** 2026-01-01  
**Status:** Ready to Execute  
**Baseline:** 44 FPS average, 22.5ms frame time, 3.4 command buffers/frame

---

## Executive Summary

This plan outlines a systematic approach to optimize ray tracing and path tracing performance on Apple Silicon, targeting a **60 FPS goal** (currently at 44 FPS). The plan is divided into **5 phases** over **8-12 weeks**, with each phase building on previous findings.

**Current State:**
- ✅ Safe profiler infrastructure operational
- ✅ RT architecture mapped (1,006 symbols analyzed)
- ✅ Baseline performance established (44 FPS, 22.5ms)
- ⚠️ Command buffer fragmentation identified (3.4 buffers/frame)

**Target State:**
- 60 FPS average (16.67ms frame time)
- <2 command buffers per frame
- RT overhead <30% of frame time
- Stable frame pacing (P99 < 20ms)

---

## Phase 1: Deep Profiling & Baseline Establishment
**Duration:** 2 weeks  
**Goal:** Establish comprehensive performance baseline and identify all bottlenecks

### Week 1: Extended Profiling

#### 1.1 Long-Run Baseline Collection
**Objective:** Collect 30+ minutes of gameplay data across different scenarios

**Tasks:**
- [ ] Run safe-continuous profiler for 30 minutes in different areas:
  - Dense urban (Corpo Plaza, City Center)
  - Open world (Badlands)
  - Interior spaces (apartments, shops)
  - Combat scenarios
- [ ] Collect frame timing data (FPS, frame times, P99/P95)
- [ ] Measure command buffer patterns across scenarios
- [ ] Document performance variance by location

**Deliverables:**
- Baseline performance report with location-specific metrics
- Frame time distribution charts
- Command buffer pattern analysis

**Success Criteria:**
- 30+ minutes of clean profiling data
- Performance variance documented
- No profiler-induced instability

#### 1.2 RT Feature Toggle Benchmarking
**Objective:** Measure impact of each RT feature independently

**Tasks:**
- [ ] Profile with RT Shadows OFF (baseline)
- [ ] Profile with RT Shadows ON
- [ ] Profile with RT Reflections OFF/ON
- [ ] Profile with RT Global Illumination OFF/ON
- [ ] Profile with Path Tracing OFF/ON (if available)
- [ ] Each test: 5 minutes of gameplay, same location

**Deliverables:**
- RT feature impact matrix (FPS delta per feature)
- Cost ranking: Highest → Lowest impact RT features
- Recommendations for which features to optimize first

**Success Criteria:**
- Clear FPS impact per RT feature
- Identified top 3 most expensive RT features

#### 1.3 Metal System Trace Capture
**Objective:** Use Apple's native tools to identify GPU bottlenecks

**Tasks:**
- [ ] Capture Metal System Trace (Xcode → Instruments)
  - 30 seconds of gameplay
  - Same location as profiler baseline
- [ ] Analyze GPU timeline:
  - Longest render passes
  - GPU idle time between submissions
  - Command buffer submission patterns
- [ ] Identify GPU-CPU synchronization stalls
- [ ] Measure RT-specific GPU time

**Deliverables:**
- Metal System Trace analysis report
- GPU bottleneck identification
- Command buffer submission timeline

**Success Criteria:**
- GPU bottlenecks identified
- RT GPU time measured
- Synchronization stalls documented

### Week 2: Burst RT Profiler Development

#### 2.1 Build Burst RT Profiler
**Objective:** Create opt-in RT hooks for short capture windows

**Tasks:**
- [ ] Extend `scripts/frida/metal_profiler.js` with RT-specific hooks:
  - Acceleration structure creation/build/refit
  - Ray dispatch calls (if detectable)
  - RT render node execution timing
- [ ] Add `rpc.exports.enableRTProfiling()` / `disableRTProfiling()`
- [ ] Implement 5-15 second capture windows
- [ ] Add safety checks (auto-disable after timeout)

**Deliverables:**
- Burst RT profiler script
- Documentation for usage
- Safety validation (no game freezes)

**Success Criteria:**
- RT profiler can capture 10-second windows without instability
- RT metrics collected (AS operations, ray dispatches)

#### 2.2 RT-Specific Metrics Collection
**Objective:** Measure RT infrastructure costs

**Tasks:**
- [ ] Run burst RT profiler in different scenarios:
  - Static scene (minimal RT updates)
  - Dynamic scene (many moving objects)
  - RT-heavy scene (many reflective surfaces)
- [ ] Measure:
  - Acceleration structure build/refit frequency
  - Acceleration structure build/refit time
  - RT render node execution time per feature
  - RT buffer allocation patterns

**Deliverables:**
- RT infrastructure cost report
- AS update frequency analysis
- RT feature timing breakdown

**Success Criteria:**
- RT costs quantified per feature
- AS update patterns identified
- Optimization targets prioritized

---

## Phase 2: Command Buffer Optimization
**Duration:** 2 weeks  
**Goal:** Reduce command buffer fragmentation from 3.4 to <2 buffers/frame

### Week 3: Command Buffer Pattern Analysis

#### 3.1 Deep Command Buffer Profiling
**Objective:** Identify which render passes create separate buffers

**Tasks:**
- [ ] Extend profiler to track command buffer creation:
  - Hook `makeCommandBuffer` calls
  - Track buffer creation context (which render pass)
  - Measure time between buffer submissions
- [ ] Profile across scenarios:
  - Simple scene (few objects)
  - Complex scene (many objects)
  - RT-heavy scene
- [ ] Identify patterns:
  - Which passes always create new buffers?
  - Which passes could be batched?
  - What causes buffer fragmentation?

**Deliverables:**
- Command buffer creation pattern report
- Buffer fragmentation source identification
- Batching opportunity analysis

**Success Criteria:**
- Clear understanding of buffer creation patterns
- Top 5 fragmentation sources identified

#### 3.2 GPU Timeline Analysis
**Objective:** Measure GPU idle time between buffer submissions

**Tasks:**
- [ ] Use Metal System Trace to measure:
  - Time between command buffer submissions
  - GPU idle time per frame
  - Pipeline stall frequency
- [ ] Correlate with Frida profiler data:
  - Buffer count vs GPU idle time
  - Buffer count vs frame time
- [ ] Calculate potential gain from batching

**Deliverables:**
- GPU idle time analysis
- Buffer fragmentation impact quantification
- Expected FPS gain estimate

**Success Criteria:**
- GPU idle time measured
- Buffer batching ROI calculated

### Week 4: Optimization Implementation & Testing

#### 4.1 Buffer Batching Recommendations
**Objective:** Create actionable recommendations for game developers

**Tasks:**
- [ ] Analyze command buffer patterns:
  - Identify render passes that can be batched
  - Identify passes that must remain separate
  - Create batching strategy
- [ ] Document optimization opportunities:
  - Low-hanging fruit (easy wins)
  - Medium effort (moderate gains)
  - High effort (significant gains)
- [ ] Estimate implementation effort vs gain

**Deliverables:**
- Command buffer optimization guide
- Batching strategy document
- Implementation priority matrix

**Success Criteria:**
- Clear optimization roadmap
- Prioritized action items

#### 4.2 Validation Testing
**Objective:** Verify optimizations (if implemented) or measure current state

**Tasks:**
- [ ] Re-profile after any optimizations
- [ ] Measure command buffer count reduction
- [ ] Measure FPS improvement
- [ ] Validate stability (no regressions)

**Deliverables:**
- Optimization validation report
- Before/after comparison
- Performance regression tests

**Success Criteria:**
- Command buffers reduced to <2 per frame
- FPS improvement measured
- No stability regressions

---

## Phase 3: RT Feature Optimization
**Duration:** 2-3 weeks  
**Goal:** Optimize highest-cost RT features identified in Phase 1

### Week 5: Acceleration Structure Optimization

#### 5.1 AS Update Frequency Analysis
**Objective:** Identify unnecessary acceleration structure updates

**Tasks:**
- [ ] Use burst RT profiler to measure:
  - Static AS update frequency (should be rare)
  - Dynamic AS update frequency (per object)
  - AS build vs refit ratio
- [ ] Identify optimization opportunities:
  - Static geometry being rebuilt unnecessarily
  - Dynamic objects updating too frequently
  - AS rebuilds that could be refits

**Deliverables:**
- AS update pattern analysis
- Optimization recommendations
- Expected performance gain estimates

**Success Criteria:**
- AS update patterns documented
- Unnecessary updates identified

#### 5.2 AS Memory Optimization
**Objective:** Optimize acceleration structure memory usage

**Tasks:**
- [ ] Profile AS memory allocation:
  - AS size per object type
  - AS memory growth over time
  - AS memory fragmentation
- [ ] Analyze buffer storage modes:
  - Verify AS buffers use `StorageModePrivate`
  - Check for unnecessary CPU-GPU copies
  - Identify memory pressure points

**Deliverables:**
- AS memory usage report
- Storage mode analysis
- Memory optimization recommendations

**Success Criteria:**
- AS memory usage understood
- Optimization opportunities identified

### Week 6: RT Feature-Specific Optimization

#### 6.1 Top RT Feature Deep Dive
**Objective:** Optimize the highest-cost RT feature from Phase 1

**Tasks:**
- [ ] Select top RT feature (e.g., RT Shadows, RT Reflections)
- [ ] Deep profile that feature:
  - Ray count per frame
  - Ray dispatch frequency
  - Denoiser cost
  - Buffer usage
- [ ] Identify optimization opportunities:
  - Reduce ray count (quality vs performance)
  - Optimize denoiser settings
  - Reduce buffer allocations
  - Improve ray dispatch batching

**Deliverables:**
- Feature-specific optimization report
- Implementation recommendations
- Quality vs performance trade-offs

**Success Criteria:**
- Top RT feature optimized
- Clear quality/performance trade-offs documented

#### 6.2 RT Render Node Optimization
**Objective:** Optimize RT render node execution order and dependencies

**Tasks:**
- [ ] Profile render node execution:
  - Node execution order
  - Node dependencies
  - Node execution time
- [ ] Identify optimization opportunities:
  - Reorder nodes to reduce dependencies
  - Parallelize independent nodes
  - Reduce node overhead

**Deliverables:**
- Render node optimization report
- Node reordering recommendations
- Dependency analysis

**Success Criteria:**
- Render node execution optimized
- Dependencies minimized

### Week 7: OMM & Advanced Features

#### 7.1 OMM (Opacity Micro-Maps) Verification
**Objective:** Verify and optimize OMM usage for alpha-tested geometry

**Tasks:**
- [ ] Verify OMM is enabled:
  - Check `GPUM_Buffer_RaytracingOMM` usage
  - Measure OMM buffer allocations
  - Profile OMM impact on RT performance
- [ ] Optimize OMM usage:
  - Ensure all alpha-tested geometry uses OMM
  - Verify OMM quality settings
  - Measure OMM performance gain

**Deliverables:**
- OMM usage report
- OMM optimization recommendations
- Performance impact measurement

**Success Criteria:**
- OMM usage verified
- OMM optimized for performance

#### 7.2 AAPL Optimization Flags Verification
**Objective:** Verify Apple-specific RT optimizations are enabled

**Tasks:**
- [ ] Use `aapl_optimization_probe.js` to verify:
  - `EnableReferenceAAPLOptim` status
  - `UseAAPLOptimPass` status
  - AAPL buffer operations
- [ ] Measure optimization impact:
  - Profile with optimizations ON/OFF
  - Measure buffer allocation differences
  - Measure RT performance differences

**Deliverables:**
- AAPL optimization status report
- Optimization impact measurement
- Recommendations for enabling optimizations

**Success Criteria:**
- AAPL optimizations verified
- Impact measured
- Recommendations provided

---

## Phase 4: Integration & Validation
**Duration:** 1-2 weeks  
**Goal:** Integrate all optimizations and validate performance gains

### Week 8: Integration Testing

#### 8.1 Combined Optimization Testing
**Objective:** Test all optimizations together

**Tasks:**
- [ ] Apply all Phase 2 & 3 optimizations
- [ ] Run comprehensive profiling:
  - 30 minutes across different scenarios
  - Measure FPS, frame times, command buffers
  - Measure RT costs
- [ ] Compare to Phase 1 baseline:
  - FPS improvement
  - Frame time reduction
  - Command buffer reduction
  - RT cost reduction

**Deliverables:**
- Combined optimization report
- Before/after comparison
- Performance gain summary

**Success Criteria:**
- All optimizations integrated
- Performance gains measured
- No regressions

#### 8.2 Stability & Regression Testing
**Objective:** Ensure optimizations don't cause instability

**Tasks:**
- [ ] Run stress tests:
  - 1 hour continuous gameplay
  - Rapid scene transitions
  - RT feature toggling
- [ ] Monitor for:
  - Crashes
  - Freezes
  - Memory leaks
  - Performance degradation over time

**Deliverables:**
- Stability test report
- Regression test results
- Known issues list

**Success Criteria:**
- No crashes or freezes
- Stable performance over time
- No memory leaks

### Week 9: Quality Validation

#### 9.1 Visual Quality Assessment
**Objective:** Ensure optimizations don't degrade visual quality

**Tasks:**
- [ ] Visual comparison:
  - Screenshots before/after
  - Video capture comparison
  - RT feature quality assessment
- [ ] Quality metrics:
  - Denoiser quality
  - RT accuracy
  - Visual artifacts

**Deliverables:**
- Visual quality report
- Before/after comparison gallery
- Quality recommendations

**Success Criteria:**
- Visual quality maintained or improved
- No unacceptable artifacts

#### 9.2 Performance Target Validation
**Objective:** Verify 60 FPS target is met

**Tasks:**
- [ ] Run final performance tests:
  - 30 minutes across all scenarios
  - Measure average FPS
  - Measure P99/P95 frame times
  - Measure frame pacing quality
- [ ] Compare to targets:
  - 60 FPS average (16.67ms)
  - P99 < 20ms
  - Stable frame pacing

**Deliverables:**
- Final performance report
- Target achievement summary
- Remaining optimization opportunities

**Success Criteria:**
- 60 FPS average achieved (or documented why not)
- P99 frame time < 20ms
- Stable frame pacing

---

## Phase 5: Documentation & Maintenance
**Duration:** 1 week  
**Goal:** Document findings and create maintenance plan

### Week 10: Documentation

#### 10.1 Comprehensive Documentation
**Objective:** Document all findings, optimizations, and recommendations

**Tasks:**
- [ ] Create optimization guide:
  - RT architecture overview
  - Optimization techniques
  - Best practices
- [ ] Document profiler usage:
  - How to run profilers
  - How to interpret results
  - Troubleshooting guide
- [ ] Create developer guide:
  - How to optimize RT features
  - Command buffer best practices
  - Apple Silicon-specific optimizations

**Deliverables:**
- RT Optimization Guide
- Profiler User Guide
- Developer Best Practices Guide

**Success Criteria:**
- Complete documentation
- Clear, actionable guides

#### 10.2 Maintenance Plan
**Objective:** Create plan for ongoing performance monitoring

**Tasks:**
- [ ] Define monitoring strategy:
  - Regular profiling schedule
  - Performance regression detection
  - Optimization opportunity identification
- [ ] Create automation:
  - Automated profiling scripts
  - Performance regression tests
  - Alert system for performance degradation

**Deliverables:**
- Maintenance plan document
- Automated monitoring scripts
- Performance regression test suite

**Success Criteria:**
- Ongoing monitoring plan in place
- Automation scripts functional

---

## Success Metrics

### Phase 1 Success Criteria
- ✅ 30+ minutes of baseline data collected
- ✅ RT feature impact matrix complete
- ✅ GPU bottlenecks identified
- ✅ Burst RT profiler operational

### Phase 2 Success Criteria
- ✅ Command buffers reduced to <2 per frame
- ✅ GPU idle time reduced by 50%
- ✅ 5-15% FPS improvement achieved

### Phase 3 Success Criteria
- ✅ Top RT feature optimized (10-20% cost reduction)
- ✅ AS update frequency optimized
- ✅ OMM verified and optimized
- ✅ AAPL optimizations verified

### Phase 4 Success Criteria
- ✅ Combined optimizations integrated
- ✅ 60 FPS average achieved (or documented gap)
- ✅ P99 frame time < 20ms
- ✅ No stability regressions

### Phase 5 Success Criteria
- ✅ Complete documentation
- ✅ Maintenance plan in place
- ✅ Automation scripts functional

---

## Risk Mitigation

### Technical Risks

**Risk:** Profiler causes game instability
- **Mitigation:** Safe-continuous mode, burst profiler with timeouts
- **Contingency:** Fall back to Instruments-only profiling

**Risk:** Optimizations degrade visual quality
- **Mitigation:** Visual quality validation in Phase 4
- **Contingency:** Quality vs performance trade-off analysis

**Risk:** Optimizations not applicable (game-specific limitations)
- **Mitigation:** Document findings, provide recommendations
- **Contingency:** Focus on measurable optimizations only

### Timeline Risks

**Risk:** Phase delays due to complexity
- **Mitigation:** Flexible timeline, prioritize high-impact work
- **Contingency:** Extend timeline, reduce scope if needed

**Risk:** Game updates break profiler
- **Mitigation:** Version pinning, update testing
- **Contingency:** Rapid profiler updates

---

## Resource Requirements

### Tools & Infrastructure
- ✅ Frida Python bindings (installed)
- ✅ Safe profiler infrastructure (operational)
- ✅ Burst RT profiler (to be built)
- ⏳ Xcode/Instruments (for Metal System Trace)
- ⏳ Game access (for testing)

### Skills Required
- Reverse engineering (RT architecture analysis)
- Performance profiling (Frida, Instruments)
- Metal API knowledge (RT optimization)
- Data analysis (performance metrics)

### Time Commitment
- **Phase 1:** 40-60 hours
- **Phase 2:** 30-40 hours
- **Phase 3:** 40-60 hours
- **Phase 4:** 20-30 hours
- **Phase 5:** 10-20 hours
- **Total:** 140-210 hours over 8-12 weeks

---

## Next Immediate Actions

1. **Start Phase 1, Week 1:**
   - Run 30-minute baseline profiling session
   - Collect data across different scenarios
   - Document performance variance

2. **Prepare Phase 1, Week 2:**
   - Begin burst RT profiler development
   - Set up Metal System Trace capture workflow

3. **Set Up Monitoring:**
   - Create automated profiling scripts
   - Set up performance tracking dashboard

---

## Conclusion

This phased plan provides a systematic approach to optimizing ray tracing performance on Apple Silicon. Each phase builds on previous findings, with clear success criteria and deliverables. The plan is flexible and can be adjusted based on findings, but provides a solid roadmap to achieving 60 FPS performance.

**Key Success Factors:**
- Comprehensive baseline establishment
- Systematic bottleneck identification
- Prioritized optimization approach
- Continuous validation and testing
- Complete documentation

**Expected Outcomes:**
- 60 FPS average performance (or documented path to achieve it)
- Reduced command buffer fragmentation
- Optimized RT feature costs
- Comprehensive optimization guide
- Ongoing performance monitoring

---

**Plan Status:** Ready to Execute  
**Start Date:** TBD  
**Target Completion:** 8-12 weeks from start
