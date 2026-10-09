# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Explicit changes to GNOME's documented desktop preferences."""

import os
from pathlib import Path

from gi.repository import Gio, GLib


SCHEMAS = {
    "interface": "org.gnome.desktop.interface",
    "accessibility": "org.gnome.desktop.a11y.applications",
    "magnifier": "org.gnome.desktop.a11y.magnifier",
    "windows": "org.gnome.desktop.wm.preferences",
}
SHORTCUT_SCHEMAS = ("org.gnome.desktop.wm.keybindings", "org.gnome.shell.keybindings", "org.gnome.mutter.keybindings", "org.gnome.settings-daemon.plugins.media-keys")
WINDOW_SHORTCUTS = {
    "powertoys-cycle-next": "Cycle next window",
    "powertoys-toggle-above": "Pin/unpin focused window",
    "powertoys-snap-left": "Snap focused window left",
    "powertoys-snap-right": "Snap focused window right",
    "powertoys-launcher": "Open PowerToys",
}


def scheduled_theme(hour, light_hour, dark_hour):
    if any(type(value) is not int or not 0 <= value <= 23 for value in (hour, light_hour, dark_hour)) or light_hour == dark_hour:
        raise ValueError("Choose different light and dark start hours between 0 and 23.")
    light = (hour - light_hour) % 24 < (dark_hour - light_hour) % 24
    return "prefer-light" if light else "prefer-dark"


class GnomeSettings:
    def __init__(self, backend=None):
        self.backend = backend
        self.source = Gio.SettingsSchemaSource.get_default()
        self.cache = {}

    def settings(self, schema_id):
        if schema_id not in self.cache:
            schema = self.source.lookup(schema_id, True) if self.source else None
            if schema is None:
                raise RuntimeError(f"This desktop does not provide {schema_id}.")
            self.cache[schema_id] = Gio.Settings.new_full(schema, self.backend, None)
        return self.cache[schema_id]

    def get(self, section, key):
        return self.settings(SCHEMAS[section]).get_value(key).unpack()

    def set(self, section, key, value):
        settings = self.settings(SCHEMAS[section])
        if not settings.is_writable(key):
            raise RuntimeError("This desktop preference is locked.")
        current = settings.get_value(key)
        variant = GLib.Variant(current.get_type_string(), value)
        if not settings.set_value(key, variant):
            raise ValueError("The desktop rejected this preference value.")

    def theme(self, value):
        if value not in ("default", "prefer-light", "prefer-dark"):
            raise ValueError("Unknown appearance preference.")
        self.set("interface", "color-scheme", value)

    def zoom(self, enabled, factor=2.0):
        if not isinstance(enabled, bool) or not 1 <= factor <= 8:
            raise ValueError("Zoom factor must be between 1 and 8.")
        self.set("magnifier", "mag-factor", float(factor))
        self.set("accessibility", "screen-magnifier-enabled", enabled)

    def cursor(self, size, locate):
        if type(size) is not int or not 16 <= size <= 96 or not isinstance(locate, bool):
            raise ValueError("Cursor size must be 16–96 pixels.")
        self.set("interface", "cursor-size", size)
        self.set("interface", "locate-pointer", locate)

    def shortcuts(self):
        result = []
        for schema_id in SHORTCUT_SCHEMAS:
            schema = self.source.lookup(schema_id, True) if self.source else None
            if schema is None:
                continue
            settings = self.settings(schema_id)
            for key in schema.list_keys():
                if key == "custom-keybindings":
                    continue
                value = settings.get_value(key)
                if value.get_type_string() == "as":
                    keys = [item for item in value.unpack() if item and item != "disabled"]
                    if keys:
                        result.append((key, ", ".join(keys), schema_id))
        custom_schema = self.source.lookup("org.gnome.settings-daemon.plugins.media-keys.custom-keybinding", True) if self.source else None
        media_schema = self.source.lookup("org.gnome.settings-daemon.plugins.media-keys", True) if self.source else None
        if custom_schema and media_schema:
            paths = self.settings(media_schema.get_id()).get_strv("custom-keybindings")
            for path in paths[:200]:
                if not path.startswith("/org/gnome/settings-daemon/plugins/media-keys/") or not path.endswith("/"):
                    continue
                custom = Gio.Settings.new_full(custom_schema, self.backend, path)
                binding = custom.get_string("binding")
                if binding and binding != "disabled":
                    result.append((custom.get_string("name") or "Custom shortcut", binding, custom_schema.get_id()))
        return sorted(result)

    def window_shortcut_settings(self):
        schema_id = "io.github.powertoys.Linux.WindowTools"
        candidates = [Path(__file__).resolve().parents[1] / "gnome-extension/powertoys-linux@local/schemas",
                      Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "gnome-shell/extensions/powertoys-linux@local/schemas"]
        for directory in candidates:
            if (directory / "gschemas.compiled").is_file():
                source = Gio.SettingsSchemaSource.new_from_directory(str(directory), self.source, False)
                schema = source.lookup(schema_id, False)
                if schema:
                    return Gio.Settings.new_full(schema, self.backend, None)
        raise RuntimeError("Install the GNOME Window Tools extension to configure its shortcuts.")
