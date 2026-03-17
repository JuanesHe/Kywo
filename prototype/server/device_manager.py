from datetime import datetime, timezone
import asyncio

from .models import DeviceRecord


class DeviceManager:
    """Manages device registry and master arbitration for Architecture 2."""
    
    def __init__(self) -> None:
        self._devices: dict[str, DeviceRecord] = {}
        self._lock = asyncio.Lock()

    async def register_device(
        self,
        device_id: str,
        device_token: str,
        firmware_version: str | None = None,
        wifi_channel: int | None = None,
    ) -> DeviceRecord:
        async with self._lock:
            record = DeviceRecord(
                device_id=device_id,
                device_token=device_token,
                firmware_version=firmware_version,
                last_seen=datetime.now(timezone.utc),
                wifi_channel=wifi_channel,
            )
            self._devices[device_id] = record
            return record

    async def heartbeat(self, device_id: str) -> None:
        async with self._lock:
            if device_id in self._devices:
                self._devices[device_id].last_seen = datetime.now(timezone.utc)

    async def validate_device(self, device_id: str, token: str) -> bool:
        async with self._lock:
            device = self._devices.get(device_id)
            return bool(device and device.device_token == token)

    async def list_devices(self) -> list[DeviceRecord]:
        async with self._lock:
            return sorted(self._devices.values(), key=lambda d: d.device_id)

    async def get_device(self, device_id: str) -> DeviceRecord | None:
        async with self._lock:
            return self._devices.get(device_id)

    async def delete_device(self, device_id: str) -> bool:
        """Remove a device from the registry. Returns True if device existed."""
        async with self._lock:
            if device_id in self._devices:
                del self._devices[device_id]
                return True
            return False

    async def cleanup_stale_devices(self, max_age_seconds: int = 30) -> int:
        """Remove devices that haven't been seen in max_age_seconds. Returns count of removed devices."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            stale_ids = [
                device_id for device_id, device in self._devices.items()
                if (now - device.last_seen).total_seconds() > max_age_seconds
            ]
            for device_id in stale_ids:
                del self._devices[device_id]
            return len(stale_ids)

    def is_device_online(self, device: DeviceRecord, timeout_seconds: int = 5) -> bool:
        """Check if a device is considered online based on last_seen timestamp."""
        now = datetime.now(timezone.utc)
        return (now - device.last_seen).total_seconds() < timeout_seconds

    async def arbitrate_master(self) -> None:
        """
        Dynamically assigns the Grandmaster role. 
        1. If a master exists and has heartbeat in last 5s, keep it.
        2. If the master is dead or there is no master, elect the first active device.
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            active_devices = [
                d for d in self._devices.values()
                if (now - d.last_seen).total_seconds() < 5
            ]
            
            if not active_devices:
                return
                
            live_master = next((d for d in active_devices if d.is_master), None)
            
            if live_master:
                # Deflate false masters
                for d in self._devices.values():
                    if d.device_id != live_master.device_id:
                        d.is_master = False
            else:
                # Elect the first active device as the new grandmaster
                active_devices.sort(key=lambda d: d.device_id)
                new_master = active_devices[0]
                for d in self._devices.values():
                    d.is_master = (d.device_id == new_master.device_id)
