# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Native GTK front end; desktop operations are delegated to GIO and GNOME."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

from .core import TEXT_ACTIONS, apply_renames, rename_plan, transform_text
from .images import resize_image
from .files import copy_template, open_file_processes, text_preview
from .desktop import ColorRequest, color_formats
from . import workspaces
from .gnome_ui import GnomeViews


class PowerToys(Gtk.Application, GnomeViews):
    def __init__(self, smoke_test=False, application_id="io.github.powertoys.Linux"):
        super().__init__(application_id=application_id, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.smoke_test = smoke_test
        self.smoke_failed = False
        self.window = None
        self.inhibitor = 0
        self.awake_timer = 0
        self.plan = []
        self.undo = []
        self.files = []
        self.image_files = []
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.color_request = None
        self.workspace_config = workspaces.config_path()
        self.template = None
        self.template_folder = None
        self.init_gnome()

    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title="PowerToys for Linux · Experimental")
        self.window.set_default_size(1020, 760)
        header = Gtk.HeaderBar(title="PowerToys for Linux", subtitle="Experimental Linux edition · GNOME tools")
        header.set_show_close_button(True)
        self.window.set_titlebar(header)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window.add(layout)
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        layout.pack_start(content, True, True, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        sidebar = Gtk.StackSidebar(stack=self.stack)
        sidebar.set_size_request(190, -1)
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.add(sidebar)
        content.pack_start(sidebar_scroll, False, False, 0)
        content.pack_start(self.stack, True, True, 0)
        self.status = Gtk.Label(label="Ready", xalign=0)
        self.status.set_margin_start(20)
        self.status.set_margin_end(20)
        self.status.set_margin_top(10)
        self.status.set_margin_bottom(10)
        self.status.set_line_wrap(True)
        layout.pack_end(self.status, False, False, 0)
        self.launcher_page()
        self.rename_page()
        self.image_page()
        self.text_page()
        self.awake_page()
        self.peek_page()
        self.locksmith_page()
        self.color_page()
        self.newplus_page()
        self.workspace_page()
        self.window_tools_page()
        self.lightswitch_page()
        self.zoom_page()
        self.mouse_page()
        self.shortcut_page()
        self.accent_page()
        self.about_page()
        self.window.show_all()
        if self.smoke_test:
            GLib.timeout_add(700, self.finish_smoke_test)

    def page(self, key, title, description):
        scroll = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for setter in (box.set_margin_start, box.set_margin_end, box.set_margin_top, box.set_margin_bottom):
            setter(24)
        heading = Gtk.Label(xalign=0)
        heading.set_markup(f"<span size='x-large' weight='bold'>{GLib.markup_escape_text(title)}</span>")
        box.pack_start(heading, False, False, 0)
        label = Gtk.Label(label=description, xalign=0)
        label.set_line_wrap(True)
        box.pack_start(label, False, False, 0)
        scroll.add(box)
        self.stack.add_titled(scroll, key, title)
        return box

    def button(self, box, title, callback):
        button = Gtk.Button(label=title)
        button.connect("clicked", lambda _: self.guard(callback))
        box.pack_start(button, False, False, 0)
        return button

    def guard(self, callback):
        try:
            callback()
        except Exception as error:
            self.status.set_text(str(error))

    def choose_files(self, title, multiple=True):
        dialog = Gtk.FileChooserDialog(title=title, transient_for=self.window, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK)
        dialog.set_select_multiple(multiple)
        result = dialog.get_filenames() if dialog.run() == Gtk.ResponseType.OK else []
        dialog.destroy()
        return result

    def launcher_page(self):
        box = self.page("launcher", "PowerToys Run", "Search installed applications. Press Enter to launch the first result.")
        self.search = Gtk.SearchEntry(placeholder_text="Search applications…")
        box.pack_start(self.search, False, False, 0)
        self.apps = sorted((app for app in Gio.AppInfo.get_all() if app.should_show()), key=lambda app: app.get_display_name().casefold())
        self.app_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        box.pack_start(self.app_list, True, True, 0)
        self.app_list.connect("row-activated", lambda _, row: self.guard(lambda: self.launch(row.app)))
        self.search.connect("search-changed", lambda _: self.filter_apps())
        self.search.connect("activate", lambda _: self.guard(self.launch_first))
        self.filter_apps()

    def filter_apps(self):
        for row in self.app_list.get_children():
            self.app_list.remove(row)
        words = self.search.get_text().casefold().split()
        apps = [app for app in self.apps if all(word in f"{app.get_display_name()} {app.get_description() or ''} {app.get_executable() or ''}".casefold() for word in words)]
        for app in apps[:60]:
            row = Gtk.ListBoxRow()
            row.app = app
            label = Gtk.Label(label=app.get_display_name(), xalign=0)
            label.set_margin_top(10)
            label.set_margin_bottom(10)
            label.set_margin_start(12)
            row.add(label)
            self.app_list.add(row)
        self.app_list.show_all()

    def launch_first(self):
        row = self.app_list.get_selected_row() or self.app_list.get_row_at_index(0)
        if row:
            self.launch(row.app)

    def launch(self, app):
        context = self.window.get_display().get_app_launch_context()
        if not app.launch([], context):
            raise RuntimeError("The desktop could not launch this application.")
        self.status.set_text(f"Launched {app.get_display_name()}")

    def rename_page(self):
        box = self.page("rename", "PowerRename", "Bulk literal search and replace for files, with preview and session undo. Folders and regex are planned for a later stage.")
        self.button(box, "Select files…", self.select_rename)
        self.rename_selection = Gtk.Label(label="No files selected", xalign=0)
        box.pack_start(self.rename_selection, False, False, 0)
        self.find = Gtk.Entry(placeholder_text="Search for")
        self.replace = Gtk.Entry(placeholder_text="Replace with (can be empty)")
        for entry in (self.find, self.replace):
            box.pack_start(entry, False, False, 0)
            entry.connect("changed", lambda _: self.invalidate_plan())
        self.case_sensitive = Gtk.CheckButton(label="Case sensitive")
        self.stem_only = Gtk.CheckButton(label="Change filename only; keep extension")
        self.stem_only.set_active(True)
        self.all_matches = Gtk.CheckButton(label="Replace all occurrences")
        self.all_matches.set_active(True)
        for check in (self.case_sensitive, self.stem_only, self.all_matches):
            check.connect("toggled", lambda _: self.invalidate_plan())
            box.pack_start(check, False, False, 0)
        self.preview = Gtk.ListStore(str, str)
        tree = Gtk.TreeView(model=self.preview)
        for index, title in enumerate(("Current name", "New name")):
            tree.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=index))
        tree.set_size_request(-1, 180)
        box.pack_start(tree, True, True, 0)
        actions = Gtk.Box(spacing=10)
        box.pack_start(actions, False, False, 0)
        self.button(actions, "Preview", self.preview_rename)
        self.apply_button = self.button(actions, "Apply rename", self.apply_rename)
        self.apply_button.set_sensitive(False)
        self.undo_button = self.button(actions, "Undo last rename", self.undo_rename)
        self.undo_button.set_sensitive(False)

    def invalidate_plan(self):
        self.plan = []
        self.preview.clear()
        self.apply_button.set_sensitive(False)

    def select_rename(self):
        selected = self.choose_files("Select files to rename")
        if selected:
            self.files = selected
            self.rename_selection.set_text(f"{len(selected)} files selected")
            self.invalidate_plan()

    def preview_rename(self):
        self.invalidate_plan()
        self.plan = rename_plan(self.files, self.find.get_text(), self.replace.get_text(), self.case_sensitive.get_active(), self.stem_only.get_active(), self.all_matches.get_active())
        for entry in self.plan:
            self.preview.append((entry.source.name, entry.target.name))
        self.apply_button.set_sensitive(bool(self.plan))
        self.status.set_text(f"{len(self.plan)} files will change. Review the preview, then apply.")

    def apply_rename(self):
        plan = self.plan
        self.invalidate_plan()
        self.undo = apply_renames(plan)
        changed = {entry.source: str(entry.target) for entry in plan}
        self.files = [changed.get(Path(path), path) for path in self.files]
        self.undo_button.set_sensitive(bool(self.undo))
        self.status.set_text(f"Renamed {len(plan)} files.")

    def undo_rename(self):
        plan = self.undo
        apply_renames(plan)
        changed = {entry.source: str(entry.target) for entry in plan}
        self.files = [changed.get(Path(path), path) for path in self.files]
        self.undo = []
        self.undo_button.set_sensitive(False)
        self.invalidate_plan()
        self.status.set_text("Previous filenames restored.")

    def image_page(self):
        box = self.page("images", "Image Resizer", "Fit PNG or JPEG images inside a box. Saves new PNG copies beside the originals. Animation and metadata preservation are not supported in this stage.")
        self.button(box, "Select images…", self.select_images)
        self.image_selection = Gtk.Label(label="No images selected", xalign=0)
        box.pack_start(self.image_selection, False, False, 0)
        row = Gtk.Box(spacing=10)
        self.width = Gtk.SpinButton.new_with_range(1, 16384, 1)
        self.height = Gtk.SpinButton.new_with_range(1, 16384, 1)
        self.width.set_value(1280)
        self.height.set_value(720)
        for label, spin in (("Width", self.width), ("Height", self.height)):
            row.pack_start(Gtk.Label(label=label), False, False, 0)
            row.pack_start(spin, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.shrink = Gtk.CheckButton(label="Only shrink; do not enlarge")
        self.shrink.set_active(True)
        box.pack_start(self.shrink, False, False, 0)
        self.resize_button = self.button(box, "Resize selected images", self.resize_images)

    def select_images(self):
        selected = self.choose_files("Select PNG or JPEG images")
        if selected:
            self.image_files = selected
            self.image_selection.set_text(f"{len(selected)} images selected")

    def resize_images(self):
        if not self.image_files:
            raise ValueError("Select images first.")
        paths = tuple(self.image_files)
        width, height = self.width.get_value_as_int(), self.height.get_value_as_int()
        shrink = self.shrink.get_active()
        self.resize_button.set_sensitive(False)
        self.status.set_text("Resizing…")

        def work():
            outputs, failures = [], []
            for path in paths:
                try:
                    outputs.append(str(resize_image(path, width, height, shrink)))
                except Exception as error:
                    failures.append(f"{path}: {error}")
            GLib.idle_add(done, outputs, failures)

        def done(outputs, failures):
            self.resize_button.set_sensitive(True)
            message = f"Saved {len(outputs)} resized copies beside the originals."
            if failures:
                message += f" {len(failures)} failed. " + " | ".join(failures)
            self.status.set_text(message)
            return False

        self.pool.submit(work)

    def text_page(self):
        box = self.page("text", "Advanced Paste", "Convert text locally, then copy the result. Clipboard content is read only when you click Paste.")
        self.text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(280)
        scroll.add(self.text)
        box.pack_start(scroll, True, True, 0)
        self.text_action = Gtk.ComboBoxText()
        for action in TEXT_ACTIONS:
            self.text_action.append_text(action)
        self.text_action.set_active(0)
        box.pack_start(self.text_action, False, False, 0)
        row = Gtk.Box(spacing=10)
        box.pack_start(row, False, False, 0)
        self.button(row, "Paste", self.paste_text)
        self.button(row, "Convert", self.convert_text)
        self.button(row, "Copy result", self.copy_text)

    def get_text(self):
        buffer = self.text.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

    def paste_text(self):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        def received(_, value, *__):
            if value is not None:
                self.text.get_buffer().set_text(value)
                self.status.set_text("Pasted clipboard text.")
        clipboard.request_text(received, None)

    def convert_text(self):
        result = transform_text(self.get_text(), self.text_action.get_active_text())
        self.text.get_buffer().set_text(result)
        self.status.set_text("Text converted. Copy result to use it elsewhere.")

    def copy_text(self):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self.get_text(), -1)
        self.status.set_text("Copied to clipboard. Keep this app open until you paste.")

    def awake_page(self):
        box = self.page("awake", "Awake", "Keep the computer awake while this app is open. Uses the desktop session's suspend inhibitor; your power settings are unchanged.")
        self.minutes = Gtk.SpinButton.new_with_range(0, 1440, 1)
        self.minutes.set_value(60)
        box.pack_start(Gtk.Label(label="Duration in minutes (0 = until stopped)", xalign=0), False, False, 0)
        box.pack_start(self.minutes, False, False, 0)
        self.keep_display = Gtk.CheckButton(label="Keep display on (also prevents automatic session locking)")
        box.pack_start(self.keep_display, False, False, 0)
        self.awake_state = Gtk.Label(label="Off", xalign=0)
        box.pack_start(self.awake_state, False, False, 0)
        self.button(box, "Start Awake", self.start_awake)
        self.button(box, "Stop Awake", self.stop_awake)

    def start_awake(self):
        self.stop_awake()
        flags = Gtk.ApplicationInhibitFlags.SUSPEND
        if self.keep_display.get_active():
            flags |= Gtk.ApplicationInhibitFlags.IDLE
        self.inhibitor = self.inhibit(self.window, flags, "PowerToys Awake")
        if not self.inhibitor:
            raise RuntimeError("This desktop did not grant a sleep inhibitor.")
        minutes = self.minutes.get_value_as_int()
        if minutes:
            self.awake_timer = GLib.timeout_add_seconds(minutes * 60, self.expire_awake)
        self.awake_state.set_text(f"On · {minutes} minutes" if minutes else "On · until stopped or app closes")
        self.status.set_text("Awake enabled.")

    def expire_awake(self):
        self.awake_timer = 0
        self.stop_awake()
        return False

    def stop_awake(self):
        if self.awake_timer:
            GLib.source_remove(self.awake_timer)
            self.awake_timer = 0
        if self.inhibitor:
            self.uninhibit(self.inhibitor)
            self.inhibitor = 0
        if hasattr(self, "awake_state"):
            self.awake_state.set_text("Off")
            self.status.set_text("Awake disabled.")

    def about_page(self):
        self.page("about", "About this port", "This experimental Linux edition provides portable file/text tools and GNOME desktop tools. Full Windows feature parity remains in progress.\n\nThe GNOME 46 Window Tools extension supports zones, pinning, cycling, move/resize and optional shortcuts for native Wayland windows. Install and enable it after your next login.\n\nGNOME tools include theme scheduling, magnification, pointer preferences and shortcut discovery. Quick Accent offers a clipboard character picker.\n\nNext: OCR, file-manager integration, general keyboard remapping, capture overlays and system/network utilities. No telemetry or network services.\n\nSee linux/ROADMAP.md in the source repository for the full utility inventory.")

    def newplus_page(self):
        box = self.page("newplus", "New+", "Create a new file from a template. Select a regular file, choose a folder, and enter the new filename including its extension. Files are copied without overwriting existing names.")
        self.button(box, "Choose template file…", self.select_template)
        self.template_label = Gtk.Label(label="No template selected", xalign=0)
        self.template_label.set_line_wrap(True)
        box.pack_start(self.template_label, False, False, 0)
        self.button(box, "Choose destination folder…", self.select_template_folder)
        self.folder_label = Gtk.Label(label="No folder selected", xalign=0)
        self.folder_label.set_line_wrap(True)
        box.pack_start(self.folder_label, False, False, 0)
        self.new_name = Gtk.Entry(placeholder_text="New filename, e.g. report.md")
        box.pack_start(self.new_name, False, False, 0)
        self.button(box, "Create file", self.create_from_template)

    def select_template(self):
        paths = self.choose_files("Select a template file", multiple=False)
        if paths:
            self.template = paths[0]
            self.template_label.set_text(self.template)
            self.new_name.set_text(Path(self.template).name)

    def select_template_folder(self):
        dialog = Gtk.FileChooserDialog(title="Choose destination", transient_for=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.template_folder = dialog.get_filename()
            self.folder_label.set_text(self.template_folder)
        dialog.destroy()

    def create_from_template(self):
        if not self.template or not self.template_folder:
            raise ValueError("Select a template and destination folder first.")
        target = copy_template(self.template, self.template_folder, self.new_name.get_text())
        self.status.set_text(f"Created {target}")

    def workspace_page(self):
        box = self.page("workspaces", "Workspaces", "Save groups of installed applications and launch them together. Window positions and monitor layouts need the later compositor backend.")
        self.workspace_choice = Gtk.ComboBoxText()
        box.pack_start(self.workspace_choice, False, False, 0)
        row = Gtk.Box(spacing=10)
        box.pack_start(row, False, False, 0)
        self.button(row, "Launch selected workspace", self.launch_workspace)
        self.button(row, "Delete selected workspace", self.delete_workspace)
        self.workspace_name = Gtk.Entry(placeholder_text="Workspace name")
        box.pack_start(self.workspace_name, False, False, 0)
        self.workspace_apps = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE)
        app_scroll = Gtk.ScrolledWindow()
        app_scroll.set_min_content_height(260)
        app_scroll.add(self.workspace_apps)
        box.pack_start(app_scroll, True, True, 0)
        for app in self.apps:
            if not app.get_id() or not app.get_id().endswith(".desktop"):
                continue
            row = Gtk.ListBoxRow()
            row.app_id = app.get_id()
            label = Gtk.Label(label=app.get_display_name(), xalign=0)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            row.add(label)
            self.workspace_apps.add(row)
        self.button(box, "Save selected applications as workspace", self.save_workspace)
        self.guard(self.refresh_workspaces)

    def refresh_workspaces(self):
        groups = workspaces.load(self.workspace_config)
        self.workspace_choice.remove_all()
        for name in sorted(groups):
            self.workspace_choice.append_text(name)
        if groups:
            self.workspace_choice.set_active(0)

    def save_workspace(self):
        groups = workspaces.load(self.workspace_config)
        name = self.workspace_name.get_text().strip()
        groups[name] = [row.app_id for row in self.workspace_apps.get_selected_rows()]
        workspaces.save(self.workspace_config, groups)
        self.refresh_workspaces()
        self.status.set_text(f"Saved workspace {name}")

    def delete_workspace(self):
        name = self.workspace_choice.get_active_text()
        if not name:
            raise ValueError("Select a saved workspace first.")
        groups = workspaces.load(self.workspace_config)
        groups.pop(name, None)
        workspaces.save(self.workspace_config, groups)
        self.refresh_workspaces()
        self.status.set_text(f"Deleted workspace {name}")

    def launch_workspace(self):
        name = self.workspace_choice.get_active_text()
        if not name:
            raise ValueError("Select a saved workspace first.")
        groups = workspaces.load(self.workspace_config)
        apps = {app.get_id(): app for app in self.apps}
        failures, launched = [], 0
        for app_id in groups.get(name, []):
            try:
                if app_id not in apps:
                    raise ValueError("Application is no longer installed")
                self.launch(apps[app_id])
                launched += 1
            except Exception as error:
                failures.append(f"{app_id}: {error}")
        self.status.set_text(f"Launched {launched} applications." + (" Failed: " + " | ".join(failures) if failures else ""))

    def peek_page(self):
        box = self.page("peek", "Peek", "Preview a UTF-8 text file or PNG/JPEG image. Text previews are limited to 200 KB; images to 40 megapixels.")
        self.button(box, "Open file…", self.open_preview)
        self.peek_name = Gtk.Label(label="No file selected", xalign=0)
        self.peek_name.set_line_wrap(True)
        box.pack_start(self.peek_name, False, False, 0)
        self.peek_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(self.peek_content, True, True, 0)

    def open_preview(self):
        paths = self.choose_files("Choose a file to preview", multiple=False)
        if paths:
            self.show_preview(paths[0])

    def show_preview(self, path):
        from .core import fingerprint
        fingerprint(path)
        image_format, width, height = GdkPixbuf.Pixbuf.get_file_info(str(path))
        if image_format and image_format.get_name() in ("png", "jpeg"):
            if width * height > 40_000_000:
                raise ValueError("Image previews are limited to 40 megapixels.")
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 680, 500, True).apply_embedded_orientation()
            widget = Gtk.Image.new_from_pixbuf(pixbuf)
        else:
            value = text_preview(path)
            widget = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            widget.get_buffer().set_text(value)
        for child in self.peek_content.get_children():
            self.peek_content.remove(child)
        self.peek_content.pack_start(widget, True, True, 0)
        self.peek_content.show_all()
        self.peek_name.set_text(str(path))
        self.status.set_text("Preview ready.")

    def locksmith_page(self):
        box = self.page("locksmith", "File Locksmith", "Find processes with an open descriptor for a selected file. Results cover readable /proc entries; memory mappings without an open descriptor are not included. No processes are stopped.")
        self.locksmith_button = self.button(box, "Select file and inspect…", self.inspect_file)
        self.locksmith_results = Gtk.ListStore(int, str)
        tree = Gtk.TreeView(model=self.locksmith_results)
        for index, title in enumerate(("PID", "Process")):
            tree.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=index))
        box.pack_start(tree, True, True, 0)
        self.locksmith_name = Gtk.Label(label="No file selected", xalign=0)
        self.locksmith_name.set_line_wrap(True)
        box.pack_start(self.locksmith_name, False, False, 0)

    def inspect_file(self):
        paths = self.choose_files("Choose a file to inspect", multiple=False)
        if not paths:
            return
        path = paths[0]
        self.locksmith_button.set_sensitive(False)
        self.locksmith_results.clear()
        self.locksmith_name.set_text(path)
        self.status.set_text("Inspecting open file descriptors…")
        def done(matches, inaccessible, error):
            self.locksmith_button.set_sensitive(True)
            for match in matches:
                self.locksmith_results.append(match)
            self.status.set_text(error or f"{len(matches)} processes have this file open. {inaccessible} process descriptor folders were inaccessible. Results are a moment-in-time snapshot.")
            return False
        def work():
            try:
                matches, inaccessible = open_file_processes(path)
                GLib.idle_add(done, matches, inaccessible, None)
            except Exception as error:
                GLib.idle_add(done, [], 0, str(error))
        self.pool.submit(work)

    def color_page(self):
        box = self.page("color", "Color Picker", "Pick a screen pixel using the desktop's color portal. Works with native Wayland windows when the desktop supports PickColor.")
        self.pick_button = self.button(box, "Pick screen color…", self.pick_color)
        self.color_hex = Gtk.Entry(editable=False, placeholder_text="HEX color")
        self.color_rgb = Gtk.Entry(editable=False, placeholder_text="RGB color")
        box.pack_start(self.color_hex, False, False, 0)
        box.pack_start(self.color_rgb, False, False, 0)
        self.button(box, "Copy HEX", lambda: self.copy_color(self.color_hex.get_text()))
        self.button(box, "Copy RGB", lambda: self.copy_color(self.color_rgb.get_text()))

    def pick_color(self):
        self.pick_button.set_sensitive(False)
        try:
            self.color_request = ColorRequest(self.color_received)
        except Exception:
            self.pick_button.set_sensitive(True)
            raise
        self.status.set_text("Choose a pixel in the desktop picker; press Escape to cancel.")

    def color_received(self, color, error):
        self.color_request = None
        self.pick_button.set_sensitive(True)
        if error:
            self.status.set_text(error)
            return
        hex_value, rgb = color_formats(color)
        self.color_hex.set_text(hex_value)
        self.color_rgb.set_text(rgb)
        self.status.set_text(f"Picked {hex_value}")

    def copy_color(self, value):
        if not value:
            raise ValueError("Pick a color first.")
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(value, -1)
        self.status.set_text(f"Copied {value}. Keep this app open until you paste.")

    def finish_smoke_test(self):
        try:
            self.smoke_checks()
        except Exception as error:
            print(f"GUI smoke test failed: {error}", file=sys.stderr, flush=True)
            self.smoke_failed = True
        self.quit()
        return False

    def smoke_checks(self):
        assert self.stack.get_children() and len(self.stack.get_children()) == 17
        self.text.get_buffer().set_text('{"linux":true}')
        self.convert_text()
        assert '"linux": true' in self.get_text()
        self.search.set_text("unlikely-application-name-1298765")
        self.filter_apps()
        assert not self.app_list.get_children()
        print(f"GUI smoke test passed: 17 pages, text conversion, application search; {len(self.apps)} installed apps.", flush=True)

    def do_shutdown(self):
        self.stop_theme_schedule()
        if self.color_request:
            self.color_request.cancel()
        self.stop_awake()
        self.pool.shutdown(wait=True)
        Gtk.Application.do_shutdown(self)


def main():
    if sys.argv[1:] not in ([], ["--smoke-test"]):
        print("Usage: powertoys-linux [--smoke-test]", file=sys.stderr)
        return 2
    if not Gtk.init_check()[0]:
        print("No graphical desktop available. Run powertoys-linux from your desktop session.", file=sys.stderr)
        return 1
    app = PowerToys(smoke_test="--smoke-test" in sys.argv)
    status = app.run([sys.argv[0]])
    return 1 if app.smoke_failed else status
