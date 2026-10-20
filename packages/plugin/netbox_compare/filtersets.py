import django_filters
from dcim.models import Device
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import BaseFilterSet

from .choices import (
    DivergenceKindChoices,
    RunStatusChoices,
    SeverityChoices,
)
from .models import CommandLog, ComparisonRun, ComparisonSchedule, Divergence


class ComparisonRunFilterSet(BaseFilterSet):
    q = django_filters.CharFilter(method="search", label=_("Search"))
    device_id = django_filters.ModelMultipleChoiceFilter(queryset=Device.objects.all())
    status = django_filters.MultipleChoiceFilter(choices=RunStatusChoices)

    class Meta:
        model = ComparisonRun
        fields = ("id", "status", "created", "finished")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(device__name__icontains=value) | Q(error__icontains=value))


class CommandLogFilterSet(BaseFilterSet):
    q = django_filters.CharFilter(method="search", label=_("Search"))
    device_id = django_filters.ModelMultipleChoiceFilter(queryset=Device.objects.all())
    run_id = django_filters.ModelMultipleChoiceFilter(queryset=ComparisonRun.objects.all())

    class Meta:
        model = CommandLog
        fields = ("id", "success", "started")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(device_name__icontains=value) | Q(command__icontains=value))


class DivergenceFilterSet(BaseFilterSet):
    q = django_filters.CharFilter(method="search", label=_("Search"))
    run_id = django_filters.ModelMultipleChoiceFilter(queryset=ComparisonRun.objects.all())
    device_id = django_filters.ModelMultipleChoiceFilter(
        field_name="run__device", queryset=Device.objects.all()
    )
    kind = django_filters.MultipleChoiceFilter(choices=DivergenceKindChoices)
    severity = django_filters.MultipleChoiceFilter(choices=SeverityChoices)

    class Meta:
        model = Divergence
        fields = ("id", "object_type", "key", "field")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(key__icontains=value) | Q(field__icontains=value))


class ComparisonScheduleFilterSet(BaseFilterSet):
    q = django_filters.CharFilter(method="search", label=_("Search"))
    device_id = django_filters.ModelMultipleChoiceFilter(
        field_name="devices", queryset=Device.objects.all()
    )

    class Meta:
        model = ComparisonSchedule
        fields = ("id", "name", "enabled")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(name__icontains=value).distinct()
