// The protocol between the cascade-windows command and this extension (see docs/GNOME.md).
//
// Everything in this file is pure JavaScript without GNOME imports, so it can be tested with Node
// (`node --test gnome-extension/tests/`).

export const PROTOCOL_VERSION = 1;
export const BUS_NAME = 'io.github.anttiraisala.CascadeWindows';
export const OBJECT_PATH = '/io/github/anttiraisala/CascadeWindows';
export const INTERFACE_NAME = 'io.github.anttiraisala.CascadeWindows';

export const INTERFACE_XML = `
<node>
  <interface name="${INTERFACE_NAME}">
    <method name="GetState">
      <arg type="s" direction="out" name="state"/>
    </method>
    <method name="Apply">
      <arg type="s" direction="in" name="operations"/>
      <arg type="s" direction="out" name="result"/>
    </method>
  </interface>
</node>`;

/** The major version of a shell version string such as "46.0" or "50.1". */
export function majorVersion(version) {
    const major = parseInt(String(version).split('.')[0], 10);
    return Number.isNaN(major) ? 0 : major;
}

/** GNOME Shell 46 maximizes and unmaximizes with Meta.MaximizeFlags; from 47 the flags are gone. */
export function usesMaximizeFlags(major) {
    return major < 47;
}

/**
 * Window kind for the protocol: "normal", "dialog" or "other".
 *
 * @param {object} window
 * @param {string} window.typeName NORMAL, DIALOG, MODAL_DIALOG or anything else
 * @param {boolean} window.hasTransientFor the window belongs to another window
 * @param {boolean} window.skipTaskbar the window is not shown in the window list
 * @param {string} window.title
 */
export function classifyWindow({typeName, hasTransientFor, skipTaskbar, title}) {
    // The desktop icons of Ubuntu (Desktop Icons NG) are drawn by windows whose title starts with "@!".
    // They must never be cascaded.
    if (skipTaskbar || String(title).startsWith('@!'))
        return 'other';
    if (typeName === 'DIALOG' || typeName === 'MODAL_DIALOG')
        return 'dialog';
    if (typeName === 'NORMAL')
        return hasTransientFor ? 'dialog' : 'normal';
    return 'other';
}

/** One window of the state, as a plain object. Rectangles are [x, y, width, height]. */
export function windowRecord(fields) {
    return {
        id: fields.id,
        title: fields.title,
        wm_class: fields.wmClass,
        workspace: String(fields.workspace),
        rect: [fields.rect.x, fields.rect.y, fields.rect.width, fields.rect.height],
        kind: fields.kind,
        minimized: Boolean(fields.minimized),
        fullscreen: Boolean(fields.fullscreen),
        sticky: Boolean(fields.sticky),
        maximized: Boolean(fields.maximized),
        resizable: Boolean(fields.resizable),
        stack_index: fields.stackIndex,
        open_index: fields.openIndex,
    };
}

export function buildState({shellVersion, monitors, workspaceCount, currentWorkspace, pointer, windows}) {
    const workspaces = [];
    for (let i = 0; i < workspaceCount; i++)
        workspaces.push(String(i));
    return {
        protocol: PROTOCOL_VERSION,
        shell_version: String(shellVersion),
        monitors,
        workspaces,
        current_workspace: String(currentWorkspace),
        pointer: [pointer.x, pointer.y],
        windows,
    };
}

function isInteger(value) {
    return Number.isInteger(value);
}

function validateOperation(operation) {
    if (operation === null || typeof operation !== 'object' || Array.isArray(operation))
        return 'an operation must be an object';
    if (!isInteger(operation.id))
        return 'the window id must be an integer';
    switch (operation.op) {
    case 'unmaximize':
    case 'raise':
        return null;
    case 'maximize':
        return typeof operation.value === 'boolean' ? null : 'maximize needs a boolean "value"';
    case 'place':
        if (!Array.isArray(operation.rect) || operation.rect.length !== 4 || !operation.rect.every(isInteger))
            return 'place needs "rect": [x, y, width, height] with integers';
        if (typeof operation.resize !== 'boolean')
            return 'place needs a boolean "resize"';
        return null;
    default:
        return `unknown operation "${operation.op}"`;
    }
}

/**
 * Parse the argument of Apply. Returns {operations, errors}; operations that cannot be understood are
 * reported in errors and left out, so one bad operation does not stop the others.
 */
export function parseOperations(text) {
    let data;
    try {
        data = JSON.parse(text);
    } catch (error) {
        return {operations: [], errors: [`the operations are not valid JSON: ${error.message}`]};
    }
    if (!Array.isArray(data))
        return {operations: [], errors: ['the operations must be a JSON array']};
    const operations = [];
    const errors = [];
    data.forEach((operation, index) => {
        const problem = validateOperation(operation);
        if (problem)
            errors.push(`operation ${index}: ${problem}`);
        else
            operations.push(operation);
    });
    return {operations, errors};
}

/**
 * Carry out operations in order. `access` does the actual work:
 *   findWindow(id) -> handle or null, unmaximize(handle), maximize(handle, value),
 *   place(handle, rect, resize), raise(handle)
 * A failing operation is reported and the rest still run. Returns {ok, errors}.
 */
export function runOperations(operations, access) {
    const errors = [];
    for (const operation of operations) {
        const handle = access.findWindow(operation.id);
        if (handle === null || handle === undefined) {
            errors.push(`no window with id ${operation.id}`);
            continue;
        }
        try {
            switch (operation.op) {
            case 'unmaximize':
                access.unmaximize(handle);
                break;
            case 'maximize':
                access.maximize(handle, operation.value);
                break;
            case 'place':
                access.place(handle, operation.rect, operation.resize);
                break;
            case 'raise':
                access.raise(handle);
                break;
            }
        } catch (error) {
            errors.push(`${operation.op} of window ${operation.id} failed: ${error.message}`);
        }
    }
    return {ok: errors.length === 0, errors};
}

/** The result string of Apply. */
export function applyResult(errors) {
    return JSON.stringify({ok: errors.length === 0, errors});
}
