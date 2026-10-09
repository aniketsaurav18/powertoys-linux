#!/bin/sh
# Standalone Linux build. The upstream MSBuild scripts require Windows.
set -eu
cd "$(dirname "$0")"
mkdir -p build
PYTHONPYCACHEPREFIX="$PWD/build/cache" /usr/bin/python3 -m compileall -q powertoys_linux launch.py install.py tests
node --check gnome-extension/powertoys-linux@local/extension.js
node --check gnome-extension/powertoys-linux@local/geometry.js
glib-compile-schemas --strict gnome-extension/powertoys-linux@local/schemas
/usr/bin/python3 -c 'from powertoys_linux.app import PowerToys; print("Linux build succeeded: Python, GTK 3, GIO and GdkPixbuf available.")'
