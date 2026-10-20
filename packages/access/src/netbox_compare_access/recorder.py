"""Execution log interface. Implemented by the caller (the plugin)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from netbox_compare_access.model import DeviceTarget


@dataclass(frozen=True)
class ExecutionInfo:
    started_at: datetime
    finished_at: datetime
    success: bool
    error: str | None = None


class ExecutionRecorder(Protocol):
    def record(
        self, device: DeviceTarget, command: str, output: str | None, info: ExecutionInfo
    ) -> None: ...
