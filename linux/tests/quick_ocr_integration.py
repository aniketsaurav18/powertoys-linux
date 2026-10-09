#!/usr/bin/python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Private GNOME test: actual area drag/release, real OCR, clipboard and IPC."""

import os
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wait_until(predicate, pump=lambda: None, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pump()
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise TimeoutError("Quick OCR integration condition timed out.")


def session():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gio, GLib, Gtk
    import cairo

    if not Gtk.init_check()[0]:
        raise RuntimeError("Cannot connect to the isolated compositor.")

    fixture_text = ["POWERTOYS LINUX OCR"]
    expected_text = [fixture_text[0]]

    def draw(widget, context):
        context.set_source_rgb(1, 1, 1)
        context.paint()
        context.set_source_rgb(0, 0, 0)
        context.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        context.set_font_size(45)
        context.move_to(30, 85)
        context.show_text(fixture_text[0])

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def control(method, parameters=None, result_type=None):
        return connection.call_sync("org.gnome.Shell", "/io/github/powertoys/OcrTest", "io.github.powertoys.Linux.OcrTest", method, parameters,
                                    GLib.VariantType.new(result_type) if result_type else None, Gio.DBusCallFlags.NONE, 5000, None)

    def state():
        try:
            return json.loads(control("State", result_type="(s)").unpack()[0])
        except GLib.Error:
            return {"ready": False, "selecting": False, "start": None, "rect": None}

    def selector():
        value = state()
        return value if value["selecting"] else None

    def drag(reverse=False):
        value = selector()
        assert value and value["start"] == [-1, -1], value
        rect = value["rect"]
        x1, y1 = rect["x"] + 5, rect["y"] + 5
        x2, y2 = rect["x"] + rect["width"] - 5, rect["y"] + rect["height"] - 5
        if reverse:
            x1, y1, x2, y2 = x2, y2, x1, y1
        control("Drag", GLib.Variant("(iiii)", (x1, y1, x2, y2)))

    window = Gtk.Window(title="Quick OCR paste target")
    window.set_decorated(False)
    window.set_default_size(1000, 140)
    drawing = Gtk.DrawingArea()
    drawing.connect("draw", draw)
    window.add(drawing)
    window.show_all()

    def pump():
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    wait_until(lambda: state()["ready"], pump)
    window.present()
    wait_until(window.is_active, pump)
    settled = time.monotonic() + 1
    wait_until(lambda: time.monotonic() >= settled, pump)
    command = ["/usr/bin/python3", str(Path(__file__).resolve()), "--worker", "--ocr"]
    log_path = ROOT / "build/quick-ocr-app.log"
    with log_path.open("w") as log:
        service = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            wait_until(selector, pump)
            duplicate = subprocess.Popen(command, stdout=log, stderr=log)
            wait_until(lambda: duplicate.poll() is not None, pump)
            assert duplicate.returncode == 0
            assert selector()["start"] == [-1, -1]
            drag()
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            received = []

            def read_clipboard():
                if window.is_active():
                    clipboard.request_text(lambda _, text, data: received.append(text), None)
                return expected_text[0] in received

            try:
                wait_until(read_clipboard, pump)
            except TimeoutError:
                print("Clipboard failure state:", state(), "active:", window.is_active(), "received:", received[-3:], flush=True)
                print(log_path.read_text(), flush=True)
                raise
            assert not selector(), "Selection remained open after mouse release."
            assert not list(Path(os.environ["XDG_RUNTIME_DIR"]).glob("powertoys-text-selection-*")), "Temporary capture was not deleted."
            assert service.poll() is None, "Clipboard owner exited before paste."
            fixture_text[0] = expected_text[0] = "INVOICE 12345"
            drawing.queue_draw()
            repeat = subprocess.Popen(command, stdout=log, stderr=log)
            wait_until(selector, pump)
            wait_until(lambda: repeat.poll() is not None, pump)
            assert repeat.returncode == 0
            drag(reverse=True)
            received.clear()
            wait_until(lambda: not selector(), pump)
            wait_until(lambda: not list(Path(os.environ["XDG_RUNTIME_DIR"]).glob("powertoys-text-selection-*")), pump)
            wait_until(read_clipboard, pump)
            wait_until(lambda: "Copied 13 characters." in log_path.read_text(), pump)
            cancelled = subprocess.Popen(command, stdout=log, stderr=log)
            wait_until(selector, pump)
            assert selector()["start"] == [-1, -1]
            control("Escape")
            wait_until(lambda: not selector(), pump)
            wait_until(lambda: cancelled.poll() is not None, pump)
            wait_until(lambda: not list(Path(os.environ["XDG_RUNTIME_DIR"]).glob("powertoys-text-selection-*")), pump)
            received.clear()
            wait_until(read_clipboard, pump)
            stop = subprocess.Popen([*command[:-1], "--stop-ocr"], stdout=log, stderr=log)
            wait_until(lambda: stop.poll() is not None and service.poll() is not None, pump)
            assert stop.returncode == service.returncode == 0
            print("Quick OCR Wayland integration passed: fresh native crosshair each time, real screen drag/release without Enter, reversed drag, automatic OCR/clipboard delivery, Escape preserving copied text, private-image cleanup and single-instance Stop.", flush=True)
        finally:
            if service.poll() is None:
                service.terminate()
                try:
                    service.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    service.kill()
                    service.wait()
            window.destroy()


def main():
    from powertoys_linux.ocr import find_engine
    from powertoys_linux.region_capture import capture_command, local_runtime as region_runtime
    engine = find_engine()
    capture_command(Path("/tmp/unused-selection.png"))
    with tempfile.TemporaryDirectory(prefix="powertoys-quick-ocr-") as folder:
        root = Path(folder)
        environment = dict(os.environ)
        for key, name in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_RUNTIME_DIR", "runtime")):
            path = root / name
            path.mkdir(mode=0o700)
            environment[key] = str(path)
        if engine.runtime:
            runtime = root / "data/powertoys-linux/ocr-runtime"
            runtime.parent.mkdir(parents=True)
            runtime.symlink_to(engine.runtime)
        if region_runtime().exists():
            runtime = root / "data/powertoys-linux/region-runtime"
            runtime.parent.mkdir(parents=True, exist_ok=True)
            runtime.symlink_to(region_runtime())
        environment.update(GSETTINGS_BACKEND="keyfile", LIBGL_ALWAYS_SOFTWARE="1", GDK_BACKEND="wayland", WAYLAND_DISPLAY="powertoys-ocr-test", NO_AT_BRIDGE="1", TMPDIR=str(root / "runtime"))
        # A headless compositor has no physical keyboard. Provide one only in
        # the isolated test session, and dismiss its startup overview.
        extension = root / "data/gnome-shell/extensions/quick-ocr-test@local"
        extension.mkdir(parents=True)
        (extension / "metadata.json").write_text(json.dumps({"uuid": "quick-ocr-test@local", "name": "Quick OCR Test Fixture", "description": "Private test keyboard", "shell-version": ["46"]}))
        (extension / "extension.js").write_text('''
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {SelectArea} from 'resource:///org/gnome/shell/ui/screenshot.js';
const XML = `<node><interface name="io.github.powertoys.Linux.OcrTest">
<method name="State"><arg type="s" direction="out"/></method>
<method name="Drag"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Escape"/></interface></node>`;
export default class Fixture extends Extension {
    enable() {
        this.keyboard = Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this.pointer = Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        this.bus = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this.bus.export(Gio.DBus.session, '/io/github/powertoys/OcrTest');
        this.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
            if (Main.layoutManager._startingUp) return GLib.SOURCE_CONTINUE;
            Main.overview.hide();
            this.timer = 0;
            return GLib.SOURCE_REMOVE;
        });
    }
    State() {
        const selection = Main.uiGroup.get_children().find(child => child instanceof SelectArea && child.visible);
        const target = global.get_window_actors().map(actor => actor.meta_window).find(window => window.get_title() === 'Quick OCR paste target');
        const rect = target?.get_frame_rect();
        return JSON.stringify({ready: !Main.layoutManager._startingUp && !Main.overview.visible,
            selecting: Boolean(selection), start: selection ? [selection._startX, selection._startY] : null,
            rect: rect ? {x: rect.x, y: rect.y, width: rect.width, height: rect.height} : null});
    }
    Drag(x1, y1, x2, y2) {
        this.pointer.notify_absolute_motion(GLib.get_monotonic_time(), x1, y1);
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
            this.pointer.notify_button(GLib.get_monotonic_time(), 1, Clutter.ButtonState.PRESSED);
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
                this.pointer.notify_absolute_motion(GLib.get_monotonic_time(), x2, y2);
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 100, () => {
                    this.pointer.notify_button(GLib.get_monotonic_time(), 1, Clutter.ButtonState.RELEASED);
                    return GLib.SOURCE_REMOVE;
                });
                return GLib.SOURCE_REMOVE;
            });
            return GLib.SOURCE_REMOVE;
        });
    }
    Escape() {
        this.keyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Escape, Clutter.KeyState.PRESSED);
        this.keyboard.notify_keyval(GLib.get_monotonic_time(), Clutter.KEY_Escape, Clutter.KeyState.RELEASED);
    }
    disable() {
        if (this.timer) GLib.source_remove(this.timer);
        this.keyboard?.run_dispose();
        this.pointer?.run_dispose();
        this.bus?.unexport();
        this.keyboard = null;
    }
}
''')
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", "['quick-ocr-test@local']"], env=environment, check=True)
        log_path = ROOT / "build/quick-ocr-compositor.log"
        with log_path.open("w") as log:
            shell = subprocess.Popen(["gnome-shell", "--headless", "--wayland", "--no-x11", "--wayland-display=powertoys-ocr-test", "--virtual-monitor=1600x900"], env=environment, stdout=log, stderr=log)
            try:
                wait_until(lambda: (root / "runtime/powertoys-ocr-test").exists())
                subprocess.run(["/usr/bin/python3", str(Path(__file__).resolve()), "--session"], env=environment, check=True, timeout=50)
            finally:
                shell.terminate()
                try:
                    shell.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    shell.kill()
                    shell.wait()


if __name__ == "__main__":
    if sys.argv[1:2] == ["--worker"]:
        from powertoys_linux.quick_ocr import QuickOcr, Gtk
        from powertoys_linux import ocr
        import shutil
        if not Gtk.init_check()[0]:
            raise RuntimeError("Cannot connect worker to the isolated compositor.")
        original_load = ocr.load_image
        def load_test_capture(path):
            shutil.copy2(path, ROOT / "build/native-region-test.png")
            image = original_load(path)
            print(f"Native test capture: {image.get_width()}x{image.get_height()}", flush=True)
            return image
        ocr.load_image = load_test_capture
        app = QuickOcr()
        app.notify = lambda message: print(message, flush=True)
        raise SystemExit(app.run([sys.argv[0], *sys.argv[2:]]))
    session() if sys.argv[1:] == ["--session"] else main()
