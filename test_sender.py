"""Sender tests use an in-memory keyboard and virtual clock."""

import sys
import unittest

from sender import SendAborted, SendOptions, WindowsKeyboard, send_rows


class FakeKeyboard:
    def __init__(self):
        self.now = 0.0
        self.events = []
        self.f8 = lambda: 0.02 <= self.now < 0.04
        self.esc = lambda: False
        self.target = lambda: 100
        self.caps = lambda: False

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def is_key_down(self, key):
        return self.f8() if key == "f8" else self.esc()

    def foreground_target(self):
        return self.target()

    def caps_lock_on(self):
        return self.caps()

    def open_chat(self, channel):
        self.events.append(("open", channel))

    def write_row(self, row, interval):
        self.events.append(("write", row, interval))

    def submit(self):
        self.events.append(("submit",))


class SenderTests(unittest.TestCase):
    def run_sender(self, backend, rows=None, **kwargs):
        return send_rows(
            rows or ["l."], SendOptions(**kwargs), backend,
            clock=backend.clock, sleep=backend.sleep
        )

    def test_team_rows_are_opened_typed_and_submitted_once_in_order(self):
        backend = FakeKeyboard()
        count = self.run_sender(
            backend, ["l.", ".l"], channel="team", start_delay=0,
            char_delay=0.03, line_delay=0
        )
        self.assertEqual(count, 2)
        self.assertEqual(backend.events, [
            ("open", "team"), ("write", "l.", 0.03), ("submit",),
            ("open", "team"), ("write", ".l", 0.03), ("submit",),
        ])

    def test_all_chat_channel_is_forwarded(self):
        backend = FakeKeyboard()
        self.run_sender(backend, start_delay=0, line_delay=0)
        self.assertEqual(backend.events[0], ("open", "all"))

    def test_wrong_foreground_at_f8_sends_nothing(self):
        backend = FakeKeyboard()
        backend.target = lambda: None
        with self.assertRaisesRegex(SendAborted, "foreground"):
            self.run_sender(backend)
        self.assertEqual(backend.events, [])

    def test_escape_during_countdown_sends_nothing(self):
        backend = FakeKeyboard()
        backend.esc = lambda: backend.now >= 0.1
        with self.assertRaisesRegex(SendAborted, "Esc"):
            self.run_sender(backend)
        self.assertEqual(backend.events, [])

    def test_focus_loss_before_typing_does_not_write_a_row(self):
        backend = FakeKeyboard()
        backend.target = lambda: None if backend.events else 100
        with self.assertRaisesRegex(SendAborted, "focus"):
            self.run_sender(backend, start_delay=0)
        self.assertEqual(backend.events, [("open", "all")])

    def test_invalid_rows_and_options_fail_before_input(self):
        backend = FakeKeyboard()
        for rows in ([], [""], ["hello"], ["l\n."]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                send_rows(rows, SendOptions(), backend)
        for value in (-1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SendOptions(char_delay=value)
        self.assertEqual(backend.events, [])

    @unittest.skipUnless(sys.platform == "win32", "Windows adapter")
    def test_windows_adapter_uses_reference_libraries(self):
        backend = WindowsKeyboard()
        self.assertEqual(backend.gui.__name__, "pyautogui")
        self.assertEqual(backend.keyboard.__name__, "keyboard")
        self.assertFalse(backend.gui.FAILSAFE)

    def test_windows_adapter_maps_to_reference_input_sequence(self):
        calls = []

        class Keyboard:
            def press_and_release(self, keys):
                calls.append(("keys", keys))

        class Gui:
            def write(self, text, interval=0):
                calls.append(("write", text, interval))

        backend = WindowsKeyboard.__new__(WindowsKeyboard)
        backend.keyboard = Keyboard()
        backend.gui = Gui()
        backend.open_chat("all")
        backend.write_row("l.", 0.01)
        backend.submit()
        backend.open_chat("team")
        self.assertEqual(calls, [
            ("keys", "shift+enter"), ("write", "l.", 0.01),
            ("write", "\n", 0), ("keys", "enter"),
        ])


if __name__ == "__main__":
    unittest.main()
