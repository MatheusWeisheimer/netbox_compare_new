"""Run one comparison: NetBox data + device state -> stored divergences.

Kept separate from the JobRunner so it can be tested without a worker.
"""

from __future__ import annotations

from collections import Counter

from django.db import transaction
from django.utils import timezone
from netbox_compare_access import CredentialProvider, collect

from . import engine, netbox_data
from .choices import RunStatusChoices
from .engine import netbox_state
from .models import ComparisonPolicy, ComparisonRun, Divergence
from .recorder import DatabaseRecorder


def run_comparison(run: ComparisonRun, provider: CredentialProvider, user=None) -> ComparisonRun:
    """Execute ``run`` and store its result. Marks the run failed and re-raises on error."""
    run.status = RunStatusChoices.RUNNING
    run.started = timezone.now()
    run.save(update_fields=("status", "started", "job"))

    try:
        policy = ComparisonPolicy.get_global()
        run.policy_snapshot = policy.to_dict()

        data = netbox_data.build(run.device)
        target = netbox_state.device_target(data)
        observed = collect.from_device(
            provider, target, DatabaseRecorder(run.device, user, comparison_run=run)
        )
        diff = engine.run(netbox_state.from_netbox(data), observed, policy.to_core())
    except Exception as exc:
        run.status = RunStatusChoices.FAILED
        run.error = f"{type(exc).__name__}: {exc}"
        run.finished = timezone.now()
        run.save(update_fields=("status", "error", "finished", "policy_snapshot"))
        raise

    counts = Counter(str(d.severity) for d in diff)
    with transaction.atomic():
        Divergence.objects.bulk_create(
            Divergence(
                run=run,
                kind=str(d.kind),
                object_type=d.object_type,
                key=d.key,
                field=d.field or "",
                expected=d.expected,
                actual=d.actual,
                severity=str(d.severity),
            )
            for d in diff
        )
        run.critical_count = counts["critical"]
        run.warning_count = counts["warning"]
        run.info_count = counts["info"]
        run.status = RunStatusChoices.COMPLETED
        run.finished = timezone.now()
        run.save()
    return run
