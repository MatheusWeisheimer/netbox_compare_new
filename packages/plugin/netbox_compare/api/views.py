from dcim.models import Device
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from netbox.api.viewsets import NetBoxReadOnlyModelViewSet
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.routers import APIRootView
from utilities.exceptions import RQWorkerNotRunningException

from .. import filtersets
from ..credentials import NoCredentials
from ..jobs import WorkerNotRunning, start_comparison
from ..models import (
    CommandLog,
    ComparisonPolicy,
    ComparisonRun,
    Divergence,
)
from . import serializers


class NetBoxCompareRootView(APIRootView):
    def get_view_name(self):
        return "NetBox Compare"


class ComparisonRunViewSet(NetBoxReadOnlyModelViewSet):
    """Comparison runs. POST {"device": <id>} starts a new one (read-only on the device)."""

    queryset = ComparisonRun.objects.select_related("device", "user", "job")
    serializer_class = serializers.ComparisonRunSerializer
    filterset_class = filtersets.ComparisonRunFilterSet

    @extend_schema(
        request=serializers.ComparisonRequestSerializer,
        responses={201: serializers.ComparisonRunSerializer},
    )
    def create(self, request, *args, **kwargs):
        body = serializers.ComparisonRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        devices = Device.objects.restrict(request.user, "view")
        device = devices.filter(pk=body.validated_data["device"]).first()
        if device is None:
            raise ValidationError({"device": _("Device not found.")})

        try:
            run = start_comparison(device, request.user)
        except NoCredentials as exc:
            raise ValidationError({"device": str(exc)}) from None
        except WorkerNotRunning:
            raise RQWorkerNotRunningException() from None

        serializer = self.get_serializer(run)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DivergenceViewSet(NetBoxReadOnlyModelViewSet):
    queryset = Divergence.objects.select_related("run__device")
    serializer_class = serializers.DivergenceSerializer
    filterset_class = filtersets.DivergenceFilterSet


class CommandLogViewSet(NetBoxReadOnlyModelViewSet):
    queryset = CommandLog.objects.select_related("device", "run", "user")
    serializer_class = serializers.CommandLogSerializer
    filterset_class = filtersets.CommandLogFilterSet


class ComparisonPolicyViewSet(NetBoxReadOnlyModelViewSet):
    """The global comparison policy. Read-only here: it is edited only in the UI."""

    queryset = ComparisonPolicy.objects.order_by("pk")
    serializer_class = serializers.ComparisonPolicySerializer
