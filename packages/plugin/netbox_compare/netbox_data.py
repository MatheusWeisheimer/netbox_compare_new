"""Read a device's documented state from NetBox's database for the comparison engine.

Produces the same shape as NetBox's REST API (the input of
``netbox_compare.engine.netbox_state.from_netbox``), limited to the fields the engine uses.
"""

from __future__ import annotations

from typing import Any

from ipam.models import IPAddress


def build(device) -> dict[str, Any]:
    device_type = device.device_type
    primary_ip = device.primary_ip
    interfaces = list(device.interfaces.select_related("primary_mac_address"))
    ip_addresses = IPAddress.objects.filter(interface__device=device).prefetch_related(
        "assigned_object"
    )

    return {
        "device": {
            "id": device.pk,
            "name": device.name,
            "serial": device.serial,
            "device_type": {
                "model": device_type.model,
                "manufacturer": {"name": device_type.manufacturer.name},
            },
            "platform": (
                {"name": device.platform.name, "slug": device.platform.slug}
                if device.platform
                else None
            ),
            "primary_ip": {"address": str(primary_ip.address)} if primary_ip else None,
        },
        "interfaces": [
            {
                "id": iface.pk,
                "name": iface.name,
                "enabled": iface.enabled,
                "description": iface.description,
                "mtu": iface.mtu,
                "speed": iface.speed,
                "primary_mac_address": (
                    {"mac_address": str(iface.primary_mac_address.mac_address)}
                    if iface.primary_mac_address
                    else None
                ),
            }
            for iface in interfaces
        ],
        "ip_addresses": [
            {
                "address": str(ip.address),
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": ip.assigned_object_id,
                "assigned_object": {"id": ip.assigned_object_id, "name": ip.assigned_object.name},
            }
            for ip in ip_addresses
        ],
    }
