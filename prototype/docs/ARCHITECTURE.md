# Architecture 2 - Distributed Autonomous Execution

## Design Philosophy
Enable **autonomous, deterministic execution** on edge nodes with **periodic clock synchronization** to maintain coordination without continuous server communication.

## Core Principles
1. **Autonomy First**: Nodes must operate independently even if server is unavailable
2. **Deterministic Execution**: Same configuration produces identical behavior
3. **Periodic Sync**: Balance sync accuracy vs. network overhead
4. **Graceful Degradation**: System continues with increasing drift if sync fails

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Python Server (FastAPI)                  │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Configuration  │  │   Metrics    │  │   Monitoring    │ │
│  │   Management   │  │  Collection  │  │   Dashboard     │ │
│  └────────────────┘  └──────────────┘  └─────────────────┘ │
└──────────────┬─────────────────────────────────────────────┘
               │ HTTP/TCP (Config polling every 1000ms)
               │
    ┏━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃           Wi-Fi Network Layer                     ┃
    ┗━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┛
              │                │
    ┌─────────▼────────┐      │      ┌──────────────────┐
    │  Grandmaster     │      │      │   Follower 1     │
    │   ESP32-C6       │      │      │    ESP32-C6      │
    │                  │      │      │                  │
    │ ┌──────────────┐ │      │      │ ┌──────────────┐ │
    │ │ Execution    │ │      │      │ │ Execution    │ │
    │ │   Engine     │ │      │      │ │   Engine     │ │
    │ └──────────────┘ │      │      │ └──────────────┘ │
    │ ┌──────────────┐ │      │      │ ┌──────────────┐ │
    │ │ Clock Source │ │      │      │ │ Clock Sync   │ │
    │ │  (Authority) │ │      │      │ │   Client     │ │
    │ └──────────────┘ │      │      │ └──────────────┘ │
    └─────────┬────────┘      │      └────────┬─────────┘
              │                │               │
              │   ESP-NOW (Clock Sync: 500ms)  │
              └────────────────┼───────────────┘
                               │
                      ┌────────▼────────┐
                      │   Follower 2    │
                      │    ESP32-C6     │
                      │                 │
                      │ ┌─────────────┐ │
                      │ │ Execution   │ │
                      │ │   Engine    │ │
                      │ └─────────────┘ │
                      │ ┌─────────────┐ │
                      │ │ Clock Sync  │ │
                      │ │   Client    │ │
                      │ └─────────────┘ │
                      └─────────────────┘
```

## Three-Layer Design

### Layer 1: Configuration Management (HTTP/TCP)
**Interval**: 1000ms (configurable)  
**Protocol**: HTTP GET requests to server  
**Purpose**: Fetch execution sequences and operating parameters

**Configuration Schema**:
```json
{
  "sequence_id": "seq_001",
  "sequence_time_us": 10000,
  "states": [
    {"duration_us": 5000, "pin_state": 1},
    {"duration_us": 5000, "pin_state": 0}
  ],
  "sync_interval_ms": 500
}
```

**Characteristics**:
- Tolerant to latency (100-500ms acceptable)
- Updates applied at next cycle boundary
- Fallback: Continue with last valid configuration

### Layer 2: Independent Execution Engines
**Runtime**: Continuous, microsecond precision  
**Engine**: Local state machine  
**Purpose**: Execute sequences deterministically

**Grandmaster Algorithm**:
```cpp
unsigned long getCurrentPhase() {
    return micros() % sequenceTimeUs;
}

int calculateState(unsigned long phase) {
    unsigned long elapsed = 0;
    for (State& state : sequence) {
        if (phase < elapsed + state.duration_us) {
            return state.pin_state;
        }
        elapsed += state.duration_us;
    }
    return 0; // Default
}
```

**Follower Algorithm**:
```cpp
unsigned long getCurrentPhase() {
    return (micros() + clockOffsetUs) % sequenceTimeUs;
}
// calculateState() same as grandmaster
```

**Key Property**: Given identical `clockOffsetUs` and `sequenceTimeUs`, followers produce identical phase calculations as grandmaster.

### Layer 3: Clock Synchronization (ESP-NOW)
**Interval**: 500ms (improved from 2000ms in POC)  
**Protocol**: ESP-NOW broadcast from grandmaster  
**Purpose**: Correct clock drift between nodes

**Sync Packet Structure**:
```cpp
struct SyncPacket {
    uint32_t magic;           // 0xDEADBEEF
    uint64_t master_time_us;  // Grandmaster micros()
    uint16_t sequence_id;     // Current sequence version
    uint32_t checksum;        // CRC32 validation
};
```

**Follower Sync Algorithm** (Improved):
```cpp
void onSyncReceived(SyncPacket packet) {
    // 1. Validate packet
    if (!validateChecksum(packet)) return;
    
    // 2. Measure actual latency (dynamic)
    uint64_t recv_time = micros();
    uint64_t estimated_latency = measureLatency(); // Rolling avg
    
    // 3. Reject outliers
    if (abs(estimated_latency - MEDIAN_LATENCY) > LATENCY_THRESHOLD) {
        outlier_count++;
        return;
    }
    
    // 4. Calculate offset with compensation
    uint64_t master_actual = packet.master_time_us + estimated_latency;
    int64_t new_offset = master_actual - recv_time;
    
    // 5. Smooth adjustment (reduce jitter)
    clockOffsetUs = (clockOffsetUs * 0.7) + (new_offset * 0.3);
    
    last_sync_time = recv_time;
}
```

## Improvements Over POC

### 1. Increased Sync Frequency
**POC**: 2000ms interval  
**Prototype**: 500ms interval

**Impact**:
- Maximum drift accumulation reduced 4x
- Clock drift between syncs: T_drift = drift_rate × sync_interval
- Example: 50ppm drift × 500ms = 25µs max drift (vs. 100µs @ 2000ms)

### 2. Dynamic Latency Compensation
**POC**: Fixed 1054µs compensation (median from measurements)  
**Prototype**: Real-time latency measurement with rolling average

**Method**:
```cpp
// Periodically measure ESP-NOW round-trip
uint64_t measureLatency() {
    // Send timestamp, receive ACK with original timestamp
    // Measure RTT, divide by 2 for one-way latency
    // Maintain rolling average of last 10 measurements
}
```

**Impact**: Compensates for Wi-Fi congestion and distance variations

### 3. Outlier Rejection
**POC**: Accepted all sync packets  
**Prototype**: Reject sync packets with anomalous latency

**Criteria**:
- Latency > 2× median: Likely interference or collision
- Consecutive outliers > 5: Switch to extrapolation mode
- Resume sync when valid packets return

**Impact**: Prevents spurious corrections from degrading sync

### 4. Predictive Drift Compensation
**POC**: Step correction every 2000ms (saw-tooth pattern)  
**Prototype**: Linear interpolation between sync points

**Method**:
```cpp
// Track drift rate from last N syncs
int64_t estimateDrift() {
    int64_t elapsed = micros() - last_sync_time;
    return drift_rate_us_per_sec * (elapsed / 1000000.0);
}

unsigned long getCurrentPhase() {
    int64_t drift = estimateDrift();
    return (micros() + clockOffsetUs + drift) % sequenceTimeUs;
}
```

**Impact**: Smoother synchronization between updates

## Synchronization Error Budget

Target: **<50µs mean drift**

| Error Source | POC | Prototype Target | Mitigation |
|--------------|-----|------------------|------------|
| Clock drift accumulation | 100µs | 25µs | 4× faster sync (500ms) |
| ESP-NOW latency jitter | ±30µs | ±10µs | Dynamic compensation |
| Spurious corrections | 50µs | 5µs | Outlier rejection |
| Phase calculation error | 10µs | 10µs | Same (acceptable) |
| **Total (RSS)** | **~115µs** | **~30µs** | **3.8× improvement** |

Additional headroom from predictive drift compensation: ~10-20µs

**Expected Result**: 30-50µs mean drift

## Network Load Analysis

### Per-Device Traffic
- **HTTP Config Poll**: ~500 bytes × 1 Hz = 500 B/s = 4 Kbps
- **ESP-NOW Sync**: ~20 bytes × 2 Hz = 40 B/s = 320 bps
- **Total**: ~4.3 Kbps per device

### 10-Device System
- **Wi-Fi (HTTP)**: 10 × 4 Kbps = 40 Kbps
- **ESP-NOW**: 20 bytes × 2 Hz × 1 broadcast = 320 bps (shared)
- **Total**: ~40 Kbps (0.04% of 100 Mbps Wi-Fi)

### Comparison to Architecture 1
**Arch 1 (UDP Broadcast)**:
- 100 Hz × 50 bytes × 10 devices = 40 Kbps (similar)
- But lacks autonomy and saturates at higher frequencies

**Arch 2 Advantage**: Constant network load regardless of sequence frequency

## Failure Modes & Recovery

### 1. Server Unavailable
**Behavior**: Nodes continue executing last valid configuration  
**Detection**: HTTP timeout (>5s)  
**Recovery**: Automatic reconnection with exponential backoff

### 2. Sync Packet Loss
**Behavior**: Continue with predictive drift compensation  
**Detection**: No sync for >2 seconds  
**Recovery**: Increase sync frequency if connection restored

### 3. Multiple Consecutive Outliers
**Behavior**: Extrapolate clock offset using drift rate  
**Detection**: >5 rejected packets in a row  
**Recovery**: Reset drift estimation when valid sync returns

### 4. Clock Overflow (micros() wraparound)
**Behavior**: Handle 32-bit wraparound at ~71 minutes  
**Detection**: master_time < last_master_time  
**Recovery**: Adjust offset calculation for wraparound

## Scalability Considerations

### ESP-NOW Limitations
- **Max nodes**: 20 encrypted peers (ESP32-C6 limit)
- **Max unencrypted**: 20 additional peers
- **Broadcast range**: ~100-200m line-of-sight

### Multi-Master Architecture (Future)
For >20 nodes, use hierarchical sync:
```
Server
  ├─ Grandmaster 1 (Nodes 1-20)
  ├─ Grandmaster 2 (Nodes 21-40)
  └─ Grandmaster 3 (Nodes 41-60)
```

Each grandmaster syncs to server NTP, broadcasts to its subnet.

## Monitoring & Diagnostics

### Real-Time Metrics
1. **Drift Statistics**: Mean, median, max drift per device
2. **Sync Health**: Packet loss rate, outlier percentage
3. **Execution Status**: Current phase, state transitions
4. **Network Health**: HTTP response time, ESP-NOW RSSI

### Alerting Thresholds
- **Warning**: Mean drift >50µs for 60s
- **Critical**: Mean drift >100µs or max >500µs
- **Emergency**: No sync for >10s

### Debug Logging Levels
- **ERROR**: Sync failures, config errors
- **WARN**: Outliers rejected, high drift
- **INFO**: Sync success, config updates
- **DEBUG**: Every sync packet, phase calculations
- **TRACE**: Microsecond timestamps, all calculations

## Testing Strategy

### 1. Unit Tests (Per-Module)
- Clock offset calculation
- Phase computation accuracy
- Outlier detection logic
- Drift extrapolation

### 2. Integration Tests (Two-Node)
- Grandmaster-follower sync
- Configuration updates
- Failure recovery

### 3. Hardware Validation (Observer Method)
- Same setup as POC Test 2
- Measure actual GPIO timing
- Target: <50µs mean drift

### 4. Long-Term Stability (24h+)
- Monitor drift over extended operation
- Detect clock overflow handling
- Measure accumulated error

### 5. Scalability Tests (10+ Nodes)
- Multi-node synchronization
- Network congestion impact
- ESP-NOW broadcast reliability

## References
- POC Results: `/poc/test_results/ANALYSIS_EVALUATION.md`
- ESP32 Clock Drift: Typical 50ppm at 25°C
- ESP-NOW Latency: 1-3ms typical (POC measured: median 1054µs)

---
**Version**: 1.0  
**Date**: March 17, 2026  
**Status**: Design Complete, Implementation In Progress
