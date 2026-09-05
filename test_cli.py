import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import league_art
from sender import SendAborted


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "my image.png"
        Image.new("RGB", (8, 8), "black").save(self.image)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def run_cli(self, *args):
        with contextlib.redirect_stdout(self.stdout), contextlib.redirect_stderr(self.stderr):
            return league_art.main([str(self.image), *args])

    def test_preview_and_export_never_initialize_keyboard(self):
        target = self.root / "art.txt"
        with patch("league_art.WindowsKeyboard", side_effect=AssertionError("No keyboard in preview")):
            code = self.run_cli("--preview-only", "--output", str(target), "--width", "8")
        self.assertEqual(code, 0)
        self.assertEqual(target.read_text(), "llllllll\nllllllll\n")
        self.assertIn("2 messages | channel: all", self.stdout.getvalue())

    def test_output_does_not_replace_source_or_existing_file(self):
        before = self.image.read_bytes()
        with patch("league_art.WindowsKeyboard", side_effect=AssertionError("No keyboard")):
            code = self.run_cli("--preview-only", "--output", str(self.image))
        self.assertEqual(code, 2)
        self.assertEqual(self.image.read_bytes(), before)

    def test_missing_input_fails_before_keyboard_setup(self):
        self.image.unlink()
        with patch("league_art.WindowsKeyboard", side_effect=AssertionError("No keyboard")):
            code = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("Error:", self.stderr.getvalue())

    def test_invalid_options_fail_before_keyboard_setup(self):
        with patch("league_art.WindowsKeyboard", side_effect=AssertionError("No keyboard")):
            for args in (("--width", "0"), ("--aspect", "nan"), ("--threshold", "256"),
                         ("--char-delay", "-1"), ("--line-delay", "inf")):
                with self.subTest(args=args):
                    self.assertEqual(self.run_cli(*args), 2)

    def test_default_sends_all_chat_once_and_reports_attempts(self):
        with patch("league_art.WindowsKeyboard") as keyboard, patch("league_art.send_rows", return_value=12) as send:
            code = self.run_cli()
        self.assertEqual(code, 0)
        keyboard.assert_called_once()
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1].channel, "all")
        self.assertIn("12 row submissions attempted", self.stdout.getvalue())
        self.assertIn("delivery is not verified", self.stdout.getvalue())

    def test_team_channel_and_timing_are_forwarded(self):
        with patch("league_art.WindowsKeyboard"), patch("league_art.send_rows", return_value=12) as send:
            code = self.run_cli("--channel", "team", "--start-delay", "3", "--char-delay", "0.02", "--line-delay", "2")
        self.assertEqual(code, 0)
        options = send.call_args.args[1]
        self.assertEqual((options.channel, options.start_delay, options.char_delay, options.line_delay),
                         ("team", 3, 0.02, 2))

    def test_abort_reports_partial_attempt_count_and_exit_code(self):
        with patch("league_art.WindowsKeyboard"), patch("league_art.send_rows", side_effect=SendAborted("Esc pressed.", 2)):
            code = self.run_cli()
        self.assertEqual(code, 130)
        self.assertIn("2 row submissions attempted", self.stderr.getvalue())
        self.assertIn("partial chat draft", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
