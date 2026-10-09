# PowerToys for Linux — experimental stages 1–2

This is a native Linux implementation of selected PowerToys workflows inside
the PowerToys source tree. It is **not an official Microsoft Linux release** or
a binary-compatible port of the Windows modules. The Windows runner, DLL module
interfaces, WPF/WinUI views and Explorer extensions cannot run natively here.
This front end keeps its code and installation separate from those components.

## Included

| Utility | Implemented Linux behavior | Remaining differences |
| --- | --- | --- |
| PowerToys Run | Search installed desktop applications and launch with GIO | No plugins, global shortcut or file index |
| PowerRename | Literal search/replace, case option, extension option, preview, session undo | Files only; no regex, metadata patterns or recursive folders |
| Image Resizer | Batch fit within dimensions, shrink-only, rotated JPEG handling, PNG copies | PNG/JPEG input only; no metadata preservation, animation, fill or stretch |
| Advanced Paste | JSON formatting, case, trim, Base64 and URL transforms; explicit clipboard access | No AI transforms or global paste shortcut |
| Awake | Desktop suspend inhibitor, optional display inhibitor, timed or indefinite | Active while app is open; desktop must support inhibition |
| Peek | UTF-8 text and PNG/JPEG preview | No global shortcut or document/video previews |
| File Locksmith | Inspect readable process file descriptors by inode | No process termination; no mappings-only detection or elevated access |
| Color Picker | Wayland-compatible desktop PickColor portal, HEX/RGB and clipboard | Requires a supported desktop portal; no history or global shortcut |
| New+ | Copy a template file into a chosen folder under a new name | No directory templates or file-manager context action |
| Workspaces | Save and launch groups of installed desktop applications | No capture/restore of window positions or monitor layouts |

GNOME Wayland is the primary target. Basic workflows also use GTK's X11 backend.
Awake's display option prevents the session being marked idle, which can also
prevent automatic locking. Closing the app releases its inhibitors.

## Run, build and test

On this Ubuntu PC the required system packages are already installed:
`python3`, `python3-gi`, `gir1.2-gtk-3.0`, and `gir1.2-gdkpixbuf-2.0`.
Use **`/usr/bin/python3`**; a pyenv or virtualenv interpreter may not have GI.
No pip packages or vendored dependencies are required.

```sh
cd linux
./build.sh
./test.sh
/usr/bin/python3 launch.py
```

The Windows MSBuild scripts and vstest cannot build or run this Python/GTK
target on Linux. `build.sh` checks compilation and system runtime imports;
`test.sh` builds first, then runs unit tests and deterministic fuzz cases.
For a basic desktop smoke test:

```sh
/usr/bin/python3 launch.py --smoke-test
```

Run GUI commands from a terminal in your graphical session. The smoke test
must be run before opening the normal app because GApplication uses one
instance per session. It checks page construction, search and text conversion.
On GNOME, run the broader desktop integration check after `test.sh`:

```sh
PYTHONPATH=. /usr/bin/python3 tests/gui_smoke.py
# Optional rendered widget capture (requires the system python3-cairo package):
PYTHONPATH=. /usr/bin/python3 tests/gui_smoke.py build/preview.png
```

This uses temporary files and temporary workspace configuration, launches
`/usr/bin/true`, and briefly acquires/releases GNOME suspend/display inhibitors.
It does not interactively select a screen color; portal request/response
handling is unit-tested, and color picking is initiated only by the app button.

## Install for the current user

```sh
/usr/bin/python3 install.py
~/.local/bin/powertoys-linux
```

This copies a snapshot to `$XDG_DATA_HOME/powertoys-linux` (by default
`~/.local/share/powertoys-linux`), adds a launcher to
`$XDG_DATA_HOME/applications`, and writes `~/.local/bin/powertoys-linux`.
Look for **PowerToys for Linux** in your application menu. No root access,
startup entry or desktop shortcut settings are needed. Run installation again
after updating the source to refresh the snapshot.

To uninstall, remove these three paths:

```sh
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/powertoys-linux"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.powertoys.Linux.desktop"
rm -f "$HOME/.local/bin/powertoys-linux"
```

## File handling limits

Renaming supports regular files on hard-link-capable local filesystems. It
rejects symlinks, duplicate targets, existing destinations, invalid filenames
and files changed since preview. A batch reserves all new names before
removing original names. Link failures remove the reserved names, leaving
originals in place. An unlink failure leaves all files at their new names and
may leave some original names too; inspect the reported folder. This is not a
crash-atomic transaction or a defense against concurrent hostile filesystem
changes. Undo lasts only for the current app session and refuses collisions.

Image Resizer writes new exclusive PNG files beside the source. Existing
copies are never replaced. Inputs and outputs are limited to 40 megapixels;
outputs are limited to 16384 pixels per side. Metadata is not preserved.
Batch failures report which files failed; successful outputs remain available.
Text conversions have a 2 MB input limit. None of these tools sends data over
the network. Fuzz tests exercise file and user input with bounded deterministic
cases; they are not a substitute for a production security review.

New+ copies regular files up to 50 MB; it rejects symlinks and existing target
names. Workspaces stores desktop app IDs in
`${XDG_CONFIG_HOME:-~/.config}/powertoys-linux/workspaces.json`, with atomic
replacement and a 256 KB limit. It preserves invalid existing configuration
rather than overwriting it. There are no saved arbitrary shell commands.

See [ROADMAP.md](ROADMAP.md) for every upstream utility and subsequent stages.
See [VALIDATION.md](VALIDATION.md) for the checks run on this PC and their limits.

## Platform references

Linux application discovery/launch follows [GIO AppInfo](https://docs.gtk.org/gio/iface.AppInfo.html).
Awake uses [GTK application inhibition](https://docs.gtk.org/gtk3/method.Application.inhibit.html).
Image operations use [GdkPixbuf](https://docs.gtk.org/gdk-pixbuf/class.Pixbuf.html).
Color picking follows the [desktop Screenshot portal](https://github.com/flatpak/xdg-desktop-portal/blob/main/data/org.freedesktop.portal.Screenshot.xml)
and [portal request lifecycle](https://flatpak.github.io/xdg-desktop-portal/docs/requests.html).
