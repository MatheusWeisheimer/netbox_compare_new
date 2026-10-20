"""Device credentials interface. Implemented by the caller (the plugin)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from netbox_compare_access.model import DeviceTarget


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str = field(repr=False)
    # Extra NAPALM optional_args (port, transport, secret, ...).
    optional_args: dict[str, Any] = field(default_factory=dict, repr=False)


class CredentialProvider(Protocol):
    def get(self, device: DeviceTarget) -> Credentials: ...
