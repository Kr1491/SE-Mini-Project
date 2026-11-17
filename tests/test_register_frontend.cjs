'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/register.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function response(status, data = {}) { return {ok: status >= 200 && status < 300, status, json: async () => data}; }
class Element {
  constructor(id) {
    this.id = id; this.handlers = {}; this.value = ''; this.textContent = '';
    this.disabled = id === 'register-fields'; this.type = id === 'password' ? 'password' : '';
    this.attributes = {}; const values = new Set();
    this.classList = {toggle: (value, on) => on ? values.add(value) : values.delete(value), contains: value => values.has(value)};
  }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  setAttribute(name, value) { this.attributes[name] = value; }
  reportValidity() { return this.valid !== false; }
}
function harness(custom = () => undefined, demo = false) {
  const elements = new Map(); const calls = []; const navigations = [];
  const element = id => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); };
  const fetch = async (url, options = {}) => {
    calls.push({url, options}); const result = custom(url, options); if (result !== undefined) return result;
    if (url === '/api/health') return response(200, {demo});
    if (url === '/api/session') return response(401, {error: 'Sign in'});
    if (url === '/api/register') return response(201, {user: {role: 'student'}});
    throw new Error(`Unexpected route ${url}`);
  };
  vm.runInNewContext(source, {document: {getElementById: element}, fetch, location: {replace: url => navigations.push(url)}}, {filename: 'register.js'});
  return {element, calls, navigations,
    submit: () => element('register-form').handlers.submit({preventDefault() {}}),
    fill: (name = ' New Student ', email = ' new@example.test ', password = 'correct horse battery') => {
      element('name').value = name; element('email').value = email; element('password').value = password; }};
}

test('form becomes usable once the server is reachable', async () => {
  const page = harness(); await flush();
  assert.equal(page.element('register-fields').disabled, false);
  assert.equal(page.element('register-status').textContent, '');
});

test('one submit sends trimmed details, clears the password and opens the dashboard', async () => {
  const page = harness(); await flush(); page.fill();
  await page.submit(); await flush();
  const call = page.calls.find(c => c.url === '/api/register');
  assert.equal(call.options.method, 'POST');
  assert.deepEqual(JSON.parse(call.options.body), {name: 'New Student', email: 'new@example.test', password: 'correct horse battery'});
  assert.equal(call.options.headers['Content-Type'], 'application/json');
  assert.equal(page.element('password').value, '');
  assert.deepEqual(page.navigations, ['/dashboard']);
});

test('server validation errors are shown and the form can be corrected', async () => {
  const page = harness(url => url === '/api/register' ? response(409, {error: 'An account with this email already exists.'}) : undefined);
  await flush(); page.fill(); await page.submit(); await flush();
  assert.equal(page.element('register-status').textContent, 'An account with this email already exists.');
  assert.equal(page.element('register-status').classList.contains('error'), true);
  assert.equal(page.element('register-fields').disabled, false);
  assert.deepEqual(page.navigations, []);
});

test('invalid browser input is not submitted', async () => {
  const page = harness(); await flush(); page.element('register-form').valid = false;
  await page.submit(); await flush();
  assert.equal(page.calls.some(c => c.url === '/api/register'), false);
});

test('duplicate submits while pending send one request', async () => {
  let release; const pending = new Promise(r => { release = r; });
  const page = harness(url => url === '/api/register' ? pending : undefined);
  await flush(); page.fill(); page.submit(); page.submit(); await flush();
  assert.equal(page.calls.filter(c => c.url === '/api/register').length, 1);
  assert.equal(page.element('create-account').textContent, 'Creating your account…');
  release(response(201, {})); await flush();
});

test('demo mode keeps registration disabled with an explanation', async () => {
  const page = harness(undefined, true); await flush();
  assert.equal(page.element('register-fields').disabled, true);
  assert.match(page.element('register-status').textContent, /turned off in the local demo/);
});

test('a signed-in visitor goes straight to the dashboard', async () => {
  const page = harness(url => url === '/api/session' ? response(200, {user: {}}) : undefined); await flush();
  assert.deepEqual(page.navigations, ['/dashboard']);
});

test('password visibility toggle updates its accessible state', async () => {
  const page = harness(); await flush();
  page.element('toggle-password').handlers.click();
  assert.equal(page.element('password').type, 'text');
  assert.equal(page.element('toggle-password').attributes['aria-pressed'], 'true');
});
