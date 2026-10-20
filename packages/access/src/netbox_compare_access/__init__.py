"""netbox-compare network access: run commands on devices and normalize their responses.

Produces the canonical model (``model``) from what a device reports. It knows nothing about
NetBox, Django, storage or users: credentials and the execution log are interfaces
(``CredentialProvider``, ``ExecutionRecorder``) implemented by the caller.
"""

from netbox_compare_access.credentials import CredentialProvider, Credentials
from netbox_compare_access.model import DeviceFacts, DeviceTarget, Interface, IPAddress, State
from netbox_compare_access.recorder import ExecutionInfo, ExecutionRecorder

__all__ = [
    "CredentialProvider",
    "Credentials",
    "DeviceFacts",
    "DeviceTarget",
    "ExecutionInfo",
    "ExecutionRecorder",
    "IPAddress",
    "Interface",
    "State",
]
