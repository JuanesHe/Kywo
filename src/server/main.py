import os
import socket
import time
from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .device_manager import DeviceManager
from .models import (
    AckRequest,
    DeviceRecord,
    DeviceRegistrationRequest,
    PendingCommandsResponse,
    QueueCommandRequest,
)

app = FastAPI(title="ESP32 Control Server", version="0.2.0")

# Mount web UI files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/ui", StaticFiles(directory=static_dir), name="ui")
manager = DeviceManager(max_queue_size=300)
admin_api_key = os.getenv("ADMIN_API_KEY", "change-me")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SHARED INFRASTRUCTURE — UDP sockets, startup/shutdown, health
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UDP broadcast sockets
UDP_BROADCAST_IP = "255.255.255.255"
UDP_BROADCAST_PORT = 4210    # Arch I  — real-time commands (relay:on/off, ping/pong)
UDP_SYNC_PORT = 4211         # Arch II — periodic clock synchronization
UDP_PARAM_PORT = 4212        # Arch II — control parameter updates

_udp_sock: socket.socket | None = None
_sync_task = None


def _get_udp_socket() -> socket.socket:
    global _udp_sock
    if _udp_sock is None:
        _udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        _udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Disable Nagle-like buffering — send immediately
        _udp_sock.setblocking(False)
    return _udp_sock


@app.on_event("startup")
async def _start_sync_broadcaster():
    # Architecture II Phase 2: Python UDP sync removed.
    # Synchronization is now handled by direct ESP-NOW hardware pulses
    # between the edge devices. The server simply assigns the Master role.
    pass


@app.on_event("shutdown")
async def _shutdown():
    global _udp_sock, _sync_task
    if _sync_task:
        _sync_task.cancel()
    if _udp_sock is not None:
        _udp_sock.close()
        _udp_sock = None


@app.get("/")
async def root():
    return RedirectResponse(url="/ui/index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ARCHITECTURE I — Real-Time UDP Command Streaming
#
# The server broadcasts high-frequency commands directly to edge devices.
# Each relay:on / relay:off triggers an instant action over Wi-Fi.
# All latency is network-bound. Measured with UDP ping/pong round-trip tests.
#
# Firmware: firmware/arduino/esp32_c6_udp_client/esp32_c6_udp_client.ino
# UDP Port: 4210
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/broadcast")
async def broadcast_command(
    payload: QueueCommandRequest,
    x_api_key: str = Header(default=""),
):
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")

    sock = _get_udp_socket()
    message = payload.command.encode('utf-8')
    sock.sendto(message, (UDP_BROADCAST_IP, UDP_BROADCAST_PORT))

    return {"status": "broadcast_sent", "command": payload.command, "bytes": len(message)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ARCHITECTURE II — Distributed Autonomous Edge Control
#
# The server acts only as a master clock + parameter registry.
# Edge devices receive a time sync pulse every 1 second, then execute
# a local FreeRTOS control loop autonomously. Network latency does NOT
# affect output timing — the edge device runs independently.
#
# Firmware: firmware/arduino/esp32_c6_arch2/esp32_c6_arch2.ino
# UDP Ports: 4211 (sync), 4212 (params)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# In-memory store for Architecture II device state machines
# Maps device_id -> dict with 'sequence' (list of states)
_arch2_state_machines: dict[str, dict] = defaultdict(lambda: {
    "sequence": [
        {"pin1": True,  "pin2": False, "duration_ms": 1000},
        {"pin1": False, "pin2": True,  "duration_ms": 1000}
    ]
})

@app.get("/arch2/devices/{device_id}/config")
async def get_arch2_config(device_id: str, x_api_key: str = Header(default="")):
    # ESP32 polls this endpoint over HTTP (TCP) to download its state machine
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
        
    # Auto-register the device if it survived a server RAM restart
    if device_id not in manager._devices:
        await manager.register_device(
            device_id=device_id,
            device_token="arch2-auto-token",
            firmware_version="2.2-AutoRecovery",
            wifi_channel=0 # Will be updated properly on full reboot, but good enough to join cluster
        )
        
    await manager.heartbeat(device_id)
    await manager.arbitrate_master()
    
    # Check if this device is the designated Grandmaster, and find the Master's channel
    is_master = False
    master_channel = 0
    device = manager._devices.get(device_id)
    if device and device.is_master:
        is_master = True

    for _, dev in manager._devices.items():
        if dev.is_master and dev.wifi_channel is not None:
            master_channel = dev.wifi_channel
            break

    config = _arch2_state_machines[device_id].copy()
    config["is_master"] = is_master
    config["master_channel"] = master_channel
    return config

@app.post("/arch2/devices/{device_id}/set_master")
async def set_arch2_master(device_id: str, x_api_key: str = Header(default="")):
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    
    if device_id not in manager._devices:
        raise HTTPException(status_code=404, detail="Device not found")

    # Clear master flag from all other devices
    for _id, dev in manager._devices.items():
        dev.is_master = False
        
    # Assign new master
    manager._devices[device_id].is_master = True
    return {"status": "success", "message": f"{device_id} is now the Grandmaster Clock for ESP-NOW sync"}


class StateNode(BaseModel):
    pin1: bool
    pin2: bool
    duration_ms: int

class StateMachineRequest(BaseModel):
    sequence: list[StateNode]

@app.post("/arch2/devices/{device_id}/config")
async def update_arch2_config(
    device_id: str,
    payload: StateMachineRequest,
    x_api_key: str = Header(default="")
):
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    
    if len(payload.sequence) == 0:
        raise HTTPException(status_code=400, detail="Sequence cannot be empty")
    
    _arch2_state_machines[device_id] = payload.dict()
    return {"status": "config_updated", "device": device_id, "states": len(payload.sequence)}


@app.post("/ping-test")
async def ping_test(
    x_api_key: str = Header(default=""),
    count: int = Query(default=100, ge=10, le=1000),
    interval_ms: int = Query(default=50, ge=10, le=500),
):
    """Send UDP pings and measure round-trip latency to all listening ESP32s."""
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")

    import asyncio

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run_ping_test_sync, count, interval_ms)
    return result


def _run_ping_test_sync(count: int, interval_ms: int) -> dict:
    """Blocking ping test — runs in a thread pool to avoid blocking the event loop."""
    import csv
    from datetime import datetime

    tx_sock = _get_udp_socket()

    # Temporary receive socket for pong replies
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx_sock.bind(("0.0.0.0", UDP_BROADCAST_PORT))
    rx_sock.settimeout(0.002)

    # Raw measurements: list of (seq, device_ip, rtt_us, timestamp)
    raw_measurements: list[tuple[int, str, float, float]] = []
    results: dict[str, list[float]] = defaultdict(list)
    send_times: dict[int, float] = {}

    test_start = time.time()

    for seq in range(1, count + 1):
        message = f"ping:{seq}".encode("utf-8")
        t_send = time.perf_counter_ns()
        tx_sock.sendto(message, (UDP_BROADCAST_IP, UDP_BROADCAST_PORT))
        send_times[seq] = t_send

        deadline = time.perf_counter_ns() + interval_ms * 1_000_000
        while time.perf_counter_ns() < deadline:
            try:
                data, addr = rx_sock.recvfrom(512)
            except (socket.timeout, BlockingIOError):
                continue

            text = data.decode("utf-8", errors="ignore")
            if not text.startswith("pong:"):
                continue

            try:
                pong_seq = int(text[5:])
            except ValueError:
                continue

            if pong_seq in send_times:
                rtt_us = (time.perf_counter_ns() - send_times[pong_seq]) / 1_000
                device_ip = addr[0]
                results[device_ip].append(rtt_us)
                raw_measurements.append((pong_seq, device_ip, rtt_us, time.time()))

    rx_sock.close()

    # ── Save raw measurements to CSV ──
    results_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "test_results")
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"ping_test_{timestamp}.csv"
    csv_path = os.path.join(results_dir, csv_filename)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seq", "device_ip", "rtt_us", "rtt_ms", "timestamp_unix"])
        for seq, ip, rtt_us, ts in raw_measurements:
            writer.writerow([seq, ip, f"{rtt_us:.1f}", f"{rtt_us/1000:.3f}", f"{ts:.6f}"])

    # ── Compute stats per device ──
    devices_stats = {}
    for ip, rtts in sorted(results.items()):
        rtts_sorted = sorted(rtts)
        n = len(rtts_sorted)
        avg = sum(rtts_sorted) / n
        variance = sum((r - avg) ** 2 for r in rtts_sorted) / n
        jitter = variance ** 0.5

        devices_stats[ip] = {
            "count": n,
            "min_ms": rtts_sorted[0] / 1000,
            "avg_ms": avg / 1000,
            "median_ms": rtts_sorted[int(n * 0.5)] / 1000,
            "p95_ms": rtts_sorted[int(n * 0.95)] / 1000,
            "p99_ms": rtts_sorted[min(int(n * 0.99), n - 1)] / 1000,
            "max_ms": rtts_sorted[-1] / 1000,
            "jitter_ms": jitter / 1000,
        }

    return {
        "pings_sent": count,
        "interval_ms": interval_ms,
        "devices": devices_stats,
        "csv_file": csv_path,
    }


@app.post("/devices/register", response_model=DeviceRecord)
async def register_device(payload: DeviceRegistrationRequest) -> DeviceRecord:
    return await manager.register_device(
        device_id=payload.device_id,
        device_token=payload.device_token,
        firmware_version=payload.firmware_version,
        wifi_channel=payload.wifi_channel,
    )


@app.get("/devices", response_model=list[DeviceRecord])
async def list_devices(x_api_key: str = Header(default="")) -> list[DeviceRecord]:
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    return await manager.list_devices()


@app.post("/commands/{device_id}")
async def queue_command(
    device_id: str,
    payload: QueueCommandRequest,
    x_api_key: str = Header(default=""),
) -> dict[str, int | str]:
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")

    try:
        queued = await manager.enqueue_command(device_id=device_id, command=payload.command)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "device_id": device_id,
        "command_id": queued.command_id,
        "status": "queued",
    }


@app.get("/devices/{device_id}/commands", response_model=PendingCommandsResponse)
async def get_device_commands(
    device_id: str,
    token: str = Query(min_length=8),
    after_command_id: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
) -> PendingCommandsResponse:
    is_valid = await manager.validate_device(device_id=device_id, token=token)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    await manager.heartbeat(device_id)
    commands = await manager.fetch_pending_commands(
        device_id=device_id,
        min_command_id=after_command_id,
        limit=limit,
    )
    return PendingCommandsResponse(device_id=device_id, commands=commands)


@app.post("/devices/{device_id}/ack")
async def ack_device_command(
    device_id: str,
    payload: AckRequest,
    token: str = Query(min_length=8),
) -> dict[str, str | int]:
    is_valid = await manager.validate_device(device_id=device_id, token=token)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    await manager.heartbeat(device_id)
    await manager.ack_command(device_id=device_id, command_id=payload.command_id)
    return {
        "device_id": device_id,
        "acked_command_id": payload.command_id,
        "status": "ok",
    }
