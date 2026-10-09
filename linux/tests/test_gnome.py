# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import json
import random
import unittest
from unittest.mock import Mock

from gi.repository import Gio, GLib

from powertoys_linux.gnome_settings import GnomeSettings, scheduled_theme
from powertoys_linux.windows import WindowBackend, validate_state


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.preferences = GnomeSettings(Gio.memory_settings_backend_new())

    def test_theme_zoom_pointer_roundtrip_without_changing_desktop(self):
        self.preferences.theme("prefer-dark")
        self.assertEqual(self.preferences.get("interface", "color-scheme"), "prefer-dark")
        self.preferences.zoom(True, 2.5)
        self.assertTrue(self.preferences.get("accessibility", "screen-magnifier-enabled"))
        self.assertEqual(self.preferences.get("magnifier", "mag-factor"), 2.5)
        self.preferences.zoom(False)
        self.assertFalse(self.preferences.get("accessibility", "screen-magnifier-enabled"))
        self.preferences.cursor(48, True)
        self.assertEqual(self.preferences.get("interface", "cursor-size"), 48)
        self.assertTrue(self.preferences.get("interface", "locate-pointer"))

    def test_invalid_preference_values(self):
        for method, args in ((self.preferences.theme, ("invalid",)), (self.preferences.zoom, (True, 100)), (self.preferences.cursor, (0, True))):
            with self.subTest(args=args), self.assertRaises(ValueError):
                method(*args)

    def test_schedule_boundaries_and_midnight(self):
        for hour, expected in ((6, "prefer-dark"), (7, "prefer-light"), (19, "prefer-light"), (20, "prefer-dark"), (0, "prefer-dark")):
            self.assertEqual(scheduled_theme(hour, 7, 20), expected)
        self.assertEqual(scheduled_theme(23, 20, 7), "prefer-light")
        self.assertEqual(scheduled_theme(8, 20, 7), "prefer-dark")
        with self.assertRaises(ValueError):
            scheduled_theme(1, 5, 5)

    def test_shortcuts_discovered_from_installed_schemas(self):
        shortcuts = self.preferences.shortcuts()
        self.assertTrue(shortcuts)
        self.assertTrue(all(len(item) == 3 and all(isinstance(value, str) for value in item) for item in shortcuts))

    def test_extension_shortcuts_unbound_by_default(self):
        settings = self.preferences.window_shortcut_settings()
        for key in settings.props.settings_schema.list_keys():
            self.assertEqual(settings.get_strv(key), [])
        settings.set_strv("powertoys-cycle-next", ["<Super><Control>F9"])
        self.assertEqual(self.preferences.window_shortcut_settings().get_strv("powertoys-cycle-next"), ["<Super><Control>F9"])

    def test_custom_desktop_shortcuts_show_binding_instead_of_config_path(self):
        path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/powertoys-test/"
        media = self.preferences.settings("org.gnome.settings-daemon.plugins.media-keys")
        media.set_strv("custom-keybindings", [path])
        schema = self.preferences.source.lookup("org.gnome.settings-daemon.plugins.media-keys.custom-keybinding", True)
        custom = Gio.Settings.new_full(schema, self.preferences.backend, path)
        custom.set_string("name", "Test shortcut")
        custom.set_string("binding", "<Control><Alt>F11")
        rows = self.preferences.shortcuts()
        self.assertIn(("Test shortcut", "<Control><Alt>F11", schema.get_id()), rows)
        self.assertFalse(any(row[0] == "custom-keybindings" for row in rows))

    def test_fuzz_schedule_inputs(self):
        rng = random.Random(730)
        for _ in range(500):
            values = [rng.randrange(-30, 60) for _ in range(3)]
            if all(0 <= value <= 23 for value in values) and values[1] != values[2]:
                self.assertIn(scheduled_theme(*values), ("prefer-dark", "prefer-light"))
            else:
                with self.assertRaises(ValueError):
                    scheduled_theme(*values)


class WindowBackendTests(unittest.TestCase):
    def test_state_and_snap_protocol(self):
        connection = Mock()
        state = {"version": 1, "windows": [{"id": 1, "title": "Example", "monitor": 0, "workspace": 0, "above": False, "fullscreen": False, "rect": {"x": 0, "y": 0, "width": 500, "height": 300}}], "monitors": [{"index": 0, "x": 0, "y": 0, "width": 1600, "height": 900, "scale": 1}]}
        connection.call_sync.return_value = GLib.Variant("(s)", (json.dumps(state),))
        backend = WindowBackend(connection)
        self.assertEqual(backend.state(), state)
        connection.call_sync.return_value = GLib.Variant("(b)", (True,))
        backend.snap(1, 0, 2, 1, 0)
        self.assertEqual(connection.call_sync.call_args[0][3], "Snap")
        self.assertEqual(connection.call_sync.call_args[0][4].unpack(), (1, 0, 2, 1, 0, 8))
        backend.move_resize(1, 0, -200, 10, 500, 400)
        self.assertEqual(connection.call_sync.call_args[0][4].get_type_string(), "(uuiiuu)")

    def test_reject_invalid_state(self):
        for value in ([], {}, {"version": 99}, {"version": 1, "windows": [], "monitors": [None]}, {"version": 1, "windows": [{"id": "bad", "title": ""}], "monitors": []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_state(value)

    def test_fuzz_backend_responses(self):
        rng = random.Random(731)
        connection = Mock()
        backend = WindowBackend(connection)
        for _ in range(250):
            data = "".join(rng.choices("abc:{}[]012,\n", k=rng.randrange(0, 200)))
            connection.call_sync.return_value = GLib.Variant("(s)", (data,))
            with self.assertRaises(ValueError):
                backend.state()
