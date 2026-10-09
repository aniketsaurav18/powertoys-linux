#!/usr/bin/python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Private GNOME/Wayland test: portal fixture, real OCR, real clipboard and IPC."""

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
    path = Path(os.environ["XDG_RUNTIME_DIR"]) / "selection.png"
    image = cairo.ImageSurface(cairo.FORMAT_RGB24, 1000, 140)
    context = cairo.Context(image)
    context.set_source_rgb(1, 1, 1)
    context.paint()
    context.set_source_rgb(0, 0, 0)
    context.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    context.set_font_size(45)
    context.move_to(30, 85)
    context.show_text("POWERTOYS LINUX OCR")
    image.write_to_png(str(path))
    before = path.read_bytes()
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    xml = '<node><interface name="org.freedesktop.portal.Screenshot"><method name="Screenshot"><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method></interface></node>'
    requests = []

    def capture(conn, sender, object_path, interface, method, parameters, invocation):
        parent, options = parameters.unpack()
        assert options["interactive"] is True
        token = options["handle_token"]
        handle = "/org/freedesktop/portal/desktop/request/" + sender[1:].replace(".", "_") + "/" + token
        requests.append(handle)
        invocation.return_value(GLib.Variant("(o)", (handle,)))

        def selected():
            conn.emit_signal(sender, handle, "org.freedesktop.portal.Request", "Response", GLib.Variant("(ua{sv})", (0, {"uri": GLib.Variant("s", path.as_uri())})))
            return False

        GLib.timeout_add(800, selected)

    info = Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]
    registration = connection.register_object("/org/freedesktop/portal/desktop", info, capture, None, None)
    owner = Gio.bus_own_name_on_connection(connection, "org.freedesktop.portal.Desktop", Gio.BusNameOwnerFlags.NONE, None, None)
    window = Gtk.Window(title="Quick OCR paste target")
    window.set_default_size(700, 250)
    window.add(Gtk.TextView())
    window.show_all()

    def pump():
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    wait_until(window.is_active, pump)
    command = ["/usr/bin/python3", str(ROOT / "launch.py"), "--ocr"]
    log_path = ROOT / "build/quick-ocr-app.log"
    with log_path.open("w") as log:
        service = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            wait_until(lambda: len(requests) == 1, pump)
            duplicate = subprocess.Popen(command, stdout=log, stderr=log)
            wait_until(lambda: duplicate.poll() is not None, pump)
            assert duplicate.returncode == 0
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            received = []

            def read_clipboard():
                if window.is_active():
                    clipboard.request_text(lambda _, text, data: received.append(text), None)
                return "POWERTOYS LINUX OCR" in received

            wait_until(read_clipboard, pump)
            assert len(requests) == 1, "Duplicate shortcut opened another capture."
            assert service.poll() is None, "Clipboard owner exited before paste."
            repeat = subprocess.Popen(command, stdout=log, stderr=log)
            wait_until(lambda: len(requests) == 2, pump)
            wait_until(lambda: repeat.poll() is not None, pump)
            assert repeat.returncode == 0
            # Wait for a second clipboard ownership change and another paste.
            received.clear()
            time.sleep(1)
            wait_until(read_clipboard, pump)
            stop = subprocess.Popen([*command[:-1], "--stop-ocr"], stdout=log, stderr=log)
            wait_until(lambda: stop.poll() is not None and service.poll() is not None, pump)
            assert stop.returncode == service.returncode == 0
            assert path.read_bytes() == before
            print("Quick OCR Wayland integration passed: portal selection fixture → real Tesseract → clipboard read by another process; duplicate/repeated commands use one instance; owner persists until Stop.", flush=True)
        finally:
            if service.poll() is None:
                service.terminate()
                try:
                    service.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    service.kill()
                    service.wait()
            window.destroy()
            connection.unregister_object(registration)
            Gio.bus_unown_name(owner)


def main():
    from powertoys_linux.ocr import find_engine
    engine = find_engine()
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
        environment.update(GSETTINGS_BACKEND="keyfile", LIBGL_ALWAYS_SOFTWARE="1", GDK_BACKEND="wayland", WAYLAND_DISPLAY="powertoys-ocr-test", NO_AT_BRIDGE="1")
        # A headless compositor has no physical keyboard. Provide one only in
        # the isolated test session, and dismiss its startup overview.
        extension = root / "data/gnome-shell/extensions/quick-ocr-test@local"
        extension.mkdir(parents=True)
        (extension / "metadata.json").write_text(json.dumps({"uuid": "quick-ocr-test@local", "name": "Quick OCR Test Fixture", "description": "Private test keyboard", "shell-version": ["46"]}))
        (extension / "extension.js").write_text('''
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
export default class Fixture extends Extension {
    enable() {
        this.keyboard = Clutter.get_default_backend().get_default_seat().create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1000, () => {
            Main.overview.hide();
            this.timer = 0;
            return GLib.SOURCE_REMOVE;
        });
    }
    disable() {
        if (this.timer) GLib.source_remove(this.timer);
        this.keyboard?.run_dispose();
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
    session() if sys.argv[1:] == ["--session"] else main()
