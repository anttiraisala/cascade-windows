// The D-Bus service the cascade-windows command talks to.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import * as P from './protocol.js';

export class Service {
    /** @param {import('./windows.js').ShellWindows} windows */
    constructor(windows) {
        this._windows = windows;
        this._exported = null;
        this._ownerId = 0;
    }

    start() {
        this._exported = Gio.DBusExportedObject.wrapJSObject(P.INTERFACE_XML, this);
        this._exported.export(Gio.DBus.session, P.OBJECT_PATH);
        this._ownerId = Gio.bus_own_name_on_connection(
            Gio.DBus.session, P.BUS_NAME, Gio.BusNameOwnerFlags.NONE, null, null);
    }

    stop() {
        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }
        if (this._exported) {
            this._exported.unexport();
            this._exported = null;
        }
    }

    // D-Bus method GetState() -> s
    GetState() {
        return new GLib.Variant('(s)', [JSON.stringify(this._windows.collectState())]);
    }

    // D-Bus method Apply(s) -> s
    Apply(text) {
        const {operations, errors} = P.parseOperations(text);
        const result = P.runOperations(operations, this._windows.access());
        return new GLib.Variant('(s)', [P.applyResult([...errors, ...result.errors])]);
    }
}
