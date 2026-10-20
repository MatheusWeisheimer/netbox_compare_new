"""What to compare and how serious each difference is.

The defaults compare everything NetBox can hold. Which of it is relevant for a
given NetBox instance is declared by the caller (the plugin) and handed
to the comparison, e.g. with ``Policy.from_dict`` on a parsed TOML/JSON policy file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from fnmatch import fnmatchcase
from typing import Any

from netbox_compare_access.model import Interface

from .diff import Kind, Severity

# os_version and platform are not comparable: the platform decides how the device is reached,
# so a wrong one shows up as a failed connection, not as a divergence; and NetBox's platform
# name ("VRP") never equals the device's version string ("V800R021C10SPC100").
COMPARABLE_FACT_FIELDS = ("hostname", "vendor", "model", "serial_number")
DEFAULT_FACT_FIELDS = COMPARABLE_FACT_FIELDS
DEFAULT_INTERFACE_FIELDS = ("enabled", "description", "mtu", "speed_mbps", "mac_address")

DEFAULT_SEVERITIES: dict[str, Severity] = {
    "facts.serial_number": Severity.CRITICAL,
    "facts.hostname": Severity.CRITICAL,
    "interface.enabled": Severity.CRITICAL,
    "interface.description": Severity.INFO,
    "ip_address": Severity.CRITICAL,
}


@dataclass(frozen=True)
class Policy:
    fact_fields: tuple[str, ...] = DEFAULT_FACT_FIELDS
    interface_fields: tuple[str, ...] = DEFAULT_INTERFACE_FIELDS
    compare_ip_addresses: bool = True
    # fnmatch patterns (case-sensitive) of interface names to leave out entirely.
    ignore_interfaces: tuple[str, ...] = ()
    # Treat a field NetBox leaves empty (None) as "don't care" instead of a mismatch.
    skip_undocumented: bool = False
    # Keys: "<object_type>.<field>" or "<object_type>"; most specific wins.
    severities: dict[str, Severity] = field(default_factory=lambda: dict(DEFAULT_SEVERITIES))
    default_severity: Severity = Severity.WARNING

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Policy:
        """Build a policy from plain data; omitted keys keep the defaults.

        ``severities`` entries are merged over the default severities.
        Raises ValueError on unknown keys, fields or severity names.
        """
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown policy keys: {', '.join(sorted(unknown))}")

        kwargs: dict[str, Any] = {}
        for key, valid in (
            ("fact_fields", set(COMPARABLE_FACT_FIELDS)),
            ("interface_fields", {f.name for f in fields(Interface)} - {"name"}),
        ):
            if key in data:
                bad = set(data[key]) - valid
                if bad:
                    raise ValueError(f"unknown {key}: {', '.join(sorted(bad))}")
                kwargs[key] = tuple(data[key])
        if "ignore_interfaces" in data:
            kwargs["ignore_interfaces"] = tuple(data["ignore_interfaces"])
        for key in ("compare_ip_addresses", "skip_undocumented"):
            if key in data:
                kwargs[key] = bool(data[key])
        if "default_severity" in data:
            kwargs["default_severity"] = Severity(data["default_severity"])
        if "severities" in data:
            kwargs["severities"] = {
                **DEFAULT_SEVERITIES,
                **{k: Severity(v) for k, v in data["severities"].items()},
            }
        return cls(**kwargs)

    def is_ignored_interface(self, name: str) -> bool:
        return any(fnmatchcase(name, pattern) for pattern in self.ignore_interfaces)

    def severity(self, object_type: str, field_name: str | None, kind: Kind) -> Severity:
        for key in (f"{object_type}.{field_name}", object_type):
            if key in self.severities:
                return self.severities[key]
        return self.default_severity
