#!/bin/sh
# Standalone Linux build. The upstream MSBuild scripts require Windows.
set -eu
cd "$(dirname "$0")"
mkdir -p build
PYTHONPYCACHEPREFIX="$PWD/build/cache" /usr/bin/python3 -m compileall -q powertoys_linux launch.py install.py tests
/usr/bin/python3 -c 'from powertoys_linux.app import PowerToys; print("Linux build succeeded: Python, GTK 3, GIO and GdkPixbuf available.")'
