"""Compare documented state (NetBox) with observed state (device)."""

from __future__ import annotations

from dataclasses import asdict

from netbox_compare_access.model import IPAddress, State

from .diff import Diff, Divergence, Kind
from .policy import Policy


def run(documented: State, observed: State, policy: Policy | None = None) -> Diff:
    """Return only the differences between ``documented`` and ``observed``.

    A field the device could not report (``None`` on the observed side) is unknown and is
    not compared; a field NetBox leaves empty is still reported unless the policy skips it.
    """
    policy = policy or Policy()
    found: list[Divergence] = []

    def add(kind: Kind, object_type: str, key: str, field, expected, actual) -> None:
        found.append(
            Divergence(
                kind=kind,
                object_type=object_type,
                key=key,
                field=field,
                expected=expected,
                actual=actual,
                severity=policy.severity(object_type, field, kind),
            )
        )

    # --- facts ---
    for name in policy.fact_fields:
        expected = getattr(documented.facts, name)
        actual = getattr(observed.facts, name)
        if policy.skip_undocumented and expected is None:
            continue
        if actual is None:
            continue  # the device could not report it: unknown, not a divergence
        if expected != actual:
            add(Kind.MISMATCH, "facts", "device", name, expected, actual)

    # --- interfaces ---
    doc_ifaces = {
        n: i for n, i in documented.interfaces.items() if not policy.is_ignored_interface(n)
    }
    obs_ifaces = {
        n: i for n, i in observed.interfaces.items() if not policy.is_ignored_interface(n)
    }

    for name in sorted(doc_ifaces.keys() - obs_ifaces.keys()):
        add(Kind.MISSING_ON_DEVICE, "interface", name, None, asdict(doc_ifaces[name]), None)
    for name in sorted(obs_ifaces.keys() - doc_ifaces.keys()):
        add(Kind.MISSING_IN_NETBOX, "interface", name, None, None, asdict(obs_ifaces[name]))
    for name in sorted(doc_ifaces.keys() & obs_ifaces.keys()):
        for field in policy.interface_fields:
            expected = getattr(doc_ifaces[name], field)
            actual = getattr(obs_ifaces[name], field)
            if policy.skip_undocumented and expected is None:
                continue
            if actual is None:
                continue  # the device could not report it: unknown, not a divergence
            if expected != actual:
                add(Kind.MISMATCH, "interface", name, field, expected, actual)

    # --- IP addresses ---
    # The atomic unit is (interface, address, prefix_length): the same address with a
    # different prefix length is reported as missing on both sides, not as a mismatch.
    if policy.compare_ip_addresses:
        doc_ips = {
            ip for ip in documented.ip_addresses if not policy.is_ignored_interface(ip.interface)
        }
        obs_ips = {
            ip for ip in observed.ip_addresses if not policy.is_ignored_interface(ip.interface)
        }
        for ip in sorted(doc_ips - obs_ips, key=_ip_sort_key):
            add(Kind.MISSING_ON_DEVICE, "ip_address", _ip_key(ip), None, _ip_dict(ip), None)
        for ip in sorted(obs_ips - doc_ips, key=_ip_sort_key):
            add(Kind.MISSING_IN_NETBOX, "ip_address", _ip_key(ip), None, None, _ip_dict(ip))

    return Diff(divergences=tuple(found))


def _ip_key(ip: IPAddress) -> str:
    return f"{ip.interface} {ip.cidr}"


def _ip_dict(ip: IPAddress) -> dict:
    return {**asdict(ip), "family": ip.family}


def _ip_sort_key(ip: IPAddress) -> tuple:
    return (ip.interface, ip.family, ip.address, ip.prefix_length)
