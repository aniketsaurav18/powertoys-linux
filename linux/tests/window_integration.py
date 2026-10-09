#!/usr/bin/python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Run via test-window-tools.sh; starts an isolated, two-monitor compositor."""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UUID = "powertoys-linux@local"


def wait_until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except Exception as error:
            last_error = error
        time.sleep(0.1)
    raise TimeoutError(f"Integration condition timed out: {last_error}")


def main():
    with tempfile.TemporaryDirectory(prefix="powertoys-compositor-") as temporary:
        folder = Path(temporary)
        for key, name in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_RUNTIME_DIR", "runtime")):
            path = folder / name
            path.mkdir(mode=0o700)
            os.environ[key] = str(path)
        os.environ.update(GSETTINGS_BACKEND="keyfile", LIBGL_ALWAYS_SOFTWARE="1", GDK_BACKEND="wayland", WAYLAND_DISPLAY="powertoys-test")
        extension = folder / "data/gnome-shell/extensions" / UUID
        shutil.copytree(ROOT / "gnome-extension" / UUID, extension)
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", f"['{UUID}']"], check=True)
        subprocess.run(["gsettings", "set", "org.gnome.shell", "disable-user-extensions", "false"], check=True)
        log_path = ROOT / "build/window-integration.log"
        with log_path.open("w") as log:
            shell = subprocess.Popen(["gnome-shell", "--headless", "--wayland", "--no-x11", "--wayland-display=powertoys-test", "--virtual-monitor=1600x900", "--virtual-monitor=1200x800"], stdout=log, stderr=log)
            try:
                import gi
                gi.require_version("Gtk", "3.0")
                from powertoys_linux.windows import WindowBackend
                backend = WindowBackend()
                state = wait_until(lambda: backend.state())
                assert len(state["monitors"]) == 2, state
                from gi.repository import Gtk
                if not Gtk.init_check()[0]:
                    raise RuntimeError("Could not connect to the isolated compositor.")
                windows = [Gtk.Window(title=f"PowerToys Test {index}") for index in (1, 2, 3)]
                for window in windows:
                    window.set_default_size(400, 250)
                    window.show_all()
                def pump():
                    while Gtk.events_pending():
                        Gtk.main_iteration_do(False)
                    return backend.state()
                state = wait_until(lambda: (value if len(value["windows"]) == 3 else None) if (value := pump()) else None)
                # Allow initial Wayland configure/commit and Shell startup placement to finish.
                for _ in range(15):
                    pump()
                    time.sleep(0.1)
                state = pump()
                print("Initial compositor state:", state, flush=True)
                ids = [window["id"] for window in state["windows"]]
                first = ids[0]
                monitor = state["monitors"][0]
                backend.snap(first, monitor["index"], 2, 1, 0)
                def snapped():
                    value = next(w for w in pump()["windows"] if w["id"] == first)
                    return value if value["rect"]["x"] == monitor["x"] + 8 else None
                try:
                    placed = wait_until(snapped, timeout=5)
                except TimeoutError:
                    print("Failed snap state:", pump(), flush=True)
                    raise
                assert abs(placed["rect"]["width"] - (monitor["width"] // 2 - 16)) <= 2, placed
                backend.above(first, True)
                assert next(w for w in pump()["windows"] if w["id"] == first)["above"]
                backend.above(first, False)
                assert not next(w for w in pump()["windows"] if w["id"] == first)["above"]
                second_monitor = state["monitors"][1]
                backend.move_resize(first, second_monitor["index"], second_monitor["x"] + 20, second_monitor["y"] + 20, 500, 350)
                moved = wait_until(lambda: (value if value["monitor"] == second_monitor["index"] and value["rect"]["width"] == 500 else None) if (value := next(w for w in pump()["windows"] if w["id"] == first)) else None)
                assert moved["rect"]["height"] == 350
                backend.activate(first)
                for _ in range(3):
                    while Gtk.events_pending():
                        Gtk.main_iteration_do(False)
                    time.sleep(0.05)
                cycle = [backend.cycle(1) for _ in range(3)]
                assert set(cycle) == set(ids), cycle
                from powertoys_linux.app import PowerToys
                from powertoys_linux.gnome_settings import GnomeSettings
                from gi.repository import Gio
                app = PowerToys(application_id="io.github.powertoys.Linux.WindowTest")
                app.preferences = GnomeSettings(Gio.memory_settings_backend_new())
                app.register(None)
                app.activate()
                for _ in range(10):
                    pump()
                    time.sleep(0.1)
                app.refresh_windows()
                for row in app.window_list:
                    if row[0] == first:
                        app.window_selection.select_iter(row.iter)
                        break
                assert app.selected_window() == first
                assert app.selected_monitor() == second_monitor["index"]
                app.pin_window(True)
                assert next(w for w in pump()["windows"] if w["id"] == first)["above"]
                app.pin_window(False)
                app.columns.set_value(2)
                app.rows.set_value(1)
                app.zone_index.set_value(2)
                app.snap_window()
                wait_until(lambda: next(w for w in pump()["windows"] if w["id"] == first)["rect"]["x"] > second_monitor["x"] + second_monitor["width"] // 2)
                app.refresh_windows()
                assert app.window_width.get_value_as_int() == second_monitor["width"] // 2 - 16
                app.window_x.set_value(second_monitor["x"] + 20)
                app.window_y.set_value(second_monitor["y"] + 20)
                app.window_width.set_value(500)
                app.window_height.set_value(350)
                app.move_window()
                wait_until(lambda: next(w for w in pump()["windows"] if w["id"] == first)["rect"]["width"] == 500)
                app.window.destroy()
                app.pool.shutdown(wait=True)
                fixture_title = next(w for w in pump()["windows"] if w["id"] == first)["title"]
                fixture = next(w for w in windows if w.get_title() == fixture_title)
                fixture.fullscreen()
                wait_until(lambda: next(w for w in pump()["windows"] if w["id"] == first)["fullscreen"])
                try:
                    backend.snap(first, 0, 2, 1, 0)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Fullscreen placement was accepted")
                fixture.unfullscreen()
                wait_until(lambda: not next(w for w in pump()["windows"] if w["id"] == first)["fullscreen"])
                try:
                    backend.snap(first, 0, 2, 1, 999)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Invalid zone index was accepted")
                try:
                    backend.move_resize(first, 0, -100000, -100000, 100, 100)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Off-monitor placement was accepted")
                subprocess.run(["gnome-extensions", "disable", UUID], check=True)
                try:
                    backend.state()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Extension object remained exported after disable")
                for window in windows:
                    window.destroy()
                print("GNOME compositor integration passed: native Wayland windows, two virtual monitors, zone snap, pin/unpin, move/resize across monitors, full window cycle, native GUI controls, invalid-input rejection and disable cleanup.", flush=True)
            finally:
                shell.terminate()
                try:
                    shell.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    shell.kill()
                    shell.wait()


if __name__ == "__main__":
    main()
