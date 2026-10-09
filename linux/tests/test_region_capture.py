# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import os
import random
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from powertoys_linux.region_capture import RegionRequest, capture_command


class RegionTests(unittest.TestCase):
    def test_command_forces_new_area_and_private_file(self):
        with patch("powertoys_linux.region_capture.shutil.which", return_value="/usr/bin/gnome-screenshot"):
            command, environment = capture_command(Path("/tmp/text selection.png"))
        self.assertEqual(command, ["/usr/bin/gnome-screenshot", "--area", "--file", "/tmp/text selection.png"])
        self.assertNotIn("--clipboard", command)
        self.assertNotIn("--interactive", command)

    def test_missing_selector_does_not_fall_back_to_screenshot_overlay(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_DATA_HOME": folder}), patch("powertoys_linux.region_capture.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Direct text selection"):
                capture_command(Path(folder) / "selection.png")

    def test_success_retains_image_until_decoded(self):
        request, callback = self.make_request()
        request.path.write_bytes(b"image fixture")
        self.assertFalse(request.poll())
        callback.assert_called_once_with(request.path, None)
        self.assertTrue(request.path.exists())
        request.cleanup()
        self.assertFalse(request.path.parent.exists())

    def test_user_cancel_removes_private_directory(self):
        request, callback = self.make_request()
        self.assertFalse(request.poll())
        callback.assert_called_once_with(None, "Text selection cancelled.")
        self.assertFalse(request.path.parent.exists())

    def test_process_failure_reports_error_and_cleans_up(self):
        request, callback = self.make_request(returncode=1)
        request.errors.write(b"Area capture unavailable")
        self.assertFalse(request.poll())
        self.assertIn("Area capture unavailable", callback.call_args[0][1])
        self.assertFalse(request.path.parent.exists())

    def test_timeout_stops_child_and_cleans_up(self):
        request, callback = self.make_request(returncode=None)
        request.deadline = time.monotonic() - 1
        with patch("powertoys_linux.region_capture.stop_process") as stop:
            self.assertFalse(request.poll())
            stop.assert_called_once_with(request.process)
        self.assertFalse(request.path.parent.exists())
        callback.assert_called_once()

    def test_fuzz_helper_error_bytes(self):
        rng = random.Random(905)
        for _ in range(200):
            request, callback = self.make_request(returncode=1)
            request.errors.write(rng.randbytes(rng.randrange(0, 3000)))
            request.poll()
            message = callback.call_args[0][1]
            self.assertIsInstance(message, str)
            self.assertNotIn("\x00", message)
            self.assertLessEqual(len(message), 2025)
            self.assertFalse(request.path.parent.exists())

    def make_request(self, returncode=0):
        process = Mock(returncode=returncode)
        process.poll.return_value = returncode
        callback = Mock()
        with patch("powertoys_linux.region_capture.capture_command", return_value=(["fixture"], {})), patch("powertoys_linux.region_capture.subprocess.Popen", return_value=process), patch("powertoys_linux.region_capture.GLib.timeout_add", return_value=0):
            request = RegionRequest(callback)
        self.addCleanup(request.cleanup)
        return request, callback
