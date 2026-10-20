from dcim.models import Device
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.object_actions import (
    AddObject,
    BulkDelete,
    BulkExport,
    DeleteObject,
    EditObject,
)
from netbox.views import generic
from utilities.views import register_model_view

from . import documentation, filtersets, forms, tables
from .choices import DivergenceResolutionChoices, RunStatusChoices
from .credentials import NoCredentials
from .documentation import DocumentationError
from .jobs import (
    WorkerNotRunning,
    start_comparison,
)
from .models import CommandLog, ComparisonPolicy, ComparisonRun, ComparisonSchedule

#
# Comparison runs
#


@register_model_view(ComparisonRun, "list", path="", detail=False)
class ComparisonRunListView(generic.ObjectListView):
    queryset = ComparisonRun.objects.select_related("device", "user")
    filterset = filtersets.ComparisonRunFilterSet
    table = tables.ComparisonRunTable
    actions = (BulkExport,)


@register_model_view(ComparisonRun)
class ComparisonRunView(generic.ObjectView):
    queryset = ComparisonRun.objects.select_related("device", "user", "job")
    actions = ()

    def get_extra_context(self, request, instance):
        can_resolve = bool(
            request.user.has_perm("netbox_compare.change_divergence")
            and instance.status == RunStatusChoices.COMPLETED
            and instance.divergence_count
        )
        divergences = tables.DivergenceTable(
            instance.divergences.select_related("resolved_by"),
            user=request.user,
            exclude=() if can_resolve else ("to_netbox", "to_device"),
        )
        commands = tables.CommandLogTable(
            CommandLog.objects.restrict(request.user, "view").filter(run=instance),
            user=request.user,
            exclude=("actions", "run"),
        )
        return {
            "divergence_table": divergences,
            "command_table": commands,
            "can_resolve": can_resolve,
        }


@register_model_view(ComparisonRun, "resolve", path="resolve")
class ComparisonRunResolveView(View):
    """Carry out each divergence's choice: update NetBox, or mark it to fix on the device.

    Rows posted as ``netbox`` are written into NetBox one by one; a row that fails is
    reported and stays open. Rows posted as ``fix_device`` are only marked (nothing is sent
    to the device), and marked rows not posted are unmarked. Deleting from NetBox is
    confirmed on a page of its own first.
    """

    def post(self, request, pk):
        if not request.user.has_perm("netbox_compare.change_divergence"):
            return HttpResponseForbidden()
        run = get_object_or_404(
            ComparisonRun.objects.restrict(request.user, "view").select_related("device"),
            pk=pk,
            status=RunStatusChoices.COMPLETED,
        )
        divergences = {d.pk: d for d in run.divergences.all()}
        to_document = _posted_pks(request.POST, "netbox", divergences)
        to_fix = _posted_pks(request.POST, "fix_device", divergences)
        if to_document & to_fix:
            messages.error(
                request,
                _("A divergence can't be both sent to NetBox and marked to fix on the device."),
            )
            return redirect(run.get_absolute_url())

        documented = DivergenceResolutionChoices.DOCUMENTED
        documenting = sorted(
            (divergences[pk] for pk in to_document if divergences[pk].resolution != documented),
            key=documentation.order,
        )
        deleting = [d for d in documenting if documentation.deletes(d)]
        if deleting and not request.POST.get("confirm"):
            return render(
                request,
                "netbox_compare/comparisonrun_resolve.html",
                {
                    "object": run,
                    "deleting": [(d, documentation.deleted_with(d)) for d in deleting],
                    "to_document": sorted(to_document),
                    "to_fix": sorted(to_fix),
                },
            )

        now = timezone.now()
        applied, failed = 0, []
        for divergence in documenting:
            try:
                with transaction.atomic():
                    documentation.apply(divergence, request.user)
            except (DocumentationError, ValidationError) as exc:
                failed.append(f"{divergence}: {_error_text(exc)}")
                continue
            _resolve(divergence, documented, request.user, now)
            applied += 1

        marked = 0
        for divergence in divergences.values():
            if divergence.resolution == documented or divergence.pk in to_document:
                continue
            wanted = (
                DivergenceResolutionChoices.FIX_DEVICE
                if divergence.pk in to_fix
                else DivergenceResolutionChoices.OPEN
            )
            if divergence.resolution != wanted:
                _resolve(divergence, wanted, request.user, now)
                marked += wanted == DivergenceResolutionChoices.FIX_DEVICE

        if applied:
            messages.success(
                request, _("NetBox updated for {count} divergence(s).").format(count=applied)
            )
        if marked:
            messages.success(
                request,
                _("{count} divergence(s) marked to fix on the device.").format(count=marked),
            )
        if failed:
            messages.error(request, _("Not applied: {failures}").format(failures="; ".join(failed)))
        return redirect(run.get_absolute_url())


def _posted_pks(data, name: str, divergences: dict) -> set[int]:
    return {int(v) for v in data.getlist(name) if v.isdigit() and int(v) in divergences}


def _resolve(divergence, resolution: str, user, when) -> None:
    divergence.resolution = resolution
    divergence.resolved_by = user if resolution else None
    divergence.resolved_at = when if resolution else None
    divergence.save(update_fields=("resolution", "resolved_by", "resolved_at"))


def _error_text(exc) -> str:
    if isinstance(exc, ValidationError):
        return " ".join(exc.messages)
    return str(exc)


class CompareDeviceView(View):
    """Start a comparison of one device (POST only)."""

    def post(self, request, pk):
        if not request.user.has_perm("netbox_compare.add_comparisonrun"):
            return HttpResponseForbidden()
        device = get_object_or_404(Device.objects.restrict(request.user, "view"), pk=pk)
        try:
            run = start_comparison(device, request.user)
        except WorkerNotRunning:
            messages.error(
                request, _("Unable to start comparison: background worker process not running.")
            )
            return redirect(device.get_absolute_url())
        except NoCredentials as exc:
            messages.error(request, str(exc))
            return redirect(device.get_absolute_url())
        messages.info(request, _("Comparison of {device} queued.").format(device=device))
        return redirect(run.get_absolute_url())


#
# Command log entry (read-only: ground rule 4); listed on each run's page
#


@register_model_view(CommandLog, "list", path="", detail=False)
class CommandLogListView(generic.ObjectListView):
    """Not in the menu: reached from a run's page; the detail page's breadcrumb needs it."""

    queryset = CommandLog.objects.select_related("run", "user")
    filterset = filtersets.CommandLogFilterSet
    table = tables.CommandLogTable
    actions = (BulkExport,)


@register_model_view(CommandLog)
class CommandLogView(generic.ObjectView):
    queryset = CommandLog.objects.select_related("device", "run", "user")
    actions = ()


#
# Global comparison policy
#


def global_policy_view(request):
    return redirect(ComparisonPolicy.get_global().get_absolute_url())


@register_model_view(ComparisonPolicy)
class ComparisonPolicyView(generic.ObjectView):
    queryset = ComparisonPolicy.objects.all()
    actions = (EditObject,)


@register_model_view(ComparisonPolicy, "edit")
class ComparisonPolicyEditView(generic.ObjectEditView):
    queryset = ComparisonPolicy.objects.all()
    form = forms.ComparisonPolicyForm
    template_name = "netbox_compare/comparisonpolicy_edit.html"


#
# Comparison schedules
#


@register_model_view(ComparisonSchedule, "list", path="", detail=False)
class ComparisonScheduleListView(generic.ObjectListView):
    queryset = ComparisonSchedule.objects.prefetch_related("devices")
    filterset = filtersets.ComparisonScheduleFilterSet
    table = tables.ComparisonScheduleTable
    actions = (AddObject, BulkExport, BulkDelete)


@register_model_view(ComparisonSchedule)
class ComparisonScheduleView(generic.ObjectView):
    queryset = ComparisonSchedule.objects.prefetch_related("devices")
    actions = (EditObject, DeleteObject)

    def get_extra_context(self, request, instance):
        runs = tables.ComparisonRunTable(
            ComparisonRun.objects.restrict(request.user, "view")
            .filter(schedule=instance)
            .select_related("device", "user")[:20],
            user=request.user,
            exclude=("actions", "schedule"),
            orderable=False,
        )
        return {"run_table": runs}


@register_model_view(ComparisonSchedule, "add", detail=False)
@register_model_view(ComparisonSchedule, "edit")
class ComparisonScheduleEditView(generic.ObjectEditView):
    queryset = ComparisonSchedule.objects.all()
    form = forms.ComparisonScheduleForm

    def alter_object(self, obj, request, url_args, url_kwargs):
        # The comparisons start as the user who saved the schedule.
        obj.user = request.user
        return obj


@register_model_view(ComparisonSchedule, "delete")
class ComparisonScheduleDeleteView(generic.ObjectDeleteView):
    queryset = ComparisonSchedule.objects.all()


@register_model_view(ComparisonSchedule, "bulk_delete", path="delete", detail=False)
class ComparisonScheduleBulkDeleteView(generic.BulkDeleteView):
    queryset = ComparisonSchedule.objects.all()
    filterset = filtersets.ComparisonScheduleFilterSet
    table = tables.ComparisonScheduleTable
