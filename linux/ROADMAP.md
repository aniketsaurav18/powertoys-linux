# Linux port roadmap

The long-term goal is Linux equivalents of all applicable PowerToys utilities.
Stage 1 and five stage-2 workflows are runnable. The inventory below identifies
which functionality is implemented and which still needs a Linux backend.
Existing Windows source remains the behavior reference. The Linux implementation
does not share the Windows JSON/IPC contracts or change their schemas.
The GNOME 46 compositor backend and several stage-3/4 desktop workflows are now
implemented. Functionality and remaining differences are listed in README.md.

## Stages

1. **Native runner and portable workflows:** GTK app, application launcher,
   rename, resize, local text transformations, session sleep inhibition.
2. **Files and desktop services:** Peek, File Locksmith, New+, Color Picker and
   Workspaces application groups are implemented with the limits listed in
   README.md. OCR image/capture controls and a local Tesseract adapter are
   implemented, with a user-local engine installed on this PC and real English
   recognition validated. GNOME shortcut-driven capture with automatic
   background recognition and clipboard delivery is implemented. Interactive
   capture validation and advanced OCR modes
   such as table reconstruction remain.
   Remaining: file-manager actions, persistent module settings and shortcut
   registration through supported desktop interfaces.
3. **Window and input tools:** GNOME 46 extension implements grid placement,
   pinning, cycling, move/resize and optional shortcuts, tested against native
   Wayland windows. GNOME drag modifier configuration, shortcut guide, zoom,
   pointer preferences and a clipboard accent picker are available. Remaining:
   overlay interactions, general remapping, input-method integration, saved
   layouts and separately tested KDE/wlroots/X11 backends.
4. **System tools and network workflows:** displays, themes, host/environment
   editing, sharing input across machines, installer/package formats and distro
   integration. Privileged actions require a separately reviewed backend.
5. **Parity and release:** module-specific settings, localization, plugin
   migration, accessibility, multi-monitor/DPI and multi-machine validation,
   sandboxing/fuzzing, distribution licensing review and packaging.

## Complete source-module inventory

| Upstream module directory (`src/modules/`) | Linux equivalent / approach | Stage |
| --- | --- | --- |
| AdvancedPaste | Local text conversion now; remaining paste/AI workflows later | 1, 5 |
| launcher | Desktop app search now; Run plugin equivalents later | 1, 5 |
| powerrename | Literal file rename now; advanced patterns and folders later | 1, 5 |
| imageresizer | Fit/shrink PNG copies now; formats and remaining modes later | 1, 5 |
| awake | GTK desktop suspend/idle inhibition now | 1 |
| cmdpal | Command Palette shell and Linux extension protocol | 2, 5 |
| peek | UTF-8 and PNG/JPEG preview implemented; more viewers later | 2 |
| FileLocksmith | Readable `/proc/*/fd` inspection implemented; process actions later | 2 |
| NewPlus | File templates implemented; directory templates and file-manager actions later | 2 |
| PowerOCR | Image/screenshot input, crop, local Tesseract OCR and GNOME screen-to-clipboard shortcut implemented; advanced extraction later | 2 |
| colorPicker | Screen-color portal and HEX/RGB implemented; history later | 2 |
| Workspaces | Saved desktop app groups implemented; window restoration later | 2, 3 |
| previewpane | Nautilus/Dolphin preview integration and thumbnail providers | 2 |
| fancyzones | GNOME grid preview and monitor-aware placement implemented; drag/saved layouts later | 3 |
| alwaysontop | GNOME pin/unpin implemented, including optional focused-window shortcut | 3 |
| AltWindowCycle | GNOME active-workspace window cycling implemented; app-group filtering later | 3 |
| CropAndLock | Capture/preview selected windows through screen-sharing portal | 3 |
| GrabAndMove | GNOME explicit move/resize and native modifier-drag configuration implemented | 3 |
| keyboardmanager | Own utility shortcuts configurable; general remapping still requires a backend | 3, 4 |
| poweraccent | Latin clipboard character picker implemented; input-method integration later | 3 |
| ShortcutGuide | GNOME configured-shortcut discovery implemented; overlay later | 3 |
| MouseUtils | GNOME pointer locator and cursor size implemented; overlays/wrapping later | 3 |
| MeasureTool | Screenshot/overlay measurement with scale-aware coordinates | 3 |
| ZoomIt | GNOME magnification/crosshairs implemented; annotation/recording later | 3 |
| LightSwitch | GNOME appearance preference and daily schedule implemented; KDE later | 4 |
| powerdisplay | GNOME DisplayConfig/KScreen and supported DDC backends | 4 |
| EnvironmentVariables | Explicit scope for shell/session env; no Windows registry | 4 |
| Hosts | Preview host edits; privileged writes via reviewed Linux helper | 4 |
| MouseWithoutBorders | New cross-platform input/network backend; physical PCs required | 4, 5 |
| cmdNotFound | Shell integration with the distro command/package database | 4 |
| registrypreview | Windows-only registry semantics; optional `.reg` viewer, no Linux registry | 2, 5 |
| interface | Replace DLL interface with Linux module/backend contract | 1, 5 |

## Completion criteria for later utilities

Each utility needs a working Linux backend, native UI, documented behavior
differences, meaningful tests and fuzz input for file/user-data handling.
Unsupported desktop capabilities must be reported accurately rather than
silently emulated using X11-only tools. Global shortcuts should be registered
with user-visible desktop mechanisms. Window utilities need testing on at least
two monitors with differing scales, and Mouse Without Borders needs physical
machines. Windows GPO, elevation, installer and signing code is not reused.
