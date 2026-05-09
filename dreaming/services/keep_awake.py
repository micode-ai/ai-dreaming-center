"""Keep system awake while long-running CLI sessions are active.

Windows-only: prevents Modern Standby (Connected Standby) from killing
child Claude processes when the laptop sits idle. On other platforms
all calls become no-ops.
"""

from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger(__name__)

# Win32 SetThreadExecutionState flags
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_AWAYMODE_REQUIRED = 0x00000040


class KeepAwake:
    """Reference-counted keep-awake guard.

    Call ``acquire()`` when a session that must survive idle starts,
    ``release()`` when it ends. The system stays awake while the counter
    is > 0; the display is allowed to turn off normally.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._refs = 0
        self._enabled = sys.platform == "win32"
        self._set_state = None
        if self._enabled:
            try:
                import ctypes
                self._set_state = ctypes.windll.kernel32.SetThreadExecutionState
                self._set_state.restype = ctypes.c_uint
                self._set_state.argtypes = [ctypes.c_uint]
            except Exception as e:
                log.warning("KeepAwake disabled: %s", e)
                self._enabled = False

    def acquire(self) -> None:
        with self._lock:
            self._refs += 1
            if self._refs == 1 and self._enabled:
                flags = _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_AWAYMODE_REQUIRED
                if self._set_state(flags) == 0:
                    log.warning("SetThreadExecutionState(ON) returned 0")
                else:
                    log.info("Keep-awake ON (system will not idle-sleep)")

    def release(self) -> None:
        with self._lock:
            if self._refs == 0:
                return
            self._refs -= 1
            if self._refs == 0 and self._enabled:
                if self._set_state(_ES_CONTINUOUS) == 0:
                    log.warning("SetThreadExecutionState(OFF) returned 0")
                else:
                    log.info("Keep-awake OFF (idle-sleep allowed again)")

    @property
    def active(self) -> bool:
        return self._refs > 0
