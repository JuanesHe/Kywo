from datetime import datetime
from pydantic import BaseModel, Field


class DeviceRegistrationRequest(BaseModel):
    """Request to register a new device."""
    device_id: str = Field(min_length=3, max_length=64)
    device_token: str = Field(min_length=8, max_length=128)
    firmware_version: str | None = None
    wifi_channel: int | None = None


class DeviceRecord(BaseModel):
    """Device registration and status record."""
    device_id: str
    device_token: str
    firmware_version: str | None = None
    last_seen: datetime
    is_master: bool = False
    wifi_channel: int | None = None


class DeviceStatus(BaseModel):
    """Enhanced device record with online status."""
    device_id: str
    device_token: str
    firmware_version: str | None = None
    last_seen: datetime
    is_master: bool = False
    wifi_channel: int | None = None
    is_online: bool
    seconds_since_seen: float
