# Proof of Concept (POC) - March 2026

This directory contains all experimental work from the proof-of-concept phase that validated two architectural approaches for synchronized ESP32-C6 device control.

## Purpose
The POC phase (completed March 16, 2026) demonstrated that both centralized and distributed architectures can achieve device synchronization, with different trade-offs.

## Contents

### `/firmware/`
All POC firmware variants tested during experimentation:
- **arduino/esp32_c6_client/** - Basic HTTP polling client
- **arduino/esp32_c6_arch2/** - Architecture 2 implementation (distributed with ESP-NOW)
- **arduino/esp32_c6_observer/** - Hardware timing measurement tools
- **arduino/esp32_c6_observer_arch1/** - Observer for Architecture 1 tests
- **arduino/esp32_c6_observer_arch2/** - Observer for Architecture 2 tests
- **arduino/esp32_c6_udp_client/** - UDP broadcast client (Architecture 1)
- **espidf/** - ESP-IDF experimental code

### `/server/`
POC Python FastAPI server:
- Device registration and authentication
- Per-device command queuing
- UDP broadcast support for Architecture 1
- Web UI for monitoring

### `/tests/`
Test scripts used for evaluation:
- `udp_ping_test.py` - Software round-trip latency measurement
- `hardware_latency_test.py` - Hardware-timed Architecture 1 evaluation
- `arch1_sync_test.py` - Architecture 1 synchronization testing
- `arch2_sync_test.py` - Architecture 2 synchronization testing
- `analyze_results.py` - Statistical analysis of test data
- `analyze_experiments.py` - Publication-ready figures and tables

### `/test_results/`
Raw CSV data, analysis reports, and publication figures:
- Multiple test runs with timestamps
- `ANALYSIS_EVALUATION.md` - Comprehensive evaluation report
- `RESULTS_ANALYSIS.md` - Statistical summaries
- `publication_figures/` - LaTeX tables and visualizations

## Key Findings

### Architecture 1: Centralized UDP Broadcast
- ✅ **Excellent synchronization**: 8µs mean drift
- ⚠️ **High network load**: Continuous UDP broadcasts required
- ⚠️ **No autonomy**: Devices depend on server for all actions
- **Use case**: Tight synchronization requirements (<10µs)

### Architecture 2: Distributed ESP-NOW + Local Execution
- ⚠️ **Poor synchronization**: 108µs mean drift (13.8x worse than Arch 1)
- ⚠️ **High variability**: 6.5ms outliers observed
- ✅ **Low network load**: ESP-NOW sync every 2000ms, HTTP poll every 1000ms
- ✅ **Full autonomy**: Devices execute independently
- **Improvement potential**: Reduce ESP-NOW interval, improve drift compensation

## Decision
**Architecture 2 selected for prototype** due to:
1. Better scalability (lower network load)
2. Autonomous operation (resilient to server downtime)
3. Deterministic local execution
4. Synchronization can be improved with firmware optimizations

## References
- See `/docs/ARCHITECTURE.md` for original architecture documentation
- See test results for detailed performance data

---
**Status**: POC Complete ✅  
**Next Phase**: Prototype development in `/prototype/` directory
