'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/dashboard.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; }
function response(status, data) { return {ok: status >= 200 && status < 300, status, json: async () => data}; }
const roles = {1: 'instructor', 2: 'student', 3: 'administrator', 4: 'student'};
function payload(uid) {
  const role = roles[uid];
  const label = role === 'student' ? 'Learning tools' : role === 'instructor' ? 'Teaching tools' : 'Administration';
  return {role, user: {id: uid, role, name: `Account ${uid}`, email: `account${uid}@example.test`}, title: `${role} dashboard`, description: `${role} workspace`,
    group_heading: role === 'administrator' ? 'All groups' : 'Your groups', tools_heading: label,
    navigation: [{label: 'Overview', href: '#overview'}, {label, href: '#tools'}],
    groups: uid === 4 ? [] : [{id: 1, name: `${role} group`, relationship: 'Member', can_manage: role !== 'student'}],
    stats: [{label: 'Visible groups', value: uid === 4 ? 0 : 1}],
    actions: [{label: 'Groups', description: 'Visible groups', available: true, href: '#study-groups'},
      {label: 'Future tool', description: 'Not available yet', available: false, href: null}],
    updated_at: '2026-10-25T12:00:00+00:00'};
}
class Element {
  constructor(tag = 'div', id = '') {
    this.tagName = tag; this.id = id; this.children = []; this.handlers = {}; this.dataset = {};
    this.textContent = ''; this.disabled = false;
    this.hidden = ['profile', 'sample-panel', 'signed-out', 'dashboard-content', 'demo-banner'].includes(id);
    const values = new Set();
    this.classList = {add: v => values.add(v), remove: v => values.delete(v), contains: v => values.has(v), toggle: (v, enabled) => enabled ? values.add(v) : values.delete(v)};
  }
  append(...items) { this.children.push(...items); for (const item of items) item.parent = this; }
  replaceChildren(...items) { this.children = []; this.append(...items); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(item => item !== this); }
  reset() { for (const item of descendants(this)) { item.value = ''; item.checked = false; } }
  addEventListener(event, fn) { this.handlers[event] = fn; }
  querySelectorAll(selector) {
    if (this.buttons) return this.buttons;
    return descendants(this).filter(item => selector.startsWith('.')
      ? (item.className || '').split(' ').includes(selector.slice(1))
      : selector === 'input[type="radio"]' && item.tagName === 'input' && item.type === 'radio');
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return selector === '[data-account]' && this.dataset.account ? this : null; }
}
function harness(fetch, pathname = '/dashboard') {
  const elements = new Map(); const created = [];
  const get = id => { if (!elements.has(id)) elements.set(id, new Element('div', id)); return elements.get(id); };
  const buttons = [1, 2, 3, 4].map(uid => { const b = new Element('button'); b.dataset.account = String(uid); return b; });
  get('sample-accounts').buttons = buttons;
  get('create-quiz-form').append(get('quiz-group'), get('quiz-title'), get('quiz-questions'));
  const navigations = [];
  const document = {body: {dataset: {}}, title: '', getElementById: get, createElement: tag => { const n = new Element(tag); created.push(n); return n; }};
  vm.runInNewContext(source, {document, fetch, location: {pathname, replace: url => navigations.push(url)}}, {filename: 'dashboard.js'});
  return {get, document, created, navigations, logout: () => get('logout').handlers.click(), select: uid => get('sample-accounts').handlers.click({target: buttons.find(b => Number(b.dataset.account) === uid)}),
    refresh: () => get('refresh-dashboard').handlers.click(),
    submitQuiz: () => get('create-quiz-form').handlers.submit({preventDefault() {}, currentTarget: get('create-quiz-form')})};
}
function mockWorkspace(initial = 2, demo = true, customize = data => data) {
  let selected = initial;
  return async (url, options = {}) => {
    if (url === '/api/health') return response(200, {demo});
    if (url === '/api/demo/session') { selected = JSON.parse(options.body).user_id; return response(200, {}); }
    if (url === '/api/session') return response(200, {user: payload(selected).user, csrf_token: 'csrf'});
    return response(200, customize(payload(selected)));
  };
}
function descendants(node) { return node.children.flatMap(child => [child, ...descendants(child)]); }

test('initial session detection settles before exposing sample account controls', async () => {
  const pending = deferred(); let chosen = 0;
  const ui = harness(async url => {
    if (url === '/api/health') return response(200, {demo: true});
    if (url === '/api/session') return pending.promise;
    if (url === '/api/demo/session') chosen++;
    throw new Error('Unexpected route');
  });
  await flush();
  assert.equal(ui.get('sample-panel').hidden, true);
  await ui.select(1); assert.equal(chosen, 0);
  pending.resolve(response(401, {error: 'Please sign in'})); await flush();
  assert.equal(ui.get('sample-panel').hidden, false);
  assert.equal(ui.get('dashboard-content').hidden, true);
  assert.equal(ui.get('signed-out').hidden, false);
});

test('switching roles replaces the title, navigation, tools and profile', async () => {
  const ui = harness(mockWorkspace()); await flush();
  for (const uid of [2, 1, 3]) {
    await ui.select(uid);
    const data = payload(uid);
    assert.equal(ui.document.body.dataset.role, roles[uid]);
    assert.equal(ui.get('dashboard-title').textContent, data.title);
    assert.equal(ui.get('profile-name').textContent, data.user.name);
    assert.equal(ui.get('tools-heading').textContent, data.tools_heading);
    assert.equal(ui.get('dashboard-nav').children.length, data.navigation.length);
    assert.equal(ui.get('dashboard-content').hidden, false);
    const labels = descendants(ui.get('dashboard-nav')).map(n => n.textContent);
    assert.ok(labels.includes(data.tools_heading));
  }
});

test('nonmember dashboard shows the empty state instead of another accounts groups', async () => {
  const ui = harness(mockWorkspace(3)); await flush(); await ui.select(4);
  assert.equal(ui.get('groups-count').textContent, '0 groups');
  assert.equal(ui.get('study-groups').children.length, 1);
  assert.equal(ui.get('study-groups').children[0].className, 'empty-state');
  assert.match(ui.get('study-groups').children[0].textContent, /No study groups/);
});

test('unavailable tools have no action link and unsafe destinations are ignored', async () => {
  const ui = harness(mockWorkspace(2, true, data => {
    data.actions.push({label: 'Unsafe tool', description: 'Must not link', available: true, href: 'javascript:alert(1)'});
    data.navigation.push({label: 'Unsafe nav', href: '//example.test/redirect'});
    return data;
  }));
  await flush();
  const tools = descendants(ui.get('tools'));
  assert.equal(tools.filter(n => n.tagName === 'a').length, 1);
  assert.equal(tools.filter(n => n.className === 'coming-soon').length, 2);
  assert.equal(ui.created.some(n => n.href && /javascript:|example\.test/.test(n.href)), false);
});

test('user and group names are displayed as literal text', async () => {
  const text = '<img src=x onerror=alert(1)>';
  const ui = harness(mockWorkspace(2, true, data => { data.user.name = text; data.groups[0].name = text; return data; }));
  await flush();
  assert.equal(ui.get('profile-name').textContent, text);
  assert.ok(descendants(ui.get('study-groups')).some(n => n.textContent === text));
  assert.equal(ui.created.some(n => ['img', 'script'].includes(n.tagName)), false);
});

test('slow refresh from the old account cannot overwrite the newly selected workspace', async () => {
  let selected = 3; let dashboardCalls = 0; const old = deferred();
  const ui = harness(async (url, options = {}) => {
    if (url === '/api/health') return response(200, {demo: true});
    if (url === '/api/demo/session') { selected = JSON.parse(options.body).user_id; return response(200, {}); }
    if (url === '/api/session') return response(200, {user: payload(selected).user, csrf_token: 'csrf'});
    if (++dashboardCalls === 2) return old.promise;
    return response(200, payload(selected));
  });
  await flush();
  const refreshing = ui.refresh(); await flush();
  await ui.select(2);
  old.resolve(response(200, payload(3))); await refreshing;
  assert.equal(ui.document.body.dataset.role, 'student');
  assert.equal(ui.get('profile-name').textContent, 'Account 2');
  assert.equal(ui.get('dashboard-title').textContent, 'student dashboard');
});

test('failed refresh clears previously rendered private account data', async () => {
  let expired = false;
  const base = mockWorkspace(3);
  const ui = harness(async (url, options) => expired && url === '/api/session' ? response(401, {error: 'Session expired'}) : base(url, options));
  await flush(); expired = true; await ui.refresh();
  assert.equal(ui.get('dashboard-content').hidden, true);
  assert.equal(ui.get('profile').hidden, true);
  assert.equal(ui.get('profile-name').textContent, '');
  assert.equal(ui.get('study-groups').children.length, 0);
  assert.equal(ui.document.body.dataset.role, undefined);
  assert.equal(ui.document.title, 'StudySpace · Your workspace');
});

test('normal mode renders a verified account without exposing the demo selector', async () => {
  let selections = 0;
  const base = mockWorkspace(1, false);
  const ui = harness(async (url, options) => { if (url === '/api/demo/session') selections++; return base(url, options); });
  await flush();
  assert.equal(ui.get('sample-panel').hidden, true);
  assert.equal(ui.get('dashboard-content').hidden, false);
  await ui.select(3); assert.equal(selections, 0);
});

test('direct role page uses a guarded role API and shows a useful denied state', async () => {
  const calls = [];
  const ui = harness(async url => {
    calls.push(url);
    if (url === '/api/health') return response(200, {demo: true});
    if (url === '/api/session') return response(200, {user: payload(2).user, csrf_token: 'csrf'});
    return response(403, {error: 'Another role'});
  }, '/dashboard/administrator');
  await flush();
  assert.ok(calls.includes('/api/dashboard/administrator'));
  assert.equal(ui.get('dashboard-content').hidden, true);
  assert.match(ui.get('signed-out-description').textContent, /another role/);
});

function luminance(hex) {
  if (hex.length === 4) hex = '#' + [...hex.slice(1)].map(c => c + c).join('');
  const rgb = hex.match(/[\da-f]{2}/gi).map(c => parseInt(c, 16) / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
  return rgb.reduce((sum, c, i) => sum + c * [.2126, .7152, .0722][i], 0);
}
function contrast(a, b) { const [low, high] = [luminance(a), luminance(b)].sort((x, y) => x - y); return (high + .05) / (low + .05); }
test('dashboard text palette meets normal-text contrast requirements', () => {
  const css = fs.readFileSync(path.join(__dirname, '../static/dashboard.css'), 'utf8');
  const variables = Object.fromEntries([...css.matchAll(/(--[a-z]+):(#[\da-f]+)/g)].map(match => [match[1], match[2]]));
  for (const [foreground, background] of [[variables['--muted'], variables['--white']], [variables['--muted'], variables['--page']], [variables['--teal'], variables['--pale']], ['#ffffff', variables['--teal']], ['#794d28', '#f4e9dd'], ['#5d4c7e', '#ece8f5'], ['#5e665f', '#f0f2ef']]) {
    assert.ok(contrast(foreground, background) >= 4.5, `${foreground} on ${background}`);
  }
});


test('merged folder and material tools have working allowlisted action links', async () => {
  const ui = harness(mockWorkspace(2, true, data => {
    data.actions.push({label: 'Folders', description: 'Group folders', available: true, href: '/access#folders-panel'});
    data.actions.push({label: 'Materials', description: 'Shared files', available: true, href: '/materials'});
    data.actions.push({label: 'Unsafe lookalike', description: 'Not a material endpoint', available: true, href: '/materials-redirect'});
    return data;
  }));
  await flush();
  const links = descendants(ui.get('tools')).filter(node => node.tagName === 'a').map(node => node.href);
  assert.ok(links.includes('/access#folders-panel'));
  assert.ok(links.includes('/materials'));
  assert.equal(links.includes('/materials-redirect'), false);
});


test('sign out uses the session CSRF token, clears private content and opens login', async () => {
  let logout;
  const base = mockWorkspace(3);
  const ui = harness(async (url, options) => {
    if (url === '/api/logout') { logout = options; return response(200, {message:'Signed out.'}); }
    return base(url, options);
  });
  await flush(); await ui.logout();
  assert.equal(logout.method,'POST');
  assert.equal(logout.headers['X-CSRF-Token'],'csrf');
  assert.equal(ui.get('profile-name').textContent,'');
  assert.equal(ui.get('dashboard-content').hidden,true);
  assert.deepEqual(ui.navigations,['/login']);
});

test('administrator management link uses the exact allowed local path', async () => {
  const ui = harness(mockWorkspace(3, true, data => {
    data.actions.push({label:'Users',description:'Account access',available:true,href:'/admin/users'});
    data.actions.push({label:'Unsafe lookalike',description:'Do not link',available:true,href:'/admin/users-external'});
    return data;
  }));
  await flush();
  const links = descendants(ui.get('tools')).filter(node=>node.tagName==='a').map(node=>node.href);
  assert.ok(links.includes('/admin/users'));
  assert.equal(links.includes('/admin/users-external'),false);
});


function fillQuiz(ui) {
  ui.get('quiz-group').value = '1'; ui.get('quiz-title').value = 'Private quiz title';
  const card = ui.get('quiz-questions').children[0];
  card.querySelector('.quiz-question-input').value = 'Private question';
  for (const [index,row] of card.querySelectorAll('.quiz-option-row').entries()) {
    row.querySelector('.quiz-option-input').value = 'Choice ' + index;
    row.querySelector('input[type="radio"]').checked = index === 2;
  }
}

test('quiz editor opens only for instructors on the quiz route and uses manageable groups', async () => {
  const ui = harness(mockWorkspace(1), '/quizzes'); await flush();
  assert.equal(ui.get('quiz-creation-panel').hidden, false);
  assert.equal(ui.get('quiz-questions').children.length, 1);
  assert.equal(ui.get('quiz-group').children[0].value, '');
  assert.equal(ui.get('quiz-group').children[1].value, '1');
  await ui.select(2);
  assert.equal(ui.get('quiz-creation-panel').hidden, true);
  assert.equal(ui.get('quiz-questions').children.length, 0);
});

test('quiz form submits selected answer flags exactly once while saving', async () => {
  const pending = deferred(); const writes = [];
  const base = mockWorkspace(1);
  const ui = harness(async (url, options = {}) => {
    if (url === '/api/groups/1/quizzes' && options.method === 'POST') {
        writes.push(options);
        return pending.promise;
    }
    return base(url, options);
  }, '/quizzes');
  await flush(); fillQuiz(ui);
  const saving = ui.submitQuiz(); await ui.submitQuiz();
  assert.equal(writes.length, 1);
  assert.equal(writes[0].headers['X-CSRF-Token'], 'csrf');
  assert.deepEqual(JSON.parse(writes[0].body).questions[0].options.map(option => option.is_correct), [false,false,true,false]);
  assert.equal(ui.get('quiz-title').disabled, true);
  pending.resolve(response(201, {quiz:{message:'Quiz created successfully.'}})); await saving;
  assert.equal(ui.get('create-quiz-status').textContent, 'Quiz created successfully.');
  assert.equal(ui.get('create-quiz-button').disabled, false);
});

test('account switch clears quiz drafts and ignores a previous account pending save response', async () => {
  const pending = deferred(); const base = mockWorkspace(1);
  const ui = harness(async (url, options = {}) =>
  url === '/api/groups/1/quizzes' && options.method === 'POST'
    ? pending.promise
    : base(url, options), '/quizzes');
  await flush(); fillQuiz(ui); const saving = ui.submitQuiz(); await ui.select(2);
  assert.equal(ui.get('quiz-title').value, '');
  assert.equal(ui.get('quiz-questions').children.length, 0);
  pending.resolve(response(201, {quiz:{message:'Old instructor success'}})); await saving;
  assert.equal(ui.get('create-quiz-status').textContent, '');
  assert.equal(ui.document.body.dataset.role, 'student');
});

test('failed dashboard refresh removes private quiz authoring data', async () => {
  let expired = false; const base = mockWorkspace(1);
  const ui = harness(async (url, options) => expired && url === '/api/session' ? response(401,{error:'Expired'}) : base(url,options), '/quizzes');
  await flush(); fillQuiz(ui); expired = true; await ui.refresh();
  assert.equal(ui.get('quiz-title').value, '');
  assert.equal(ui.get('quiz-questions').children.length, 0);
  assert.equal(ui.get('quiz-creation-panel').hidden, true);
});
