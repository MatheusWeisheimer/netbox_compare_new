import django_tables2 as tables
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from netbox.tables import BaseTable, NetBoxTable, columns

from . import documentation
from .choices import DivergenceResolutionChoices
from .models import CommandLog, ComparisonRun, ComparisonSchedule, Divergence


class ComparisonRunTable(NetBoxTable):
    id = tables.Column(linkify=True, verbose_name=_("ID"))
    device = tables.Column(linkify=True)
    status = columns.ChoiceFieldColumn()
    critical_count = tables.Column(verbose_name=_("Critical"))
    warning_count = tables.Column(verbose_name=_("Warning"))
    info_count = tables.Column(verbose_name=_("Info"))
    user = tables.Column(verbose_name=_("Started by"))
    schedule = tables.Column(linkify=True)
    created = columns.DateTimeColumn()
    finished = columns.DateTimeColumn()
    # Runs are produced by jobs: no edit/delete actions.
    actions = columns.ActionsColumn(actions=())

    class Meta(NetBoxTable.Meta):
        model = ComparisonRun
        fields = (
            "pk",
            "id",
            "device",
            "status",
            "critical_count",
            "warning_count",
            "info_count",
            "user",
            "schedule",
            "created",
            "started",
            "finished",
            "error",
        )
        default_columns = (
            "id",
            "device",
            "status",
            "critical_count",
            "warning_count",
            "info_count",
            "user",
            "created",
        )


class DivergenceTable(BaseTable):
    severity = columns.ChoiceFieldColumn()
    kind = columns.ChoiceFieldColumn()
    object_type = tables.Column(verbose_name=_("Object"))
    key = tables.Column()
    field = tables.Column()
    expected = tables.Column(verbose_name=_("NetBox"))
    actual = tables.Column(verbose_name=_("Device"))
    resolution = tables.Column(verbose_name=_("Resolution"), empty_values=())
    to_netbox = tables.Column(
        verbose_name=_("Update NetBox"), empty_values=(), attrs={"td": {"class": "text-center"}}
    )
    to_device = tables.Column(
        verbose_name=_("Fix device"), empty_values=(), attrs={"td": {"class": "text-center"}}
    )

    class Meta(BaseTable.Meta):
        model = Divergence
        fields = (
            "severity", "kind", "object_type", "key", "field", "expected", "actual",
            "resolution", "to_netbox", "to_device",
        )  # fmt: skip
        default_columns = fields
        orderable = False

    def render_resolution(self, record):
        if not record.resolution:
            return "—"
        badge = format_html(
            '<span class="badge text-bg-{}">{}</span>',
            record.get_resolution_color(),
            record.get_resolution_display(),
        )
        if record.resolved_by:
            return format_html(
                '{} <span class="text-muted small">{}</span>', badge, record.resolved_by
            )
        return badge

    def render_to_netbox(self, record):
        if record.resolution == DivergenceResolutionChoices.DOCUMENTED:
            return format_html('<i class="mdi mdi-check-bold text-success"></i>')
        if not documentation.applicable(record):
            return format_html(
                '<span class="text-muted" title="{}">—</span>',
                _("NetBox has no field for this; it can only be marked to fix on the device"),
            )
        return format_html(
            '<input type="checkbox" class="form-check-input" name="netbox" value="{}" '
            'data-resolution-row="{}">',
            record.pk,
            record.pk,
        )

    def render_to_device(self, record):
        if record.resolution == DivergenceResolutionChoices.DOCUMENTED:
            return ""
        marked = record.resolution == DivergenceResolutionChoices.FIX_DEVICE
        return format_html(
            '<input type="checkbox" class="form-check-input" name="fix_device" value="{}" '
            'data-resolution-row="{}"{}>',
            record.pk,
            record.pk,
            mark_safe(" checked") if marked else "",
        )


class CommandLogTable(NetBoxTable):
    id = tables.Column(linkify=True, verbose_name=_("ID"))
    device_name = tables.Column(verbose_name=_("Device"))
    run = tables.Column(linkify=True)
    command = tables.Column(linkify=lambda record: record.get_absolute_url())
    success = columns.BooleanColumn()
    user = tables.Column()
    started = columns.DateTimeColumn()
    finished = columns.DateTimeColumn()
    actions = columns.ActionsColumn(actions=())

    class Meta(NetBoxTable.Meta):
        model = CommandLog
        fields = (
            "pk",
            "id",
            "device_name",
            "run",
            "command",
            "success",
            "error",
            "user",
            "started",
            "finished",
        )
        default_columns = ("id", "device_name", "command", "success", "user", "started")


class ComparisonScheduleTable(NetBoxTable):
    name = tables.Column(linkify=True)
    enabled = columns.BooleanColumn()
    weekdays = tables.Column(accessor="get_weekdays_display", orderable=False)
    time_of_day = tables.Column()
    device_count = tables.Column(
        accessor="devices__count", verbose_name=_("Devices"), orderable=False
    )
    next_run = columns.DateTimeColumn(orderable=False)
    last_run = columns.DateTimeColumn()
    actions = columns.ActionsColumn(actions=("edit", "delete"))

    class Meta(NetBoxTable.Meta):
        model = ComparisonSchedule
        fields = (
            "pk",
            "id",
            "name",
            "enabled",
            "weekdays",
            "time_of_day",
            "device_count",
            "next_run",
            "last_run",
            "created",
            "last_updated",
        )
        default_columns = (
            "name",
            "enabled",
            "weekdays",
            "time_of_day",
            "device_count",
            "next_run",
            "last_run",
        )
