#!/usr/bin/python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Install a source snapshot for this user only; no root privileges needed."""

import os
import argparse
import shlex
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gnome-extension", action="store_true", help="Also install the GNOME 46 window-control extension (enable it in GNOME Extensions after login)")
    options = parser.parse_args()
    source = Path(__file__).resolve().parent
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    destination = data / "powertoys-linux"
    command = Path.home() / ".local/bin/powertoys-linux"
    desktop = data / "applications/io.github.powertoys.Linux.desktop"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "powertoys_linux", destination / "powertoys_linux", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("launch.py", "README.md", "ROADMAP.md", "VALIDATION.md"):
        shutil.copy2(source / name, destination / name)
    for name in ("LICENSE", "NOTICE.md"):
        shutil.copy2(source.parent / name, destination / name)
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text(f'#!/bin/sh\nexec /usr/bin/python3 {shlex.quote(str(destination / "launch.py"))} "$@"\n')
    command.chmod(0o755)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(command).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    desktop.write_text(f'[Desktop Entry]\nType=Application\nName=PowerToys for Linux\nComment=Experimental Linux productivity utilities\nExec="{escaped}"\nIcon=applications-utilities\nTerminal=false\nCategories=Utility;\nStartupNotify=true\nStartupWMClass=io.github.powertoys.Linux\n')
    print(f"Installed command: {command}\nInstalled application: {desktop}")
    if options.gnome_extension:
        extension = data / "gnome-shell/extensions/powertoys-linux@local"
        shutil.copytree(source / "gnome-extension/powertoys-linux@local", extension, dirs_exist_ok=True)
        import subprocess
        subprocess.run(["glib-compile-schemas", "--strict", str(extension / "schemas")], check=True)
        print(f"Installed GNOME extension: {extension}\nEnable PowerToys for Linux Window Tools in GNOME Extensions after your next login.")


if __name__ == "__main__":
    main()
