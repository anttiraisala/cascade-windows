// The panel menu with the same entries as the desktop menus of the other versions.

import GObject from 'gi://GObject';
import St from 'gi://St';

import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

// Entries in menu order. `args` are passed to the cascade-windows command.
export const MENU_ENTRIES = [
    {label: 'Cascade Windows', args: ['--scope', 'monitor']},
    {label: 'Cascade Workspace', args: ['--scope', 'workspace']},
    {label: 'Cascade All Workspaces', args: ['--scope', 'all']},
    null,
    {label: 'Undo Cascade', args: ['--undo']},
    {label: 'Cascade Settings...', args: ['--edit-config']},
];

export const CascadeIndicator = GObject.registerClass(
class CascadeIndicator extends PanelMenu.Button {
    /**
     * @param {function(string[]): void} run starts the cascade-windows command with the given arguments
     * @param {Gio.Icon} icon the top bar icon (a symbolic SVG, so that the shell can recolor it)
     */
    _init(run, icon) {
        super._init(0.0, 'Cascade Windows');
        this.add_child(new St.Icon({
            gicon: icon,
            style_class: 'system-status-icon',
        }));
        for (const entry of MENU_ENTRIES) {
            if (entry === null)
                this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            else
                this.menu.addAction(entry.label, () => run(entry.args));
        }
    }
});
