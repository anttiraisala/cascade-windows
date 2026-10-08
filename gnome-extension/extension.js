// Cascade Windows: GNOME Shell extension.
//
// A thin window mover. It reports the state of the shell and moves windows on request over D-Bus; all
// layout decisions are made by the cascade-windows command (see docs/GNOME.md). The keyboard shortcut and
// the panel menu start that command.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {PACKAGE_VERSION} from 'resource:///org/gnome/shell/misc/config.js';

import {CascadeIndicator} from './lib/panel.js';
import {Service} from './lib/service.js';
import {ShellWindows} from './lib/windows.js';

const COMMAND_NAME = 'cascade-windows';

// Shortcut setting name -> arguments of the command
const SHORTCUTS = {
    'cascade-monitor': ['--scope', 'monitor'],
    'cascade-workspace': ['--scope', 'workspace'],
    'cascade-all': ['--scope', 'all'],
    'undo-cascade': ['--undo'],
};

function findCommand() {
    const installed = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', COMMAND_NAME]);
    if (GLib.file_test(installed, GLib.FileTest.IS_EXECUTABLE))
        return installed;
    return GLib.find_program_in_path(COMMAND_NAME);
}

export default class CascadeWindowsExtension extends Extension {
    enable() {
        this._service = new Service(new ShellWindows(global, PACKAGE_VERSION));
        this._service.start();

        this._settings = this.getSettings();
        for (const [name, args] of Object.entries(SHORTCUTS)) {
            Main.wm.addKeybinding(name, this._settings, Meta.KeyBindingFlags.NONE,
                Shell.ActionMode.NORMAL, () => this._run(args));
        }

        const icon = Gio.icon_new_for_string(GLib.build_filenamev([this.path, 'icons', 'cascade-symbolic.svg']));
        this._indicator = new CascadeIndicator(args => this._run(args), icon);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        for (const name of Object.keys(SHORTCUTS))
            Main.wm.removeKeybinding(name);
        this._settings = null;

        this._indicator?.destroy();
        this._indicator = null;

        this._service?.stop();
        this._service = null;
    }

    /** Start the cascade-windows command without waiting for it (it calls back into this extension). */
    _run(args) {
        const command = findCommand();
        if (command === null) {
            Main.notify('Cascade Windows',
                'The cascade-windows command was not found. Run ./install.sh from the project folder.');
            return;
        }
        try {
            Gio.Subprocess.new([command, '--backend', 'gnome', ...args], Gio.SubprocessFlags.NONE);
        } catch (error) {
            Main.notify('Cascade Windows', `Could not start ${command}: ${error.message}`);
        }
    }
}
