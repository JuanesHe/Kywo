# Kywo System: Distributed ESP32-C6 Coordination Platform

A distributed system for synchronized control of multiple ESP32-C6 devices using autonomous execution with periodic clock synchronization.

## Project Status

### ✅ POC Complete (March 16, 2026)
Proof-of-concept validated two architectures with comprehensive testing. **Architecture 2** selected for prototype development.

### 🚧 Prototype In Development (Started March 17, 2026)
Production-ready implementation of Architecture 2 with improved synchronization algorithms.

## Repository Structure

```
kywoSystem/
├── poc/                    # Proof-of-concept artifacts (COMPLETE)
│   ├── firmware/          # All POC firmware variants
│   ├── server/           # POC FastAPI server (command queuing)
│   ├── tests/             # Test scripts and experiments
│   └── test_results/      # Performance data & analysis
│
├── prototype/             # Production prototype (IN PROGRESS)
│   ├── firmware/          # Production-ready arch2 firmware
│   ├── server/           # New server for sequence config & monitoring
│   └── docs/             # Prototype-specific documentation
│
└── docs/                 # Project-wide documentation
    └── ARCHITECTURE.md   # Original architecture overview
```

## Quick Navigation

### For Understanding the Project
- [POC Overview & Results](poc/README.md) - What we learned
- [POC Test Analysis](poc/test_results/ANALYSIS_EVALUATION.md) - Detailed performance data
- [Architecture Overview](docs/ARCHITECTURE.md) - Original design concepts

### For Prototype Development
- [Prototype README](prototype/README.md) - Current development status
- [Prototype Architecture](prototype/docs/ARCHITECTURE.md) - Detailed Arch2 design
- [Prototype Firmware](prototype/firmware/) - Production firmware (coming soon)

## Architecture 2 Overview

**Design**: Distributed autonomous execution with periodic clock synchronization
- **Autonomy**: Nodes execute independently without continuous server communication
- **Synchronization**: ESP-NOW broadcasts keep clocks aligned (500ms intervals)
- **Configuration**: HTTP polling for sequence updates (1000ms intervals)
- **Target**: <50µs mean drift (vs. 108µs in POC)

## POC Key Findings

### Architecture 1: Centralized UDP Broadcast
- ✅ **Excellent sync**: 8µs mean drift
- ⚠️ **High network load**: Continuous broadcasts
- ⚠️ **No autonomy**: Server-dependent
- **Decision**: Great for tight sync, but doesn't scale

### Architecture 2: Distributed ESP-NOW + Local Execution
- ⚠️ **POC sync**: 108µs mean drift (13.8× worse than Arch1)
- ✅ **Low network load**: Periodic sync only
- ✅ **Full autonomy**: Survives server downtime
- ✅ **Deterministic**: Predictable local execution
- **Decision**: Selected for prototype with sync improvements

## Prototype Improvements

The prototype addresses POC synchronization issues:
1. **4× faster sync**: 2000ms → 500ms intervals
2. **Dynamic compensation**: Measured latency vs. fixed 1054µs
3. **Outlier rejection**: Ignore spurious sync packets
4. **Predictive drift**: Linear interpolation between syncs

**Target**: <50µs mean drift (vs. 108µs in POC)

## Development Setup

### POC Server (for reference)
```powershell
cd poc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ../requirements.txt
$env:ADMIN_API_KEY = "super-secret-admin"
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

### Firmware Development
See [prototype/firmware/](prototype/firmware/) for production firmware (coming soon)  
See [poc/firmware/](poc/firmware/) for POC variants

## Contributing

This project is in active prototype development. See [prototype/README.md](prototype/README.md) for current status and development roadmap.
