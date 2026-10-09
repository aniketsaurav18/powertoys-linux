#!/bin/sh
set -eu
cd "$(dirname "$0")"
./build.sh
PYTHONPATH="$PWD" dbus-run-session --config-file="$PWD/tests/isolated-session.conf" -- /usr/bin/python3 tests/window_integration.py
