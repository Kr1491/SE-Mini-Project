'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/materials.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; }
function response(status, data = {}, headers = {}) {
  const normalized = Object.fromEntries(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), String(value)]));
  return {ok: status >= 200 && status < 300, status, json: async () => data, text: async () => data,
    headers: {get: key => normalized[key.toLowerCase()] ?? null}, body: {cancel: async () => {}}};
}
function account(role = 'student') { return {user: {id: 2, name: `Sample ${role}`, role}}; }
function material(id = 1, kind = 'text') { return {id, title: `Resource ${id}`, original_name: kind === 'text' ? 'policy.py' : `guide.${kind}`, preview_kind: kind, size_bytes: 120, group_name: 'Software Engineering', group_id: 1}; }
function catalog(items = [material()], extra = {}) { return {materials: items, groups: [{id: 1, name: 'Software Engineering'}, {id: 2, name: 'Database Systems'}], limit: 24, offset: 0, total: items.length, ...extra}; }
class Element {
  constructor(tag = '', id = '', dataset = {}, clicks = []) {
    this.tag = tag; this.id = id; this.dataset = dataset; this.clicks = clicks; this.children = []; this.handlers = {};
    this.textContent = ''; this.value = ''; this.disabled = false; this.open = false;
    this.hidden = ['sample-panel', 'demo-banner', 'library', 'role-badge', 'preview-text', 'preview-image', 'preview-frame'].includes(id);
    const classes = new Set();
    this.classList = {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x), toggle: (x, on) => on ? classes.add(x) : classes.delete(x)};
  }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  append(...nodes) { this.children.push(...nodes); nodes.forEach(node => { node.parent = this; }); }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(node => node !== this); }
  removeAttribute(name) { delete this[name]; }
  querySelectorAll() { return this.buttons || []; }
  closest(selector) { const key = selector.match(/^\[data-(\w+)\]$/)?.[1]; return key && this.dataset[key] !== undefined ? this : null; }
  showModal() { this.open = true; }
  close() { this.open = false; this.handlers.close?.(); }
  click() { this.clicks.push({href: this.href, download: this.download}); }
}
function harness(routes = () => undefined, {demo = true} = {}) {
  const elements = new Map(); const clicks = []; const calls = [];
  const element = id => { if (!elements.has(id)) elements.set(id, new Element('', id, {}, clicks)); return elements.get(id); };
  const buttons = [1, 2, 3, 4].map(id => new Element('button', '', {account: String(id)}, clicks));
  element('sample-accounts').buttons = buttons;
  const document = {getElementById: element, createElement: tag => new Element(tag, '', {}, clicks), body: new Element('body')};
  const fetch = async (url, options = {}) => {
    calls.push({url, options});
    const custom = routes(url, options); if (custom !== undefined) return custom;
    if (url === '/api/health') return response(200, {demo});
    if (url === '/api/session') return response(200, account());
    if (url === '/api/demo/session') return response(200);
    if (url.startsWith('/api/materials?')) return response(200, catalog());
    throw new Error(`Unexpected route ${url}`);
  };
  vm.runInNewContext(source, {document, fetch, URLSearchParams, AbortController}, {filename: 'materials.js'});
  return {element, clicks, calls, buttons, ready: flush,
    select: id => element('sample-accounts').handlers.click({target: buttons.find(b => b.dataset.account === String(id))}),
    action: (kind, id = 1) => element('material-list').handlers.click({target: new Element('button', '', {[kind]: String(id)})}),
    click: id => element(id).handlers.click(),
    group: value => { element('material-group').value = value; return element('material-group').handlers.change(); }};
}

test('initial session must settle before the demo selector becomes interactive', async () => {
  const initial = deferred(); let sessions = 0;
  const ui = harness(url => url === '/api/session' && ++sessions === 1 ? initial.promise : undefined);
  await ui.ready(); assert.equal(ui.element('sample-panel').hidden, true);
  await ui.select(1); assert.equal(ui.calls.some(call => call.url === '/api/demo/session'), false);
  initial.resolve(response(401, {error: 'Sign in'})); await flush();
  assert.equal(ui.element('sample-panel').hidden, false);
  await ui.select(1); assert.equal(ui.element('library').hidden, false);
});

test('normal mode hides sample selection and reports authentication requirement', async () => {
  const ui = harness(url => url === '/api/session' ? response(401, {error: 'Sign in'}) : undefined, {demo: false});
  await ui.ready(); await ui.select(1);
  assert.equal(ui.element('sample-panel').hidden, true);
  assert.match(ui.element('library-status').textContent, /Sign in/);
  assert.equal(ui.calls.some(call => call.url === '/api/demo/session'), false);
});

test('catalog renders filenames and titles as literal text with download-only fallback', async () => {
  const item = {...material(), title: '<img src=x onerror=alert(1)>', original_name: '<script>.py'};
  const ui = harness(url => url.startsWith('/api/materials?') ? response(200, catalog([item, material(2, null)])) : undefined);
  await ui.ready();
  const cards = ui.element('material-list').children;
  assert.equal(cards[0].children[1].children[0].textContent, item.title);
  assert.equal(cards[1].children[2].children[0].textContent, 'Download only');
  assert.equal(ui.element('material-count').textContent, '2 materials');
});

test('a slow previous group response cannot replace the latest selected group', async () => {
  const old = deferred();
  const ui = harness(url => url.includes('group_id=1') ? old.promise : url.includes('group_id=2') ? response(200, catalog([material(22)])) : undefined);
  await ui.ready(); const first = ui.group('1'); await ui.group('2');
  old.resolve(response(200, catalog([material(11)]))); await first;
  assert.equal(ui.element('material-list').children[0].children[1].children[0].textContent, 'Resource 22');
  assert.equal(ui.element('material-group').value, '2');
});

test('paging uses the server offset and resets after changing group', async () => {
  const ui = harness(url => url.startsWith('/api/materials?') ? response(200, catalog([material()], {limit: 1, total: 3, offset: Number(new URLSearchParams(url.split('?')[1]).get('offset'))})) : undefined);
  await ui.ready(); await ui.click('next-page');
  assert.match(ui.calls.at(-1).url, /offset=1/);
  assert.equal(ui.element('previous-page').disabled, false);
  await ui.group('2'); assert.match(ui.calls.at(-1).url, /offset=0.*group_id=2/);
});

test('pending catalog from a previous account cannot repopulate private cards', async () => {
  const old = deferred(); let lists = 0;
  const ui = harness(url => url.startsWith('/api/materials?') ? (++lists === 2 ? old.promise : response(200, catalog(lists === 3 ? [] : [material()]))) : undefined);
  await ui.ready(); const refresh = ui.click('refresh-library'); await ui.select(4);
  old.resolve(response(200, catalog([material(999)]))); await refresh;
  assert.equal(ui.element('material-count').textContent, '0 materials');
  assert.equal(ui.element('material-list').children[0].tag, 'p');
});

test('text preview stays literal and closes without retaining private content', async () => {
  const ui = harness(url => url.endsWith('/view') ? response(200, '<script>alert(1)</script>', {'Content-Type': 'text/plain; charset=utf-8', 'Content-Length': 25}) : undefined);
  await ui.ready(); await ui.action('view');
  assert.equal(ui.element('preview-text').textContent, '<script>alert(1)</script>');
  assert.equal(ui.element('preview-frame').hidden, true);
  ui.click('close-preview'); assert.equal(ui.element('preview-text').textContent, '');
  assert.equal(ui.element('preview-dialog').open, false);
});

test('oversized text is download-only without consuming response body', async () => {
  let read = false;
  const large = response(200, 'big', {'Content-Type': 'text/plain', 'Content-Length': 3 * 1024 * 1024});
  large.text = async () => { read = true; return 'big'; };
  const ui = harness(url => url.endsWith('/view') ? large : undefined);
  await ui.ready(); await ui.action('view');
  assert.equal(read, false); assert.match(ui.element('preview-status').textContent, /too large/);
});

test('PDF and raster previews use authenticated endpoints; unsafe attachments never embed', async () => {
  let mode = 'application/pdf';
  const ui = harness(url => url.endsWith('/view') ? response(200, '', {'Content-Type': mode, 'Content-Disposition': mode === 'text/html' ? 'attachment' : 'inline'}) : undefined);
  await ui.ready(); await ui.action('view');
  assert.equal(ui.element('preview-frame').src, '/api/materials/1/view');
  mode = 'image/png'; await ui.action('view');
  assert.equal(ui.element('preview-frame').src, undefined);
  assert.equal(ui.element('preview-image').src, '/api/materials/1/view');
  mode = 'text/html'; await ui.action('view');
  assert.equal(ui.element('preview-image').src, undefined);
  assert.equal(ui.element('preview-frame').hidden, true);
  assert.match(ui.element('preview-status').textContent, /download/);
});

test('slow preview cannot overwrite a newer preview or reopen a closed dialog', async () => {
  const first = deferred(); let views = 0;
  const ui = harness(url => url.endsWith('/view') ? (++views === 1 ? first.promise : response(200, 'latest', {'Content-Type': 'text/plain', 'Content-Length': 6})) : undefined);
  await ui.ready(); const pending = ui.action('view'); await ui.action('view');
  first.resolve(response(200, 'stale', {'Content-Type': 'text/plain', 'Content-Length': 5})); await pending;
  assert.equal(ui.element('preview-text').textContent, 'latest');
  const late = deferred(); const other = harness(url => url.endsWith('/view') ? late.promise : undefined);
  await other.ready(); const closed = other.action('view'); other.click('close-preview');
  late.resolve(response(200, 'private', {'Content-Type': 'text/plain', 'Content-Length': 7})); await closed;
  assert.equal(other.element('preview-text').textContent, ''); assert.equal(other.element('preview-dialog').open, false);
});

test('account switch clears open preview and ignores its delayed text body', async () => {
  const text = deferred(); const file = response(200, '', {'Content-Type': 'text/plain', 'Content-Length': 7}); file.text = () => text.promise;
  const ui = harness(url => url.endsWith('/view') ? file : undefined);
  await ui.ready(); const pending = ui.action('view'); await flush(); await ui.select(4);
  text.resolve('private'); await pending;
  assert.equal(ui.element('preview-dialog').open, false);
  assert.equal(ui.element('preview-text').textContent, '');
});

test('native download starts only after a successful HEAD without reading file bytes in JS', async () => {
  const ui = harness((url, options) => url.endsWith('/download') ? (assert.equal(options.method, 'HEAD'), response(200)) : undefined);
  await ui.ready(); await ui.action('download');
  assert.deepEqual(ui.clicks, [{href: '/api/materials/1/download', download: ''}]);
  assert.match(ui.element('library-status').textContent, /requested/);
});

test('denied or missing file produces useful feedback and does not start download', async () => {
  for (const [status, message] of [[401, /expired/], [403, /access/], [404, /unavailable/]]) {
    const ui = harness(url => url.endsWith('/download') || url.endsWith('/view') ? response(status) : undefined);
    await ui.ready(); await ui.action('download');
    assert.equal(ui.clicks.length, 0); assert.match(ui.element('library-status').textContent, message);
    await ui.action('view'); assert.match(ui.element('preview-status').textContent, message);
  }
});

test('pending download from an old account never launches under the new account', async () => {
  const head = deferred(); const ui = harness(url => url.endsWith('/download') ? head.promise : undefined);
  await ui.ready(); const pending = ui.action('download'); await ui.select(4);
  head.resolve(response(200)); await pending;
  assert.equal(ui.clicks.length, 0);
});

test('an expired catalog session clears profile, cards, groups, and preview', async () => {
  let lists = 0;
  const ui = harness(url => url.startsWith('/api/materials?') && ++lists > 1 ? response(401, {error: 'Session expired'}) : undefined);
  await ui.ready(); await ui.click('refresh-library');
  assert.equal(ui.element('library').hidden, true);
  assert.equal(ui.element('profile-name').textContent, '');
  assert.equal(ui.element('material-group').children.length, 0);
  assert.equal(ui.element('material-list').children.length, 0);
});
