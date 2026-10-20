"""Write a divergence's device-side state into NetBox: the inverse of ``netbox_data``.

Every write goes through NetBox's models with the user's object permissions, so it is
validated and change-logged like an edit made in the UI.
"""

from __future__ import annotations

import ipaddress
from dataclasses import asdict

from dcim.models import Device, Interface, MACAddress
from django.utils.translation import gettext as _
from ipam.models import IPAddress

from . import netbox_data
from .engine import Kind, netbox_state

# Core fact -> Device field. Vendor, model and platform are foreign keys and the OS
# version has no field, so they can only be flagged.
FACT_FIELDS = {"hostname": "name", "serial_number": "serial"}
INTERFACE_FIELDS = {"enabled", "description", "mtu", "speed_mbps", "mac_address"}


class DocumentationError(Exception):
    pass


def applicable(divergence) -> bool:
    """Whether NetBox can be brought to the device's state for this divergence."""
    if divergence.kind == Kind.MISMATCH:
        if divergence.object_type == "facts":
            return divergence.field in FACT_FIELDS
        if divergence.object_type == "interface":
            return divergence.field in INTERFACE_FIELDS
        return False
    return divergence.object_type in ("interface", "ip_address")


def deletes(divergence) -> bool:
    return divergence.kind == Kind.MISSING_ON_DEVICE and applicable(divergence)


def order(divergence) -> int:
    """Apply order: an interface is created before its IPs and deleted after them."""
    kind, object_type = divergence.kind, divergence.object_type
    if kind == Kind.MISSING_IN_NETBOX:
        return 0 if object_type == "interface" else 2
    if kind == Kind.MISSING_ON_DEVICE:
        return 3 if object_type == "ip_address" else 4
    return 1


def deleted_with(divergence) -> list:
    """The IP addresses NetBox deletes along with an interface this divergence deletes."""
    if not (deletes(divergence) and divergence.object_type == "interface"):
        return []
    return list(
        IPAddress.objects.filter(
            interface__device=divergence.run.device, interface__name=divergence.key
        )
    )


def apply(divergence, user) -> None:
    if not applicable(divergence):
        raise DocumentationError(_("NetBox can't be updated for this divergence"))
    device = divergence.run.device
    if not _still_documented(divergence, device):
        raise DocumentationError(_("NetBox changed since this comparison"))

    kind, object_type = divergence.kind, divergence.object_type
    if object_type == "facts":
        _update_device(device, divergence, user)
    elif object_type == "interface":
        if kind == Kind.MISMATCH:
            _update_interface(device, divergence, user)
        elif kind == Kind.MISSING_IN_NETBOX:
            _create_interface(device, divergence.actual, user)
        else:
            _delete_interface(device, divergence.key, user)
    elif kind == Kind.MISSING_IN_NETBOX:
        _create_ip(device, divergence.actual, user)
    else:
        _delete_ip(device, divergence.expected, user)


def _still_documented(divergence, device) -> bool:
    """Whether NetBox still shows what the comparison saw, as the comparison would read it."""
    state = netbox_state.from_netbox(netbox_data.build(device))
    kind, key = divergence.kind, divergence.key
    if divergence.object_type == "facts":
        return getattr(state.facts, divergence.field) == divergence.expected
    if divergence.object_type == "interface":
        iface = state.interfaces.get(key)
        if kind == Kind.MISMATCH:
            return iface is not None and getattr(iface, divergence.field) == divergence.expected
        if kind == Kind.MISSING_IN_NETBOX:
            return iface is None
        return iface is not None and asdict(iface) == divergence.expected
    ip = divergence.actual if kind == Kind.MISSING_IN_NETBOX else divergence.expected
    present = any(
        (doc.interface, doc.address, doc.prefix_length)
        == (ip["interface"], ip["address"], ip["prefix_length"])
        for doc in state.ip_addresses
    )
    return present == (kind == Kind.MISSING_ON_DEVICE)


def _restricted(model, user, action, **filters):
    obj = model.objects.restrict(user, action).filter(**filters).first()
    if obj is None:
        raise DocumentationError(
            _("You don't have permission to {action} this {model}").format(
                action=action, model=model._meta.verbose_name
            )
        )
    return obj


def _save(obj, user, created=False) -> None:
    obj.full_clean()
    obj.save()
    # Constraints of an "add" permission can only be checked once the object exists; the
    # caller's transaction rolls it back.
    if created and not type(obj).objects.restrict(user, "add").filter(pk=obj.pk).exists():
        raise DocumentationError(
            _("You don't have permission to add this {model}").format(
                model=type(obj)._meta.verbose_name
            )
        )


def _update_device(device, divergence, user) -> None:
    device = _restricted(Device, user, "change", pk=device.pk)
    device.snapshot()
    value = divergence.actual or ""
    if divergence.field == "hostname" and not value:
        raise DocumentationError(_("The device reported no hostname"))
    setattr(device, FACT_FIELDS[divergence.field], value)
    _save(device, user)


def _interface_values(observed: dict) -> dict:
    speed = observed.get("speed_mbps")
    return {
        "enabled": observed["enabled"] if observed.get("enabled") is not None else True,
        "description": observed.get("description") or "",
        "mtu": observed.get("mtu"),
        "speed": round(speed * 1000) if speed else None,
    }


def _update_interface(device, divergence, user) -> None:
    iface = _restricted(Interface, user, "change", device=device, name=divergence.key)
    iface.snapshot()
    field, value = divergence.field, divergence.actual
    if field == "mac_address":
        _set_mac(iface, value, user)
    elif field == "enabled" and value is None:
        raise DocumentationError(_("The device reported no enabled state"))
    elif field == "speed_mbps":
        iface.speed = _interface_values({"speed_mbps": value})["speed"]
    elif field == "description":
        iface.description = value or ""
    else:
        setattr(iface, field, value)
    _save(iface, user)


def _set_mac(iface, mac: str | None, user) -> None:
    """Point the interface's primary MAC at ``mac``; the caller saves the interface."""
    if mac is None:
        iface.primary_mac_address = None
        return
    if iface.primary_mac_address_id:
        record = _restricted(MACAddress, user, "change", pk=iface.primary_mac_address_id)
        record.snapshot()
        record.mac_address = mac
        _save(record, user)
    else:
        record = MACAddress(mac_address=mac, assigned_object=iface)
        _save(record, user, created=True)
        iface.primary_mac_address = record


def _create_interface(device, observed: dict, user) -> None:
    iface = Interface(device=device, name=observed["name"], type="other")
    for name, value in _interface_values(observed).items():
        setattr(iface, name, value)
    _save(iface, user, created=True)
    if observed.get("mac_address"):
        iface.snapshot()
        _set_mac(iface, observed["mac_address"], user)
        _save(iface, user)


def _delete_interface(device, name: str, user) -> None:
    iface = _restricted(Interface, user, "delete", device=device, name=name)
    ips = IPAddress.objects.filter(interface=iface)
    if ips.count() != ips.restrict(user, "delete").count():
        raise DocumentationError(
            _("You don't have permission to delete the IP addresses of this interface")
        )
    iface.snapshot()
    iface.delete()


def _create_ip(device, observed: dict, user) -> None:
    iface = Interface.objects.filter(device=device, name=observed["interface"]).first()
    if iface is None:
        raise DocumentationError(
            _("Interface {name} isn't in NetBox").format(name=observed["interface"])
        )
    ip = IPAddress(
        address=f"{observed['address']}/{observed['prefix_length']}", assigned_object=iface
    )
    _save(ip, user, created=True)


def _delete_ip(device, documented: dict, user) -> None:
    wanted = (documented["address"], documented["prefix_length"])
    for ip in IPAddress.objects.restrict(user, "delete").filter(
        interface__device=device, interface__name=documented["interface"]
    ):
        iface_net = ipaddress.ip_interface(str(ip.address))
        if (str(iface_net.ip), iface_net.network.prefixlen) == wanted:
            ip.snapshot()
            ip.delete()
            return
    raise DocumentationError(_("You don't have permission to delete this IP address"))
