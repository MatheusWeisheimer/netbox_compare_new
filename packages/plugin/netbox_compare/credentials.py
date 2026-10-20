"""Where the plugin gets device credentials: the credential connector.

A connector answers two questions about a NetBox device, identified by its **name**: does the
credential source have credentials for it (``has_credentials``), and what are they (``get``,
which makes a connector a ``netbox_compare_access.CredentialProvider``). Device work only
starts for devices that have credentials.

Credentials are only read inside background jobs and are never stored in the database,
logged or shown in the UI. Today the source is a local TOML file (development); a vault
would be another connector returned by ``get_connector``.

File format:

    [devices."<NetBox device name>"]
    username = "..."
    password = "..."
    port = 22            # any other key is passed to NAPALM as optional_args
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Protocol

from django.utils.translation import gettext_lazy as _
from netbox.plugins import get_plugin_config
from netbox_compare_access import Credentials, DeviceTarget

RESERVED = ("host", "username", "password")


class CredentialsNotConfigured(LookupError):
    pass


class NoCredentials(LookupError):
    """The credential source has no credentials for the device."""

    def __init__(self, device_name: str = ""):
        super().__init__(device_name)
        self.device_name = device_name

    def __str__(self):
        return str(_("No credentials are configured for this device."))


class CredentialConnector(Protocol):
    def has_credentials(self, device_name: str) -> bool: ...

    def get(self, device: DeviceTarget) -> Credentials: ...


class DevFileCredentialConnector:
    def __init__(self, path: str | Path):
        with open(path, "rb") as f:
            self._devices = tomllib.load(f).get("devices", {})

    @classmethod
    def from_settings(cls) -> DevFileCredentialConnector:
        path = get_plugin_config("netbox_compare", "credentials_file")
        if not path:
            raise CredentialsNotConfigured(
                "PLUGINS_CONFIG['netbox_compare']['credentials_file'] is not set"
            )
        return cls(path)

    def has_credentials(self, device_name: str) -> bool:
        return device_name in self._devices

    def get(self, device: DeviceTarget) -> Credentials:
        entry = self._devices.get(device.name)
        if not entry:
            raise NoCredentials(device.name)
        extra = {k: v for k, v in entry.items() if k not in RESERVED}
        return Credentials(entry["username"], entry["password"], extra)


def get_connector() -> CredentialConnector:
    """The configured credential connector (raises ``CredentialsNotConfigured``)."""
    return DevFileCredentialConnector.from_settings()


def credentialed_devices(queryset):
    """``queryset`` of devices narrowed to those the credential source knows (by name)."""
    try:
        connector = get_connector()
    except (CredentialsNotConfigured, OSError):
        return queryset.none()
    pks = [pk for pk, name in queryset.values_list("pk", "name") if connector.has_credentials(name)]
    return queryset.filter(pk__in=pks)


def has_credentials(device) -> bool:
    """Whether ``device`` can be accessed; False (not an error) when no source is configured."""
    try:
        return get_connector().has_credentials(device.name)
    except (CredentialsNotConfigured, OSError):
        return False
