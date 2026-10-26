'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/folders.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; }
function response(status, data) { return {ok: status >= 200 && status < 300, json: async () => data}; }
const session = {user: {id: 1, role: 'instructor'}, csrf_token: 'current-session-csrf'};
const groups = [{id: 1, name: 'First group'}, {id: 2, name: 'Second group'}];
class Element {
  constructor() {
    this.value = ''; this.textContent = ''; this.children = []; this.hidden = false;
    this.disabled = false; this.handlers = {}; this.className = '';
    const values = new Set(); this.classList = {add: v => values.add(v), remove: v => values.delete(v), toggle: (v, active) => active ? values.add(v) : values.delete(v), contains: v => values.has(v)};
  }
  addEventListener(name, callback) { this.handlers[name] = callback; }
  append(...children) { this.children.push(...children); }
  replaceChildren() { this.children = []; }
}
function harness(fetch) {
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const context = {document: {getElementById: get, createElement: () => new Element()}, fetch};
  vm.runInNewContext(source, context, {filename: 'folders.js'});
  return {get, context, ui: context.StudyFolders,
    change: value => { get('folder-group').value = String(value); return get('folder-group').handlers.change(); },
    submit: value => { get('folder-name').value = value; return get('create-folder-form').handlers.submit({preventDefault() {}}); }};
}
const names = ui => ui.get('folder-list').children.filter(c => c.className === 'folder-card').map(c => c.children[1].textContent);

test('owner creates and sees a folder using current CSRF; names remain literal text', async () => {
  const rows = []; const writes = [];
  const ui = harness(async (url, options = {}) => {
    if (url === '/api/groups') return response(200, {groups});
    if (options.method === 'POST') {
      writes.push(options); const folder = {id: 1, name: JSON.parse(options.body).name}; rows.push(folder);
      return response(201, {folder});
    }
    return response(200, {folders: [...rows], can_create: true});
  });
  await ui.ui.load(session);
  assert.equal(ui.get('create-folder-form').hidden, false);
  assert.equal(ui.get('folder-group').value, '1');
  const name = '<img src=x onerror=alert(1)>';
  await ui.submit(name);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].headers['X-CSRF-Token'], session.csrf_token);
  assert.deepEqual(names(ui), [name]);
  assert.equal(ui.get('folder-count').textContent, '1 folder');
  assert.equal(ui.get('folder-message').classList.contains('success'), true);
  assert.equal(ui.get('folder-group').disabled, false);
});

test('read-only group hides creation and ignores form submission', async () => {
  let writes = 0;
  const ui = harness(async (url, options = {}) => {
    if (options.method === 'POST') writes++;
    return response(200, url === '/api/groups' ? {groups} : {folders: [{name: 'Shared notes'}], can_create: false});
  });
  await ui.ui.load({...session, user: {id: 2, role: 'student'}});
  assert.equal(ui.get('create-folder-form').hidden, true);
  assert.deepEqual(names(ui), ['Shared notes']);
  await ui.submit('Not authorized'); assert.equal(writes, 0);
});

test('account without groups has a clear empty state and no creation controls', async () => {
  const calls = [];
  const ui = harness(async url => { calls.push(url); return response(200, {groups: []}); });
  await ui.ui.load(session);
  assert.deepEqual(calls, ['/api/groups']);
  assert.equal(ui.get('folder-group').disabled, true);
  assert.equal(ui.get('create-folder-form').hidden, true);
  assert.match(ui.get('folder-status').textContent, /No study groups/);
});

test('older group response cannot replace the newly selected group', async () => {
  const older = deferred();
  const ui = harness(async url => {
    if (url === '/api/groups') return response(200, {groups});
    if (url === '/api/groups/2/folders') return older.promise;
    return response(200, {folders: [{name: 'First group folder'}], can_create: true});
  });
  await ui.ui.load(session);
  const old = ui.change(2); await ui.change(1);
  older.resolve(response(200, {folders: [{name: 'Stale second group folder'}], can_create: false}));
  await old;
  assert.deepEqual(names(ui), ['First group folder']);
  assert.equal(ui.get('create-folder-form').hidden, false);
});

test('reset prevents pending group load from restoring an old account workspace', async () => {
  const pending = deferred();
  const ui = harness(async url => url === '/api/groups' ? response(200, {groups}) : pending.promise);
  const load = ui.ui.load(session); await flush(); ui.ui.reset();
  pending.resolve(response(200, {folders: [{name: 'Old account folder'}], can_create: true})); await load;
  assert.equal(ui.get('folders-panel').hidden, true);
  assert.deepEqual(names(ui), []);
  assert.equal(ui.get('create-folder-form').hidden, true);
});

test('duplicate error keeps the input and restores form controls', async () => {
  const ui = harness(async (url, options = {}) => {
    if (options.method === 'POST') return response(409, {error: 'A folder with this name already exists.'});
    return response(200, url === '/api/groups' ? {groups} : {folders: [], can_create: true});
  });
  await ui.ui.load(session); await ui.submit('Existing notes');
  assert.equal(ui.get('folder-name').value, 'Existing notes');
  assert.match(ui.get('folder-message').textContent, /already exists/);
  assert.equal(ui.get('create-folder-button').disabled, false);
  assert.equal(ui.get('folder-group').disabled, false);
});

test('an old account save cannot modify a new account empty state', async () => {
  const pending = deferred(); let groupLoads = 0;
  const ui = harness(async (url, options = {}) => {
    if (url === '/api/groups') return response(200, {groups: ++groupLoads === 1 ? groups : []});
    if (options.method === 'POST') return pending.promise;
    return response(200, {folders: [], can_create: true});
  });
  await ui.ui.load(session); const old = ui.submit('Old account notes'); await flush();
  ui.ui.reset(); await ui.ui.load({...session, user: {id: 4, role: 'student'}});
  pending.resolve(response(201, {folder: {id: 1, name: 'Old account notes'}})); await old;
  assert.equal(ui.get('folder-group').disabled, true);
  assert.equal(ui.get('folder-message').textContent, '');
  assert.deepEqual(names(ui), []);
});

test('repeated submit while saving sends exactly one create request', async () => {
  const pending = deferred(); let writes = 0;
  const ui = harness(async (url, options = {}) => {
    if (options.method === 'POST') { writes++; return pending.promise; }
    return response(200, url === '/api/groups' ? {groups} : {folders: [], can_create: true});
  });
  await ui.ui.load(session); const save = ui.submit('Notes'); await ui.submit('Notes');
  assert.equal(writes, 1);
  pending.resolve(response(409, {error: 'Already exists'})); await save;
});

test('successful save with failed refresh explains both outcomes', async () => {
  let saved = false;
  const ui = harness(async (url, options = {}) => {
    if (url === '/api/groups') return response(200, {groups});
    if (options.method === 'POST') { saved = true; return response(201, {folder: {id: 1, name: 'Saved notes'}}); }
    return saved ? response(403, {error: 'Group access changed'}) : response(200, {folders: [], can_create: true});
  });
  await ui.ui.load(session); await ui.submit('Saved notes');
  assert.match(ui.get('folder-message').textContent, /was created, but.*could not be refreshed/);
  assert.equal(ui.get('create-folder-form').hidden, true);
});


test('access application loads the folder module after successful session detection', async () => {
  const calls = [];
  const ui = harness(async url => {
    calls.push(url);
    if (url === '/api/health') return response(200, {demo: true});
    if (url === '/api/session') return response(200, {...session, user: {id: 1, role: 'instructor', name: 'Instructor'}, permissions: ['folders.create']});
    if (url === '/api/groups') return response(200, {groups});
    return response(200, {folders: [{id: 1, name: 'Integrated notes'}], can_create: true});
  });
  const app = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
  await vm.runInNewContext(app, ui.context, {filename: 'app.js'});
  assert.equal(ui.get('access-panel').hidden, false);
  assert.equal(ui.get('folders-panel').hidden, false);
  assert.deepEqual(names(ui), ['Integrated notes']);
  assert.ok(calls.includes('/api/groups/1/folders'));
});
