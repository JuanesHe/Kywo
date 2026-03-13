from collections import deque
from datetime import datetime, timezone
import asyncio

from .models import CommandMessage, DeviceRecord


class DeviceManager:
    def __init__(self, max_queue_size: int = 200) -> None:
        self._devices: dict[str, DeviceRecord] = {}
        self._queues: dict[str, deque[CommandMessage]] = {}
        self._next_command_id = 1
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    async def register_device(
        self,
        device_id: str,
        device_token: str,
        firmware_version: str | None = None,
    ) -> DeviceRecord:
        async with self._lock:
            record = DeviceRecord(
                device_id=device_id,
                device_token=device_token,
                firmware_version=firmware_version,
                last_seen=datetime.now(timezone.utc),
            )
            self._devices[device_id] = record
            self._queues.setdefault(device_id, deque())
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

    async def enqueue_command(self, device_id: str, command: str) -> CommandMessage:
        async with self._lock:
            if device_id not in self._devices:
                raise KeyError(f"Unknown device '{device_id}'")

            message = CommandMessage(
                command_id=self._next_command_id,
                command=command,
                created_at=datetime.now(timezone.utc),
            )
            self._next_command_id += 1

            queue = self._queues.setdefault(device_id, deque())
            queue.append(message)
            while len(queue) > self._max_queue_size:
                queue.popleft()
            return message

    async def fetch_pending_commands(
        self,
        device_id: str,
        min_command_id: int = 0,
        limit: int = 20,
    ) -> list[CommandMessage]:
        async with self._lock:
            queue = self._queues.get(device_id, deque())
            pending = [c for c in queue if c.command_id > min_command_id]
            return pending[:limit]

    async def ack_command(self, device_id: str, command_id: int) -> None:
        async with self._lock:
            queue = self._queues.get(device_id)
            if not queue:
                return

            while queue and queue[0].command_id <= command_id:
                queue.popleft()
