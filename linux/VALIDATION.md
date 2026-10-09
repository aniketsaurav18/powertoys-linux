# Local validation — 2026-10-09

Environment: Ubuntu 24.04.5 LTS, x86-64, GNOME Wayland, GTK 3.24,
system Python 3. All commands below completed with exit code 0.

| Check | Result |
| --- | --- |
| `./build.sh` | Source compilation and runtime imports pass |
| `./test.sh` | 36 tests pass, including 1,950 generated input cases |
| `PYTHONPATH=. /usr/bin/python3 tests/gui_smoke.py build/preview.png` in the graphical session | 11 pages render; rename preview/apply/undo, UTF-8 preview, template copying, workspace save/delete, text conversion, app search and GIO `/usr/bin/true` launch pass |
| GNOME session inhibition in the desktop test | Suspend flags = 4; suspend + idle flags = 12; both are removed after Stop |
| Live file-descriptor inspection | Finds the test process's own open file |
| EXIF rotation | Orientation-6 JPEG is rotated before resizing; 200×100 input fits to 50×100 in a 100×100 box |
| Desktop color portal | This desktop exposes Screenshot portal version 2 and PickColor; request/response/cancel handling unit-tested with a mock connection |
| User installation | Command and application menu entry installed; desktop entry passes `desktop-file-validate` |
| Installed `powertoys-linux --smoke-test` | Passes; detects 74 installed applications, including the new Linux app |
| `git diff --check` | Passes |

The deterministic generated cases cover filenames, rename roundtrips, Unicode
conversions, invalid image headers, file preview bytes, color components,
template names and workspace configuration bytes. These are bounded local
fuzz tests, not OneFuzz runs or an exhaustive security assessment.

The widget capture was visually inspected. Screen-pixel selection itself has
not been exercised interactively; it requires clicking a pixel in the desktop
picker. Unsupported/future utilities, multi-monitor window placement,
multi-machine input sharing, other desktops and distro packaging have not been
validated. This is an experimental partial port, not a production release or
full feature parity.
