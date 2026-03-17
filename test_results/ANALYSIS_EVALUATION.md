# Experiment Analysis Evaluation Report
Date: March 16, 2026

## Overview
The analysis correctly processes three test datasets measuring latency and synchronization performance of two different architectures using both software and hardware measurement methods.

## Architectural Context

### Architecture 1: Centralized UDP Broadcast Topology
**Design Philosophy**: Real-time centralized control
- Central Python server computes application state and broadcasts UDP commands ("relay:on"/"relay:off")
- All ESP32 edge nodes listen on port 4210 and execute digitalWrite() immediately upon packet arrival
- **Synchronization mechanism**: Physical network propagation timing
- **Skew source**: Wi-Fi carrier sense, routing jitter, and contention (Δt = |t_n - t_1|)
- **Critical assumption**: Δt must stay below hardware threshold or system becomes unstable

### Architecture 2: Distributed Parameterized Execution with ESP-NOW
**Design Philosophy**: Autonomous distributed execution with periodic synchronization
- **Layer 1 - Config Polling** (every 1000ms): Nodes fetch execution sequences via HTTP/TCP
- **Layer 2 - Independent Execution**: Each node runs deterministic local execution engine
  - Grandmaster: `phase = (current_timeUs) % sequenceTimeUs`
  - Followers: `phase = (current_timeUs + offsetUs) % sequenceTimeUs`
- **Layer 3 - Clock Sync** (every 2000ms): ESP-NOW broadcasts master clock for drift correction
  - Followers adjust: `clockOffsetUs = (master_time + 1054µs) - local_time`
  - Target: Keep drift δ(T_sync) < Δτ_crit between sync pulses

**Key Difference**: Arch 1 = direct command triggering, Arch 2 = coordinated autonomous execution

## Test Summary

### Test 0: Software Ping-Pong (Arch 1 - UDP Baseline)
- **Purpose**: Software-based round-trip latency measurement
- **Sample Size**: 399 ping-pong exchanges (2 devices)
- **Key Findings**:
  - Device A: Mean 58.25 ms, Median 41.92 ms (Std Dev: 56.58 ms)
  - Device B: Mean 57.13 ms, Median 41.58 ms (Std Dev: 54.96 ms)
  - Range: 4-258 ms (very high variability)
- **Assessment**: High network jitter, software timestamps show significant variability

### Test 1: Hardware Observer - Architecture 1 (UDP)
- **Purpose**: Ground truth hardware latency and synchronization measurement
- **Sample Size**: 200 hardware-timed events
- **Key Findings**:
  - Hardware Latency (Device A & B): Mean 49.42 ms, Median 25.16 ms
  - **Synchronization Drift**: Mean 7.88 µs, Median 5.00 µs (Std Dev: 10.34 µs)
  - Max drift: 99 µs
- **Assessment**: Excellent synchronization! Sub-10 µs average drift demonstrates tight coordination

### Test 2: Hardware Observer - Architecture 2 (ESP-NOW)
- **Purpose**: Autonomous synchronization drift in ESP-NOW protocol
- **Sample Size**: 200 autonomous pulse pairs
- **Key Findings**:
  - **Synchronization Drift**: Mean 108.47 µs, Median 31.00 µs (Std Dev: 495.96 µs)
  - Max drift: 6,449 µs (6.45 ms)
- **Assessment**: ⚠️ Much worse than Arch 1 - 13.8x higher mean drift, 48x more variability

## Analysis Quality Assessment

### ✅ Strengths
1. **Appropriate statistical measures**: Mean, median, std dev, min, max provide comprehensive view
2. **Correct data loading**: Each test's unique CSV structure is handled properly
3. **Meaningful comparisons**: Direct drift comparison between architectures is valid
4. **Dual reuse of Test 1 data**: Correctly extracts both latency and drift from same dataset
5. **Visualization strategy**: 4 publication-quality figures with appropriate plot types
6. **Publication-ready outputs**: LaTeX tables formatted correctly

### ⚠️ Observations & Potential Issues

1. **Skewed distributions detected**:
   - All tests show Mean > Median, indicating right-skewed distributions
   - High standard deviations relative to medians (especially Test 0 and Test 2)
   - **Recommendation**: Consider reporting IQR (interquartile range) alongside std dev

2. **Test 2 has extreme outliers**:
   - Max drift 6449 µs vs median 31 µs (208x difference!)
   - Std dev (495.96 µs) > mean (108.47 µs) indicates severe outliers
   - **Current mitigation**: Analysis uses absolute values and removes outliers in boxplots (showfliers=False)
   - **Concern**: Are these outliers measurement errors or real system behavior?

3. **Sample size imbalance**:
   - Test 0: 399 samples vs Tests 1&2: 200 samples each
   - Not critical but worth noting for statistical power comparisons

4. **Missing percentile analysis**:
   - For wireless systems, 95th/99th percentiles are often more important than max
   - **Recommendation**: Add P95, P99 to tables

5. **Test 0 vs Test 1 discrepancy**:
   - Software RTT (58 ms) > Hardware latency (49 ms)
   - Expected (software overhead), but worth explicitly calling out
   - Hardware measures one-way, software measures round-trip divided by 2

6. **Figure 4 interpretation unclear**:
   - Scatter plot shows latency vs sync skew correlation
   - Is there actually a correlation? Add correlation coefficient (Pearson's r)

### 🔍 Specific Code Observations

1. **Line 67-68**: Loads Test 1 file for sync data
   ```python
   a1_samples, a1_drifts = load_sync_data(f_arch1)
   ```

2. **Line 124**: Loads same Test 1 file for latency data
   ```python
   h_samples, h_lat_a, h_lat_b, h_drifts = load_hardware_latency_data(f_arch1)
   ```
   - **Status**: ✅ Correct - extracts different columns for different analyses

3. **Absolute value handling**: Both comparisons use `np.abs()` on drifts
   - **Status**: ✅ Appropriate for measuring synchronization error magnitude

## Key Scientific Conclusions

### Architecture 1 (UDP Broadcast) Performance
- ✅ **Excellent synchronization**: ~8 µs mean drift
- ⚠️ **High latency variability**: 25-210 ms range (hardware), 4-258 ms (software)
- **Why it works**: All nodes receive the SAME broadcast packet nearly simultaneously
  - Skew is purely from Wi-Fi contention and physical propagation differences
  - No clock drift accumulation between commands
  - Direct stimulus-response model ensures tight coordination
- **Use case**: Real-time control requiring microsecond synchronization, tolerant of latency variance

### Architecture 2 (ESP-NOW) Performance
- ⚠️ **Poor synchronization**: ~108 µs mean drift (13.8x worse than Arch 1)
- ⚠️ **Very unstable**: 496 µs std dev indicates unpredictable timing
- ⚠️ **Extreme outliers**: 6.5 ms worst-case drift
- **Why it struggles**: Three compounding factors
  1. **Clock drift accumulation**: 2000ms between ESP-NOW sync pulses allows significant drift (δ(T))
  2. **ESP-NOW latency variance**: ~1054µs median compensation may not match actual ToF for each sync
  3. **Phase calculation errors**: Small clock errors amplified through `(current_timeUs + offsetUs) % sequenceTimeUs`
- **Hypothesis for outliers**: Measurements captured just before ESP-NOW sync correction (maximum drift state)
- **Use case**: Autonomous operation with looser timing requirements (>100µs tolerance)

### Architectural Trade-offs Revealed

| Aspect | Architecture 1 (UDP Broadcast) | Architecture 2 (ESP-NOW + Local Exec) |
|--------|--------------------------------|---------------------------------------|
| **Synchronization** | ✅ Excellent (8µs) | ⚠️ Poor (108µs) |
| **Network Load** | ⚠️ High (continuous broadcasts) | ✅ Low (2s ESP-NOW + 1s HTTP) |
| **Scalability** | ⚠️ Limited (UDP broadcast storms) | ✅ Better (P2P + polling) |
| **Autonomy** | ❌ None (server-dependent) | ✅ Full (survives server downtime) |
| **Latency** | ⚠️ Variable (4-258ms) | ✅ Deterministic (local execution) |

### Overall Test Validity
- ✅ Hardware observer methodology provides ground truth
- ✅ Comparison between architectures is fair and meaningful
- ✅ Sample sizes (200+) are adequate for statistical significance
- ✅ Results align with architectural design predictions

## Recommendations for Improvement

### Analysis Enhancements
1. **Add percentile statistics** (P50, P95, P99) to all tables
2. **Add correlation analysis** to Figure 4 with Pearson's r value
3. **Investigate Test 2 outliers**: Are drifts > 500 µs real or measurement errors?
4. **Consider log-scale plots** for Test 0 and Test 2 (high variance)
5. **Add statistical significance testing**: T-test or Mann-Whitney U for Arch1 vs Arch2
6. **Document outlier removal policy**: Currently hidden in boxplots but not explicitly stated
7. **Add sample size (N) to all plots and tables** for transparency

### Architecture 2 Design Improvements
Based on test results, Architecture 2 could achieve better synchronization by:

1. **Increase ESP-NOW sync frequency**: 2000ms interval → 500ms or 1000ms
   - Trade-off: Slightly higher ESP-NOW traffic vs. 4-10x better drift control
   
2. **Dynamic latency compensation**: Replace fixed 1054µs with measured round-trip
   - Current: Assumes median latency for all sync events
   - Improvement: Measure actual ToF per sync and adjust offset dynamically

3. **Predictive drift compensation**: Use linear regression on recent drift measurements
   - Extrapolate between sync pulses instead of step corrections
   - Reduces saw-tooth drift pattern

4. **Add drift rate limiting**: Reject outlier sync corrections that imply unrealistic clock drift
   - Protects against spurious ESP-NOW packets or measurement glitches

5. **Hybrid approach**: Use Arch 1 for synchronization-critical phases, Arch 2 for autonomous execution
   - UDP broadcast for tight coordination windows
   - ESP-NOW autonomous mode for extended operation

## Final Verdict

**Analysis Quality: 8.5/10**
- Methodology is sound and appropriate
- Statistics are correctly calculated
- Visualizations are publication-ready
- Main weakness: Could benefit from more robust statistics (percentiles, significance tests) given the skewed distributions

**Scientific Findings: Clear and Actionable**
- Architecture 1 demonstrates superior synchronization performance
- Architecture 2 requires significant improvement for timing-critical applications
- Hardware observer approach successfully validates synchronization claims
