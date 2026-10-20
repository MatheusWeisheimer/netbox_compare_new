"""Send CLI commands to a device, reporting every one to a recorder.

This module does not decide whether a command is allowed: approval and the
read-only check are the caller's responsibility (the plugin).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from netbox_compare_access.collect import open_device
from netbox_compare_access.credentials import CredentialProvider
from netbox_compare_access.model import DeviceTarget
from netbox_compare_access.recorder import ExecutionInfo, ExecutionRecorder


def run_commands(
    provider: CredentialProvider,
    device: DeviceTarget,
    commands: Sequence[str],
    recorder: ExecutionRecorder,
) -> dict[str, str]:
    """Run ``commands`` in order and return ``{command: output}``.

    Stops at the first failing command (after recording the failure) and re-raises.
    """
    outputs: dict[str, str] = {}
    with open_device(provider, device) as conn:
        for command in commands:
            started = datetime.now(UTC)
            try:
                output = conn.cli([command])[command]
            except Exception as exc:
                recorder.record(
                    device,
                    command,
                    None,
                    ExecutionInfo(started, datetime.now(UTC), False, repr(exc)),
                )
                raise
            recorder.record(
                device, command, output, ExecutionInfo(started, datetime.now(UTC), True)
            )
            outputs[command] = output
    return outputs
