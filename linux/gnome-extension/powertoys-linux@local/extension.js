// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {rectangle, zone} from './geometry.js';

const XML = `<node>
<interface name="io.github.powertoys.Linux.WindowTools">
<method name="GetState"><arg direction="out" type="s"/></method>
<method name="Snap"><arg direction="in" type="u"/><arg direction="in" type="u"/>
<arg direction="in" type="u"/><arg direction="in" type="u"/><arg direction="in" type="u"/>
<arg direction="in" type="u"/><arg direction="out" type="b"/></method>
<method name="MoveResize"><arg direction="in" type="u"/><arg direction="in" type="u"/>
<arg direction="in" type="i"/><arg direction="in" type="i"/><arg direction="in" type="u"/>
<arg direction="in" type="u"/><arg direction="out" type="b"/></method>
<method name="SetAbove"><arg direction="in" type="u"/><arg direction="in" type="b"/>
<arg direction="out" type="b"/></method>
<method name="Activate"><arg direction="in" type="u"/><arg direction="out" type="b"/></method>
<method name="Cycle"><arg direction="in" type="i"/><arg direction="out" type="u"/></method>
</interface></node>`;

function plainRect(rect) {
    return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
}

export default class PowerToysWindowTools extends Extension {
    enable() {
        this._bindings = [];
        try {
            this._enable();
        } catch (error) {
            this.disable();
            throw error;
        }
    }

    _enable() {
        this._bus = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._bus.export(Gio.DBus.session, '/io/github/powertoys/Linux/WindowTools');
        this._settings = this.getSettings();
        const focused = () => this._window(global.display.focus_window?.get_stable_sequence());
        const actions = {
            'powertoys-cycle-next': () => this.Cycle(1),
            'powertoys-toggle-above': () => {
                const window = focused();
                this.SetAbove(window.get_stable_sequence(), !window.is_above());
            },
            'powertoys-snap-left': () => {
                const window = focused();
                this.Snap(window.get_stable_sequence(), window.get_monitor(), 2, 1, 0, 8);
            },
            'powertoys-snap-right': () => {
                const window = focused();
                this.Snap(window.get_stable_sequence(), window.get_monitor(), 2, 1, 1, 8);
            },
            'powertoys-launcher': () => {
                const executable = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'powertoys-linux']);
                Gio.Subprocess.new([executable], Gio.SubprocessFlags.NONE);
            },
        };
        for (const [name, action] of Object.entries(actions)) {
            Main.wm.addKeybinding(name, this._settings, Meta.KeyBindingFlags.NONE,
                Shell.ActionMode.NORMAL, () => {
                    try {
                        action();
                    } catch (error) {
                        console.warn(`PowerToys shortcut: ${error.message}`);
                    }
                });
            this._bindings.push(name);
        }
    }

    disable() {
        for (const name of this._bindings ?? [])
            Main.wm.removeKeybinding(name);
        this._bindings = [];
        this._settings = null;
        this._bus?.unexport();
        this._bus = null;
    }

    _windows() {
        return global.get_window_actors().map(actor => actor.meta_window)
            .filter(window => window.get_window_type() === Meta.WindowType.NORMAL &&
                !window.is_override_redirect() && !window.skip_taskbar);
    }

    _window(id) {
        const window = this._windows().find(item => item.get_stable_sequence() === id);
        if (!window)
            throw new Error('The selected window has closed. Refresh the window list.');
        return window;
    }

    _area(monitor) {
        if (!Number.isInteger(monitor) || monitor < 0 || monitor >= Main.layoutManager.monitors.length)
            throw new Error('The selected monitor is unavailable. Refresh the monitor list.');
        return global.workspace_manager.get_active_workspace().get_work_area_for_monitor(monitor);
    }

    GetState() {
        const monitors = Main.layoutManager.monitors.map((monitor, index) => ({
            index, ...plainRect(this._area(index)),
            scale: global.display.get_monitor_scale(index),
        }));
        const windows = this._windows().map(window => ({
            id: window.get_stable_sequence(), title: window.get_title() ?? '',
            app: window.get_wm_class() ?? '', monitor: window.get_monitor(),
            workspace: window.get_workspace()?.index() ?? -1,
            above: window.is_above(), fullscreen: window.is_fullscreen(),
            rect: plainRect(window.get_frame_rect()),
        }));
        return JSON.stringify({version: 1, monitors, windows});
    }

    _place(window, monitor, rect) {
        if (window.is_fullscreen() || !window.allows_move() || !window.allows_resize())
            throw new Error('This window does not permit placement. Leave fullscreen first.');
        window.unmaximize(Meta.MaximizeFlags.BOTH);
        window.unminimize();
        if (window.get_monitor() !== monitor)
            window.move_to_monitor(monitor);
        window.move_resize_frame(true, rect.x, rect.y, rect.width, rect.height);
        // The client may enforce a minimum size, so GetState reports actual geometry.
        return true;
    }

    Snap(id, monitor, columns, rows, index, gap) {
        return this._place(this._window(id), monitor, zone(this._area(monitor), columns, rows, index, gap));
    }

    MoveResize(id, monitor, x, y, width, height) {
        return this._place(this._window(id), monitor, rectangle(x, y, width, height, this._area(monitor)));
    }

    SetAbove(id, above) {
        const window = this._window(id);
        if (above)
            window.make_above();
        else
            window.unmake_above();
        return true;
    }

    Activate(id) {
        this._window(id).activate(global.get_current_time());
        return true;
    }

    Cycle(direction) {
        if (direction !== -1 && direction !== 1)
            throw new Error('Cycle direction must be -1 or 1.');
        // Stable order prevents alternating only between the two most recent windows.
        const workspace = global.workspace_manager.get_active_workspace();
        const windows = this._windows().filter(window => window.located_on_workspace(workspace))
            .sort((a, b) => a.get_stable_sequence() - b.get_stable_sequence());
        if (!windows.length)
            return 0;
        const current = windows.indexOf(global.display.focus_window);
        const index = current < 0 ? 0 : (current + direction + windows.length) % windows.length;
        windows[index].activate(global.get_current_time());
        return windows[index].get_stable_sequence();
    }
}
