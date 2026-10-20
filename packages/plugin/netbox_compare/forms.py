from dcim.models import Device
from django import forms
from django.utils.translation import gettext_lazy as _

from .choices import POLICY_SECTIONS, WEEKDAY_CHOICES, SeverityChoices
from .credentials import credentialed_devices
from .jobs import reschedule
from .models import ComparisonPolicy, ComparisonSchedule


class ComparisonPolicyForm(forms.ModelForm):
    """One row per thing that can diverge: whether it is compared and how serious it is.

    Every severity is saved explicitly, so the engine's built-in severities, which it merges
    under the stored ones, can't override a choice made here.
    """

    ignore_interfaces = forms.CharField(
        required=False,
        label=_("Ignored interfaces"),
        widget=forms.Textarea(attrs={"rows": 3, "class": "font-monospace"}),
        help_text=_(
            "One pattern per line, case-sensitive; * matches anything, e.g. NULL* or "
            "Vlanif*. Their interfaces and IP addresses are left out entirely."
        ),
    )
    skip_undocumented = forms.BooleanField(
        required=False,
        label=_("Skip fields empty in NetBox"),
        help_text=_("A field NetBox leaves empty is not reported, whatever the device has"),
    )

    class Meta:
        model = ComparisonPolicy
        fields = ("ignore_interfaces", "skip_undocumented")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        policy = self.instance
        core = policy.to_core()
        self.initial["ignore_interfaces"] = "\n".join(policy.ignore_interfaces)
        self.sections = []
        for name, title, rows in POLICY_SECTIONS:
            section = {"name": name, "title": title, "rows": []}
            for row in rows:
                compared = policy.is_compared(row)
                if compared is not None:
                    self.fields[self._compare_name(row)] = forms.BooleanField(
                        required=False,
                        initial=compared,
                        label=row.label,
                    )
                self.fields[self._severity_name(row)] = forms.ChoiceField(
                    choices=SeverityChoices,
                    initial=policy.effective_severity(row, core),
                    label=_("{section}, {label}: severity").format(section=title, label=row.label),
                    widget=forms.Select(attrs={"class": "no-ts"}),
                )
                section["rows"].append(
                    {
                        "row": row,
                        "compare": self[self._compare_name(row)] if compared is not None else None,
                        "severity": self[self._severity_name(row)],
                    }
                )
            self.sections.append(section)

    @staticmethod
    def _compare_name(row) -> str:
        return f"compare__{row.key.replace('.', '__')}"

    @staticmethod
    def _severity_name(row) -> str:
        return f"severity__{row.key.replace('.', '__')}"

    def clean_ignore_interfaces(self):
        text = self.cleaned_data["ignore_interfaces"] or ""
        return [line.strip() for line in text.splitlines() if line.strip()]

    def clean(self):
        data = super().clean()
        compared = {"facts": [], "interface": [], "ip_address": []}
        severities = {}
        for _name, _title, rows in POLICY_SECTIONS:
            for row in rows:
                if data.get(self._compare_name(row)):
                    compared[row.object_type].append(row.field)
                if self._severity_name(row) in data:
                    severities[row.key] = data[self._severity_name(row)]
        # Set here, before the model's own clean() checks the whole policy against the engine.
        self.instance.fact_fields = compared["facts"]
        self.instance.interface_fields = compared["interface"]
        self.instance.compare_ip_addresses = bool(compared["ip_address"])
        self.instance.severities = severities
        return data


class WeekdayCheckboxes(forms.CheckboxSelectMultiple):
    """One checkbox per line. NetBox's field renderer puts ``form-control`` on every input, which
    makes default checkbox lists render as full-width boxes, so the markup is our own."""

    template_name = "netbox_compare/widgets/weekdays.html"
    option_template_name = "netbox_compare/widgets/weekday_option.html"


class ComparisonScheduleForm(forms.ModelForm):
    """Which devices to compare, on which weekdays and at what time."""

    weekdays = forms.TypedMultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        coerce=int,
        widget=WeekdayCheckboxes,
        help_text=ComparisonSchedule._meta.get_field("weekdays").help_text,
    )
    time_of_day = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        input_formats=["%H:%M", "%H:%M:%S"],
        help_text=ComparisonSchedule._meta.get_field("time_of_day").help_text,
    )
    devices = forms.ModelMultipleChoiceField(
        queryset=Device.objects.none(),  # set per request in __init__
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "netbox-static-select"}),
        help_text=_("Only devices with credentials configured can be chosen"),
    )

    class Meta:
        model = ComparisonSchedule
        fields = ("name", "enabled", "weekdays", "time_of_day", "devices")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only devices the credential source knows are selectable (looked up per request).
        self.fields["devices"].queryset = credentialed_devices(Device.objects.all())

    def save(self, commit=True):
        schedule = super().save(commit=commit)
        if commit:
            reschedule(schedule)
        return schedule
