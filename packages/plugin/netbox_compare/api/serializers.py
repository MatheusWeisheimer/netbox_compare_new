from core.api.serializers import JobSerializer
from dcim.api.serializers import DeviceSerializer
from netbox.api.serializers import BaseModelSerializer
from rest_framework import serializers
from users.api.serializers import UserSerializer

from ..models import (
    CommandLog,
    ComparisonPolicy,
    ComparisonRun,
    Divergence,
)

__all__ = (
    "CommandLogSerializer",
    "ComparisonRequestSerializer",
    "ComparisonPolicySerializer",
    "ComparisonRunSerializer",
    "DivergenceSerializer",
)


class ComparisonRunSerializer(BaseModelSerializer):
    device = DeviceSerializer(nested=True, read_only=True)
    user = UserSerializer(nested=True, read_only=True)
    job = JobSerializer(nested=True, read_only=True)
    divergence_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ComparisonRun
        fields = (
            "id", "url", "display_url", "display", "device", "user", "job", "status",
            "created", "started", "finished", "critical_count", "warning_count", "info_count",
            "divergence_count", "policy_snapshot", "error",
        )  # fmt: skip
        read_only_fields = fields
        brief_fields = ("id", "url", "display", "device", "status", "created", "divergence_count")


class ComparisonRequestSerializer(serializers.Serializer):
    """Body of POST runs/: the device to compare."""

    device = serializers.IntegerField(min_value=1)


class DivergenceSerializer(BaseModelSerializer):
    display_url = None  # divergences are shown on their run's page, not on their own
    run = ComparisonRunSerializer(nested=True, read_only=True)

    class Meta:
        model = Divergence
        fields = (
            "id", "url", "display", "run", "kind", "object_type", "key", "field",
            "expected", "actual", "severity",
        )  # fmt: skip
        read_only_fields = fields
        brief_fields = ("id", "url", "display", "kind", "severity")


class CommandLogSerializer(BaseModelSerializer):
    device = DeviceSerializer(nested=True, read_only=True)
    run = ComparisonRunSerializer(nested=True, read_only=True)
    user = UserSerializer(nested=True, read_only=True)

    class Meta:
        model = CommandLog
        fields = (
            "id", "url", "display_url", "display", "device", "device_name", "run",
            "user", "command", "output", "success", "error", "started", "finished",
        )  # fmt: skip
        read_only_fields = fields
        brief_fields = ("id", "url", "display", "device_name", "command", "success", "started")


class ComparisonPolicySerializer(BaseModelSerializer):
    class Meta:
        model = ComparisonPolicy
        fields = (
            "id", "url", "display_url", "display", "fact_fields", "interface_fields",
            "compare_ip_addresses", "ignore_interfaces", "skip_undocumented",
            "default_severity", "severities", "created", "last_updated",
        )  # fmt: skip
        read_only_fields = fields
        brief_fields = ("id", "url", "display")
