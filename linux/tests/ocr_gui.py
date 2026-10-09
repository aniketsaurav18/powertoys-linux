#!/usr/bin/python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Exercise asynchronous OCR controls with a CLI test double, not real OCR."""

import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from powertoys_linux.app import PowerToys
from gi.repository import GdkPixbuf, Gio, GLib
from powertoys_linux.gnome_settings import GnomeSettings
from powertoys_linux import ocr
from test_ocr import ENGINE


class OcrTest(PowerToys):
    def __init__(self, path):
        super().__init__(application_id="io.github.powertoys.Linux.OcrTest")
        self.preferences = GnomeSettings(Gio.memory_settings_backend_new())
        self.path = path
        self.failed = False
        self.stage = 0
        self.deadline = time.monotonic() + 15

    def do_activate(self):
        super().do_activate()
        self.stack.set_visible_child_name("ocr")
        GLib.timeout_add(80, self.check)

    def check(self):
        try:
            if time.monotonic() > self.deadline:
                raise TimeoutError("OCR GUI did not finish: " + self.status.get_text())
            if self.ocr_busy:
                return True
            if self.stage == 0:
                if self.ocr_engine_label.get_text() == "Checking optional OCR engine…":
                    return True
                assert self.ocr_language.get_active_text() == "eng", (self.ocr_engine_label.get_text(), self.status.get_text())
                self.ocr_load(self.path)
                self.stage = 1
            elif self.stage == 1 and self.ocr_rectangle:
                ox, oy, pw, ph = self.ocr_rectangle
                self.ocr_press(self.ocr_preview, SimpleNamespace(button=1, x=ox + pw / 4, y=oy + ph / 3))
                self.ocr_release(self.ocr_preview, SimpleNamespace(button=1, x=ox + 3 * pw / 4, y=oy + 2 * ph / 3))
                assert self.ocr_crop == (10, 10, 20, 10), self.ocr_crop
                self.ocr_start()
                assert not self.ocr_load_button.get_sensitive()
                assert self.ocr_cancel_button.get_sensitive()
                self.stage = 2
            elif self.stage == 2:
                buffer = self.ocr_text.get_buffer()
                text = buffer.get_text(*buffer.get_bounds(), True)
                assert text == "Hello Linux\n12345", (text, self.status.get_text())
                clipboard = Mock()
                with patch("powertoys_linux.ocr_ui.Gtk.Clipboard.get", return_value=clipboard):
                    self.ocr_copy()
                clipboard.set_text.assert_called_once_with(text, -1)
                self.ocr_reset()
                assert self.ocr_crop is None
                self.stage = 3
            elif self.stage == 3:
                if len(sys.argv) > 1:
                    import cairo
                    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.window.get_allocated_width(), self.window.get_allocated_height())
                    self.window.draw(cairo.Context(surface))
                    surface.write_to_png(sys.argv[1])
                print("OCR GUI passed: background loading/recognition, drag crop, controls, editable text and clipboard contract; CLI test double only.", flush=True)
                self.quit()
                return False
            return True
        except Exception:
            traceback.print_exc()
            self.failed = True
            self.quit()
            return False


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    executable = root / "tesseract"
    executable.write_text(ENGINE)
    executable.chmod(0o700)
    path = root / "image.png"
    image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 40, 30)
    image.fill(0xffffffff)
    image.savev(str(path), "png", [], [])
    before = path.read_bytes()
    with patch.object(ocr, "find_engine", return_value=ocr.Engine(executable)):
        app = OcrTest(path)
        result = app.run([sys.argv[0]])
    assert path.read_bytes() == before
    raise SystemExit(1 if app.failed else result)
