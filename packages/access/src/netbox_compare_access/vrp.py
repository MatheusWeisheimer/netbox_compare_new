"""Huawei VRP specifics.

``napalm-huawei-vrp`` sets ``is_enabled`` from the physical state (``UP``/``DOWN``), so a
port that is enabled but has no link looks disabled. The administrative state is only
visible in ``display interface brief`` (PHY column ``*down``), which this module reads.
"""

from __future__ import annotations

import re
from typing import Any

ADMIN_STATE_COMMAND = "display interface brief"

# Abbreviation used by ``display interface brief`` -> name used by ``display interface``.
ABBREVIATIONS = {
    "GE": "GigabitEthernet",
    "XGE": "XGigabitEthernet",
    "Eth": "Ethernet",
}

_PHY = re.compile(r"^(?P<mark>[*^])?(?P<state>up|down)(\(.+\))?$", re.IGNORECASE)
_NAME = re.compile(r"^(?P<prefix>[A-Za-z]+)(?=\d)")


def parse_admin_states(output: str) -> dict[str, bool]:
    """Return ``{interface name as printed: enabled}`` from ``display interface brief``.

    Only the PHY column is read: ``*down`` is administratively down (``False``); every
    other valid state (``up``, ``down``, ``^down``, ``up(s)``, ...) means enabled.
    Lines that are not interface rows (legend, header, blanks) are ignored.
    """
    states: dict[str, bool] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        match = _PHY.match(parts[1])
        if match is None:
            continue
        states[parts[0]] = match["mark"] != "*"
    return states


def _full_name(brief_name: str) -> str:
    match = _NAME.match(brief_name)
    if match and match["prefix"] in ABBREVIATIONS:
        return ABBREVIATIONS[match["prefix"]] + brief_name[match.end() :]
    return brief_name


def apply_admin_state(interfaces: dict[str, Any], brief_output: str | None) -> dict[str, Any]:
    """Copy of NAPALM's ``get_interfaces`` with ``is_enabled`` taken from the admin state.

    An interface missing from the brief output, or no output at all, gets ``None``
    (unknown): the link-state value from the driver is never kept.
    """
    admin: dict[str, bool] = {}
    for name, enabled in parse_admin_states(brief_output or "").items():
        admin[name] = enabled
        admin[_full_name(name)] = enabled
    return {name: {**attrs, "is_enabled": admin.get(name)} for name, attrs in interfaces.items()}
