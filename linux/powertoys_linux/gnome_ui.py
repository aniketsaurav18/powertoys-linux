# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Native views for GNOME desktop and compositor tools."""

from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk

from .gnome_settings import GnomeSettings, WINDOW_SHORTCUTS, scheduled_theme
from .windows import WindowBackend


ACCENTS = {
    "a": "áàâäãåāăąæ", "c": "çćčĉċ", "d": "ďđ", "e": "éèêëēėęěĕ",
    "g": "ğģĝġ", "h": "ĥħ", "i": "íìîïīįĭı", "j": "ĵ", "k": "ķ",
    "l": "łĺļľŀ", "n": "ñńňņŋ", "o": "óòôöõøōőŏœ", "r": "ŕřŗ",
    "s": "śšşŝșß", "t": "ťţțŧ", "u": "úùûüūůűŭųũ", "w": "ŵẃẁẅ",
    "y": "ýÿŷ", "z": "źżž",
}


class GnomeViews:
    def init_gnome(self):
        self.preferences = GnomeSettings()
        self.theme_timer = 0
        self.window_state = {"windows": [], "monitors": []}

    def spin(self, box, label, minimum, maximum, value, step=1):
        row = Gtk.Box(spacing=10)
        row.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
        control = Gtk.SpinButton.new_with_range(minimum, maximum, step)
        control.set_value(value)
        row.pack_start(control, False, False, 0)
        box.pack_start(row, False, False, 0)
        return control

    def window_tools_page(self):
        box = self.page("windows", "Window tools", "GNOME Window Tools extension: zone layouts, Always on Top, window cycling and explicit move/resize. Coordinates use logical desktop pixels. Install and enable the extension, then refresh.")
        self.button(box, "Refresh windows and monitors", self.refresh_windows)
        self.window_list = Gtk.ListStore(int, str, str)
        tree = Gtk.TreeView(model=self.window_list)
        for index, title in ((1, "Window"), (2, "Application")):
            tree.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=index))
        tree.get_selection().connect("changed", self.window_selected)
        self.window_selection = tree.get_selection()
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(160)
        scroll.add(tree)
        box.pack_start(scroll, True, True, 0)
        self.monitor_choice = Gtk.ComboBoxText()
        box.pack_start(self.monitor_choice, False, False, 0)
        self.columns = self.spin(box, "Zone columns", 1, 6, 2)
        self.rows = self.spin(box, "Zone rows", 1, 6, 1)
        self.zone_index = self.spin(box, "Zone number (left to right, top to bottom)", 1, 36, 1)
        self.zone_gap = self.spin(box, "Zone margin (logical pixels)", 0, 64, 8)
        self.zone_preview = Gtk.DrawingArea()
        self.zone_preview.set_size_request(-1, 130)
        self.zone_preview.connect("draw", self.draw_zones)
        box.pack_start(self.zone_preview, False, False, 0)
        self.columns.connect("value-changed", self.layout_changed)
        self.rows.connect("value-changed", self.layout_changed)
        self.layout_changed()
        self.button(box, "Snap selected window to zone", self.snap_window)
        row = Gtk.Box(spacing=8)
        box.pack_start(row, False, False, 0)
        self.button(row, "Always on Top", lambda: self.pin_window(True))
        self.button(row, "Unpin", lambda: self.pin_window(False))
        self.button(row, "Activate", lambda: WindowBackend().activate(self.selected_window()))
        row = Gtk.Box(spacing=8)
        box.pack_start(row, False, False, 0)
        self.button(row, "Previous window", lambda: WindowBackend().cycle(-1))
        self.button(row, "Next window", lambda: WindowBackend().cycle(1))
        self.window_x = self.spin(box, "X", -100000, 100000, 0)
        self.window_y = self.spin(box, "Y", -100000, 100000, 0)
        self.window_width = self.spin(box, "Width", 64, 65536, 800)
        self.window_height = self.spin(box, "Height", 64, 65536, 600)
        self.button(box, "Apply position and size", self.move_window)
        self.window_details = Gtk.Label(label="No window selected", xalign=0)
        self.window_details.set_line_wrap(True)
        box.pack_start(self.window_details, False, False, 0)
        label = Gtk.Label(label="Optional global shortcuts (unbound by default). Use GTK notation, e.g. <Super><Control>Right. Leave empty to disable.", xalign=0)
        label.set_line_wrap(True)
        box.pack_start(label, False, False, 0)
        self.window_shortcut_entries = {}
        for key, title in WINDOW_SHORTCUTS.items():
            entry = Gtk.Entry(placeholder_text=title)
            self.window_shortcut_entries[key] = entry
            row = Gtk.Box(spacing=8)
            row.pack_start(Gtk.Label(label=title, xalign=0), True, True, 0)
            row.pack_start(entry, False, False, 0)
            box.pack_start(row, False, False, 0)
        self.button(box, "Read current window shortcuts", self.read_window_shortcuts)
        self.button(box, "Save window shortcuts", self.save_window_shortcuts)
        self.drag_modifier = Gtk.ComboBoxText()
        self.drag_modifier.append("<Super>", "Super + drag")
        self.drag_modifier.append("<Alt>", "Alt + drag")
        self.drag_modifier.set_active(0)
        box.pack_start(self.drag_modifier, False, False, 0)
        self.button(box, "Apply move/resize drag modifier", self.apply_drag_modifier)

    def apply_drag_modifier(self):
        self.preferences.set("windows", "mouse-button-modifier", self.drag_modifier.get_active_id())
        self.preferences.set("windows", "resize-with-right-button", True)
        self.status.set_text("Hold the chosen modifier and drag: primary button to move, secondary button to resize. GNOME applies this to native Wayland windows.")

    def read_window_shortcuts(self):
        settings = self.preferences.window_shortcut_settings()
        for key, entry in self.window_shortcut_entries.items():
            values = settings.get_strv(key)
            entry.set_text(values[0] if values else "")

    def save_window_shortcuts(self):
        values, seen = {}, set()
        existing = set()
        for _, bindings, _ in self.preferences.shortcuts():
            for value in bindings.split(", "):
                keyval, modifiers = Gtk.accelerator_parse(value)
                if keyval:
                    existing.add(Gtk.accelerator_name(keyval, modifiers))
        for key, entry in self.window_shortcut_entries.items():
            text = entry.get_text().strip()
            if not text:
                values[key] = []
                continue
            keyval, modifiers = Gtk.accelerator_parse(text)
            if not Gtk.accelerator_valid(keyval, modifiers) or not modifiers & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.SUPER_MASK):
                raise ValueError("Shortcuts need a valid key with Control, Alt or Super.")
            canonical = Gtk.accelerator_name(keyval, modifiers)
            if canonical in seen or canonical in existing:
                raise ValueError(f"Shortcut is already assigned: {canonical}")
            seen.add(canonical)
            values[key] = [canonical]
        settings = self.preferences.window_shortcut_settings()
        if any(not settings.is_writable(key) for key in values):
            raise RuntimeError("A window shortcut preference is locked.")
        settings.delay()
        try:
            for key, value in values.items():
                if not settings.set_strv(key, value):
                    raise ValueError("GNOME rejected a shortcut preference.")
            settings.apply()
        except Exception:
            settings.revert()
            raise
        self.status.set_text("Window shortcuts saved. They become active when the GNOME extension is enabled.")

    def layout_changed(self, *_):
        self.zone_index.set_range(1, self.columns.get_value_as_int() * self.rows.get_value_as_int())
        self.zone_preview.queue_draw()

    def draw_zones(self, widget, context):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        columns, rows = self.columns.get_value_as_int(), self.rows.get_value_as_int()
        context.set_source_rgb(0.25, 0.55, 0.8)
        for index in range(columns * rows):
            x, y = index % columns * width / columns, index // columns * height / rows
            context.rectangle(x + 4, y + 4, width / columns - 8, height / rows - 8)
            context.stroke()
            context.move_to(x + 15, y + 25)
            context.show_text(str(index + 1))

    def refresh_windows(self):
        state = WindowBackend().state()
        old = self.window_selection.get_selected()
        selected = old[0][old[1]][0] if old[1] else None
        self.window_state = state
        self.window_list.clear()
        self.monitor_choice.remove_all()
        for monitor in state["monitors"]:
            self.monitor_choice.append(str(monitor["index"]), f"Monitor {monitor['index'] + 1} · {monitor['width']}×{monitor['height']} logical pixels · scale {monitor['scale']}")
        self.monitor_choice.set_active(0)
        for window in state["windows"]:
            iterator = self.window_list.append((window["id"], window["title"], window.get("app", "")))
            if window["id"] == selected:
                self.window_selection.select_iter(iterator)
        self.status.set_text(f"{len(state['windows'])} windows and {len(state['monitors'])} monitors available.")

    def selected_window(self):
        model, iterator = self.window_selection.get_selected()
        if iterator is None:
            raise ValueError("Select a window first.")
        return model[iterator][0]

    def selected_monitor(self):
        value = self.monitor_choice.get_active_id()
        if value is None:
            raise ValueError("Refresh and select a monitor first.")
        return int(value)

    def window_selected(self, selection):
        model, iterator = selection.get_selected()
        if iterator is None:
            return
        window = next(item for item in self.window_state["windows"] if item["id"] == model[iterator][0])
        for key, control in (("x", self.window_x), ("y", self.window_y), ("width", self.window_width), ("height", self.window_height)):
            control.set_value(window["rect"][key])
        self.monitor_choice.set_active_id(str(window["monitor"]))
        self.window_details.set_text(f"{window['title']} · {'Pinned' if window['above'] else 'Unpinned'} · workspace {window['workspace'] + 1}")

    def snap_window(self):
        WindowBackend().snap(self.selected_window(), self.selected_monitor(), self.columns.get_value_as_int(), self.rows.get_value_as_int(), self.zone_index.get_value_as_int() - 1, self.zone_gap.get_value_as_int())
        self.status.set_text("Window placement requested. Refresh to see its actual size; applications can enforce minimum dimensions.")

    def pin_window(self, enabled):
        WindowBackend().above(self.selected_window(), enabled)
        self.status.set_text("Window pinned above other windows." if enabled else "Window unpinned.")

    def move_window(self):
        WindowBackend().move_resize(self.selected_window(), self.selected_monitor(), *(control.get_value_as_int() for control in (self.window_x, self.window_y, self.window_width, self.window_height)))
        self.status.set_text("Position and size requested. Refresh to inspect the result.")

    def lightswitch_page(self):
        box = self.page("lightswitch", "Light Switch", "Set GNOME's light/dark preference, or switch on a daily schedule while this app is open. Changes persist in your desktop settings.")
        self.theme_choice = Gtk.ComboBoxText()
        for key, title in (("default", "Desktop default"), ("prefer-light", "Light"), ("prefer-dark", "Dark")):
            self.theme_choice.append(key, title)
        self.theme_choice.set_active(0)
        box.pack_start(self.theme_choice, False, False, 0)
        self.button(box, "Apply appearance", self.apply_theme)
        self.light_hour = self.spin(box, "Light starts at hour", 0, 23, 7)
        self.dark_hour = self.spin(box, "Dark starts at hour", 0, 23, 20)
        self.button(box, "Start daily schedule", self.start_theme_schedule)
        self.button(box, "Stop daily schedule", self.stop_theme_schedule)
        self.theme_state = Gtk.Label(label="Schedule off", xalign=0)
        box.pack_start(self.theme_state, False, False, 0)

    def apply_theme(self):
        self.preferences.theme(self.theme_choice.get_active_id())
        self.status.set_text("GNOME appearance preference updated.")

    def update_scheduled_theme(self):
        try:
            value = scheduled_theme(datetime.now().hour, self.light_hour.get_value_as_int(), self.dark_hour.get_value_as_int())
            self.preferences.theme(value)
        except Exception as error:
            self.theme_timer = 0
            self.theme_state.set_text("Schedule stopped")
            self.status.set_text(str(error))
            return False
        return True

    def start_theme_schedule(self):
        self.stop_theme_schedule()
        if self.update_scheduled_theme():
            self.theme_timer = GLib.timeout_add_seconds(60, self.update_scheduled_theme)
            self.theme_state.set_text("Schedule on while app is open")
            self.status.set_text("Daily appearance schedule started.")

    def stop_theme_schedule(self):
        if self.theme_timer:
            GLib.source_remove(self.theme_timer)
            self.theme_timer = 0
        if hasattr(self, "theme_state"):
            self.theme_state.set_text("Schedule off")

    def zoom_page(self):
        box = self.page("zoom", "ZoomIt", "Control GNOME's desktop magnifier, including native Wayland applications. Drawing, annotation and recording are planned for a later stage.")
        self.zoom_factor = self.spin(box, "Magnification", 1, 8, 2, 0.25)
        self.button(box, "Enable desktop zoom", lambda: self.set_zoom(True))
        self.button(box, "Disable desktop zoom", lambda: self.set_zoom(False))
        self.zoom_crosshairs = Gtk.CheckButton(label="Show crosshairs while magnifier is enabled")
        box.pack_start(self.zoom_crosshairs, False, False, 0)
        self.button(box, "Apply crosshairs preference", self.set_crosshairs)

    def set_zoom(self, enabled):
        self.preferences.zoom(enabled, self.zoom_factor.get_value())
        self.status.set_text("Desktop magnifier enabled." if enabled else "Desktop magnifier disabled.")

    def set_crosshairs(self):
        self.preferences.set("magnifier", "show-cross-hairs", self.zoom_crosshairs.get_active())
        self.status.set_text("Magnifier crosshairs preference updated.")

    def mouse_page(self):
        box = self.page("mouse", "Mouse utilities", "Adjust GNOME's cursor size and pointer locator. When enabled, pressing Control highlights the pointer. Other pointer overlays and cursor wrapping need additional compositor support.")
        self.cursor_size = self.spin(box, "Cursor size", 16, 96, 24)
        self.locate_pointer = Gtk.CheckButton(label="Highlight pointer when Control is pressed")
        box.pack_start(self.locate_pointer, False, False, 0)
        self.button(box, "Read current preferences", self.read_mouse)
        self.button(box, "Apply pointer preferences", self.apply_mouse)
        self.guard(self.read_mouse)

    def read_mouse(self):
        self.cursor_size.set_value(self.preferences.get("interface", "cursor-size"))
        self.locate_pointer.set_active(self.preferences.get("interface", "locate-pointer"))

    def apply_mouse(self):
        self.preferences.cursor(self.cursor_size.get_value_as_int(), self.locate_pointer.get_active())
        self.status.set_text("GNOME pointer preferences updated.")

    def shortcut_page(self):
        box = self.page("shortcuts", "Shortcut Guide", "Browse configured GNOME desktop shortcuts. Super is the Windows/Meta key. This guide reads the desktop's current settings; it does not replace shortcuts.")
        self.shortcut_store = Gtk.ListStore(str, str, str)
        self.button(box, "Refresh configured shortcuts", self.refresh_shortcuts)
        tree = Gtk.TreeView(model=self.shortcut_store)
        for index, title in enumerate(("Action", "Shortcut", "Settings schema")):
            tree.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=index))
        box.pack_start(tree, True, True, 0)
        self.guard(self.refresh_shortcuts)

    def refresh_shortcuts(self):
        self.shortcut_store.clear()
        for shortcut in self.preferences.shortcuts():
            self.shortcut_store.append(shortcut)

    def accent_page(self):
        box = self.page("accents", "Quick Accent", "Choose accented Latin characters and copy them to your clipboard. Hold-to-type activation and input-method integration are planned for a later stage.")
        self.accent_letter = Gtk.ComboBoxText()
        for letter in sorted(ACCENTS):
            self.accent_letter.append_text(letter)
        self.accent_letter.set_active(0)
        box.pack_start(self.accent_letter, False, False, 0)
        self.accent_uppercase = Gtk.CheckButton(label="Uppercase")
        box.pack_start(self.accent_uppercase, False, False, 0)
        self.accent_grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
        box.pack_start(self.accent_grid, False, False, 0)
        self.accent_letter.connect("changed", self.refresh_accents)
        self.accent_uppercase.connect("toggled", self.refresh_accents)
        self.refresh_accents()

    def refresh_accents(self, *_):
        for child in self.accent_grid.get_children():
            self.accent_grid.remove(child)
        characters = ACCENTS[self.accent_letter.get_active_text()]
        for character in characters:
            value = ("ẞ" if character == "ß" else character.upper()) if self.accent_uppercase.get_active() else character
            button = Gtk.Button(label=value)
            button.connect("clicked", lambda _, text=value: self.copy_accent(text))
            self.accent_grid.add(button)
        self.accent_grid.show_all()

    def copy_accent(self, value):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(value, -1)
        self.status.set_text(f"Copied {value}. Keep this app open until you paste.")
