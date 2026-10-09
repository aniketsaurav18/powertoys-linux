# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""GNOME Wayland window backend, independent of the Windows runner protocol."""

import json

from gi.repository import Gio, GLib


INTERFACE = "io.github.powertoys.Linux.WindowTools"
OBJECT = "/io/github/powertoys/Linux/WindowTools"
UUID = "powertoys-linux@local"


def validate_state(value):
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Unsupported window backend version.")
    for key in ("windows", "monitors"):
        if not isinstance(value.get(key), list) or len(value[key]) > 1000:
            raise ValueError("Invalid window backend response.")
    for monitor in value["monitors"]:
        if not isinstance(monitor, dict) or any(type(monitor.get(key)) is not int for key in ("index", "x", "y", "width", "height", "scale")):
            raise ValueError("Invalid monitor geometry.")
        if monitor["width"] <= 0 or monitor["height"] <= 0 or monitor["scale"] <= 0:
            raise ValueError("Invalid monitor dimensions.")
    for window in value["windows"]:
        if not isinstance(window, dict) or type(window.get("id")) is not int or not 0 < window["id"] <= 0xFFFFFFFF or not isinstance(window.get("title"), str):
            raise ValueError("Invalid window identity.")
        if any(type(window.get(key)) is not int for key in ("monitor", "workspace")) or any(type(window.get(key)) is not bool for key in ("above", "fullscreen")):
            raise ValueError("Invalid window state.")
        rect = window.get("rect")
        if not isinstance(rect, dict) or any(type(rect.get(key)) is not int for key in ("x", "y", "width", "height")) or rect["width"] <= 0 or rect["height"] <= 0:
            raise ValueError("Invalid window geometry.")
    return value


class WindowBackend:
    def __init__(self, connection=None):
        self.connection = connection or Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def call(self, method, signature=None, arguments=()):
        parameters = GLib.Variant(signature, arguments) if signature else None
        try:
            return self.connection.call_sync("org.gnome.Shell", OBJECT, INTERFACE, method,
                                             parameters, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        except GLib.Error as error:
            if "UnknownMethod" in str(error) or "UnknownObject" in str(error) or "ServiceUnknown" in str(error):
                raise RuntimeError("GNOME Window Tools extension is not active. Install it, then enable PowerToys for Linux Window Tools in GNOME Extensions after your next login.") from error
            raise RuntimeError(error.message) from error

    def state(self):
        data = self.call("GetState")
        if len(data.encode("utf-8")) > 2_000_000:
            raise ValueError("Window backend response exceeds 2 MB.")
        return validate_state(json.loads(data))

    def snap(self, window, monitor, columns, rows, index, gap=8):
        return self.call("Snap", "(uuuuuu)", (window, monitor, columns, rows, index, gap))

    def move_resize(self, window, monitor, x, y, width, height):
        return self.call("MoveResize", "(uuiiuu)", (window, monitor, x, y, width, height))

    def above(self, window, enabled):
        return self.call("SetAbove", "(ub)", (window, enabled))

    def activate(self, window):
        return self.call("Activate", "(u)", (window,))

    def cycle(self, direction):
        return self.call("Cycle", "(i)", (direction,))
