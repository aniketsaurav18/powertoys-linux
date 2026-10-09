#!/usr/bin/python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Install a source snapshot for this user only; no root privileges needed."""

import os
import shlex
import shutil
from pathlib import Path


def main():
    source = Path(__file__).resolve().parent
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    destination = data / "powertoys-linux"
    command = Path.home() / ".local/bin/powertoys-linux"
    desktop = data / "applications/io.github.powertoys.Linux.desktop"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / "powertoys_linux", destination / "powertoys_linux", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("launch.py", "README.md", "ROADMAP.md", "VALIDATION.md"):
        shutil.copy2(source / name, destination / name)
    shutil.copy2(source.parent / "LICENSE", destination / "LICENSE")
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text(f'#!/bin/sh\nexec /usr/bin/python3 {shlex.quote(str(destination / "launch.py"))} "$@"\n')
    command.chmod(0o755)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(command).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
    desktop.write_text(f'[Desktop Entry]\nType=Application\nName=PowerToys for Linux\nComment=Experimental Linux productivity utilities\nExec="{escaped}"\nIcon=applications-utilities\nTerminal=false\nCategories=Utility;\nStartupNotify=true\nStartupWMClass=io.github.powertoys.Linux\n')
    print(f"Installed command: {command}\nInstalled application: {desktop}")


if __name__ == "__main__":
    main()
