"""Result of a comparison: a flat list of divergences."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    # Object exists on both sides but a field differs.
    MISMATCH = "mismatch"
    # Documented in NetBox, not found on the device.
    MISSING_ON_DEVICE = "missing_on_device"
    # Found on the device, not documented in NetBox.
    MISSING_IN_NETBOX = "missing_in_netbox"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Divergence:
    kind: Kind
    object_type: str  # "facts" | "interface" | "ip_address"
    key: str  # object identity, e.g. interface name or "GE0/0/1 10.0.0.1/24"
    field: str | None  # set for MISMATCH only
    expected: Any  # NetBox side
    actual: Any  # device side
    severity: Severity = Severity.WARNING

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "object_type": self.object_type,
            "key": self.key,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "severity": str(self.severity),
        }


@dataclass(frozen=True)
class Diff:
    divergences: tuple[Divergence, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return bool(self.divergences)

    def __len__(self) -> int:
        return len(self.divergences)

    def __iter__(self):
        return iter(self.divergences)

    def to_dict(self) -> dict[str, Any]:
        return {"divergences": [d.to_dict() for d in self.divergences]}
