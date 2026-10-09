# Local validation — 2026-10-10

Environment: Ubuntu 24.04.5 LTS, x86-64, GNOME Wayland, GTK 3.24,
system Python 3. All commands below completed with exit code 0.

| Check | Result |
| --- | --- |
| `./build.sh` | Source compilation and runtime imports pass |
| `./test.sh` | 46 Python tests and 3 JavaScript tests pass, including 3,700 generated input cases and all grid shapes up to 6×6 |
| `PYTHONPATH=. /usr/bin/python3 tests/gui_smoke.py build/gnome-preview.png` in the graphical session | 17 pages render; existing file/text/launch workflows pass; theme/schedule, zoom, pointer, drag modifier and shortcut settings roundtrip against an in-memory backend; duplicate bindings rejected; shortcut guide and accent picker render |
| `./test-window-tools.sh` | GNOME 46.0/Mutter 46.2 extension loads in a private headless compositor with two virtual monitors; native Wayland GTK windows snap, pin/unpin, move/resize across monitors and cycle through all windows; GUI window controls pass; invalid zones, off-monitor placement and fullscreen placement are rejected; disable removes the exported object |
| GNOME session inhibition in the desktop test | Suspend flags = 4; suspend + idle flags = 12; both are removed after Stop |
| Live file-descriptor inspection | Finds the test process's own open file |
| EXIF rotation | Orientation-6 JPEG is rotated before resizing; 200×100 input fits to 50×100 in a 100×100 box |
| Desktop color portal | This desktop exposes Screenshot portal version 2 and PickColor; request/response/cancel handling unit-tested with a mock connection |
| User installation | Command and application menu entry installed; desktop entry passes `desktop-file-validate` |
| Installed `powertoys-linux --smoke-test` | 17-page smoke check passes; detects installed applications including the Linux app |
| `git diff --check` | Passes |

The deterministic generated cases cover filenames, rename roundtrips, Unicode
conversions, invalid image headers, file preview bytes, color components,
template names and workspace configuration bytes. These are bounded local
fuzz tests, not OneFuzz runs or an exhaustive security assessment.
New cases cover schedule values, backend response strings and zone inputs.

The extension integration uses temporary XDG folders and a private D-Bus
configuration with service activation disabled. It does not alter the current
desktop's windows or settings. Theme, zoom, pointer and shortcut UI tests use
in-memory settings. Global keybinding registration/cleanup is exercised in the
compositor; shortcut save/validation is tested, but physical keystroke activation
and pointer modifier dragging have not been exercised interactively.

The widget capture was visually inspected. Screen-pixel selection itself has
not been exercised interactively; it requires clicking a pixel in the desktop
picker. Multi-monitor window placement was tested on two virtual monitors at
scale 1, not on physical monitors with different DPI. Other GNOME versions,
KDE/wlroots, multi-machine input sharing, remaining utilities and distro
packaging have not been validated. The window extension is installed for this
user, with activation pending discovery at the next login. This is an
experimental partial port, not a production release or full feature parity.
