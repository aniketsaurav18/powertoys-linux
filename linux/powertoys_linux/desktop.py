# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Wayland-compatible desktop services. No screen scraping or elevated access."""

import math
import uuid
from urllib.parse import unquote, urlsplit
from pathlib import Path

from gi.repository import Gio, GLib


def color_formats(color):
    if len(color) != 3 or any(not math.isfinite(c) or c < 0 or c > 1 for c in color):
        raise ValueError("The desktop returned an invalid color.")
    channels = tuple(round(c * 255) for c in color)
    return "#" + "".join(f"{c:02X}" for c in channels), f"rgb({channels[0]}, {channels[1]}, {channels[2]})"


class ColorRequest:
    """Subscribe before calling PickColor to avoid the portal response race."""
    method = "PickColor"
    description = "Color picking"

    def __init__(self, callback):
        self.callback = callback
        self.subscription = 0
        self.timer = 0
        self.active = True
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        token = "powertoys_" + uuid.uuid4().hex
        sender = self.connection.get_unique_name()[1:].replace(".", "_")
        self.path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        self.subscription = self.connection.signal_subscribe(
            "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request",
            "Response", self.path, None, Gio.DBusSignalFlags.NONE, self.response)
        self.timer = GLib.timeout_add_seconds(180, self.timeout)
        options = {"handle_token": GLib.Variant("s", token)}
        if self.method == "Screenshot":
            options["interactive"] = GLib.Variant("b", True)
        self.connection.call(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot", self.method,
            GLib.Variant("(sa{sv})", ("", options)),
            GLib.VariantType.new("(o)"), Gio.DBusCallFlags.NONE, 20000, None, self.started)

    def started(self, connection, result):
        try:
            returned_path = connection.call_finish(result).unpack()[0]
            if self.active and returned_path != self.path:
                self.cancel()
        except GLib.Error as error:
            self.finish(None, f"{self.description} is unavailable: {error.message}")

    def response(self, connection, sender, path, interface, signal, parameters):
        code, results = parameters.unpack()
        if code == 0:
            color = results.get("color")
            try:
                color_formats(color)
            except (TypeError, ValueError):
                self.finish(None, "The desktop did not return a valid color.")
                return
            self.finish(color, None)
        else:
            self.finish(None, "Color picking cancelled." if code == 1 else "Desktop color picking failed.")

    def finish(self, color, error):
        if not self.active:
            return
        self.active = False
        if self.subscription:
            self.connection.signal_unsubscribe(self.subscription)
            self.subscription = 0
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        self.callback(color, error)

    def cancel(self):
        if not self.active:
            return
        self.connection.call("org.freedesktop.portal.Desktop", self.path,
                             "org.freedesktop.portal.Request", "Close", None, None,
                             Gio.DBusCallFlags.NONE, 2000, None, None)
        self.finish(None, f"{self.description} cancelled.")

    def timeout(self):
        self.timer = 0
        self.cancel()
        return False


def screenshot_path(uri):
    """Only local portal images may enter the image decoder."""
    if not isinstance(uri, str) or len(uri) > 8192:
        raise ValueError("The desktop did not return a local screenshot.")
    parts = urlsplit(uri)
    path = unquote(parts.path)
    if (parts.scheme != "file" or parts.netloc not in ("", "localhost")
            or parts.query or parts.fragment or not path.startswith("/") or "\x00" in path):
        raise ValueError("The desktop did not return a local screenshot.")
    return Path(path)


class ScreenshotRequest(ColorRequest):
    """Interactive screenshot capture using the same portal lifecycle."""
    method = "Screenshot"
    description = "Screenshot capture"

    def response(self, connection, sender, path, interface, signal, parameters):
        code, results = parameters.unpack()
        if code != 0:
            self.finish(None, "Screenshot capture cancelled." if code == 1 else "Screenshot capture failed.")
            return
        try:
            image = screenshot_path(results.get("uri"))
        except ValueError as error:
            self.finish(None, str(error))
            return
        self.finish(image, None)
