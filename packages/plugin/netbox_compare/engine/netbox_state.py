"""Turn NetBox data into the canonical model (``netbox_compare_access.model``).

Django-free: the input is shaped like NetBox's REST API output (see ``netbox_data.build``).
Unit and format conventions are those of ``netbox_compare_access.normalize``.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from netbox_compare_access.model import DeviceFacts, DeviceTarget, Interface, IPAddress, State


def from_netbox(data: dict[str, Any]) -> State:
    """Normalize NetBox data shaped like its REST API output.

    Expected keys:
      - ``device``: a dcim device object (nested ``device_type``, ``platform``, ...)
      - ``interfaces``: list of dcim interface objects for that device
      - ``ip_addresses``: list of ipam ip-address objects assigned to those interfaces
    """
    device = data["device"]
    device_type = device.get("device_type") or {}
    manufacturer = device_type.get("manufacturer") or {}
    platform = device.get("platform") or {}

    facts = DeviceFacts(
        hostname=_str(device.get("name")),
        vendor=_str(manufacturer.get("name")),
        model=_str(device_type.get("model")),
        serial_number=_str(device.get("serial")),
        platform=_str(platform.get("name")),
    )

    interfaces: dict[str, Interface] = {}
    names_by_id: dict[Any, str] = {}
    for iface in data.get("interfaces", []):
        names_by_id[iface.get("id")] = iface["name"]
        speed_kbps = iface.get("speed")
        interfaces[iface["name"]] = Interface(
            name=iface["name"],
            enabled=iface.get("enabled"),
            description=iface.get("description") or "",
            mtu=_positive_int(iface.get("mtu")),
            speed_mbps=float(speed_kbps) / 1000 if speed_kbps else None,
            mac_address=_mac(_netbox_mac(iface)),
        )

    ips: set[IPAddress] = set()
    for ip in data.get("ip_addresses", []):
        object_type = ip.get("assigned_object_type")
        if object_type not in (None, "dcim.interface"):
            continue
        iface_name = names_by_id.get(ip.get("assigned_object_id"))
        if iface_name is None:
            iface_name = (ip.get("assigned_object") or {}).get("name")
        if iface_name is None:
            continue
        iface_net = ipaddress.ip_interface(str(ip["address"]))
        ips.add(
            IPAddress(
                interface=iface_name,
                address=str(iface_net.ip),
                prefix_length=iface_net.network.prefixlen,
            )
        )

    return State(facts=facts, interfaces=interfaces, ip_addresses=frozenset(ips))


def device_target(data: dict[str, Any], host: str | None = None) -> DeviceTarget:
    """Build a DeviceTarget from NetBox device data.

    ``host`` defaults to the device's primary IP (without prefix length).
    """
    device = data["device"]
    if host is None:
        primary = device.get("primary_ip") or device.get("primary_ip4") or device.get("primary_ip6")
        if not primary:
            raise ValueError(f"device {device.get('name')!r} has no primary IP in NetBox")
        host = str(ipaddress.ip_interface(str(primary["address"])).ip)
    platform = (device.get("platform") or {}).get("name")
    if not platform:
        raise ValueError(f"device {device.get('name')!r} has no platform in NetBox")
    return DeviceTarget(name=device["name"], host=host, platform=platform)


def _netbox_mac(iface: dict[str, Any]) -> Any:
    # NetBox >= 4.2 moved MACs to their own model; older versions have a plain field.
    primary = iface.get("primary_mac_address")
    if isinstance(primary, dict):
        return primary.get("mac_address")
    return iface.get("mac_address")


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: Any) -> int | None:
    # NAPALM uses -1 (and some drivers 0) for "unknown".
    if value is None or int(value) <= 0:
        return None
    return int(value)


def _mac(value: Any) -> str | None:
    if not value:
        return None
    hex_digits = "".join(c for c in str(value).lower() if c in "0123456789abcdef")
    if len(hex_digits) != 12:
        return str(value).lower()
    return ":".join(hex_digits[i : i + 2] for i in range(0, 12, 2))
