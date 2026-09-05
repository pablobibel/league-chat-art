"""One-shot League chat sender."""

from dataclasses import dataclass
import math
import time


@dataclass(frozen=True)
class SendOptions:
    channel: str = "all"
    start_delay: float = 2.0
    char_delay: float = 0.003
    line_delay: float = 0.4

    def __post_init__(self):
        if self.channel not in ("all", "team"):
            raise ValueError("Channel must be all or team.")
        for name in ("start_delay", "char_delay", "line_delay"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name.replace('_', ' ')} must be finite and nonnegative.")


class SendAborted(RuntimeError):
    def __init__(self, message, attempted_rows=0):
        super().__init__(message)
        self.attempted_rows = attempted_rows


def estimated_seconds(rows, options):
    return (
        options.start_delay
        + sum(max(0, len(row) - 1) for row in rows) * options.char_delay
        + max(0, len(rows) - 1) * options.line_delay
        + len(rows) * 0.2
    )


def send_rows(rows, options, backend, *, clock=time.monotonic, sleep=time.sleep,
              on_start=None):
    """Wait for a fresh F8 press, then type every row once."""
    if not rows or any(not row or set(row) - {"l", "."} for row in rows):
        raise ValueError("Expected nonempty art rows containing only l and .")

    attempted = 0
    target_pid = None

    def checkpoint():
        if backend.is_key_down("esc"):
            raise SendAborted("Esc pressed.")
        if target_pid is not None and backend.foreground_target() != target_pid:
            raise SendAborted("League lost focus or its process could not be verified.")
        if target_pid is not None and backend.caps_lock_on():
            raise SendAborted("Turn Caps Lock off so l is typed in lowercase.")

    def wait(seconds):
        deadline = clock() + seconds
        while clock() < deadline:
            checkpoint()
            sleep(min(0.01, deadline - clock()))
        checkpoint()

    try:
        previous_f8 = backend.is_key_down("f8")
        while True:
            checkpoint()
            current_f8 = backend.is_key_down("f8")
            if current_f8 and not previous_f8:
                target_pid = backend.foreground_target()
                if target_pid is None:
                    raise SendAborted("F8 requires the League match window in the foreground.")
                break
            previous_f8 = current_f8
            sleep(0.01)

        while backend.is_key_down("f8"):
            checkpoint()
            sleep(0.01)

        if on_start is not None:
            on_start()
        wait(options.start_delay)

        for index, row in enumerate(rows):
            checkpoint()
            backend.open_chat(options.channel)
            wait(0.2)
            backend.write_row(row, options.char_delay)
            checkpoint()
            backend.submit()
            attempted += 1
            if index + 1 < len(rows):
                wait(options.line_delay)
        return attempted
    except SendAborted as exc:
        exc.attempted_rows = attempted
        raise
    except KeyboardInterrupt as exc:
        raise SendAborted("Interrupted.", attempted) from exc
    except Exception as exc:
        raise SendAborted(f"Keyboard input stopped: {exc}", attempted) from exc


class WindowsKeyboard:
    """Reference-compatible keyboard input plus a League focus check."""

    KEYS = {"f8": 0x77, "esc": 0x1B}

    def __init__(self):
        import sys
        if sys.platform != "win32":
            raise RuntimeError("Automatic typing requires Windows. Use --preview-only here.")
        import ctypes
        from ctypes import wintypes
        try:
            import keyboard
            import pyautogui
        except ImportError as exc:
            raise RuntimeError(
                "Install the dependencies: python -m pip install -r requirements.txt"
            ) from exc

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.keyboard = keyboard
        self.gui = pyautogui
        self.gui.PAUSE = 0
        self.gui.FAILSAFE = False

        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.GetKeyState.argtypes = [ctypes.c_int]
        self.user32.GetKeyState.restype = ctypes.c_short
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.kernel32.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
        ]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)
        ]
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
            if not self.kernel32.QueryFullProcessImageNameW(
                    handle, 0, path, self.ctypes.byref(size)):
                return None
            if ntpath.basename(path.value).casefold() != "league of legends.exe":
                return None
            return pid.value
        finally:
            self.kernel32.CloseHandle(handle)

    def open_chat(self, channel):
        self.keyboard.press_and_release("shift+enter" if channel == "all" else "enter")

    def write_row(self, row, interval):
        self.gui.write(row, interval=interval)

    def submit(self):
        self.gui.write("\n")
