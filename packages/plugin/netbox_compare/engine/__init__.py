"""The comparison business rule: NetBox state vs. device state -> divergences.

Django-free. The device side comes from ``netbox_compare_access`` (canonical model); the
NetBox side is built by ``netbox_state`` from data shaped like NetBox's REST API output.
"""

from .compare import run
from .diff import Diff, Divergence, Kind, Severity
from .policy import Policy

__all__ = ["Diff", "Divergence", "Kind", "Policy", "Severity", "run"]
