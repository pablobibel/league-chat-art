"""One-shot chat typing; Windows input is initialized only for an actual send."""

from dataclasses import dataclass
import math
import time


@dataclass(frozen=True)
class SendOptions:
    channel: str = "all"
    start_delay: float = 2.0
    char_delay: float = 0.01
    line_delay: float = 1.5

    def __post_init__(self):
        if self.channel not in ("all", "team"):
            raise ValueError("Channel must be all or team.")
        for name in ("start_delay", "char_delay", "line_delay"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name.replace('_', ' ')} must be finite and nonnegative.")


class SendAborted(RuntimeError):
    """A stopped run, including how many rows reached the submit attempt."""

    def __init__(self, message, attempted_rows=0):
        super().__init__(message)
        self.attempted_rows = attempted_rows


def estimated_seconds(rows, options):
    """Estimate after F8, excluding OS overhead and the user's key release."""
    return (
        options.start_delay
        + sum(max(0, len(row) - 1) for row in rows) * options.char_delay
        + max(0, len(rows) - 1) * options.line_delay
        + len(rows) * 0.2  # Allow the chat box to open before typing.
    )


def send_rows(rows, options, backend, *, clock=time.monotonic, sleep=time.sleep,
              on_start=None):
    """Wait for a fresh F8, send one image, return attempted row submissions.

    The backend supplies key state, foreground identity, press, key_down/key_up,
    and release_held methods. Tests replace all OS input.
    Focus is checked immediately before each action, but OS focus changes and
    input injection cannot be made atomic; this is a best-effort guard.
    """
    if not rows or any(not row or set(row) - {"l", "."} for row in rows):
        raise ValueError("Expected nonempty art rows containing only l and .")
    attempted = 0
    target = None
    owned_shift = False

    def checkpoint():
        if backend.is_key_down("esc"):
            raise SendAborted("Esc pressed.")
        if target is not None:
            if backend.foreground_target() != target:
                raise SendAborted("League lost focus or its window could not be verified.")
            if backend.caps_lock_on():
                raise SendAborted("Turn Caps Lock off so l is typed in lowercase.")

    def wait_for_modifiers():
        # Alt may still be reported briefly after Alt+Tab. Pausing avoids both
        # false cancellations and accidentally emitting modified shortcuts.
        while True:
            checkpoint()
            keys = ("ctrl", "alt", "winleft", "winright")
            active = any(backend.is_key_down(key) for key in keys)
            active_shift = not owned_shift and backend.is_key_down("shift")
            if not active and not active_shift:
                return
            sleep(0.01)

    def wait(seconds):
        deadline = clock() + seconds
        while True:
            checkpoint()
            remaining = deadline - clock()
            if remaining <= 0:
                return
            sleep(min(0.01, remaining))

    def press(key):
        checkpoint()
        wait_for_modifiers()
        backend.press(key)

    try:
        previous_f8 = backend.is_key_down("f8")
        while True:
            checkpoint()
            current_f8 = backend.is_key_down("f8")
            if current_f8 and not previous_f8:
                target = backend.foreground_target()
                if target is None:
                    raise SendAborted("F8 requires the League match window in the foreground.")
                break
            previous_f8 = current_f8
            sleep(0.01)

        # Starting with F8 already held cannot trigger a run, and holding the
        # accepted key cannot retrigger or overlap sending.
        while backend.is_key_down("f8"):
            wait(0.01)
        checkpoint()
        wait_for_modifiers()
        if on_start is not None:
            on_start()
        wait(options.start_delay)

        for row_index, row in enumerate(rows):
            if options.channel == "all":
                checkpoint()
                wait_for_modifiers()
                backend.key_down("shift")
                owned_shift = True
                press("enter")
                checkpoint()
                backend.key_up("shift")
                owned_shift = False
            else:
                press("enter")
            wait(0.2)
            for index, character in enumerate(row):
                press(character)
                if index + 1 < len(row):
                    wait(options.char_delay)
            checkpoint()
            attempted += 1
            backend.press("enter")
            if row_index + 1 < len(rows):
                wait(options.line_delay)
        return attempted
    except SendAborted as exc:
        exc.attempted_rows = attempted
        raise
    except KeyboardInterrupt as exc:
        raise SendAborted("Interrupted.", attempted) from exc
    except Exception as exc:
        raise SendAborted(f"Keyboard input stopped: {exc}", attempted) from exc
    finally:
        try:
            backend.release_held()
        except Exception as exc:
            raise SendAborted(f"Could not release a script-held modifier; check your Shift key: {exc}", attempted) from exc


class WindowsKeyboard:
    """Normal desktop keyboard input plus read-only foreground process metadata."""

    KEYS = {"f8": 0x77, "esc": 0x1B, "shift": 0x10, "ctrl": 0x11,
            "alt": 0x12, "winleft": 0x5B, "winright": 0x5C}

    def __init__(self):
        import sys
        if sys.platform != "win32":
            raise RuntimeError("Automatic typing requires Windows. Use --preview-only here.")
        import ctypes
        from ctypes import wintypes
        try:
            import pyautogui
        except ImportError as exc:
            raise RuntimeError("Install the dependencies: python -m pip install -r requirements.txt") from exc

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.gui = pyautogui
        self.gui.PAUSE = 0  # Explicit cancellable waits control timing.
        # League may confine or hide its cursor at a screen corner, which makes
        # PyAutoGUI's mouse-corner fail-safe stop valid chat input. Esc and the
        # foreground-window guard remain available as emergency stops.
        self.gui.FAILSAFE = False
        self.held = set()
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.GetKeyState.argtypes = [ctypes.c_int]
        self.user32.GetKeyState.restype = ctypes.c_short
        self.user32.GetForegroundWindow.argtypes = []
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    def is_key_down(self, name):
        return bool(self.user32.GetAsyncKeyState(self.KEYS[name]) & 0x8000)

    def caps_lock_on(self):
        return bool(self.user32.GetKeyState(0x14) & 1)

    def foreground_target(self):
        import ntpath
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = self.wintypes.DWORD()
        if not self.user32.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid)):
            return None
        handle = self.kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return None
        try:
            size = self.wintypes.DWORD(32768)
            path = self.ctypes.create_unicode_buffer(size.value)
            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, path, self.ctypes.byref(size)):
                return None
            if ntpath.basename(path.value).casefold() != "league of legends.exe":
                return None
            return hwnd
        finally:
            self.kernel32.CloseHandle(handle)

    def press(self, key):
        self.gui.press(key)

    def key_down(self, key):
        self.held.add(key)
        self.gui.keyDown(key)

    def key_up(self, key):
        self.gui.keyUp(key)
        self.held.discard(key)

    def release_held(self):
        for key in list(self.held):
            self.gui.keyUp(key)
            self.held.discard(key)
