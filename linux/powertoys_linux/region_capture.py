# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Fresh drag-to-select capture through GNOME's supported area utility."""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from gi.repository import GLib

from .ocr import stop_process


def local_runtime():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "powertoys-linux/region-runtime"


def capture_command(destination):
    executable = shutil.which("gnome-screenshot")
    environment = dict(os.environ)
    if not executable:
        runtime = local_runtime()
        executable = runtime / "usr/bin/gnome-screenshot"
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError("Direct text selection needs GNOME Screenshot area support. See the Text Extractor setup instructions.")
        environment["GSETTINGS_SCHEMA_DIR"] = str(runtime / "usr/share/glib-2.0/schemas")
    # --area starts a fresh crosshair; --file avoids both the save dialog and
    # screenshot clipboard writes. No interactive screenshot-overlay fallback.
    return [str(executable), "--area", "--file", str(destination)], environment


class RegionRequest:
    """Own a private capture file until the consumer has loaded it."""
    def __init__(self, callback, timeout=180):
        self.callback = callback
        self.active = True
        self.timer = 0
        self.process = None
        self.folder = tempfile.TemporaryDirectory(prefix="powertoys-text-selection-")
        self.path = Path(self.folder.name) / "selection.png"
        self.errors = tempfile.TemporaryFile()
        try:
            command, environment = capture_command(self.path)
            self.process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=self.errors,
                                            start_new_session=True)
            self.deadline = time.monotonic() + timeout
            self.timer = GLib.timeout_add(50, self.poll)
        except Exception:
            self.cleanup()
            raise

    def poll(self):
        if not self.active:
            return False
        if self.process.poll() is not None:
            self.timer = 0
            if self.process.returncode:
                self.errors.seek(0)
                error = self.errors.read(2000).decode("utf-8", errors="replace").replace("\x00", "").strip()
                self.finish(None, "Text selection failed." + (" " + error if error else ""))
            elif not self.path.is_file():
                self.finish(None, "Text selection cancelled.")
            else:
                self.finish(self.path, None)
            return False
        if time.monotonic() >= self.deadline or os.fstat(self.errors.fileno()).st_size > 64_000:
            self.timer = 0
            self.cancel()
            return False
        return True

    def finish(self, path, error):
        if not self.active:
            return
        self.active = False
        self.errors.close()
        if error:
            self.cleanup()
        self.callback(path, error)

    def cleanup(self):
        # After a successful selection only the private image remains. The
        # worker may remove it after decoding, before recognition starts.
        if self.errors and not self.errors.closed:
            self.errors.close()
        self.folder.cleanup()

    def cancel(self):
        if not self.active:
            self.cleanup()
            return
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        stop_process(self.process)
        self.finish(None, "Text selection cancelled.")
