"""Turn NAPALM getter output into the canonical model.

All unit/format conversions live here so consumers can use plain equality.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from netbox_compare_access.model import DeviceFacts, Interface, IPAddress, State


def from_napalm(
    facts: dict[str, Any], interfaces: dict[str, Any], interfaces_ip: dict[str, Any]
) -> State:
    """Normalize the output of NAPALM's get_facts / get_interfaces / get_interfaces_ip."""
    device_facts = DeviceFacts(
        hostname=_str(facts.get("hostname")),
        vendor=_str(facts.get("vendor")),
        model=_str(facts.get("model")),
        serial_number=_serial(facts.get("serial_number")),
        os_version=_str(facts.get("os_version")),
    )

    ifaces = {
        name: Interface(
            name=name,
            enabled=attrs.get("is_enabled"),
            description=_unquote(attrs.get("description") or ""),
            mtu=_positive_int(attrs.get("mtu")),
            speed_mbps=_positive_float(attrs.get("speed")),
            mac_address=_mac(attrs.get("mac_address")),
        )
        for name, attrs in interfaces.items()
    }

    ips = {
        IPAddress(
            interface=iface_name,
            address=str(ipaddress.ip_address(addr)),
            prefix_length=int(details["prefix_length"]),
        )
        for iface_name, families in interfaces_ip.items()
        for family in ("ipv4", "ipv6")
        for addr, details in (families.get(family) or {}).items()
    }

    return State(facts=device_facts, interfaces=ifaces, ip_addresses=frozenset(ips))


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _serial(value: Any) -> str | None:
    # huawei_vrp returns a list (one ESN per stack member), empty when it can't parse it.
    if isinstance(value, list | tuple):
        return ",".join(v for v in (_str(x) for x in value) if v) or None
    return _str(value)


def _unquote(text: str) -> str:
    # huawei_vrp returns descriptions containing spaces wrapped in double quotes.
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1]
    return text


def _positive_int(value: Any) -> int | None:
    # NAPALM uses -1 (and some drivers 0) for "unknown".
    if value is None or int(value) <= 0:
        return None
    return int(value)


def _positive_float(value: Any) -> float | None:
    if value is None or float(value) <= 0:
        return None
    return float(value)


def _mac(value: Any) -> str | None:
    if not value:
        return None
    hex_digits = "".join(c for c in str(value).lower() if c in "0123456789abcdef")
    if len(hex_digits) != 12:
        return str(value).lower()
    return ":".join(hex_digits[i : i + 2] for i in range(0, 12, 2))
