"""Common model that both NetBox data and device data are normalized into.

Conventions (applied by ``normalize``, relied on by ``compare``):
- unknown / undocumented values are ``None`` (never sentinels like ``-1`` or ``""``);
- speeds are in Mbps (float), MTU in bytes (int);
- MAC addresses are lowercase, colon-separated (``aa:bb:cc:dd:ee:ff``).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeviceTarget:
    """Which device to talk to and how. Built by the caller (CLI / plugin)."""

    name: str
    host: str
    platform: str


@dataclass(frozen=True)
class DeviceFacts:
    hostname: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    # Software version string reported by the device (NetBox has no equivalent).
    os_version: str | None = None
    # NetBox platform name, e.g. "VRP" (the device has no equivalent).
    platform: str | None = None


@dataclass(frozen=True)
class Interface:
    name: str
    enabled: bool | None = None
    description: str = ""
    mtu: int | None = None
    speed_mbps: float | None = None
    mac_address: str | None = None


@dataclass(frozen=True)
class IPAddress:
    interface: str
    address: str
    prefix_length: int

    @property
    def family(self) -> str:
        return f"ipv{ipaddress.ip_address(self.address).version}"

    @property
    def cidr(self) -> str:
        return f"{self.address}/{self.prefix_length}"


@dataclass(frozen=True)
class State:
    facts: DeviceFacts = field(default_factory=DeviceFacts)
    interfaces: dict[str, Interface] = field(default_factory=dict)
    ip_addresses: frozenset[IPAddress] = frozenset()
