"""Keyboard tests use only in-memory events and a virtual clock."""

import unittest
import sys

from sender import SendAborted, SendOptions, WindowsKeyboard, estimated_seconds, send_rows


class FakeKeyboard:
    def __init__(self):
        self.now = 0.0
        self.events = []
        self.held = set()
        self.cleaned = False
        self.f8 = lambda: 0.02 <= self.now < 0.04
        self.esc = lambda: False
        self.target = lambda: 100
        self.physical = set()
        self.caps = lambda: False
        self.fail_action = None

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.now > 30:
            raise AssertionError("Sender failed to finish with the virtual clock")

    def is_key_down(self, key):
        if key == "f8":
            return self.f8()
        if key == "esc":
            return self.esc()
        return key in self.held or key in self.physical

    def foreground_target(self):
        return self.target()

    def caps_lock_on(self):
        return self.caps()

    def record(self, action, key):
        self.events.append((action, key))
        if self.fail_action == (action, key):
            raise RuntimeError("Input backend failed")

    def press(self, key):
        self.record("press", key)

    def key_down(self, key):
        self.held.add(key)
        self.record("down", key)

    def key_up(self, key):
        self.record("up", key)
        self.held.discard(key)

    def release_held(self):
        self.cleaned = True
        for key in list(self.held):
            self.record("cleanup_up", key)
            self.held.discard(key)


class SenderTests(unittest.TestCase):
    def run_sender(self, backend, rows=None, **kwargs):
        return send_rows(rows or ["l."], SendOptions(**kwargs), backend,
                         clock=backend.clock, sleep=backend.sleep)

    def test_all_chat_sends_exactly_one_image_in_order_and_cleans_up(self):
        backend = FakeKeyboard()
        count = self.run_sender(backend, ["l.", ".l"], start_delay=0)
        opening = [("down", "shift"), ("press", "enter"), ("up", "shift")]
        self.assertEqual(backend.events,
            opening + [("press", "l"), ("press", "."), ("press", "enter")]
            + opening + [("press", "."), ("press", "l"), ("press", "enter")])
        self.assertEqual(count, 2)
        self.assertTrue(backend.cleaned)
        self.assertFalse(backend.held)

    def test_team_chat_does_not_press_shift(self):
        backend = FakeKeyboard()
        self.run_sender(backend, channel="team", start_delay=0)
        self.assertEqual(backend.events, [("press", "enter"), ("press", "l"),
                                          ("press", "."), ("press", "enter")])

    def test_f8_held_at_start_needs_release_and_a_fresh_press(self):
        backend = FakeKeyboard()
        backend.f8 = lambda: backend.now < 0.03 or 0.2 <= backend.now < 0.22
        starts = []
        send_rows(["l"], SendOptions(start_delay=0), backend, clock=backend.clock,
                  sleep=backend.sleep, on_start=lambda: starts.append(backend.now))
        self.assertEqual(len(starts), 1)
        self.assertGreaterEqual(starts[0], 0.22)

    def test_wrong_foreground_at_trigger_sends_nothing(self):
        backend = FakeKeyboard()
        backend.target = lambda: None
        with self.assertRaisesRegex(SendAborted, "foreground"):
            self.run_sender(backend)
        self.assertEqual(backend.events, [])

    def test_escape_before_trigger_sends_nothing(self):
        backend = FakeKeyboard()
        backend.esc = lambda: True
        with self.assertRaisesRegex(SendAborted, "Esc") as caught:
            self.run_sender(backend)
        self.assertEqual(caught.exception.attempted_rows, 0)
        self.assertEqual(backend.events, [])

    def test_escape_during_countdown(self):
        backend = FakeKeyboard()
        backend.esc = lambda: backend.now >= 0.5
        with self.assertRaises(SendAborted):
            self.run_sender(backend)
        self.assertLess(backend.now, 0.52)
        self.assertEqual(backend.events, [])

    def test_escape_between_characters_does_not_submit_partial_row(self):
        backend = FakeKeyboard()
        backend.esc = lambda: ("press", "l") in backend.events
        with self.assertRaises(SendAborted) as caught:
            self.run_sender(backend, start_delay=0, channel="team")
        self.assertEqual(caught.exception.attempted_rows, 0)
        self.assertEqual(backend.events, [("press", "enter"), ("press", "l")])

    def test_escape_during_inter_row_wait_preserves_attempted_count(self):
        backend = FakeKeyboard()
        backend.esc = lambda: backend.events.count(("press", "enter")) >= 2
        with self.assertRaises(SendAborted) as caught:
            self.run_sender(backend, ["l", "."], start_delay=0, channel="team")
        self.assertEqual(caught.exception.attempted_rows, 1)
        self.assertNotIn(("press", "."), backend.events)

    def test_focus_loss_during_countdown(self):
        backend = FakeKeyboard()
        backend.target = lambda: 100 if backend.now < 0.1 else None
        with self.assertRaisesRegex(SendAborted, "focus"):
            self.run_sender(backend)
        self.assertEqual(backend.events, [])

    def test_focus_loss_mid_row_prevents_next_character(self):
        backend = FakeKeyboard()
        backend.target = lambda: None if ("press", "l") in backend.events else 100
        with self.assertRaisesRegex(SendAborted, "focus"):
            self.run_sender(backend, start_delay=0, channel="team", char_delay=0)
        self.assertEqual(backend.events, [("press", "enter"), ("press", "l")])

    def test_second_game_window_is_not_the_original_target(self):
        backend = FakeKeyboard()
        backend.target = lambda: 200 if backend.events else 100
        with self.assertRaisesRegex(SendAborted, "focus"):
            self.run_sender(backend, start_delay=0)
        self.assertEqual(backend.events, [("down", "shift"), ("cleanup_up", "shift")])

    def test_backend_error_releases_shift(self):
        backend = FakeKeyboard()
        backend.fail_action = ("press", "enter")
        with self.assertRaisesRegex(SendAborted, "backend failed"):
            self.run_sender(backend, start_delay=0)
        self.assertFalse(backend.held)
        self.assertEqual(backend.events[-1], ("cleanup_up", "shift"))

    def test_physical_modifiers_prevent_start(self):
        for key in ("ctrl", "alt", "shift", "winleft", "winright"):
            with self.subTest(key=key):
                backend = FakeKeyboard()
                backend.physical.add(key)
                with self.assertRaises(SendAborted):
                    self.run_sender(backend)
                self.assertEqual(backend.events, [])

    def test_zero_delays_still_check_cancellation(self):
        backend = FakeKeyboard()
        backend.esc = lambda: ("press", "l") in backend.events
        with self.assertRaises(SendAborted):
            self.run_sender(backend, start_delay=0, char_delay=0, line_delay=0)
        self.assertNotIn(("press", "."), backend.events)

    def test_caps_lock_prevents_uppercase_art(self):
        backend = FakeKeyboard()
        backend.caps = lambda: True
        with self.assertRaisesRegex(SendAborted, "Caps Lock"):
            self.run_sender(backend)
        self.assertEqual(backend.events, [])

    def test_caps_lock_enabled_mid_row_stops_typing(self):
        backend = FakeKeyboard()
        backend.caps = lambda: ("press", "l") in backend.events
        with self.assertRaisesRegex(SendAborted, "Caps Lock"):
            self.run_sender(backend, start_delay=0, channel="team")
        self.assertEqual(backend.events, [("press", "enter"), ("press", "l")])

    def test_cleanup_failure_reports_attempts_instead_of_raw_exception(self):
        backend = FakeKeyboard()
        backend.fail_action = ("cleanup_up", "shift")
        backend.target = lambda: None if backend.held else 100
        with self.assertRaisesRegex(SendAborted, "Could not release") as caught:
            self.run_sender(backend, start_delay=0)
        self.assertEqual(caught.exception.attempted_rows, 0)

    def test_estimate_matches_virtual_timing_after_trigger_release(self):
        backend = FakeKeyboard()
        started = []
        options = SendOptions(start_delay=0.3, char_delay=0.1, line_delay=0.4)
        rows = ["lll", ".ll"]
        send_rows(rows, options, backend, clock=backend.clock, sleep=backend.sleep,
                  on_start=lambda: started.append(backend.now))
        self.assertAlmostEqual(backend.now - started[0], estimated_seconds(rows, options))

    def test_invalid_rows_never_reach_keyboard(self):
        backend = FakeKeyboard()
        for rows in ([], [""], ["/all hello"], ["l\n."], ["lll", "...​"]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                send_rows(rows, SendOptions(), backend)
        self.assertEqual(backend.events, [])

    def test_nonfinite_negative_delays_and_bad_channel(self):
        for name in ("start_delay", "char_delay", "line_delay"):
            for value in (-1, float("nan"), float("inf")):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    SendOptions(**{name: value})
        with self.assertRaises(ValueError):
            SendOptions(channel="party")

    def test_windows_cleanup_releases_held_key(self):
        class Gui:
            def __init__(self):
                self.released = []

            def keyUp(self, key):
                self.released.append(key)

        backend = WindowsKeyboard.__new__(WindowsKeyboard)
        backend.gui = Gui()
        backend.held = {"shift"}
        backend.release_held()
        self.assertEqual(backend.gui.released, ["shift"])
        self.assertFalse(backend.held)

    @unittest.skipUnless(sys.platform == "win32", "Windows adapter")
    def test_windows_adapter_disables_mouse_corner_failsafe(self):
        backend = WindowsKeyboard()
        self.assertFalse(backend.gui.FAILSAFE)


if __name__ == "__main__":
    unittest.main()
