from datetime import datetime
from pydantic import BaseModel, Field


class DeviceRegistrationRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=64)
    device_token: str = Field(min_length=8, max_length=128)
    firmware_version: str | None = None
    wifi_channel: int | None = None


class DeviceRecord(BaseModel):
    device_id: str
    device_token: str
    firmware_version: str | None = None
    last_seen: datetime
    is_master: bool = False
    wifi_channel: int | None = None


class QueueCommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=256)


class CommandMessage(BaseModel):
    command_id: int
    command: str
    created_at: datetime


class PendingCommandsResponse(BaseModel):
    device_id: str
    commands: list[CommandMessage]


class AckRequest(BaseModel):
    command_id: int = Field(ge=1)
