from dataclasses import dataclass, fields

from django.utils.translation import gettext_lazy as _
from netbox_compare_access import Interface
from utilities.choices import ChoiceSet

from .engine.policy import COMPARABLE_FACT_FIELDS


class RunStatusChoices(ChoiceSet):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    ACTIVE = (PENDING, RUNNING)

    CHOICES = [
        (PENDING, _("Pending"), "cyan"),
        (RUNNING, _("Running"), "blue"),
        (COMPLETED, _("Completed"), "green"),
        (FAILED, _("Failed"), "red"),
    ]


class SeverityChoices(ChoiceSet):
    # Values match netbox_compare.engine.Severity.
    CHOICES = [
        ("info", _("Info"), "blue"),
        ("warning", _("Warning"), "orange"),
        ("critical", _("Critical"), "red"),
    ]


class DivergenceKindChoices(ChoiceSet):
    # Values match netbox_compare.engine.Kind.
    CHOICES = [
        ("mismatch", _("Mismatch"), "orange"),
        ("missing_on_device", _("Missing on device"), "purple"),
        ("missing_in_netbox", _("Missing in NetBox"), "gray"),
    ]


WEEKDAY_CHOICES = [
    (0, _("Monday")),
    (1, _("Tuesday")),
    (2, _("Wednesday")),
    (3, _("Thursday")),
    (4, _("Friday")),
    (5, _("Saturday")),
    (6, _("Sunday")),
]


class DivergenceResolutionChoices(ChoiceSet):
    OPEN = ""
    # The device's state was written into NetBox.
    DOCUMENTED = "documented"
    # Marked as needing a fix on the real device. Only a marker: nothing is sent anywhere.
    FIX_DEVICE = "fix_device"

    CHOICES = [
        (OPEN, _("Open"), "gray"),
        (DOCUMENTED, _("NetBox updated"), "green"),
        (FIX_DEVICE, _("To fix on device"), "purple"),
    ]


# Comparable fields come from the canonical model, so the policy form can't drift from it.
FACT_FIELD_CHOICES = [(name, name) for name in COMPARABLE_FACT_FIELDS]
INTERFACE_FIELD_CHOICES = [(f.name, f.name) for f in fields(Interface) if f.name != "name"]

# Display labels for the policy screen; kept apart from the choices above so relabelling
# doesn't touch migrations. A field added to the model later falls back to its own name.
FIELD_LABELS = {
    "hostname": _("Hostname"),
    "vendor": _("Vendor"),
    "model": _("Model"),
    "serial_number": _("Serial number"),
    "enabled": _("Enabled"),
    "description": _("Description"),
    "mtu": _("MTU"),
    "speed_mbps": _("Speed (Mbps)"),
    "mac_address": _("MAC address"),
}
FIELD_HINTS: dict = {}


@dataclass(frozen=True)
class PolicyRow:
    """One line of the policy screen: something that can diverge, and its severity key."""

    object_type: str
    field: str | None
    label: str
    hint: str = ""

    @property
    def key(self) -> str:
        return f"{self.object_type}.{self.field}" if self.field else self.object_type


def _field_rows(object_type: str, choices: list) -> tuple[PolicyRow, ...]:
    return tuple(
        PolicyRow(object_type, name, FIELD_LABELS.get(name, name), FIELD_HINTS.get(name, ""))
        for name, _label in choices
    )


# Every severity key a comparison can look up: "<object_type>.<field>" for a mismatch,
# "<object_type>" for an object present on one side only.
POLICY_SECTIONS = (
    ("facts", _("Device facts"), _field_rows("facts", FACT_FIELD_CHOICES)),
    (
        "interface",
        _("Interfaces"),
        (
            PolicyRow("interface", None, _("Present on one side only")),
            *_field_rows("interface", INTERFACE_FIELD_CHOICES),
        ),
    ),
    (
        "ip_address",
        _("IP addresses"),
        (PolicyRow("ip_address", None, _("Present on one side only")),),
    ),
)
