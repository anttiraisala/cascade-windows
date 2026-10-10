// Reading the state of the shell and moving windows. This is the only file that talks to Mutter.
//
// GNOME Shell changes its API between releases. The few calls that differ between 46 and later versions
// are isolated here (maximizing and unmaximizing); everything else is stable.

import Meta from 'gi://Meta';

import * as P from './protocol.js';

function windowTypeName(window) {
    switch (window.get_window_type()) {
    case Meta.WindowType.NORMAL:
        return 'NORMAL';
    case Meta.WindowType.DIALOG:
        return 'DIALOG';
    case Meta.WindowType.MODAL_DIALOG:
        return 'MODAL_DIALOG';
    default:
        return 'OTHER';
    }
}

/** True for maximized windows and for windows tiled to a screen edge (which are maximized in one direction). */
function isMaximized(window) {
    if ('maximized_horizontally' in window)
        return Boolean(window.maximized_horizontally || window.maximized_vertically);
    return typeof window.is_maximized === 'function' ? window.is_maximized() : false;
}

export class ShellWindows {
    /**
     * @param {object} shellGlobal the `global` object of GNOME Shell
     * @param {string} shellVersion for example Config.PACKAGE_VERSION
     */
    constructor(shellGlobal, shellVersion) {
        this._global = shellGlobal;
        this._version = shellVersion;
        this._flags = P.usesMaximizeFlags(P.majorVersion(shellVersion));
    }

    _metaWindows() {
        // The actors are in stacking order, bottom to top.
        return this._global.get_window_actors()
            .map(actor => actor.meta_window)
            .filter(window => window && !window.is_override_redirect());
    }

    collectState() {
        const display = this._global.display;
        const workspaceManager = this._global.workspace_manager;
        const activeWorkspace = workspaceManager.get_active_workspace();

        const monitors = [];
        for (let i = 0; i < display.get_n_monitors(); i++) {
            const rect = display.get_monitor_geometry(i);
            const area = activeWorkspace.get_work_area_for_monitor(i);
            monitors.push({
                index: i,
                name: `Monitor ${i}`,
                rect: [rect.x, rect.y, rect.width, rect.height],
                workarea: [area.x, area.y, area.width, area.height],
            });
        }

        const current = workspaceManager.get_active_workspace_index();
        const windows = [];
        this._metaWindows().forEach((window, stackIndex) => {
            const kind = P.classifyWindow({
                typeName: windowTypeName(window),
                hasTransientFor: window.get_transient_for() !== null,
                skipTaskbar: window.skip_taskbar,
                title: window.get_title() ?? '',
            });
            if (kind === 'other')
                return;
            const workspace = window.get_workspace();
            windows.push(P.windowRecord({
                id: window.get_id(),
                title: window.get_title() ?? '',
                wmClass: window.get_wm_class() ?? '',
                workspace: workspace ? workspace.index() : current,
                rect: window.get_frame_rect(),
                kind,
                minimized: window.minimized,
                fullscreen: window.is_fullscreen(),
                sticky: window.is_on_all_workspaces(),
                maximized: isMaximized(window),
                resizable: window.allows_resize(),
                stackIndex,
                openIndex: window.get_stable_sequence(),
            }));
        });

        // open_index: the creation order, 0 = oldest
        const order = windows.map(w => w.open_index).sort((a, b) => a - b);
        windows.forEach(w => {
            w.open_index = order.indexOf(w.open_index);
        });

        const [x, y] = this._global.get_pointer();
        const workspaceCount = workspaceManager.get_n_workspaces();
        return P.buildState({
            shellVersion: this._version,
            monitors,
            workspaceCount,
            workspaceColumns: this._workspaceColumns(workspaceManager, workspaceCount),
            currentWorkspace: current,
            pointer: {x, y},
            windows,
        });
    }

    /** Columns of the workspace grid as Mutter reports them (0 when unknown). */
    _workspaceColumns(workspaceManager, count) {
        try {
            return P.layoutColumns({
                count,
                columns: workspaceManager.layout_columns,
                rows: workspaceManager.layout_rows,
            });
        } catch (error) {
            return 0;
        }
    }

    /** The object runOperations() uses to carry out operations on real windows. */
    access() {
        const byId = new Map(this._metaWindows().map(window => [window.get_id(), window]));
        return {
            findWindow: id => byId.get(id) ?? null,
            unmaximize: window => this._setMaximized(window, false),
            maximize: (window, value) => this._setMaximized(window, value),
            place: (window, rect, resize) => {
                if (isMaximized(window))
                    throw new Error('the window is still maximized');
                const [x, y, width, height] = rect;
                if (resize && window.allows_resize())
                    window.move_resize_frame(true, x, y, width, height);
                else
                    window.move_frame(true, x, y);
            },
            raise: window => window.raise(),
        };
    }

    _setMaximized(window, value) {
        if (value === isMaximized(window))
            return;
        if (this._flags) {
            // GNOME Shell 46
            if (value)
                window.maximize(Meta.MaximizeFlags.BOTH);
            else
                window.unmaximize(Meta.MaximizeFlags.BOTH);
        } else if (value) {
            window.maximize();
        } else {
            window.unmaximize();
        }
    }
}
