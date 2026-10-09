# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Single-instance screen-to-clipboard OCR, invoked by a desktop shortcut."""

import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from . import ocr
from .desktop import ScreenshotRequest


class QuickOcr(Gtk.Application):
    def __init__(self, application_id="io.github.powertoys.Linux.TextExtractor"):
        super().__init__(application_id=application_id, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.cancel = threading.Event()
        self.request = None
        self.busy = False
        self.closed = False
        self.held = False
        self.copied = False
        self.copy_window = None
        self.copy_timer = 0
        self.copy_attempts = 0
        self.pending_text = None

    def do_command_line(self, command_line):
        arguments = command_line.get_arguments()[1:]
        if arguments == ["--stop-ocr"]:
            self.quit()
            return 0
        if arguments != ["--ocr"]:
            return 2
        self.capture()
        return 0

    def notify(self, message):
        notification = Gio.Notification.new("PowerToys Text Extractor")
        notification.set_body(message)
        self.send_notification("ocr-result", notification)

    def capture(self):
        if self.busy:
            self.notify("Text extraction is already in progress. Finish or cancel the current selection.")
            return
        self.busy = True
        self.cancel.clear()
        if not self.held:
            self.hold()
            self.held = True

        def discover():
            engine = ocr.find_engine()
            languages = ocr.list_languages(engine)
            return engine, "eng" if "eng" in languages else languages[0]

        self.submit(discover, self.select_screen)

    def submit(self, work, completed):
        future = self.pool.submit(work)

        def finish():
            if self.closed:
                return False
            try:
                result = future.result()
                if self.cancel.is_set():
                    raise ocr.OcrCancelled("Text extraction cancelled.")
                completed(result)
            except Exception as error:
                self.finish(str(error))
            return False

        future.add_done_callback(lambda _: GLib.idle_add(finish))

    def select_screen(self, engine_language):
        engine, language = engine_language

        def selected(path, error):
            self.request = None
            if self.closed:
                return
            if error:
                self.finish(error)
                return

            def recognize():
                image = ocr.load_image(path)
                return ocr.recognize(image, language, "Scattered text", cancel=self.cancel, engine=engine)

            self.submit(recognize, self.copy_text)

        self.request = ScreenshotRequest(selected)

    def copy_text(self, text):
        if not text:
            self.finish("No text found. Try selecting a clearer or larger region.")
            return
        self.pending_text = text
        self.copy_attempts = 0
        if self.copy_window is None:
            # Wayland clipboard writes require keyboard focus and an input
            # serial. This brief utility window obtains both without relying
            # on restricted Shell interfaces or an additional clipboard tool.
            self.copy_window = Gtk.ApplicationWindow(application=self, title="Text Extractor")
            self.copy_window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
            self.copy_window.set_skip_taskbar_hint(True)
            self.copy_window.set_skip_pager_hint(True)
            self.copy_window.set_default_size(280, 65)
            self.copy_window.set_position(Gtk.WindowPosition.CENTER)
            self.copy_window.add(Gtk.Label(label="Copying recognized text…"))
            self.copy_window.connect("delete-event", self.cancel_copy)
        self.copy_window.show_all()
        self.copy_window.present()
        self.copy_timer = GLib.timeout_add(50, self.copy_when_focused)

    def copy_when_focused(self):
        self.copy_attempts += 1
        if not self.copy_window.is_active():
            if self.copy_attempts < 60:
                return True
            self.copy_timer = 0
            self.copy_window.destroy()
            self.copy_window = None
            self.pending_text = None
            self.finish("Could not access the clipboard. Try the shortcut again.")
            return False
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self.pending_text, -1)
        clipboard.store()
        count = len(self.pending_text)
        self.pending_text = None
        self.copied = True
        self.copy_timer = 0
        GLib.timeout_add(100, self.finish_copy, count)
        return False

    def finish_copy(self, count):
        if self.copy_window:
            self.copy_window.hide()
        self.finish(f"Copied {count} characters. Paste with Ctrl+V.")
        return False

    def cancel_copy(self, *_):
        if self.copy_timer:
            GLib.source_remove(self.copy_timer)
            self.copy_timer = 0
        self.pending_text = None
        self.copy_window.destroy()
        self.copy_window = None
        self.finish("Text extraction cancelled.")
        return True

    def finish(self, message):
        self.busy = False
        self.notify(message)
        if not self.copied:
            GLib.timeout_add(300, self.release_if_idle)

    def release_if_idle(self):
        if self.held and not self.busy and not self.copied:
            self.held = False
            self.release()
        return False

    def do_shutdown(self):
        self.closed = True
        self.cancel.set()
        if self.copy_timer:
            GLib.source_remove(self.copy_timer)
        if self.request:
            self.request.cancel()
        self.pool.shutdown(wait=True)
        Gtk.Application.do_shutdown(self)


def main(arguments):
    if not Gtk.init_check()[0]:
        print("Run Text Extractor from your graphical desktop session.", file=sys.stderr)
        return 1
    app = QuickOcr()
    return app.run([sys.argv[0], *arguments])
