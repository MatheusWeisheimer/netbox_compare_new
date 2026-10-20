from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import ChangeLoggedModel
from netbox.models.features import JobsMixin
from utilities.querysets import RestrictedQuerySet

from .choices import (
    FACT_FIELD_CHOICES,
    INTERFACE_FIELD_CHOICES,
    POLICY_SECTIONS,
    WEEKDAY_CHOICES,
    DivergenceKindChoices,
    DivergenceResolutionChoices,
    PolicyRow,
    RunStatusChoices,
    SeverityChoices,
)
from .engine import Kind, Policy
from .engine.policy import (
    DEFAULT_FACT_FIELDS,
    DEFAULT_INTERFACE_FIELDS,
    DEFAULT_SEVERITIES,
)

__all__ = (
    "CommandLog",
    "ComparisonPolicy",
    "ComparisonRun",
    "ComparisonSchedule",
    "Divergence",
)


def _default_fact_fields():
    return list(DEFAULT_FACT_FIELDS)


def _default_interface_fields():
    return list(DEFAULT_INTERFACE_FIELDS)


def _default_severities():
    return {key: str(value) for key, value in DEFAULT_SEVERITIES.items()}


class ComparisonPolicy(ChangeLoggedModel):
    """The single, global comparison policy: which information is relevant for this NetBox."""

    GLOBAL_PK = 1

    fact_fields = ArrayField(
        models.CharField(max_length=50, choices=FACT_FIELD_CHOICES),
        default=_default_fact_fields,
        blank=True,
        verbose_name=_("device facts"),
    )
    interface_fields = ArrayField(
        models.CharField(max_length=50, choices=INTERFACE_FIELD_CHOICES),
        default=_default_interface_fields,
        blank=True,
        verbose_name=_("interface fields"),
    )
    compare_ip_addresses = models.BooleanField(default=True)
    ignore_interfaces = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
        help_text=_("Glob patterns (case-sensitive) of interface names to leave out, e.g. NULL*"),
    )
    skip_undocumented = models.BooleanField(
        default=False,
        help_text=_("Don't report a field that is empty in NetBox for that object"),
    )
    default_severity = models.CharField(max_length=20, choices=SeverityChoices, default="warning")
    severities = models.JSONField(
        default=_default_severities,
        blank=True,
        help_text=_(
            'Severity per "object_type.field" or "object_type" '
            "(object types: facts, interface, ip_address)"
        ),
    )

    class Meta:
        verbose_name = _("comparison policy")
        verbose_name_plural = _("comparison policies")

    def __str__(self):
        return str(_("Global comparison policy"))

    def get_absolute_url(self):
        return reverse("plugins:netbox_compare:comparisonpolicy", args=[self.pk])

    @classmethod
    def get_global(cls) -> "ComparisonPolicy":
        policy, _created = cls.objects.get_or_create(pk=cls.GLOBAL_PK)
        return policy

    def to_dict(self) -> dict:
        return {
            "fact_fields": list(self.fact_fields),
            "interface_fields": list(self.interface_fields),
            "compare_ip_addresses": self.compare_ip_addresses,
            "ignore_interfaces": list(self.ignore_interfaces),
            "skip_undocumented": self.skip_undocumented,
            "default_severity": self.default_severity,
            "severities": dict(self.severities or {}),
        }

    def to_core(self) -> Policy:
        return Policy.from_dict(self.to_dict())

    def is_compared(self, row: PolicyRow) -> bool | None:
        """Whether the row is compared; None for rows that are always compared."""
        if row.object_type == "facts":
            return row.field in self.fact_fields
        if row.object_type == "interface" and row.field:
            return row.field in self.interface_fields
        if row.object_type == "ip_address":
            return self.compare_ip_addresses
        return None

    def effective_severity(self, row: PolicyRow, core: Policy | None = None) -> str:
        core = core or self.to_core()
        return str(core.severity(row.object_type, row.field, Kind.MISMATCH))

    def sections(self) -> list[dict]:
        """The policy as the screen shows it: per section, each row with its settings."""
        core = self.to_core()
        return [
            {
                "name": name,
                "title": title,
                "rows": [
                    {
                        "row": row,
                        "compared": self.is_compared(row),
                        "severity": (severity := self.effective_severity(row, core)),
                        "severity_label": dict(SeverityChoices)[severity],
                        "severity_color": SeverityChoices.colors.get(severity),
                    }
                    for row in rows
                ],
            }
            for name, title, rows in POLICY_SECTIONS
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.severities, dict):
            raise ValidationError({"severities": _("Must be a JSON object.")})
        try:
            self.to_core()
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class ComparisonSchedule(JobsMixin, ChangeLoggedModel):
    """Compare a chosen set of devices every week on the given weekdays, at a time of day.

    The recurrence lives in a scheduled NetBox job (see ``jobs.reschedule``); this object only
    holds what to run and when. Times are in NetBox's time zone.
    """

    name = models.CharField(max_length=100, unique=True)
    enabled = models.BooleanField(default=True)
    weekdays = ArrayField(
        models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES),
        help_text=_("Days of the week on which the comparisons run"),
    )
    time_of_day = models.TimeField(help_text=_("In NetBox's time zone"))
    devices = models.ManyToManyField(
        to="dcim.Device", related_name="netbox_compare_schedules", blank=True
    )
    # The comparisons start as this user (the one who last saved the schedule).
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    last_run = models.DateTimeField(null=True, blank=True, editable=False)

    objects = RestrictedQuerySet.as_manager()

    class Meta:
        ordering = ("name",)
        verbose_name = _("comparison schedule")
        verbose_name_plural = _("comparison schedules")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_compare:comparisonschedule", args=[self.pk])

    def clean(self):
        super().clean()
        if not self.weekdays:
            raise ValidationError({"weekdays": _("Choose at least one weekday.")})
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValidationError({"weekdays": _("Weekdays must not repeat.")})

    @property
    def next_run(self):
        """When the next comparison starts (from the scheduled job), or None."""
        job = self.jobs.filter(status="scheduled").order_by("scheduled").first()
        return job.scheduled if job else None

    def get_weekdays_display(self) -> str:
        names = dict(WEEKDAY_CHOICES)
        return ", ".join(str(names[day]) for day in sorted(set(self.weekdays)))

    def delete(self, *args, **kwargs):
        # Cancel the scheduled job explicitly: cascading deletes don't remove its queue entry.
        for job in self.jobs.all():
            job.delete()
        return super().delete(*args, **kwargs)


class ComparisonRun(JobsMixin, models.Model):
    """One comparison of a device against NetBox. Created by the UI, filled by the job."""

    device = models.ForeignKey(
        to="dcim.Device", on_delete=models.CASCADE, related_name="netbox_compare_runs"
    )
    job = models.ForeignKey(
        to="core.Job", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Set when a schedule started this run.
    schedule = models.ForeignKey(
        to="netbox_compare.ComparisonSchedule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    status = models.CharField(
        max_length=20, choices=RunStatusChoices, default=RunStatusChoices.PENDING
    )
    created = models.DateTimeField(auto_now_add=True)
    started = models.DateTimeField(null=True, blank=True)
    finished = models.DateTimeField(null=True, blank=True)
    # The policy as it was when this run compared, so later edits don't change old results.
    policy_snapshot = models.JSONField(null=True, blank=True)
    critical_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    info_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    objects = RestrictedQuerySet.as_manager()

    class Meta:
        ordering = ("-created",)
        verbose_name = _("comparison run")
        verbose_name_plural = _("comparison runs")

    def __str__(self):
        return f"{self.device} #{self.pk}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_compare:comparisonrun", args=[self.pk])

    def get_status_color(self):
        return RunStatusChoices.colors.get(self.status)

    @property
    def is_active(self) -> bool:
        return self.status in RunStatusChoices.ACTIVE

    @property
    def divergence_count(self) -> int:
        return self.critical_count + self.warning_count + self.info_count


class Divergence(models.Model):
    """One difference found by a run (see netbox_compare.engine.Divergence)."""

    run = models.ForeignKey(to=ComparisonRun, on_delete=models.CASCADE, related_name="divergences")
    kind = models.CharField(max_length=30, choices=DivergenceKindChoices)
    object_type = models.CharField(max_length=30)
    key = models.CharField(max_length=300)
    field = models.CharField(max_length=50, blank=True)
    expected = models.JSONField(null=True, blank=True)
    actual = models.JSONField(null=True, blank=True)
    severity = models.CharField(max_length=20, choices=SeverityChoices)
    resolution = models.CharField(
        max_length=20, choices=DivergenceResolutionChoices, blank=True, default=""
    )
    resolved_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = RestrictedQuerySet.as_manager()

    class Meta:
        ordering = ("run", "pk")
        verbose_name = _("divergence")
        verbose_name_plural = _("divergences")

    def __str__(self):
        return f"{self.kind} {self.object_type} {self.key} {self.field}".strip()

    def get_kind_color(self):
        return DivergenceKindChoices.colors.get(self.kind)

    def get_severity_color(self):
        return SeverityChoices.colors.get(self.severity)

    def get_resolution_color(self):
        return DivergenceResolutionChoices.colors.get(self.resolution)


class CommandLog(models.Model):
    """Every command sent to a device (ground rule 4). Never edited or deleted from the UI."""

    device = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="netbox_compare_commands",
    )
    # Kept so the entry stays meaningful if the device is deleted.
    device_name = models.CharField(max_length=200)
    run = models.ForeignKey(
        to=ComparisonRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commands",
    )
    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    command = models.TextField()
    output = models.TextField(blank=True)
    success = models.BooleanField()
    error = models.TextField(blank=True)
    started = models.DateTimeField()
    finished = models.DateTimeField()

    objects = RestrictedQuerySet.as_manager()

    class Meta:
        ordering = ("-started", "-pk")
        verbose_name = _("command log entry")
        verbose_name_plural = _("command log")

    def __str__(self):
        return f"{self.device_name}: {self.command}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_compare:commandlog", args=[self.pk])


PARAMETER_KEYS = {"name", "type", "description", "required", "choices"}


MAX_SUGGESTED_COMMANDS = 50
MAX_COMMAND_LENGTH = 500
