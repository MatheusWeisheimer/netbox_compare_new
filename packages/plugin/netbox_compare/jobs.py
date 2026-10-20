from core.choices import JobStatusChoices
from dcim.models import Device
from django.utils import timezone
from netbox.jobs import JobFailed, JobRunner
from utilities.rqworker import get_queue_for_model, get_workers_for_queue

from .comparison import run_comparison
from .credentials import NoCredentials, get_connector, has_credentials
from .models import ComparisonRun, ComparisonSchedule
from .schedules import next_occurrence


class CompareDeviceJob(JobRunner):
    """Background job: compare one device (all device access happens here, in the worker)."""

    class Meta:
        name = "Device comparison"

    def run(self, run_id, *args, **kwargs):
        run = ComparisonRun.objects.select_related("device").get(pk=run_id)
        run.job = self.job
        self.logger.info(f"Comparing {run.device}")
        try:
            run_comparison(run, get_connector(), self.job.user)
        except Exception as exc:
            self.logger.error(run.error or repr(exc))
            raise JobFailed() from exc
        self.logger.info(
            f"Completed: {run.critical_count} critical, {run.warning_count} warning, "
            f"{run.info_count} info"
        )


class ScheduledComparisonJob(JobRunner):
    """Background job: start a comparison of each device of a schedule, then plan the next one.

    Each device gets its own ``CompareDeviceJob``. Devices that no longer have credentials
    are skipped and said so in this job's log.
    """

    class Meta:
        name = "Scheduled comparisons"

    def run(self, schedule_id, *args, **kwargs):
        schedule = ComparisonSchedule.objects.filter(pk=schedule_id).first()
        if schedule is None or not schedule.enabled:
            self.logger.info("Schedule deleted or disabled: nothing to do")
            return
        try:
            self._start_comparisons(schedule)
        finally:
            # Whatever happened, the recurrence must go on.
            reschedule(schedule)

    def _start_comparisons(self, schedule):
        user = schedule.user
        if (
            user is None
            or not user.is_active
            or not user.has_perm("netbox_compare.add_comparisonrun")
        ):
            self.logger.error("The user who saved this schedule can no longer start comparisons")
            raise JobFailed()
        devices = Device.objects.restrict(user, "view").filter(pk__in=schedule.devices.values("pk"))
        started = 0
        for device in devices:
            try:
                start_comparison(device, user, schedule=schedule)
            except NoCredentials:
                self.logger.warning(f"Skipped {device}: no credentials configured")
            else:
                started += 1
        schedule.last_run = timezone.now()
        schedule.save(update_fields=("last_run",))
        self.logger.info(f"Started {started} comparison(s) of {schedule.devices.count()} device(s)")


def reschedule(schedule: ComparisonSchedule) -> None:
    """Make the scheduled job match ``schedule``: one job at its next occurrence, or none.

    Safe to call repeatedly: an unchanged schedule keeps its job.
    """
    if not schedule.enabled:
        for job in ScheduledComparisonJob.get_jobs(schedule).filter(
            status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES
        ):
            job.delete()
        return
    when = next_occurrence(
        schedule.weekdays, schedule.time_of_day, timezone.now(), timezone.get_default_timezone()
    )
    ScheduledComparisonJob.enqueue_once(
        instance=schedule, schedule_at=when, user=schedule.user, schedule_id=schedule.pk
    )


class WorkerNotRunning(Exception):
    """No background worker serves the queue, so a queued comparison would never run."""


def _require_worker(model) -> None:
    """Like NetBox's own scripts, refuse to queue when no worker serves the job's queue."""
    if not get_workers_for_queue(get_queue_for_model(model._meta.model_name)):
        raise WorkerNotRunning("Background worker (rqworker) not running")


def _require_credentials(device) -> None:
    """Device work only starts for devices the credential source knows (by name)."""
    if not has_credentials(device):
        raise NoCredentials(device.name)


def start_comparison(device, user, schedule=None) -> ComparisonRun:
    """Create a pending run for a device and queue its job (used by the UI and the API).

    Raises ``NoCredentials`` and ``WorkerNotRunning``.
    """
    _require_credentials(device)
    _require_worker(ComparisonRun)
    run = ComparisonRun.objects.create(device=device, user=user, schedule=schedule)
    run.job = CompareDeviceJob.enqueue(instance=run, user=user, run_id=run.pk)
    run.save(update_fields=("job",))
    return run
