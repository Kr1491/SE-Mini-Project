'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; }
function response(status, data) { return {ok: status >= 200 && status < 300, status, json: async () => data}; }
function account(role = 'administrator') { return {user: {id: 3, name: `Sample ${role}`, role}, permissions: ['dashboard'], csrf_token: 'sample-csrf'}; }
class Element {
  constructor(id = '', dataset = {}) {
    this.id = id; this.dataset = dataset; this.hidden = ['account-panel', 'access-panel', 'demo-notice'].includes(id);
    this.disabled = false; this.textContent = ''; this.children = []; this.handlers = {};
    const values = new Set();
    this.classList = {add: v => values.add(v), remove: v => values.delete(v), contains: v => values.has(v),
      toggle: (v, enabled) => enabled ? values.add(v) : values.delete(v)};
  }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  append(value) { this.children.push(value); }
  replaceChildren() { this.children = []; }
  querySelectorAll() { return this.buttons || []; }
  closest(selector) { return selector === '[data-user]' && this.dataset.user || selector === '[data-check]' && this.dataset.check ? this : null; }
}
function harness(fetch) {
  const elements = new Map();
  const element = id => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); };
  const buttons = [1, 2, 3, 4].map(id => new Element('', {user: String(id)}));
  element('accounts').buttons = buttons;
  const document = {getElementById: element, createElement: () => new Element()};
  const initialized = vm.runInNewContext(source, {document, fetch}, {filename: 'app.js'});
  return {element, buttons, initialized,
    select: id => element('accounts').handlers.click({target: buttons.find(b => b.dataset.user === String(id))}),
    probe: name => element('access-panel').handlers.click({target: new Element('', {check: name})})};
}

test('selector stays unavailable until initial session detection finishes', async () => {
  const initialSession = deferred(); let sessions = 0; let selections = 0;
  const ui = harness(async url => {
    if (url === '/api/health') return response(200, {demo: true});
    if (url === '/api/demo/session') { selections++; return response(200, {}); }
    if (url === '/api/session') return ++sessions === 1 ? initialSession.promise : response(200, account('instructor'));
    throw new Error(`Unexpected route ${url}`);
  });
  await flush();
  assert.equal(ui.element('account-panel').hidden, true);
  await ui.select(1);
  assert.equal(selections, 0);
  initialSession.resolve(response(401, {error: 'Sign in'}));
  await ui.initialized;
  assert.equal(ui.element('account-panel').hidden, false);
  await ui.select(1);
  assert.equal(ui.element('access-panel').hidden, false);
  assert.equal(ui.element('account-name').textContent, 'Sample instructor');
});

test('a slow earlier success cannot overwrite the latest denied probe', async () => {
  const earlier = deferred(); const latest = deferred();
  const ui = harness(async url => {
    if (url === '/api/health') return response(200, {demo: true});
    if (url === '/api/session') return response(200, account());
    if (url === '/api/access/instructor') return earlier.promise;
    if (url === '/api/access/admin') return latest.promise;
    throw new Error(`Unexpected route ${url}`);
  });
  await ui.initialized;
  const first = ui.probe('instructor'); const second = ui.probe('admin');
  latest.resolve(response(403, {error: 'Access denied'})); await second;
  const expected = ui.element('check-result').textContent;
  assert.match(expected, /403.*Access denied/);
  earlier.resolve(response(200, {message: 'Earlier allowed result'})); await first;
  assert.equal(ui.element('check-result').textContent, expected);
  assert.equal(ui.element('check-result').classList.contains('allowed'), false);
});

test('a slow earlier denial cannot overwrite the latest successful probe', async () => {
  const earlier = deferred(); const latest = deferred();
  const ui = harness(async url => {
    if (url === '/api/health') return response(200, {demo: true});
    if (url === '/api/session') return response(200, account());
    if (url === '/api/access/instructor') return earlier.promise;
    if (url === '/api/access/admin') return latest.promise;
    throw new Error(`Unexpected route ${url}`);
  });
  await ui.initialized;
  const first = ui.probe('instructor'); const second = ui.probe('admin');
  latest.resolve(response(200, {message: 'Latest allowed result'})); await second;
  earlier.resolve(response(403, {error: 'Earlier denied result'})); await first;
  assert.equal(ui.element('check-result').textContent, 'Allowed: Latest allowed result');
  assert.equal(ui.element('check-result').classList.contains('allowed'), true);
});

test('pending probe from the previous account cannot overwrite a new account', async () => {
  const oldProbe = deferred(); let sessions = 0;
  const ui = harness(async url => {
    if (url === '/api/health') return response(200, {demo: true});
    if (url === '/api/session') return response(200, account(++sessions === 1 ? 'administrator' : 'student'));
    if (url === '/api/demo/session') return response(200, {});
    if (url === '/api/access/admin') return oldProbe.promise;
    throw new Error(`Unexpected route ${url}`);
  });
  await ui.initialized;
  const old = ui.probe('admin'); await ui.select(2);
  oldProbe.resolve(response(200, {message: 'Old administrator access'})); await old;
  assert.equal(ui.element('account-name').textContent, 'Sample student');
  assert.equal(ui.element('check-result').textContent, '');
});

function luminance(hex) {
  if (hex.length === 4) hex = '#' + [...hex.slice(1)].map(c => c + c).join('');
  const rgb = hex.match(/[\da-f]{2}/gi).map(x => parseInt(x, 16) / 255)
    .map(x => x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
  return rgb.reduce((sum, x, i) => sum + x * [0.2126, 0.7152, 0.0722][i], 0);
}
function contrast(a, b) {
  const values = [luminance(a), luminance(b)].sort((x, y) => x - y);
  return (values[1] + 0.05) / (values[0] + 0.05);
}
test('secondary text meets 4.5:1 contrast against its actual background', () => {
  const css = fs.readFileSync(path.join(__dirname, '../static/style.css'), 'utf8');
  const rule = selector => css.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\{([^}]+)\\}`))[1];
  const color = selector => rule(selector).match(/(?:^|;)color:(#[\da-f]+)/i)[1];
  const background = selector => rule(selector).match(/(?:^|;)background:(#[\da-f]+)/i)[1];
  for (const [selector, bg] of [['.intro', background('body')], ['.muted', background('.panel')], ['footer', background('body')]]) {
    const value = contrast(color(selector), bg);
    assert.ok(value >= 4.5, `${selector}: ${value.toFixed(2)}:1`);
  }
});
