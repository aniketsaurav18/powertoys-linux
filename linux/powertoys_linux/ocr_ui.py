# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Native image, crop and text controls for the optional OCR backend."""

import threading
from pathlib import Path

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from . import ocr
from .desktop import ScreenshotRequest
from .ocr_shortcut import DEFAULT_BINDING, OcrShortcut


class OcrViews:
    def init_ocr(self):
        self.ocr_image = None
        self.ocr_crop = None
        self.ocr_engine = None
        self.ocr_busy = False
        self.ocr_closed = False
        self.ocr_cancel = threading.Event()
        self.ocr_request = None
        self.ocr_drag = None
        self.ocr_rectangle = None

    def ocr_page(self):
        box = self.page("ocr", "Text Extractor", "Recognize printed text from a PNG/JPEG or an interactive desktop screenshot. Drag over the preview to select a region. Recognition runs locally using optional Tesseract language models.")
        self.ocr_engine_label = Gtk.Label(label="Checking optional OCR engine…", xalign=0)
        self.ocr_engine_label.set_line_wrap(True)
        box.pack_start(self.ocr_engine_label, False, False, 0)
        row = Gtk.Box(spacing=10)
        box.pack_start(row, False, False, 0)
        self.ocr_load_button = self.button(row, "Open image…", self.ocr_choose)
        self.ocr_capture_button = self.button(row, "Capture screen…", self.ocr_capture)
        self.ocr_refresh_button = self.button(row, "Refresh engine", self.ocr_refresh)
        self.ocr_preview = Gtk.DrawingArea()
        self.ocr_preview.set_size_request(400, 300)
        self.ocr_preview.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.ocr_preview.connect("draw", self.ocr_draw)
        self.ocr_preview.connect("button-press-event", self.ocr_press)
        self.ocr_preview.connect("motion-notify-event", self.ocr_motion)
        self.ocr_preview.connect("button-release-event", self.ocr_release)
        box.pack_start(self.ocr_preview, False, False, 0)
        self.ocr_selection = Gtk.Label(label="No image selected", xalign=0)
        box.pack_start(self.ocr_selection, False, False, 0)
        row = Gtk.Box(spacing=10)
        box.pack_start(row, False, False, 0)
        self.ocr_language = Gtk.ComboBoxText()
        self.ocr_mode = Gtk.ComboBoxText()
        for mode in ocr.MODES:
            self.ocr_mode.append_text(mode)
        self.ocr_mode.set_active(1)
        for label, control in (("Language", self.ocr_language), ("Layout", self.ocr_mode)):
            row.pack_start(Gtk.Label(label=label), False, False, 0)
            row.pack_start(control, False, False, 0)
        self.ocr_reset_button = self.button(row, "Use whole image", self.ocr_reset)
        row = Gtk.Box(spacing=10)
        box.pack_start(row, False, False, 0)
        self.ocr_start_button = self.button(row, "Extract text", self.ocr_start)
        self.ocr_cancel_button = self.button(row, "Cancel", self.ocr_stop)
        self.ocr_text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.ocr_text.set_size_request(-1, 180)
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.ocr_text)
        box.pack_start(scroll, True, True, 0)
        self.button(box, "Copy recognized text", self.ocr_copy)
        label = Gtk.Label(label="Screen-to-clipboard shortcut: drag around text and release. OCR copies it automatically. Escape cancels selection.", xalign=0)
        label.set_line_wrap(True)
        box.pack_start(label, False, False, 0)
        row = Gtk.Box(spacing=10)
        box.pack_start(row, False, False, 0)
        self.ocr_shortcut_entry = Gtk.Entry(placeholder_text="<Super><Shift>t")
        row.pack_start(self.ocr_shortcut_entry, True, True, 0)
        self.button(row, "Save shortcut", self.ocr_save_shortcut)
        self.button(row, "Remove shortcut", self.ocr_remove_shortcut)
        self.button(box, "Select screen area and copy text…", self.ocr_quick_capture)
        self.button(box, "Stop background Text Extractor", self.ocr_stop_background)
        try:
            self.ocr_shortcut_entry.set_text(OcrShortcut(self.preferences).read() or DEFAULT_BINDING)
        except (RuntimeError, ValueError):
            self.ocr_shortcut_entry.set_text(DEFAULT_BINDING)
        self.ocr_controls()
        GLib.idle_add(self.ocr_refresh)

    def ocr_controls(self):
        for button in (self.ocr_load_button, self.ocr_capture_button, self.ocr_refresh_button, self.ocr_language, self.ocr_mode):
            button.set_sensitive(not self.ocr_busy)
        self.ocr_start_button.set_sensitive(not self.ocr_busy and self.ocr_image is not None and self.ocr_engine is not None)
        self.ocr_reset_button.set_sensitive(not self.ocr_busy and self.ocr_image is not None)
        self.ocr_cancel_button.set_sensitive(self.ocr_busy)

    def ocr_submit(self, work, completed):
        self.ocr_busy = True
        self.ocr_cancel.clear()
        self.ocr_controls()
        future = self.pool.submit(work)

        def finish():
            if self.ocr_closed:
                return False
            self.ocr_busy = False
            try:
                value = future.result()
                if self.ocr_cancel.is_set():
                    raise ocr.OcrCancelled("OCR cancelled.")
                completed(value)
            except Exception as error:
                self.status.set_text(str(error))
            self.ocr_controls()
            return False

        future.add_done_callback(lambda _: GLib.idle_add(finish))

    def ocr_refresh(self):
        if self.ocr_closed or self.ocr_busy:
            return False
        self.ocr_engine = None

        def discover():
            try:
                engine = ocr.find_engine()
                return engine, ocr.list_languages(engine), None
            except Exception as error:
                return None, [], str(error)

        def completed(result):
            engine, languages, error = result
            previous = self.ocr_language.get_active_text()
            self.ocr_engine = engine
            self.ocr_language.remove_all()
            for language in languages:
                self.ocr_language.append_text(language)
            preferred = previous if previous in languages else "eng" if "eng" in languages else next(iter(languages), None)
            if preferred:
                self.ocr_language.set_active(languages.index(preferred))
            self.ocr_engine_label.set_text(error or f"Tesseract ready · {len(languages)} installed language(s)")

        self.ocr_submit(discover, completed)
        return False

    def ocr_choose(self):
        if self.ocr_busy:
            return
        files = self.choose_files("Select a PNG or JPEG for OCR", multiple=False)
        if files:
            self.ocr_load(files[0])

    def ocr_load(self, path):
        if self.ocr_busy or self.ocr_closed:
            return
        self.status.set_text("Loading OCR image…")

        def completed(image):
            self.ocr_image = image
            self.ocr_rectangle = None
            self.ocr_reset()
            self.status.set_text("Drag over the image to select text, or extract the whole image.")

        self.ocr_submit(lambda: ocr.load_image(path), completed)

    def ocr_capture(self):
        if self.ocr_busy:
            return
        self.ocr_busy = True
        self.ocr_controls()
        self.window.hide()
        self.status.set_text("Choose a capture in the desktop screenshot dialog.")

        def begin():
            if self.ocr_closed or not self.ocr_busy:
                return False
            try:
                self.ocr_request = ScreenshotRequest(self.ocr_captured)
            except Exception as error:
                self.ocr_captured(None, str(error))
            return False

        GLib.idle_add(begin)

    def ocr_captured(self, path, error):
        self.ocr_request = None
        self.ocr_busy = False
        if self.ocr_closed:
            return
        self.window.present()
        self.ocr_controls()
        if error:
            self.status.set_text(error)
        else:
            self.ocr_load(path)

    def ocr_reset(self):
        self.ocr_crop = None
        self.ocr_drag = None
        self.ocr_update_selection()

    def ocr_update_selection(self):
        if self.ocr_image:
            width, height = self.ocr_image.get_width(), self.ocr_image.get_height()
            self.ocr_selection.set_text(f"Region: {self.ocr_crop}" if self.ocr_crop else f"Whole image: {width} × {height} pixels")
        self.ocr_preview.queue_draw()

    def ocr_draw(self, widget, context):
        if self.ocr_image is None:
            return False
        width, height = self.ocr_image.get_width(), self.ocr_image.get_height()
        scale = min(widget.get_allocated_width() / width, widget.get_allocated_height() / height, 1)
        pw, ph = max(1, round(width * scale)), max(1, round(height * scale))
        ox, oy = (widget.get_allocated_width() - pw) / 2, (widget.get_allocated_height() - ph) / 2
        self.ocr_rectangle = ox, oy, pw, ph
        preview = self.ocr_image.scale_simple(pw, ph, GdkPixbuf.InterpType.BILINEAR)
        context.set_source_rgb(1, 1, 1)
        context.rectangle(ox, oy, pw, ph)
        context.fill()
        Gdk.cairo_set_source_pixbuf(context, preview, ox, oy)
        context.paint()
        if self.ocr_crop:
            x, y, w, h = self.ocr_crop
            context.set_source_rgb(0.1, 0.5, 1)
            context.set_line_width(2)
            context.rectangle(ox + x * pw / width, oy + y * ph / height, w * pw / width, h * ph / height)
            context.stroke()
        return False

    def ocr_press(self, widget, event):
        if event.button != 1 or self.ocr_busy or self.ocr_image is None or self.ocr_rectangle is None:
            return False
        ox, oy, pw, ph = self.ocr_rectangle
        if ox <= event.x <= ox + pw and oy <= event.y <= oy + ph:
            self.ocr_drag = (event.x - ox, event.y - oy)
        return True

    def ocr_motion(self, widget, event):
        if self.ocr_drag is None or self.ocr_busy:
            return False
        ox, oy, pw, ph = self.ocr_rectangle
        try:
            self.ocr_crop = ocr.crop_from_drag(self.ocr_drag, (event.x - ox, event.y - oy),
                                              self.ocr_image.get_width(), self.ocr_image.get_height(), pw, ph)
            self.ocr_update_selection()
        except ValueError:
            pass
        return True

    def ocr_release(self, widget, event):
        if event.button != 1 or self.ocr_drag is None:
            return False
        self.ocr_motion(widget, event)
        self.ocr_drag = None
        return True

    def ocr_start(self):
        if self.ocr_busy:
            return
        if self.ocr_image is None or self.ocr_engine is None:
            raise ValueError("Select an image and install the optional OCR engine first.")
        image, crop, engine = self.ocr_image, self.ocr_crop, self.ocr_engine
        language, mode = self.ocr_language.get_active_text(), self.ocr_mode.get_active_text()
        self.status.set_text("Extracting text locally…")

        def completed(text):
            self.ocr_text.get_buffer().set_text(text)
            self.status.set_text(f"Extracted {len(text)} characters. Review or edit the text before copying." if text else "No text found. Try another crop, language or layout.")

        self.ocr_submit(lambda: ocr.recognize(image, language, mode, crop, self.ocr_cancel, engine), completed)

    def ocr_stop(self):
        self.ocr_cancel.set()
        self.status.set_text("Cancelling OCR…")
        if self.ocr_request:
            self.ocr_request.cancel()
        elif self.ocr_busy and not self.window.get_visible():
            self.ocr_captured(None, "Screenshot capture cancelled.")

    def ocr_copy(self):
        buffer = self.ocr_text.get_buffer()
        text = buffer.get_text(*buffer.get_bounds(), True)
        if not text:
            raise ValueError("Extract text first.")
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        self.status.set_text("OCR text copied. Keep this app open until you paste.")

    def close_ocr(self):
        self.ocr_closed = True
        self.ocr_cancel.set()
        if self.ocr_request:
            self.ocr_request.cancel()

    def ocr_save_shortcut(self):
        binding = OcrShortcut(self.preferences).save(self.ocr_shortcut_entry.get_text())
        self.ocr_shortcut_entry.set_text(binding)
        self.status.set_text("Screen-to-clipboard shortcut saved. Drag around text and release; OCR copies it automatically.")

    def ocr_remove_shortcut(self):
        OcrShortcut(self.preferences).remove()
        self.status.set_text("Screen-to-clipboard shortcut removed.")

    def ocr_background_command(self, argument):
        executable = Path.home() / ".local/bin/powertoys-linux"
        if not executable.is_file():
            raise RuntimeError("Install PowerToys for this user first.")
        Gio.Subprocess.new([str(executable), argument], Gio.SubprocessFlags.NONE)

    def ocr_quick_capture(self):
        self.ocr_background_command("--ocr")
        self.status.set_text("Drag around the screen text and release. Recognized text will be copied automatically.")

    def ocr_stop_background(self):
        self.ocr_background_command("--stop-ocr")
        self.status.set_text("Background Text Extractor stopped.")
