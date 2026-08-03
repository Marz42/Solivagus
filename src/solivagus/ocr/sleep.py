from __future__ import annotations

import atexit
import ctypes
import os


def enable_prevent_sleep(enabled: bool) -> None:
    """Prevent Windows idle sleep while the process is running."""
    if not enabled:
        return
    if os.name != "nt":
        return

    es_continuous = 0x80000000
    es_system_required = 0x00000001
    result = ctypes.windll.kernel32.SetThreadExecutionState(
        es_continuous | es_system_required
    )
    if result == 0:
        return

    def reset() -> None:
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(es_continuous)
        except Exception:  # noqa: BLE001
            pass

    atexit.register(reset)
