# kywoSystem: ESP32-C6 Command Server (Python)

A small Python server to connect and manage multiple ESP32 WiFi devices. Each device has its own command queue so commands are routed independently.

## Current Scope
- Register ESP32 devices with `device_id` and `device_token`
- Queue commands for specific devices
- Devices poll for pending commands
- Devices acknowledge processed commands

## Folder Layout
- `src/server/main.py`: FastAPI endpoints
- `src/server/device_manager.py`: In-memory registry and queues
- `src/server/models.py`: Request/response schemas
- `docs/ARCHITECTURE.md`: architecture and flow

## Run Locally
```powershell
cd c:\Users\jehm\Documents\Playground\kywoSystem
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ADMIN_API_KEY = "super-secret-admin"
uvicorn src.server.main:app --host 0.0.0.0 --port 8000 --reload
```

## Example: Two ESP32 Devices
Register both devices:

```powershell
curl -X POST http://localhost:8000/devices/register `
  -H "Content-Type: application/json" `
  -d '{"device_id":"esp32-a","device_token":"token-device-a","firmware_version":"1.0.0"}'

curl -X POST http://localhost:8000/devices/register `
  -H "Content-Type: application/json" `
  -d '{"device_id":"esp32-b","device_token":"token-device-b","firmware_version":"1.0.0"}'
```

Queue device-specific commands:

```powershell
curl -X POST http://localhost:8000/commands/esp32-a `
  -H "X-API-Key: super-secret-admin" `
  -H "Content-Type: application/json" `
  -d '{"command":"relay:on"}'

curl -X POST http://localhost:8000/commands/esp32-b `
  -H "X-API-Key: super-secret-admin" `
  -H "Content-Type: application/json" `
  -d '{"command":"fan:off"}'
```

Device `esp32-a` fetches only its commands:

```powershell
curl "http://localhost:8000/devices/esp32-a/commands?token=token-device-a&after_command_id=0&limit=10"
```

Device `esp32-b` fetches only its commands:

```powershell
curl "http://localhost:8000/devices/esp32-b/commands?token=token-device-b&after_command_id=0&limit=10"
```

Acknowledge processed command:

```powershell
curl -X POST "http://localhost:8000/devices/esp32-a/ack?token=token-device-a" `
  -H "Content-Type: application/json" `
  -d '{"command_id":1}'
```

## Next Steps
- Persist devices and queues in Redis/PostgreSQL
- Add retry/timeout logic for command delivery
- Add TLS and token rotation
- Add dashboard or CLI for operations

## ESP32 Firmware
- Firmware client sketch: `firmware/esp32_c6_client/esp32_c6_client.ino`
- Firmware instructions: `firmware/README.md`

Suggested flow:
1. Start this Python server.
2. Flash one ESP32-C6 as `esp32-a` and another as `esp32-b`.
3. Queue commands with `POST /commands/{device_id}`.
4. Check serial logs on each board to confirm per-device routing.
