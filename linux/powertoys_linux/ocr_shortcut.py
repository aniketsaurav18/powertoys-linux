# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Manage only PowerToys' own GNOME custom shortcut; preserve other entries."""

import shlex
import re
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio


MEDIA_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = MEDIA_SCHEMA + ".custom-keybinding"
SHORTCUT_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/powertoys-text-extractor/"
SHORTCUT_NAME = "PowerToys Text Extractor"
DEFAULT_BINDING = "<Super><Shift>t"
MODIFIER_ALIASES = {"primary": "Control", "ctrl": "Control", "control": "Control",
                    "alt": "Alt", "mod1": "Alt", "super": "Super", "shift": "Shift"}


def canonical_binding(value):
    if not isinstance(value, str) or len(value) > 120 or "\x00" in value:
        raise ValueError("Enter a valid shortcut with Control, Alt or Super.")
    match = re.fullmatch(r"((?:<[A-Za-z0-9]+>)*)((?:[A-Za-z0-9_]+|[^<>\s]))", value.strip())
    if not match:
        raise ValueError("Enter a valid shortcut with Control, Alt or Super.")
    modifiers = set()
    for token in re.findall(r"<([A-Za-z0-9]+)>", match[1]):
        if token.lower() not in MODIFIER_ALIASES:
            raise ValueError("Use Control, Alt, Shift or Super modifiers.")
        modifiers.add(MODIFIER_ALIASES[token.lower()])
    name = match[2]
    key = Gdk.keyval_from_name(name)
    if key == Gdk.KEY_VoidSymbol and len(name) == 1:
        key = Gdk.unicode_to_keyval(ord(name))
    if (not modifiers.intersection(("Control", "Alt", "Super")) or key in (0, Gdk.KEY_VoidSymbol)
            or name in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R", "Meta_L", "Meta_R", "Caps_Lock", "Num_Lock", "ISO_Level3_Shift")):
        raise ValueError("Enter a valid shortcut with Control, Alt or Super.")
    return "".join(f"<{modifier}>" for modifier in ("Shift", "Control", "Alt", "Super") if modifier in modifiers) + Gdk.keyval_name(Gdk.keyval_to_lower(key))


class OcrShortcut:
    def __init__(self, preferences, executable=None):
        self.preferences = preferences
        self.executable = Path(executable or Path.home() / ".local/bin/powertoys-linux")
        self.command = shlex.quote(str(self.executable)) + " --ocr"
        self.media = preferences.settings(MEDIA_SCHEMA)
        schema = preferences.source.lookup(CUSTOM_SCHEMA, True)
        if schema is None:
            raise RuntimeError("This desktop does not provide GNOME custom shortcuts.")
        self.custom = Gio.Settings.new_full(schema, preferences.backend, SHORTCUT_PATH)

    def registered(self):
        return SHORTCUT_PATH in self.media.get_strv("custom-keybindings")

    def check_owner(self):
        if self.custom.get_string("command") not in ("", self.command):
            raise ValueError("The PowerToys shortcut path is already used by another command.")

    def read(self):
        self.check_owner()
        return self.custom.get_string("binding") if self.registered() else ""

    def conflicts(self, binding):
        existing = list(self.preferences.shortcuts())
        if self.registered():
            own = (self.custom.get_string("name") or "Custom shortcut", self.custom.get_string("binding"), CUSTOM_SCHEMA)
            if own in existing:
                existing.remove(own)
        try:
            settings = self.preferences.window_shortcut_settings()
            for key in settings.props.settings_schema.list_keys():
                existing.append((key, ", ".join(settings.get_strv(key)), "window tools"))
        except RuntimeError:
            pass
        for name, values, _ in existing:
            for value in values.split(", "):
                try:
                    canonical = canonical_binding(value)
                except ValueError:
                    continue
                if canonical == binding:
                    raise ValueError(f"Shortcut already assigned to {name}.")

    def save(self, binding=DEFAULT_BINDING):
        self.check_owner()
        binding = canonical_binding(binding)
        if not self.executable.is_file():
            raise RuntimeError("Install PowerToys for this user before enabling its shortcut.")
        self.conflicts(binding)
        if not self.media.is_writable("custom-keybindings") or any(not self.custom.is_writable(key) for key in ("name", "command", "binding")):
            raise RuntimeError("GNOME custom shortcuts are locked.")
        paths = self.media.get_strv("custom-keybindings")
        self.custom.delay()
        try:
            for key, value in (("name", SHORTCUT_NAME), ("command", self.command), ("binding", binding)):
                if not self.custom.set_string(key, value):
                    raise ValueError("GNOME rejected the shortcut.")
            self.custom.apply()
        except Exception:
            self.custom.revert()
            raise
        if SHORTCUT_PATH not in paths and not self.media.set_strv("custom-keybindings", [*paths, SHORTCUT_PATH]):
            raise ValueError("GNOME could not register the shortcut.")
        Gio.Settings.sync()
        return binding

    def remove(self):
        self.check_owner()
        if not self.media.is_writable("custom-keybindings") or not self.custom.is_writable("binding"):
            raise RuntimeError("GNOME custom shortcuts are locked.")
        paths = [path for path in self.media.get_strv("custom-keybindings") if path != SHORTCUT_PATH]
        if not self.media.set_strv("custom-keybindings", paths):
            raise ValueError("GNOME could not remove the shortcut.")
        self.custom.delay()
        self.custom.reset("binding")
        self.custom.apply()
        Gio.Settings.sync()
