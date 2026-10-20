"""The plugin's ExecutionRecorder: one CommandLog row per command sent to a device."""

from netbox_compare_access import DeviceTarget, ExecutionInfo

from .models import CommandLog


class DatabaseRecorder:
    """Log commands for ``device`` (a dcim.Device), linked to the run that sent them."""

    def __init__(self, device, user=None, comparison_run=None):
        self.device = device
        self.user = user
        self.comparison_run = comparison_run

    def record(
        self, device: DeviceTarget, command: str, output: str | None, info: ExecutionInfo
    ) -> None:
        CommandLog.objects.create(
            device=self.device,
            device_name=device.name,
            run=self.comparison_run,
            user=self.user,
            command=command,
            output=output or "",
            success=info.success,
            error=info.error or "",
            started=info.started_at,
            finished=info.finished_at,
        )
