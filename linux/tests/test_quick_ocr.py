# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock, patch

from gi.repository import GLib
from powertoys_linux.quick_ocr import QuickOcr


class QuickOcrTests(unittest.TestCase):
    def setUp(self):
        self.app = QuickOcr(application_id="io.github.powertoys.Linux.QuickUnitTest")
        self.addCleanup(self.app.pool.shutdown)
        self.app.notify = Mock()
        self.app.hold = Mock()
        self.app.release = Mock()
        self.jobs = []

        def queue(work):
            future = Future()
            self.jobs.append((work, future))
            return future

        self.app.pool.submit = Mock(side_effect=queue)

    def complete_job(self):
        work, future = self.jobs.pop(0)
        try:
            future.set_result(work())
        except Exception as error:
            future.set_exception(error)
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def test_command_line_routes_capture_and_stop(self):
        command = Mock()
        command.get_arguments.return_value = ["powertoys-linux", "--ocr"]
        with patch.object(self.app, "capture") as capture:
            self.assertEqual(self.app.do_command_line(command), 0)
            capture.assert_called_once()
        command.get_arguments.return_value = ["powertoys-linux", "--stop-ocr"]
        with patch.object(self.app, "quit") as quit_app:
            self.app.do_command_line(command)
            quit_app.assert_called_once()

    def test_selection_automatically_recognizes_and_copies(self):
        engine = Mock()
        self.app.copy_text = Mock()
        with patch("powertoys_linux.quick_ocr.ocr.find_engine", return_value=engine), patch("powertoys_linux.quick_ocr.ocr.list_languages", return_value=["eng"]), patch("powertoys_linux.quick_ocr.ScreenshotRequest") as request:
            self.app.capture()
            self.assertTrue(self.app.busy)
            request.assert_not_called()
            self.complete_job()
            selected = request.call_args[0][0]
            with patch("powertoys_linux.quick_ocr.ocr.load_image", return_value=Mock()) as load, patch("powertoys_linux.quick_ocr.ocr.recognize", return_value="Recognized text") as recognize:
                selected(Path("/tmp/selection.png"), None)
                self.complete_job()
                load.assert_called_once_with(Path("/tmp/selection.png"))
                self.assertEqual(recognize.call_args[0][1:3], ("eng", "Scattered text"))
            self.app.copy_text.assert_called_once_with("Recognized text")

    def test_duplicate_trigger_does_not_start_another_job(self):
        self.app.capture()
        self.app.capture()
        self.assertEqual(len(self.jobs), 1)
        self.app.hold.assert_called_once()
        self.assertIn("already", self.app.notify.call_args[0][0])

    def test_empty_result_does_not_copy_or_keep_alive(self):
        self.app.held = True
        with patch("powertoys_linux.quick_ocr.GLib.timeout_add"), patch("powertoys_linux.quick_ocr.Gtk.Clipboard.get") as clipboard:
            self.app.copy_text("")
            clipboard.assert_not_called()
        self.assertFalse(self.app.copied)
        self.app.release_if_idle()
        self.app.release.assert_called_once()

    def test_clipboard_requires_focus_and_keeps_owner_alive(self):
        self.app.copy_window = Mock()
        self.app.copy_window.is_active.return_value = False
        self.app.pending_text = "Private recognized text"
        with patch("powertoys_linux.quick_ocr.Gtk.Clipboard.get") as clipboard:
            self.assertTrue(self.app.copy_when_focused())
            clipboard.assert_not_called()
            self.app.copy_window.is_active.return_value = True
            with patch("powertoys_linux.quick_ocr.GLib.timeout_add"):
                self.assertFalse(self.app.copy_when_focused())
            clipboard.return_value.set_text.assert_called_once_with("Private recognized text", -1)
        self.app.finish_copy(23)
        self.app.release_if_idle()
        self.app.release.assert_not_called()
        self.assertNotIn("Private recognized text", self.app.notify.call_args[0][0])

    def test_clipboard_focus_timeout(self):
        self.app.copy_window = Mock()
        self.app.copy_window.is_active.return_value = False
        self.app.copy_attempts = 59
        with patch("powertoys_linux.quick_ocr.GLib.timeout_add"):
            self.assertFalse(self.app.copy_when_focused())
        self.assertIsNone(self.app.copy_window)
        self.assertFalse(self.app.copied)
        self.assertIn("clipboard", self.app.notify.call_args[0][0])

    def test_cancelled_selection_and_engine_failure(self):
        with patch("powertoys_linux.quick_ocr.ScreenshotRequest") as request, patch("powertoys_linux.quick_ocr.GLib.timeout_add"):
            self.app.select_screen((Mock(), "eng"))
            request.call_args[0][0](None, "Screenshot capture cancelled.")
            self.assertFalse(self.app.busy)
            self.assertEqual(self.jobs, [])
            with patch("powertoys_linux.quick_ocr.ocr.find_engine", side_effect=RuntimeError("Missing engine")):
                self.app.capture()
                self.complete_job()
            self.assertFalse(self.app.busy)
            self.app.notify.assert_called_with("Missing engine")
