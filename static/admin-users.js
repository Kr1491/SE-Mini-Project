"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const state = {session: null, revision: 0, users: new Map(), roles: [], readOnly: false, limit: 20, offset: 0, total: 0, query: '', role: '', access: 'all', edit: null, saving: false};
  const filterIds = ['account-search', 'role-filter', 'access-filter', 'apply-filters', 'refresh-users'];
  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function message(text, kind = '') {
    byId('admin-status').textContent = text;
    byId('admin-status').classList.toggle('error', kind === 'error');
    byId('admin-status').classList.toggle('success', kind === 'success');
  }
  async function request(path, options = {}) {
    const headers = {...options.headers};
    if (options.body !== undefined) { headers['Content-Type'] = 'application/json'; headers['X-CSRF-Token'] = state.session.csrf_token; }
    const response = await fetch(path, {...options, headers, credentials: 'same-origin'});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || 'The account request could not be completed.'); error.status = response.status; throw error; }
    return data;
  }
  function clearPrivate() {
    state.users.clear(); state.session = null;
    byId('user-rows').replaceChildren(); byId('role-guide').replaceChildren();
    byId('admin-profile').textContent = ''; byId('manage-content').hidden = true;
    byId('account-count').textContent = ''; byId('page-info').textContent = '';
    closeDialog();
  }
  function denied(error) {
    clearPrivate();
    message(error.status === 401 ? 'Your session has expired. Sign in again.' : 'Administrator access is required for user management.', 'error');
    if (error.status === 401) globalThis.location?.replace?.('/login');
  }
  function changed(entry) { return entry.role.value !== entry.user.role || (entry.access.value === 'active') !== entry.user.is_active; }
  function lockControls() {
    const locked = state.saving || state.edit !== null;
    for (const id of filterIds) byId(id).disabled = locked;
    byId('previous-page').disabled = locked || state.offset === 0;
    byId('next-page').disabled = locked || state.offset + state.users.size >= state.total;
    for (const entry of state.users.values()) {
      const disabled = locked || state.readOnly || entry.user.is_you;
      entry.role.disabled = disabled; entry.access.disabled = disabled;
      entry.save.disabled = disabled || !changed(entry);
    }
    byId('confirm-change').disabled = state.saving;
    byId('cancel-change').disabled = state.saving;
  }
  function closeDialog() {
    state.edit = null;
    if (byId('confirm-dialog').open) byId('confirm-dialog').close();
    byId('confirm-person').textContent = ''; byId('confirm-details').textContent = '';
    lockControls();
  }
  function options(select, choices, selected) {
    for (const choice of choices) { const option = node('option', '', choice.label); option.value = choice.value; select.append(option); }
    select.value = selected;
  }
  function render(data) {
    state.readOnly = data.read_only; state.roles = data.roles; state.total = data.total; state.limit = data.limit; state.offset = data.offset;
    state.users.clear(); byId('user-rows').replaceChildren(); byId('role-guide').replaceChildren();
    byId('demo-notice').hidden = !data.read_only;
    for (const role of data.roles) {
      const card = node('details', 'role-card'); card.append(node('summary', '', role.label + ' permissions'));
      const list = node('ul'); for (const permission of role.permissions) list.append(node('li', '', permission));
      card.append(list); byId('role-guide').append(card);
    }
    for (const user of data.users) {
      const row = node('tr'); const person = node('td', 'person-cell'); const name = node('div', 'person-name');
      name.append(node('strong', '', user.name)); if (user.is_you) name.append(node('span', 'you-badge', 'You'));
      person.append(name, node('span', 'person-email', user.email));
      const roleCell = node('td'); const role = node('select'); role.setAttribute('aria-label', `Role for ${user.name}`); role.dataset.userRole = String(user.id);
      options(role, data.roles, user.role); roleCell.append(role);
      const accessCell = node('td'); const access = node('select'); access.setAttribute('aria-label', `Account access for ${user.name}`); access.dataset.userAccess = String(user.id);
      options(access, [{value: 'active', label: 'Active'}, {value: 'inactive', label: 'Suspended'}], user.is_active ? 'active' : 'inactive'); accessCell.append(access);
      const saveCell = node('td'); const save = node('button', 'secondary-button', 'Review change'); save.type = 'button'; save.dataset.save = String(user.id); saveCell.append(save);
      row.append(person, roleCell, accessCell, saveCell); byId('user-rows').append(row);
      state.users.set(user.id, {user, role, access, save});
    }
    if (!data.users.length) { const row = node('tr'); const empty = node('td', 'empty-state', 'No accounts match these filters.'); empty.colSpan = 4; row.append(empty); byId('user-rows').append(row); }
    byId('account-count').textContent = `${data.total} ${data.total === 1 ? 'account' : 'accounts'}`;
    byId('page-info').textContent = data.users.length ? `${data.offset + 1}–${data.offset + data.users.length} of ${data.total}` : 'No matching accounts';
    byId('manage-content').hidden = false; lockControls();
  }
  async function load() {
    const token = ++state.revision;
    state.users.clear(); byId('user-rows').replaceChildren();
    byId('previous-page').disabled = true; byId('next-page').disabled = true;
    message('Loading accounts…');
    const params = new URLSearchParams({q: state.query, role: state.role, access: state.access, limit: String(state.limit), offset: String(state.offset)});
    try {
      const data = await request(`/api/admin/users?${params}`);
      if (token !== state.revision) return false;
      if (!data.users.length && state.offset > 0) { state.offset = Math.max(0, Math.floor((data.total - 1) / data.limit) * data.limit); return load(); }
      render(data); message(''); return true;
    } catch (error) {
      if (token !== state.revision) return false;
      if ([401, 403].includes(error.status)) denied(error);
      else message(error.message || 'Cannot load accounts. Try Refresh.', 'error');
      return false;
    }
  }
  byId('user-rows').addEventListener('change', lockControls);
  byId('user-rows').addEventListener('click', event => {
    const button = event.target.closest('[data-save]');
    if (!button || button.disabled || state.saving || state.readOnly || state.edit) return;
    const entry = state.users.get(Number(button.dataset.save));
    if (!entry || entry.user.is_you || !changed(entry)) return;
    state.edit = {id: entry.user.id, name: entry.user.name, role: entry.role.value, is_active: entry.access.value === 'active', version: entry.user.version};
    byId('confirm-person').textContent = `${entry.user.name} · ${entry.user.email}`;
    const label = state.roles.find(role => role.value === state.edit.role)?.label || state.edit.role;
    byId('confirm-details').textContent = `Role: ${label}. Access: ${state.edit.is_active ? 'Active' : 'Suspended'}.`;
    lockControls(); byId('confirm-dialog').showModal();
  });
  byId('confirm-change').addEventListener('click', async () => {
    if (!state.edit || state.saving || !state.session) return;
    const edit = {...state.edit}; state.saving = true; lockControls(); message('Saving account access…');
    try {
      const result = await request(`/api/admin/users/${edit.id}`, {method: 'POST', body: JSON.stringify({role: edit.role, is_active: edit.is_active, version: edit.version})});
      closeDialog();
      if (await load()) message(result.message, 'success');
    } catch (error) {
      closeDialog();
      if ([401, 403].includes(error.status)) denied(error);
      else if (error.status === 409) { if (await load()) message(error.message, 'error'); }
      else message(error.message || 'Could not save. Refresh to check the account before retrying.', 'error');
    } finally { state.saving = false; lockControls(); }
  });
  byId('cancel-change').addEventListener('click', () => { if (!state.saving) closeDialog(); });
  byId('confirm-dialog').addEventListener('cancel', event => { if (state.saving) event.preventDefault(); else closeDialog(); });
  byId('confirm-dialog').addEventListener('close', () => { if (!byId('confirm-dialog').open && !state.saving) closeDialog(); });
  byId('account-filters').addEventListener('submit', event => {
    event.preventDefault(); if (!state.session || state.saving || state.edit) return;
    state.query = byId('account-search').value.trim(); state.role = byId('role-filter').value; state.access = byId('access-filter').value; state.offset = 0;
    return load();
  });
  byId('refresh-users').addEventListener('click', () => { if (state.session && !state.saving && !state.edit) return load(); });
  for (const [id, direction] of [['previous-page', -1], ['next-page', 1]]) byId(id).addEventListener('click', () => {
    if (!state.session || state.saving || state.edit || byId(id).disabled) return;
    state.offset = Math.max(0, state.offset + direction * state.limit); return load();
  });
  (async () => {
    try {
      state.session = await request('/api/session');
      if (state.session.user.role !== 'administrator') return denied({status: 403});
      byId('admin-profile').textContent = state.session.user.name;
      await load();
    } catch (error) { if ([401, 403].includes(error.status)) denied(error); else { clearPrivate(); message('Cannot reach the application. Refresh to try again.', 'error'); } }
  })();
})();
