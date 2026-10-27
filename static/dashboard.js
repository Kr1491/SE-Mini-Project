"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let initialized = false;
  let demoMode = false;
  let switching = false;
  let revision = 0;
  let currentSession = null;
  const rolePath = (globalThis.location?.pathname || '').match(/^\/dashboard\/(student|instructor|administrator)$/);
  const dashboardApi = rolePath ? `/api/dashboard/${rolePath[1]}` : '/api/dashboard';
  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }
  async function request(path, options = {}) {
    const headers = {...options.headers};
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (currentSession) headers['X-CSRF-Token'] = currentSession.csrf_token;
    const response = await fetch(path, {...options, headers, credentials: 'same-origin'});
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || 'Your workspace could not be loaded.');
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function status(text, error = false) {
    byId('dashboard-status').textContent = text;
    byId('dashboard-status').classList.toggle('error', error);
  }
  function clearWorkspace() {
    document.title = 'StudySpace · Your workspace';
    byId('dashboard-content').hidden = true;
    byId('profile').hidden = true;
    byId('signed-out').hidden = true;
    for (const id of ['dashboard-stats', 'study-groups', 'tools', 'dashboard-nav']) byId(id).replaceChildren();
    for (const id of ['profile-name', 'profile-email', 'profile-avatar', 'dashboard-title', 'dashboard-description', 'dashboard-role', 'updated-at']) byId(id).textContent = '';
    delete document.body.dataset.role;
  }
  function safeHref(value) {
    return typeof value === 'string' && (/^#[a-z0-9-]+$/.test(value) || value === '/access' || value === '/access#folders-panel' || value === '/materials') ? value : null;
  }
  function render(data) {
    document.body.dataset.role = data.role;
    document.title = `StudySpace · ${data.role[0].toUpperCase() + data.role.slice(1)} dashboard`;
    byId('dashboard-eyebrow').textContent = `${data.role.toUpperCase()} WORKSPACE`;
    byId('dashboard-title').textContent = data.title;
    byId('dashboard-description').textContent = data.description;
    byId('dashboard-role').textContent = data.role;
    byId('profile-name').textContent = data.user.name;
    byId('profile-email').textContent = data.user.email;
    byId('profile-avatar').textContent = data.user.name.trim().slice(0, 1).toUpperCase() || 'S';
    byId('profile').hidden = false;
    for (const [index, entry] of data.navigation.entries()) {
      const href = safeHref(entry.href); if (!href) continue;
      const link = node('a', 'nav-link'); link.href = href;
      link.append(node('span', 'nav-marker', ['▦', '▱', '↗'][index] || '·'), node('span', '', entry.label));
      byId('dashboard-nav').append(link);
    }
    for (const [index, stat] of data.stats.entries()) {
      const card = node('article', 'stat-card'); const content = node('div');
      content.append(node('p', 'stat-label', stat.label), node('strong', 'stat-value', String(stat.value)));
      card.append(node('span', 'stat-icon', ['▦', '↗', '✓'][index] || '·'), content);
      byId('dashboard-stats').append(card);
    }
    byId('groups-heading').textContent = data.group_heading;
    byId('groups-count').textContent = `${data.groups.length} ${data.groups.length === 1 ? 'group' : 'groups'}`;
    for (const group of data.groups) {
      const card = node('article', 'group-card');
      card.append(node('span', 'group-icon', '▱'), node('h3', '', group.name),
        node('p', '', group.relationship), node('span', 'group-tag', group.can_manage ? 'Management access' : 'Read access'));
      byId('study-groups').append(card);
    }
    if (!data.groups.length) byId('study-groups').append(node('p', 'empty-state', 'No study groups are available for this account yet. Your groups will appear here when access is granted.'));
    byId('tools-heading').textContent = data.tools_heading;
    for (const action of data.actions) {
      const card = node('article', 'tool-card'); const content = node('div');
      content.append(node('h3', '', action.label), node('p', '', action.description));
      const href = action.available && safeHref(action.href);
      if (href) { const link = node('a', 'tool-link', 'Open workspace ↗'); link.href = href; content.append(link); }
      else content.append(node('span', 'coming-soon', 'Coming soon'));
      card.append(node('span', 'tool-icon', action.available ? '↗' : '▱'), content);
      byId('tools').append(card);
    }
    const updated = new Date(data.updated_at);
    byId('updated-at').textContent = Number.isNaN(updated.getTime()) ? '' : `Updated ${updated.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    byId('signed-out').hidden = true;
    byId('dashboard-content').hidden = false;
  }
  async function load(token) {
    clearWorkspace(); status('Loading your workspace…');
    try {
      const authenticated = await request('/api/session');
      if (token !== revision) return false;
      currentSession = authenticated;
      const data = await request(dashboardApi);
      if (token !== revision) return false;
      render(data); status('');
      return true;
    } catch (error) {
      if (token !== revision) return false;
      currentSession = null; clearWorkspace();
      byId('signed-out').hidden = false;
      byId('signed-out-description').textContent = error.status === 403
        ? 'This page is for another role. Open your own dashboard to continue.'
        : 'Sign in to see your groups and role-specific tools. In local demo mode, select a sample account above.';
      status(error.message, error.status !== 401);
      return false;
    }
  }
  byId('sample-accounts').addEventListener('click', async event => {
    const button = event.target.closest('[data-account]');
    if (!button || !initialized || !demoMode || switching) return;
    switching = true;
    const token = ++revision;
    const buttons = [...byId('sample-accounts').querySelectorAll('button')];
    buttons.forEach(item => { item.disabled = true; item.classList.remove('selected'); });
    byId('refresh-dashboard').disabled = true;
    currentSession = null; clearWorkspace(); status('Opening the selected workspace…');
    try {
      await request('/api/demo/session', {method: 'POST', body: JSON.stringify({user_id: Number(button.dataset.account)})});
      const loaded = await load(token);
      if (token === revision) buttons.forEach(item => item.classList.toggle('selected', loaded && item === button));
    } catch (error) {
      if (token === revision) { clearWorkspace(); byId('signed-out').hidden = false; status(error.message, true); }
    } finally {
      switching = false;
      buttons.forEach(item => item.disabled = false);
      if (token === revision) byId('refresh-dashboard').disabled = false;
    }
  });
  byId('logout').addEventListener('click', async () => {
    if (!currentSession || switching) return;
    switching = true; ++revision;
    byId('logout').disabled = true;
    clearWorkspace(); status('Signing out…');
    try {
      await request('/api/logout', {method: 'POST', body: '{}'});
      currentSession = null;
      globalThis.location?.replace?.('/login');
    } catch (error) {
      currentSession = null;
      if (error.status === 401) globalThis.location?.replace?.('/login');
      else { byId('signed-out').hidden = false; status(error.message, true); }
    } finally { switching = false; byId('logout').disabled = false; }
  });
  byId('refresh-dashboard').addEventListener('click', async () => {
    if (!initialized || switching || byId('refresh-dashboard').disabled) return;
    const token = ++revision;
    byId('refresh-dashboard').disabled = true;
    await load(token);
    if (token === revision) byId('refresh-dashboard').disabled = false;
  });
  (async () => {
    try {
      const health = await request('/api/health');
      demoMode = health.demo;
      byId('demo-banner').hidden = !health.demo;
      await load(revision);
      initialized = true;
      byId('sample-panel').hidden = !health.demo;
    } catch (error) {
      clearWorkspace(); byId('signed-out').hidden = false;
      status('Cannot reach the application. Start the server and refresh.', true);
    }
  })();
})();
