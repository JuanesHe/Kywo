# Kywo Prototype — API & System Description

## System Overview

Kywo is a distributed edge-control system. Multiple **ESP32-C6 nodes** execute synchronized output sequences (digital + PWM) autonomously. A central **Python/FastAPI server** provides configuration storage and device management. Nodes communicate with the server over **HTTP/TCP** and synchronize clocks with each other over **ESP-NOW** (no server involvement in the sync path).

```
┌──────────────────────────────────────────────┐
│  Admin / Web UI  (browser → HTTP)            │
└───────────────────────┬──────────────────────┘
                        │  REST API
              ┌─────────▼──────────┐
              │   FastAPI Server   │
              │   (port 8000)      │
              └──┬──────────────┬──┘
         HTTP/TCP│              │HTTP/TCP
         (poll)  │              │ (poll)
        ┌────────▼──┐      ┌────▼────────┐
        │  Node A   │◄────►│   Node B    │
        │ (Master)  │      │ (Follower)  │
        └───────────┘      └─────────────┘
           ESP-NOW broadcast (clock sync only)
```

---

## Communication Channels

| Channel      | Protocol   | Direction              | Purpose                                |
|--------------|------------|------------------------|----------------------------------------|
| HTTP polling | TCP/HTTP   | Device → Server        | Fetch config + heartbeat (1 s interval)|
| HTTP register| TCP/HTTP   | Device → Server        | One-time registration on boot          |
| REST API     | TCP/HTTP   | Admin/UI → Server      | Manage devices, push sequences         |
| ESP-NOW      | Wi-Fi (raw)| Master → All followers | Clock synchronization (2 s interval)   |

---

## How the Server Handles Device Communication

The server uses a **pull model** — it never pushes data to devices. Devices are responsible for periodically fetching updates.

### Boot sequence (on each ESP32 node)

1. Connect to Wi-Fi.
2. Generate a unique device ID from the MAC address (`ESP32-C6-XXYY`).
3. `POST /devices/register` — tells the server this device is alive.
4. `GET /devices/{device_id}/config` — immediately fetches the initial state machine and ESP-NOW role.
5. Start two FreeRTOS tasks:
   - **Core 0** — ESP-NOW sync broadcast task.
   - **Core 1** — State machine execution engine (highest priority).
6. `loop()` polls `GET /devices/{device_id}/config` every **1000 ms**.

---

## How the Config Polling ("Subscription") Works

There is no WebSocket or server-side push. Config delivery is implemented as **HTTP long-polling with a local diff check**:

```
Every 1 000 ms:
  ESP32 ──GET /devices/{id}/config──► Server
         ◄─── JSON config ───────────

  If payload != lastPayload:
    parse new sequence
    write into inactive double-buffer
    atomically swap buffer index   → execution engine picks up change
    update lastPayload
```

### Why double-buffering?
The state machine execution task runs continuously on Core 1. Rather than locking, the firmware writes the new config into an *inactive* buffer slot and then flips `activeConfigIdx`. The engine always reads from `activeConfigIdx`, so the swap is race-free.

### Heartbeat via polling
Every config poll also acts as a **heartbeat**. The server calls `manager.heartbeat(device_id)` on each successful poll, updating `last_seen`. A device is considered **online** if `last_seen` is less than **5 seconds** ago.

If the server is restarted and loses in-memory state, the poll endpoint auto-registers any unknown device ID so it can continue operating without manual intervention.

---

## Master Arbitration

On every config poll the server runs `arbitrate_master()`:

1. Find all devices with `last_seen < 5 s` (active).
2. If a current master is still active → keep it; clear `is_master` on all others.
3. If no master is active → elect the **lexicographically first** active device (deterministic).

The elected master's `device_id` is reflected in the config response (`"is_master": true`). When a node sees this flag flip it reconfigures its ESP-NOW stack (add broadcast peer, start sending sync frames).

---

## REST API Reference

Base URL: `http://<server>:8000`

All routes that mutate state or expose sensitive data require the header:

```
x-api-key: <ADMIN_API_KEY>   # default: "change-me"  (set via env var ADMIN_API_KEY)
```

---

### Health

#### `GET /health`
Returns server liveness. No authentication required.

**Response `200`**
```json
{ "status": "ok" }
```

---

### Device Management

#### `POST /devices/register`
Registers a new device. Called by the firmware on boot. No API key required.

**Request body**
```json
{
  "device_id": "ESP32-C6-AABB",     // 3–64 chars
  "device_token": "kywo-device-token", // 8–128 chars, stored for future token validation
  "firmware_version": "3.0.0-Production",
  "wifi_channel": 6
}
```

**Response `200`** — `DeviceRecord`
```json
{
  "device_id": "ESP32-C6-AABB",
  "device_token": "kywo-device-token",
  "firmware_version": "3.0.0-Production",
  "last_seen": "2026-04-22T10:00:00Z",
  "is_master": false,
  "wifi_channel": 6
}
```

---

#### `GET /devices`
Lists all registered devices with online status. Requires API key.

**Response `200`** — array of `DeviceStatus`
```json
[
  {
    "device_id": "ESP32-C6-AABB",
    "device_token": "kywo-device-token",
    "firmware_version": "3.0.0-Production",
    "last_seen": "2026-04-22T10:00:01Z",
    "is_master": true,
    "wifi_channel": 6,
    "is_online": true,
    "seconds_since_seen": 0.8
  }
]
```

`is_online` is `true` when `seconds_since_seen < 5`.

---

#### `DELETE /devices/{device_id}`
Removes a device from the registry. Requires API key.

**Response `200`**
```json
{ "status": "success", "message": "Device ESP32-C6-AABB removed" }
```

**Response `404`** if device not found.

---

### Configuration (State Machine)

#### `GET /devices/{device_id}/config`
Fetches the current state machine configuration for a device.  
**This is the endpoint polled by firmware every 1 s.** Requires API key.

In addition to returning the config, each call:
- Updates `last_seen` (heartbeat).
- Runs master arbitration.
- Auto-registers unknown device IDs (server restart recovery).

**Response `200`**
```json
{
  "sequence": [
    {
      "digital_out1": true,
      "digital_out2": false,
      "digital_out3": false,
      "pwm_out": 128,
      "duration_ms": 1000
    },
    {
      "digital_out1": false,
      "digital_out2": true,
      "digital_out3": true,
      "pwm_out": 255,
      "duration_ms": 1000
    }
  ],
  "is_master": false,
  "master_channel": 6
}
```

| Field          | Description                                                       |
|----------------|-------------------------------------------------------------------|
| `sequence`     | Ordered list of output states to execute in a loop               |
| `is_master`    | Whether this device should act as ESP-NOW Grandmaster Clock       |
| `master_channel` | Wi-Fi channel the current master is on (followers must match)  |

---

#### `POST /devices/{device_id}/config`
Pushes a new state machine sequence to a device. The device picks it up on its next poll (≤ 1 s). Requires API key.

**Request body**
```json
{
  "sequence": [
    {
      "digital_out1": true,
      "digital_out2": false,
      "digital_out3": false,
      "pwm_out": 200,
      "duration_ms": 500
    }
  ]
}
```

| Field         | Type    | Constraints              |
|---------------|---------|--------------------------|
| `digital_out1`| bool    | GPIO 15                  |
| `digital_out2`| bool    | GPIO 16                  |
| `digital_out3`| bool    | GPIO 17                  |
| `pwm_out`     | int     | 0–255, LEDC on GPIO 18   |
| `duration_ms` | int     | > 0 ms                   |

Sequence length is limited to **20 states** by the firmware buffer. The server stores any size; the firmware silently truncates at 20.

**Response `200`**
```json
{ "status": "config_updated", "device": "ESP32-C6-AABB", "states": 1 }
```

---

### Master Role Assignment

#### `POST /devices/{device_id}/set_master`
Manually forces a specific device to become the ESP-NOW Grandmaster Clock. Clears the master flag on all other devices. Requires API key.

**Response `200`**
```json
{
  "status": "success",
  "message": "ESP32-C6-AABB is now the Grandmaster Clock for ESP-NOW sync"
}
```

**Response `404`** if device not found.

The device learns about the role change on its next config poll (≤ 1 s) via the `"is_master": true` flag.

---

## How ESP-NOW Clock Synchronization Works

Clock sync is entirely **device-to-device** — the server only designates the master role.

```
Grandmaster (Core 0 task, every 2 000 ms):
  msg = { magic: 0xA2C22026, master_time_us: esp_timer_get_time() }
  esp_now_send(FF:FF:FF:FF:FF:FF, msg)   ← broadcast to all peers

Follower (ISR/callback):
  receive msg
  compensated_master = msg.master_time_us + 1054 µs  (measured latency)
  clockOffsetUs = compensated_master - esp_timer_get_time()
  clockSynced = true
```

The execution engine uses `getSyncedTimeUs()` = `esp_timer_get_time() + clockOffsetUs` to compute the current position within the shared sequence timeline. All nodes resolve the same position independently, so they drive their outputs in lockstep.

---

## State Machine Execution Engine

The execution engine (Core 1, highest FreeRTOS priority) runs a time-phase algorithm:

```
nowUs       = getSyncedTimeUs()
totalUs     = sum of all state durations
phaseUs     = nowUs mod totalUs          ← position in current loop
activeState = first state where phaseUs < cumulative_duration
```

This means all nodes — with an accurate synchronized clock — execute the same state at the same moment, regardless of when they individually joined.

**Timing precision strategy:**
- `timeToNextState > 2 ms` → `vTaskDelay()` (yield to OS)
- `timeToNextState ≤ 2 ms` → busy-wait loop (sub-millisecond precision)

---

## Web UI

Served at `GET /ui/index.html` (root `/` redirects there).

The UI communicates with the same REST API using fetch calls with the hardcoded key `super-secret-admin`. It provides:
- **Device list** with online/offline status and last-seen time.
- **Sequence builder** — visual table to define states with selectors and inputs.
- **Deploy button** — `POST /devices/{id}/config` with the built sequence.
- **Set Grandmaster button** — `POST /devices/{id}/set_master`.
- **Event log** — timestamped log of all UI actions and API responses.

> **Security note**: The API key is embedded in the UI source. For production use, serve the key server-side (e.g., via a session cookie or a dedicated login flow) rather than embedding it in client JavaScript.

---

## Data Flow Summary

```
1. ESP32 boots → POST /devices/register
2. ESP32 polls GET /devices/{id}/config every 1 s
   └── Server responds: sequence + is_master + master_channel
   └── Device updates state machine buffer (double-buffered, race-free)
   └── Device updates ESP-NOW role if changed

3. Admin uses Web UI or REST to POST /devices/{id}/config with new sequence
   └── Server stores in _arch2_state_machines[device_id]
   └── Device picks it up on next poll (≤ 1 s)

4. Grandmaster broadcasts ESP-NOW sync every 2 s
   └── Followers compute clockOffsetUs
   └── All nodes execute same phase of state machine in sync
```

---

## Environment Variables

| Variable        | Default        | Description                            |
|-----------------|----------------|----------------------------------------|
| `ADMIN_API_KEY` | `change-me`    | Shared secret for all protected routes |

---

## Running the Server

```bash
cd prototype/
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

The server must be started from the `prototype/` directory so that Python resolves the `server` package (relative imports inside `main.py`).
