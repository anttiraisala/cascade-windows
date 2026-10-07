import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';

import * as P from '../lib/protocol.js';

test('major version of shell version strings', () => {
    assert.equal(P.majorVersion('46.0'), 46);
    assert.equal(P.majorVersion('50.1'), 50);
    assert.equal(P.majorVersion('47.alpha.3'), 47);
    assert.equal(P.majorVersion('garbage'), 0);
});

test('maximize flags are used up to GNOME Shell 46 only', () => {
    assert.equal(P.usesMaximizeFlags(46), true);
    assert.equal(P.usesMaximizeFlags(47), false);
    assert.equal(P.usesMaximizeFlags(50), false);
});

test('window classification', () => {
    const base = {typeName: 'NORMAL', hasTransientFor: false, skipTaskbar: false, title: 'Terminal'};
    assert.equal(P.classifyWindow(base), 'normal');
    assert.equal(P.classifyWindow({...base, typeName: 'DIALOG'}), 'dialog');
    assert.equal(P.classifyWindow({...base, typeName: 'MODAL_DIALOG'}), 'dialog');
    assert.equal(P.classifyWindow({...base, hasTransientFor: true}), 'dialog');
    assert.equal(P.classifyWindow({...base, typeName: 'OTHER'}), 'other');
    assert.equal(P.classifyWindow({...base, skipTaskbar: true}), 'other');
});

test('the desktop icons window is never a normal window', () => {
    const icons = {typeName: 'NORMAL', hasTransientFor: false, skipTaskbar: false, title: '@!0,0;BDHF'};
    assert.equal(P.classifyWindow(icons), 'other');
});

test('window record has the fields of the protocol', () => {
    const record = P.windowRecord({
        id: 7, title: 'Files', wmClass: 'org.gnome.Nautilus', workspace: 2,
        rect: {x: 1, y: 2, width: 3, height: 4}, kind: 'normal', minimized: false, fullscreen: false,
        sticky: false, maximized: true, resizable: true, stackIndex: 5, openIndex: 1,
    });
    assert.deepEqual(record, {
        id: 7, title: 'Files', wm_class: 'org.gnome.Nautilus', workspace: '2', rect: [1, 2, 3, 4],
        kind: 'normal', minimized: false, fullscreen: false, sticky: false, maximized: true,
        resizable: true, stack_index: 5, open_index: 1,
    });
});

test('state has the protocol version and string workspace keys', () => {
    const state = P.buildState({
        shellVersion: '46.0', monitors: [], workspaceCount: 3, currentWorkspace: 1,
        pointer: {x: 10, y: 20}, windows: [],
    });
    assert.equal(state.protocol, P.PROTOCOL_VERSION);
    assert.deepEqual(state.workspaces, ['0', '1', '2']);
    assert.equal(state.current_workspace, '1');
    assert.deepEqual(state.pointer, [10, 20]);
});

test('operations are parsed and validated one by one', () => {
    const text = JSON.stringify([
        {op: 'unmaximize', id: 1},
        {op: 'place', id: 1, rect: [0, 0, 100, 100], resize: true},
        {op: 'place', id: 1, rect: [0, 0, 100], resize: true},
        {op: 'place', id: 1, rect: [0, 0, 1.5, 100], resize: true},
        {op: 'maximize', id: 1},
        {op: 'raise', id: 'x'},
        {op: 'explode', id: 1},
        'nonsense',
        {op: 'raise', id: 2},
    ]);
    const {operations, errors} = P.parseOperations(text);
    assert.deepEqual(operations.map(o => o.op), ['unmaximize', 'place', 'raise']);
    assert.equal(errors.length, 6);
});

test('broken operation text is reported', () => {
    assert.equal(P.parseOperations('not json').operations.length, 0);
    assert.match(P.parseOperations('not json').errors[0], /not valid JSON/);
    assert.match(P.parseOperations('{}').errors[0], /array/);
});

test('operations run in order and failures do not stop the rest', () => {
    const log = [];
    const access = {
        findWindow: id => (id === 99 ? null : {id}),
        unmaximize: w => log.push(['unmaximize', w.id]),
        maximize: (w, value) => log.push(['maximize', w.id, value]),
        place: (w, rect, resize) => {
            if (w.id === 3)
                throw new Error('boom');
            log.push(['place', w.id, rect, resize]);
        },
        raise: w => log.push(['raise', w.id]),
    };
    const result = P.runOperations([
        {op: 'unmaximize', id: 1},
        {op: 'place', id: 3, rect: [0, 0, 1, 1], resize: false},
        {op: 'place', id: 99, rect: [0, 0, 1, 1], resize: false},
        {op: 'place', id: 1, rect: [5, 6, 7, 8], resize: true},
        {op: 'maximize', id: 1, value: true},
        {op: 'raise', id: 1},
    ], access);
    assert.deepEqual(log, [
        ['unmaximize', 1],
        ['place', 1, [5, 6, 7, 8], true],
        ['maximize', 1, true],
        ['raise', 1],
    ]);
    assert.equal(result.ok, false);
    assert.equal(result.errors.length, 2);
    assert.match(result.errors[0], /place of window 3 failed: boom/);
    assert.match(result.errors[1], /no window with id 99/);
});

test('apply result is JSON with ok and errors', () => {
    assert.deepEqual(JSON.parse(P.applyResult([])), {ok: true, errors: []});
    assert.deepEqual(JSON.parse(P.applyResult(['x'])), {ok: false, errors: ['x']});
});

test('the D-Bus interface declares both methods', () => {
    assert.match(P.INTERFACE_XML, /<method name="GetState">/);
    assert.match(P.INTERFACE_XML, /<method name="Apply">/);
    assert.match(P.INTERFACE_XML, new RegExp(P.INTERFACE_NAME.replaceAll('.', '\\.')));
});

test('the extension agrees with the Python side on the names and the protocol version', () => {
    const python = readFileSync(new URL('../../cascade_windows/shell_protocol.py', import.meta.url), 'utf8');
    const value = name => python.match(new RegExp(`^${name} = "?([^"\\n]+)"?$`, 'm'))[1];
    assert.equal(value('BUS_NAME'), P.BUS_NAME);
    assert.equal(value('OBJECT_PATH'), P.OBJECT_PATH);
    assert.equal(value('INTERFACE'), P.INTERFACE_NAME);
    assert.equal(Number(value('PROTOCOL_VERSION')), P.PROTOCOL_VERSION);
});

test('metadata lists the supported shell versions and a matching schema', () => {
    const metadata = JSON.parse(readFileSync(new URL('../metadata.json', import.meta.url), 'utf8'));
    assert.equal(metadata.uuid, 'cascade-windows@anttiraisala.github.io');
    for (const version of ['46', '50'])
        assert.ok(metadata['shell-version'].includes(version), version);
    const schema = readFileSync(
        new URL(`../schemas/${metadata['settings-schema']}.gschema.xml`, import.meta.url), 'utf8');
    assert.match(schema, new RegExp(`id="${metadata['settings-schema'].replaceAll('.', '\\.')}"`));
});

test('the panel menu has the entries in the requested order', async () => {
    const source = readFileSync(new URL('../lib/panel.js', import.meta.url), 'utf8');
    const labels = [...source.matchAll(/label: '([^']+)'/g)].map(m => m[1]);
    assert.deepEqual(labels, [
        'Cascade Windows', 'Cascade Workspace', 'Cascade All Workspaces', 'Undo Cascade', 'Cascade Settings...',
    ]);
});
