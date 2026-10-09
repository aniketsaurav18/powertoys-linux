# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import random
import tempfile
import unittest
from pathlib import Path

from gi.repository import Gio
from powertoys_linux.gnome_settings import GnomeSettings
from powertoys_linux.ocr_shortcut import CUSTOM_SCHEMA, DEFAULT_BINDING, OcrShortcut, SHORTCUT_PATH, canonical_binding


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.executable = Path(self.folder.name) / "PowerToys with spaces"
        self.executable.write_text("#!/bin/sh\nexit 0\n")
        self.preferences = GnomeSettings(Gio.memory_settings_backend_new())
        self.shortcut = OcrShortcut(self.preferences, self.executable)
        self.other_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/other/"
        schema = self.preferences.source.lookup(CUSTOM_SCHEMA, True)
        self.other = Gio.Settings.new_full(schema, self.preferences.backend, self.other_path)
        self.other.set_string("name", "Existing shortcut")
        self.other.set_string("command", "/usr/bin/true")
        self.shortcut.media.set_strv("custom-keybindings", [self.other_path])

    def test_save_update_remove_preserves_other_shortcuts(self):
        binding = self.shortcut.save()
        self.assertEqual(binding, canonical_binding(DEFAULT_BINDING))
        self.assertEqual(self.shortcut.read(), binding)
        self.assertEqual(self.shortcut.media.get_strv("custom-keybindings"), [self.other_path, SHORTCUT_PATH])
        self.assertTrue(self.shortcut.custom.get_string("command").endswith("' --ocr"))
        self.shortcut.save("<Control><Alt>F11")
        self.assertEqual(self.shortcut.media.get_strv("custom-keybindings").count(SHORTCUT_PATH), 1)
        self.shortcut.remove()
        self.assertEqual(self.shortcut.read(), "")
        self.assertEqual(self.shortcut.media.get_strv("custom-keybindings"), [self.other_path])
        self.assertEqual(self.other.get_string("command"), "/usr/bin/true")
        self.assertEqual(OcrShortcut(self.preferences, self.executable).custom.get_string("binding"), "")

    def test_refuses_conflicting_custom_shortcut(self):
        self.other.set_string("binding", "<Shift><Super>t")
        with self.assertRaisesRegex(ValueError, "Existing shortcut"):
            self.shortcut.save()
        self.assertEqual(self.shortcut.media.get_strv("custom-keybindings"), [self.other_path])

    def test_refuses_conflicting_window_extension_shortcut(self):
        settings = self.preferences.window_shortcut_settings()
        settings.set_strv("powertoys-launcher", [DEFAULT_BINDING])
        with self.assertRaisesRegex(ValueError, "powertoys-launcher"):
            self.shortcut.save()

    def test_refuses_foreign_command_at_own_path(self):
        self.shortcut.custom.set_string("command", "/usr/bin/false")
        for action in (self.shortcut.read, self.shortcut.save, self.shortcut.remove):
            with self.assertRaisesRegex(ValueError, "another command"):
                action()

    def test_requires_installed_command(self):
        self.executable.unlink()
        with self.assertRaisesRegex(RuntimeError, "Install"):
            self.shortcut.save()

    def test_invalid_accelerators(self):
        for binding in (None, [], "", "t", "<Shift>t", "<Super>", "<Super>t\x00", "x" * 121):
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                canonical_binding(binding)

    def test_fuzz_shortcut_strings(self):
        rng = random.Random(904)
        for _ in range(300):
            value = rng.choice(("", "<Shift>", "<Control>", "<Alt><Super>", "<Super><Shift>")) + rng.choice(("t", "F11", "Escape", "", "badkey"))
            try:
                binding = canonical_binding(value)
                self.assertEqual(canonical_binding(binding), binding)
            except ValueError:
                pass
