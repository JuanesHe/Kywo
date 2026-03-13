import os

from fastapi import FastAPI, Header, HTTPException, Query

from .device_manager import DeviceManager
from .models import (
    AckRequest,
    DeviceRecord,
    DeviceRegistrationRequest,
    PendingCommandsResponse,
    QueueCommandRequest,
)

app = FastAPI(title="ESP32 Command Router", version="0.1.0")
manager = DeviceManager(max_queue_size=300)
admin_api_key = os.getenv("ADMIN_API_KEY", "change-me")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/devices/register", response_model=DeviceRecord)
async def register_device(payload: DeviceRegistrationRequest) -> DeviceRecord:
    return await manager.register_device(
        device_id=payload.device_id,
        device_token=payload.device_token,
        firmware_version=payload.firmware_version,
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
