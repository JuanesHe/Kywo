# Architecture: Python Command Router for Multiple ESP32-C6 Devices

## Goal
A lightweight server sends simple, device-specific commands to multiple ESP32-C6 WiFi microcontrollers.

## Pattern
Use a **central command router** with **per-device queues**.

- ESP32 devices are clients that authenticate and pull commands.
- A control client (CLI, UI, or automation) pushes commands for specific devices.
- The server keeps each device queue isolated so commands do not mix.

## Components
1. API Server (`FastAPI`)
   - Receives device registration and heartbeat traffic.
   - Accepts operator commands targeted to a specific `device_id`.
   - Returns pending commands only for the requesting device.

2. Device Registry
   - Tracks known devices and metadata:
     - `device_id`
     - `device_token`
     - `firmware_version`
     - `last_seen`

3. Per-Device Command Queues
   - One FIFO queue per device.
   - Commands get increasing global IDs.
   - Device acknowledges commands to remove delivered items.

4. Control Side
   - Any trusted tool can call `POST /commands/{device_id}` with admin API key.

## Data Flow
1. Device registers once: `POST /devices/register`.
2. Operator sends command for `esp32-A` or `esp32-B`.
3. Device polls: `GET /devices/{device_id}/commands`.
4. Device executes command.
5. Device confirms with `POST /devices/{device_id}/ack`.

## Why Polling First
Polling is simple and stable on ESP32 firmware and avoids always-open socket complexity. You can later upgrade to MQTT/WebSocket while keeping the same logical architecture.

## Scaling Path
- Replace in-memory registry/queues with Redis or PostgreSQL.
- Add retries and TTL for commands.
- Add TLS and signed tokens.
- Add metrics (online devices, queue depth, command latency).
- Deploy behind reverse proxy.
