# PowerToys for Linux — experimental native and GNOME tools

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
| Text Extractor | Local Tesseract OCR, image/screenshot input, editable text and clipboard; GNOME shortcut with fresh drag-to-select and automatic OCR on release | Optional engine and area helper required; no table reconstruction or click-word extraction |
| New+ | Copy a template file into a chosen folder under a new name | No directory templates or file-manager context action |
| Workspaces | Save and launch groups of installed desktop applications | No capture/restore of window positions or monitor layouts |
| FancyZones | Choose a grid up to 6×6, preview zones, snap a selected window to a chosen monitor | GNOME 46 extension required; no drag overlay or saved custom layouts |
| Always on Top | Pin/unpin selected or focused windows | GNOME 46 extension required |
| Alt Window Cycle | Cycle all normal windows on the active workspace in stable order | GNOME 46 extension required; no application-group filter |
| Grab and Move | Position/resize selected windows; choose GNOME's Super/Alt drag modifier | Explicit placement uses extension; drag uses GNOME's native behavior |
| Light Switch | Light/dark/default preference and daily hour-based schedule | GNOME only; schedule runs while this app is open |
| ZoomIt | Desktop magnification and magnifier crosshairs | GNOME only; no drawing, annotation or recording |
| Mouse Utilities | Cursor size and Control-key pointer locator | GNOME only; remaining overlays/wrapping not implemented |
| Shortcut Guide | Read configured GNOME shortcuts, including custom bindings | No overlay or global hold-to-show shortcut |
| Quick Accent | Accented Latin character picker with uppercase and clipboard | No hold-to-type or input-method integration |

GNOME Wayland is the primary target. Basic workflows also use GTK's X11 backend.
Awake's display option prevents the session being marked idle, which can also
prevent automatic locking. Closing the app releases its inhibitors.

## Run, build and test

On this Ubuntu PC the required system packages are already installed:
`python3`, `python3-gi`, `gir1.2-gtk-3.0`, and `gir1.2-gdkpixbuf-2.0`.
Use **`/usr/bin/python3`**; a pyenv or virtualenv interpreter may not have GI.
No pip packages or vendored dependencies are required.
Development checks also use the already installed `node` (Node.js 18+) and
`glib-compile-schemas`. GNOME 46 and its GJS/Mutter runtime are required only for
the window extension. No dependency packages are installed by these scripts.

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
Theme, zoom, cursor, drag-modifier and shortcut writes in the desktop test use
an isolated in-memory GSettings backend, preserving your actual preferences.

The OCR controls can be exercised without installing an engine:

```sh
./build.sh
PYTHONPATH=. /usr/bin/python3 tests/ocr_gui.py build/ocr-preview.png
```

This uses a temporary CLI test double to check background work, crop selection,
text rendering and the clipboard contract. It does **not** test recognition
accuracy or replace Tesseract. The clipboard is mocked in this check.

For native Wayland window integration, run:

```sh
./test-window-tools.sh
```

This starts a separate headless GNOME compositor with two virtual monitors,
temporary configuration/data/runtime folders, and a private session bus with
service activation disabled. It tests real GTK Wayland windows through both
the extension API and native app controls. It does not move your existing
windows or restart your desktop. Logs are in `build/window-integration.log`.

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

## Optional OCR engine

Open **Text Extractor**, choose **Open image…** or **Capture screen…**, drag over
the preview if you want a smaller region, select a language and layout, then
click **Extract text**. Review or edit the result before **Copy recognized
text**. Capture uses your desktop's interactive Screenshot portal; the app
temporarily hides itself and restores its window when the request finishes.
The screenshot dialog and available capture modes are supplied by the desktop.
Screenshot files belong to the portal and are not deleted by this app.

Tesseract and at least one language model must be installed separately.
On this PC, Tesseract 5.3.4, English models and orientation data are installed
in the user-local runtime described below, using approximately 22 MB.
Real English recognition has passed both backend and installed GTK app checks.
The app and installer never fetch engine packages. The repository's dependency
approval rule applies before introducing these optional third-party packages.
On Ubuntu, after approval, an administrator can install `tesseract-ocr` and
`tesseract-ocr-eng` using the distribution package manager.

For this Ubuntu 24.04 x86-64 PC, a user-local alternative is to download the
distribution packages `tesseract-ocr`, `libtesseract5`, `liblept5`,
`tesseract-ocr-eng` and `tesseract-ocr-osd` with `apt download`, then extract
them with `dpkg-deb --extract` into
`${XDG_DATA_HOME:-~/.local/share}/powertoys-linux/ocr-runtime`.
This is intended for the current PC, whose remaining shared libraries are
already present, rather than a portable bundle for other distributions.
It requires no root access and makes no system package changes.
The adapter supplies that runtime's library and language paths only to its
child process. A system `tesseract` on PATH takes precedence. Keep the
extracted package copyright files in `usr/share/doc` with the runtime.

Click **Refresh engine** after setup. Additional languages appear when their
models are installed; combined language selections are not implemented.
For a real English recognition check (also uses the existing system Cairo):

```sh
./build.sh
PYTHONPATH=. /usr/bin/python3 tests/ocr_integration.py
```

Inputs are limited to PNG/JPEG, 50 MB and 20 megapixels. Recognition has a
30-second limit, a 2 MB text limit and a Cancel button. Transparent pixels are
composited onto white; rotated JPEGs are oriented before crop selection.
Recognition uses a temporary copy and never writes to your original image.
Small text, handwriting and complex layouts may produce poor results. The
four layouts are automatic page, text block, single line and scattered text.
All recognition stays local, with no cloud service or telemetry.

See [Tesseract installation](https://tesseract-ocr.github.io/tessdoc/Installation.html)
and [image quality guidance](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html).

### Screen-to-clipboard shortcut

On this PC, **Super + Shift + T** (Windows key + Shift + T) is registered as a
GNOME custom shortcut. Press it to get a fresh crosshair, drag around the text,
then release the mouse. OCR runs in the background and copies non-empty
recognized text automatically. There is no initial selection box to readjust,
screenshot toolbar, capture button or Enter confirmation.
A notification tells you when to paste with **Ctrl + V**. Press **Escape** in
the selector to cancel. The main PowerToys window need not be open, and no
window-tools extension or new login is required.

On another installation, opt in with:

```sh
/usr/bin/python3 install.py --ocr-shortcut
```

Direct selection requires the separate `gnome-screenshot` area helper.
Following dependency approval, install it using your distribution's package
manager, or extract Ubuntu's `gnome-screenshot` package into
`${XDG_DATA_HOME:-~/.local/share}/powertoys-linux/region-runtime` and compile
its `usr/share/glib-2.0/schemas` directory with `glib-compile-schemas --strict`.
The runtime is installed for this user on the current Ubuntu/GNOME 46 PC and
uses about 2 MB of disk space (0.8 MB of file data). Its package copyright files
remain in `usr/share/doc`.
The app and its installer do not download packages. A system helper on PATH
takes precedence over the user-local copy. An unavailable helper produces a
notification rather than reverting to the adjustable screenshot overlay.

The installer checks discoverable shortcut conflicts and preserves other GNOME
custom bindings. Change or remove the binding on the **Text Extractor** page;
use notation such as `<Super><Shift>t` or `<Control><Alt>F11`. Other programs'
private bindings may not be discoverable. Registration is explicit: an ordinary
installation does not add or change this shortcut.

You can also start or stop the background helper from the Text Extractor page,
or run these commands in your graphical session:

```sh
~/.local/bin/powertoys-linux --ocr
~/.local/bin/powertoys-linux --stop-ocr
```

Shortcut OCR uses English if installed, otherwise the first installed language,
with scattered-text recognition. Repeated triggers use one helper process;
a trigger during an active job reports that extraction is already in progress.
The helper briefly shows a copying window to obtain Wayland clipboard focus,
then hides it and restores focus to the previous app. It stays running after
copying so the text remains available to other applications. **Stop background
Text Extractor** releases that owner; paste first. There is no login autostart.
Shortcut captures are private temporary files, deleted after loading the image
and before recognition. They are not saved to Pictures or copied to the
clipboard as images. Empty or failed recognition reports a notification and
does not copy an empty string. The separate manual **Capture screen…** button
continues to use the desktop Screenshot portal and its normal confirmation UI;
that desktop may save its screenshots, which this app does not delete.

For an isolated Wayland integration check:

```sh
./test-quick-ocr.sh
```

This starts a private headless GNOME session with temporary configuration and a
virtual keyboard and pointer. A GTK window displays text; the real GNOME area
selector receives synthetic press/drag/release events, real Tesseract recognizes
the captured screen pixels, and a separate GTK process reads the real Wayland
clipboard. Checks also cover fresh selections, reverse drags, Escape,
temporary-file deletion, repeated commands and Stop. It leaves your clipboard
and desktop settings unchanged. Physical shortcut presses and physical monitors
with different DPI still require separate checks.

## GNOME window tools and global shortcuts

```sh
./build.sh
/usr/bin/python3 install.py --gnome-extension
```

After your next normal login, enable **PowerToys for Linux Window Tools** in
GNOME Extensions, or run:

```sh
gnome-extensions enable powertoys-linux@local
```

Then open the app's **Window tools** page and click **Refresh windows and
monitors**. Select a window and monitor, set a grid and zone number, and snap,
pin, activate or move/resize. Application minimum sizes may constrain the
requested rectangle; Refresh displays the actual result. Leave fullscreen
before placing a window. Refresh after changing your monitor configuration.

GNOME 46 is the tested/supported extension version. A newly installed extension
is discovered on login; this installer does not log you out or restart Shell.
After an extension code update, a new login is also needed to replace cached
JavaScript. See [GNOME's extension development guide](https://gjs.guide/extensions/development/creating.html).

Optional window shortcuts are **unbound by default**. On the Window tools page,
read current shortcuts, enter GTK accelerator notation such as
`<Super><Control>Right`, then save. Bindings need Control, Alt or Super, and the
app rejects duplicates and conflicts it can discover in GNOME's desktop
shortcut settings. Other extensions' private bindings may not be discoverable.
Shortcuts run only while the extension is enabled, and are removed when it is
disabled. General keyboard remapping is not implemented.

Light Switch, ZoomIt, pointer preferences and the drag modifier explicitly
change GNOME settings when you apply them; changes persist after the app closes.
The appearance schedule stops when the app closes and leaves the last applied
preference in place. Pinning/placement remain native window state after an
extension is disabled. GNOME's drag gesture uses the chosen modifier plus the
primary button to move, or the secondary button to resize.

Before uninstalling, remove the OCR shortcut and stop the background helper
from the Text Extractor page. Then remove these paths:

```sh
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/powertoys-linux"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.powertoys.Linux.desktop"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.powertoys.Linux.TextExtractor.desktop"
rm -f "$HOME/.local/bin/powertoys-linux"
```

If you installed the optional extension, disable it before removing its folder:

```sh
gnome-extensions disable powertoys-linux@local
rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/powertoys-linux@local"
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
