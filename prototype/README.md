# Kywo Prototype - Architecture 2 Implementation

Production-ready implementation of the distributed Architecture 2 approach with improved synchronization.

## Overview
This prototype builds on POC learnings to create a scalable, autonomous ESP32-C6 device coordination system using:
- **ESP-NOW** for low-latency clock synchronization
- **Local execution engines** for deterministic autonomous operation
- **HTTP polling** for configuration updates
- **Improved sync algorithms** to address POC drift issues

## Goals
1. **Improve synchronization**: Target <50µs mean drift (vs. 108µs in POC)
2. **Production-ready code**: Clean, documented, maintainable firmware
3. **Monitoring & diagnostics**: Real-time drift tracking and alerting
4. **Scalable architecture**: Support 10+ edge nodes reliably

## Structure

### `/firmware/`
Production firmware for edge nodes:
- `grandmaster/` - Master node with clock authority
- `follower/` - Follower nodes that sync to master
- `shared/` - Common libraries and utilities

### `/server/`
Python FastAPI server for configuration and monitoring:
- Configuration endpoint for sequence control
- Real-time drift monitoring API
- Device health checks and diagnostics

### `/docs/`
Prototype-specific documentation:
- `ARCHITECTURE.md` - Detailed Architecture 2 design
- `DEPLOYMENT.md` - Setup and deployment guide
- `API.md` - Server API documentation
- `IMPROVEMENTS.md` - Changes from POC

## Key Improvements Over POC

### 1. Enhanced Synchronization
- ✅ Reduced ESP-NOW interval: 2000ms → 500ms
- ✅ Dynamic latency compensation (measured vs. fixed 1054µs)
- ✅ Outlier rejection for spurious sync packets
- ✅ Predictive drift compensation between syncs

### 2. Production Code Quality
- ✅ Modular firmware architecture
- ✅ Configuration via header files
- ✅ Comprehensive error handling
- ✅ Debug logging levels

### 3. Monitoring & Operations
- ✅ Real-time drift metrics API
- ✅ Device health dashboard
- ✅ Alerting for drift thresholds
- ✅ Remote configuration updates

## Quick Start

### 1. Flash Firmware
```bash
# Flash grandmaster node
cd firmware/grandmaster/
# Configure platformio.ini, upload

# Flash follower nodes
cd ../follower/
# Configure config.h with unique device_id
# Upload to each follower
```

### 2. Start Server
```bash
cd server/
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Monitor Operation
```bash
# Check device status
curl http://localhost:8000/devices

# View sync metrics
curl http://localhost:8000/metrics/drift
```

## Development Status

### Phase 1: Core Firmware ⏳
- [ ] Grandmaster firmware with improved sync broadcast
- [ ] Follower firmware with dynamic drift compensation
- [ ] Shared library for common functions

### Phase 2: Server Enhancement ⏳
- [ ] Sequence configuration API
- [ ] Real-time metrics collection
- [ ] Dashboard UI

### Phase 3: Testing & Validation ⏳
- [ ] Hardware sync validation (target: <50µs)
- [ ] Long-term stability testing (24h+ runs)
- [ ] Multi-node scalability tests (10+ devices)

### Phase 4: Documentation & Deployment ⏳
- [ ] Complete API documentation
- [ ] Deployment guide
- [ ] Troubleshooting guide

## Target Specifications

| Metric | POC Result | Prototype Target |
|--------|------------|------------------|
| Mean Drift | 108µs | <50µs |
| Std Dev | 496µs | <100µs |
| Max Drift | 6.5ms | <500µs |
| Sync Interval | 2000ms | 500ms |
| Network Load | Low | Low |
| Device Autonomy | Full | Full |

---
**Status**: In Development 🚧  
**Started**: March 17, 2026  
**POC Results**: See `/poc/` directory
