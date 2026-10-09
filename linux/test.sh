#!/bin/sh
set -eu
cd "$(dirname "$0")"
./build.sh
PYTHONPATH="$PWD" /usr/bin/python3 -m unittest discover -s tests -v
