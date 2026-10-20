"""Collect a device's observed state through NAPALM."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from napalm import get_network_driver

from netbox_compare_access import normalize, vrp
from netbox_compare_access.credentials import CredentialProvider
from netbox_compare_access.model import DeviceTarget, State
from netbox_compare_access.recorder import ExecutionInfo, ExecutionRecorder

# NetBox platform name or slug, normalized by _platform_key() -> NAPALM driver name.
PLATFORM_DRIVERS: dict[str, str] = {
    "junos": "junos",
    "juniper-junos": "junos",
    "vrp": "huawei_vrp",
    "huawei-vrp": "huawei_vrp",
}

GETTERS = ("get_facts", "get_interfaces", "get_interfaces_ip")


class UnsupportedPlatform(ValueError):
    pass


def _platform_key(platform: str) -> str:
    return "-".join(platform.strip().lower().replace("_", " ").split())


def driver_name(platform: str) -> str:
    try:
        return PLATFORM_DRIVERS[_platform_key(platform)]
    except KeyError:
        raise UnsupportedPlatform(
            f"no NAPALM driver for platform {platform!r} "
            f"(known: {', '.join(sorted(PLATFORM_DRIVERS))})"
        ) from None


@contextmanager
def open_device(provider: CredentialProvider, device: DeviceTarget) -> Iterator[Any]:
    """Open a NAPALM connection; credentials never leave this function."""
    creds = provider.get(device)
    driver = get_network_driver(driver_name(device.platform))
    conn = driver(
        hostname=device.host,
        username=creds.username,
        password=creds.password,
        optional_args=dict(creds.optional_args),
    )
    conn.open()
    try:
        yield conn
    finally:
        conn.close()


def _timed(recorder, device, command, call, keep_output=False):
    """Run ``call()``, report it to ``recorder`` (if any) and return its result."""
    started = datetime.now(UTC)
    try:
        result = call()
    except Exception as exc:
        if recorder:
            recorder.record(
                device,
                command,
                None,
                ExecutionInfo(started, datetime.now(UTC), False, repr(exc)),
            )
        raise
    if recorder:
        recorder.record(
            device,
            command,
            result if keep_output else None,
            ExecutionInfo(started, datetime.now(UTC), True),
        )
    return result


def raw_from_device(
    provider: CredentialProvider,
    device: DeviceTarget,
    recorder: ExecutionRecorder | None = None,
) -> dict[str, Any]:
    """Return the raw NAPALM getter output, keyed by getter name.

    On Huawei VRP, ``get_interfaces`` is corrected with the administrative state read from
    ``display interface brief`` (see ``vrp``); that command is recorded like any other.
    """
    raw: dict[str, Any] = {}
    with open_device(provider, device) as conn:
        for getter in GETTERS:
            raw[getter] = _timed(recorder, device, f"napalm:{getter}", getattr(conn, getter))
        if driver_name(device.platform) == "huawei_vrp":
            command = vrp.ADMIN_STATE_COMMAND
            try:
                brief = _timed(
                    recorder, device, command, lambda: conn.cli([command])[command], True
                )
            except Exception:
                brief = None  # recorded as failed; enabled becomes unknown
            raw["get_interfaces"] = vrp.apply_admin_state(raw["get_interfaces"], brief)
    return raw


def state_from_raw(raw: dict[str, Any]) -> State:
    return normalize.from_napalm(raw["get_facts"], raw["get_interfaces"], raw["get_interfaces_ip"])


def from_device(
    provider: CredentialProvider,
    device: DeviceTarget,
    recorder: ExecutionRecorder | None = None,
) -> State:
    return state_from_raw(raw_from_device(provider, device, recorder))
