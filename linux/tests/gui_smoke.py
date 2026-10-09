#!/usr/bin/python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Run in a GNOME session after test.sh; optional widget capture via Cairo."""

import sys
import tempfile
import traceback
from pathlib import Path

from powertoys_linux.app import PowerToys
from powertoys_linux.gnome_settings import GnomeSettings
from gi.repository import Gio, GLib


class DesktopTest(PowerToys):
    def __init__(self):
        super().__init__(application_id="io.github.powertoys.Linux.DesktopTest")
        self.preferences = GnomeSettings(Gio.memory_settings_backend_new())
        self.failed = False

    def do_activate(self):
        super().do_activate()
        GLib.timeout_add(600, self.run_checks)

    def run_checks(self):
        try:
            self.checks()
            self.stack.set_visible_child_name("lightswitch")
            GLib.timeout_add(500, self.capture)
        except Exception:
            traceback.print_exc()
            self.failed = True
            self.quit()
        return False

    def checks(self):
        assert len(self.stack.get_children()) == 18
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "photo.txt"
            path.write_text("Hello Linux")
            self.files = [str(path)]
            self.find.set_text("photo")
            self.replace.set_text("picture")
            self.preview_rename()
            assert len(self.preview) == 1 and self.apply_button.get_sensitive()
            self.apply_rename()
            assert not path.exists() and (path.parent / "picture.txt").read_text() == "Hello Linux"
            self.undo_rename()
            assert path.read_text() == "Hello Linux"
            self.show_preview(path)
            assert self.peek_content.get_children()[0].get_buffer().get_text(
                *self.peek_content.get_children()[0].get_buffer().get_bounds(), True) == "Hello Linux"
            self.template = str(path)
            self.template_folder = directory
            self.new_name.set_text("from-template.txt")
            self.create_from_template()
            assert (Path(directory) / "from-template.txt").read_text() == "Hello Linux"
            self.workspace_config = Path(directory) / "workspaces.json"
            self.workspace_name.set_text("Smoke Test")
            first = self.workspace_apps.get_row_at_index(0)
            self.workspace_apps.select_row(first)
            self.save_workspace()
            assert self.workspace_choice.get_active_text() == "Smoke Test"
            self.delete_workspace()
            assert self.workspace_choice.get_active_text() is None
            self.color_received((1, 0, 0), None)
            assert self.color_hex.get_text() == "#FF0000"
            self.text.get_buffer().set_text('{"linux":true}')
            self.convert_text()
            assert '"linux": true' in self.get_text()
            self.search.set_text("unlikely-application-1823895")
            self.filter_apps()
            assert not self.app_list.get_children()
            self.launch(Gio.AppInfo.create_from_commandline("/usr/bin/true", "Smoke Test", Gio.AppInfoCreateFlags.NONE))

        self.minutes.set_value(1)
        self.start_awake()
        assert self.inhibitor and self.awake_timer
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        def call(path, interface, method):
            return connection.call_sync("org.gnome.SessionManager", path, interface, method,
                                        None, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        def ours():
            paths = call("/org/gnome/SessionManager", "org.gnome.SessionManager", "GetInhibitors")
            return [(path, call(path, "org.gnome.SessionManager.Inhibitor", "GetFlags")) for path in paths
                    if call(path, "org.gnome.SessionManager.Inhibitor", "GetAppId") == self.get_application_id()]
        inhibitors = ours()
        assert inhibitors and all(flags == 4 for path, flags in inhibitors), inhibitors
        self.stop_awake()
        assert not ours() and not self.inhibitor and not self.awake_timer
        self.keep_display.set_active(True)
        self.start_awake()
        assert all(flags == 12 for path, flags in ours())
        self.stop_awake()
        self.keep_display.set_active(False)
        self.theme_choice.set_active_id("prefer-dark")
        self.apply_theme()
        assert self.preferences.get("interface", "color-scheme") == "prefer-dark"
        self.start_theme_schedule()
        assert self.theme_timer
        self.stop_theme_schedule()
        assert not self.theme_timer
        self.set_zoom(True)
        assert self.preferences.get("accessibility", "screen-magnifier-enabled")
        self.set_zoom(False)
        self.cursor_size.set_value(48)
        self.locate_pointer.set_active(True)
        self.apply_mouse()
        assert self.preferences.get("interface", "cursor-size") == 48
        assert len(self.shortcut_store) > 0
        assert self.accent_grid.get_children()
        self.window_shortcut_entries["powertoys-cycle-next"].set_text("<Super><Control>F9")
        self.save_window_shortcuts()
        self.read_window_shortcuts()
        assert "F9" in self.window_shortcut_entries["powertoys-cycle-next"].get_text()
        self.window_shortcut_entries["powertoys-toggle-above"].set_text("<Super><Control>F9")
        try:
            self.save_window_shortcuts()
        except ValueError:
            pass
        else:
            raise AssertionError("Duplicate global shortcut accepted")
        self.drag_modifier.set_active_id("<Alt>")
        self.apply_drag_modifier()
        assert self.preferences.get("windows", "mouse-button-modifier") == "<Alt>"
        self.search.set_text("")
        self.filter_apps()
        assert self.ocr_mode.get_active_text() == "Text block"
        assert not self.ocr_start_button.get_sensitive()
        self.ocr_shortcut_entry.set_text("<Super><Control>F11")
        self.ocr_save_shortcut()
        self.ocr_remove_shortcut()
        print("Desktop tests passed: 18 pages; existing workflows; theme/schedule, zoom and pointer controls against in-memory settings; shortcuts and accents; OCR controls; GNOME suspend/display inhibitors and cleanup.", flush=True)

    def capture(self):
        try:
            if len(sys.argv) > 1:
                import cairo
                width, height = self.window.get_allocated_width(), self.window.get_allocated_height()
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
                self.window.draw(cairo.Context(surface))
                surface.write_to_png(sys.argv[1])
                print(f"Widget capture: {sys.argv[1]}", flush=True)
        except Exception:
            traceback.print_exc()
            self.failed = True
        self.quit()
        return False


app = DesktopTest()
status = app.run([sys.argv[0]])
raise SystemExit(1 if app.failed else status)
