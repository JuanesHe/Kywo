import os
from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .device_manager import DeviceManager
from .models import (
    DeviceRecord,
    DeviceRegistrationRequest,
    DeviceStatus,
)

app = FastAPI(title="Kywo Prototype Server - Architecture 2", version="1.0.0")

# Mount web UI files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/ui", StaticFiles(directory=static_dir), name="ui")
manager = DeviceManager()
admin_api_key = os.getenv("ADMIN_API_KEY", "super-secret-admin")


@app.on_event("startup")
async def _startup():
    """Initialize server resources."""
    pass


@app.on_event("shutdown")
async def _shutdown():
    """Cleanup server resources."""
    pass


@app.get("/")
async def root():
    return RedirectResponse(url="/ui/index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configuration Management — Sequence Storage
#
# Devices poll for sequence configurations via HTTP and execute locally.
# ESP-NOW handles clock synchronization directly between devices (no server involvement).
#
# Target: <50µs mean drift with 500ms ESP-NOW sync intervals
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# In-memory store for device state machines
# Maps device_id -> dict with 'sequence' (list of states)
# Default: 2-state alternating pattern with all outputs
_arch2_state_machines: dict[str, dict] = defaultdict(lambda: {
    "sequence": [
        {"digital_out1": True,  "digital_out2": False, "digital_out3": False, "pwm_out": 128, "duration_ms": 1000},
        {"digital_out1": False, "digital_out2": True,  "digital_out3": True,  "pwm_out": 255, "duration_ms": 1000}
    ]
})

@app.get("/devices/{device_id}/config")
async def get_device_config(device_id: str, x_api_key: str = Header(default="")):
    # ESP32 polls this endpoint over HTTP (TCP) to download its state machine
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
        
    # Auto-register the device if it survived a server RAM restart
    if device_id not in manager._devices:
        await manager.register_device(
            device_id=device_id,
            device_token="auto-token",
            firmware_version="2.0-AutoRecovery",
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

@app.post("/devices/{device_id}/set_master")
async def set_device_master(device_id: str, x_api_key: str = Header(default="")):
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
    """Fixed configuration: 3 digital outputs + 1 PWM output."""
    digital_out1: bool
    digital_out2: bool
    digital_out3: bool
    pwm_out: int = Field(ge=0, le=255, description="PWM duty cycle (0-255)")
    duration_ms: int = Field(gt=0, description="State duration in milliseconds")

class StateMachineRequest(BaseModel):
    sequence: list[StateNode]

@app.post("/devices/{device_id}/config")
async def update_device_config(
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Device Management Endpoints
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/devices/register", response_model=DeviceRecord)
async def register_device(payload: DeviceRegistrationRequest) -> DeviceRecord:
    return await manager.register_device(
        device_id=payload.device_id,
        device_token=payload.device_token,
        firmware_version=payload.firmware_version,
        wifi_channel=payload.wifi_channel,
    )


@app.get("/devices", response_model=list[DeviceStatus])
async def list_devices(x_api_key: str = Header(default="")) -> list[DeviceStatus]:
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    
    from datetime import datetime, timezone
    devices = await manager.list_devices()
    now = datetime.now(timezone.utc)
    
    # Enhance each device with online status
    device_statuses = []
    for device in devices:
        seconds_since_seen = (now - device.last_seen).total_seconds()
        is_online = seconds_since_seen < 5  # 5 second timeout
        
        device_statuses.append(DeviceStatus(
            device_id=device.device_id,
            device_token=device.device_token,
            firmware_version=device.firmware_version,
            last_seen=device.last_seen,
            is_master=device.is_master,
            wifi_channel=device.wifi_channel,
            is_online=is_online,
            seconds_since_seen=seconds_since_seen
        ))
    
    return device_statuses


@app.delete("/devices/{device_id}")
async def delete_device(device_id: str, x_api_key: str = Header(default="")):
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    
    deleted = await manager.delete_device(device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return {"status": "success", "message": f"Device {device_id} removed"}


@app.post("/devices/cleanup")
async def cleanup_stale_devices(x_api_key: str = Header(default="")):
    if x_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    
    removed_count = await manager.cleanup_stale_devices(max_age_seconds=30)
    return {"status": "success", "removed": removed_count}
