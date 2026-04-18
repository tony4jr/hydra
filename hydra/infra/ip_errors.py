"""IP rotation related exceptions."""


class IPRotationFailed(RuntimeError):
    """Raised when `rotate_and_verify` fails all attempts.

    The executor catches this to reschedule the task, rather than marking
    it failed immediately.
    """
    pass


class ADBDeviceNotFound(RuntimeError):
    """Raised when the worker's ADB device is not connected."""
    pass
