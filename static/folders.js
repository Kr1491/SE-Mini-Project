"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let current = null;
  let revision = 0;
  let groupSequence = 0;
  let selectedGroup = null;
  let saving = false;
  async function request(path, options = {}) {
    const headers = {...options.headers};
    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      headers['X-CSRF-Token'] = current.csrf_token;
    }
    const response = await fetch(path, {...options, headers, credentials: 'same-origin'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The folder request could not be completed.');
    return data;
  }
  function message(text, success = false) {
    byId('folder-message').textContent = text;
    byId('folder-message').classList.toggle('success', success);
  }
  function reset() {
    ++revision; ++groupSequence;
    current = null; selectedGroup = null; saving = false;
    byId('folders-panel').hidden = true;
    byId('create-folder-form').hidden = true;
    byId('folder-list').replaceChildren();
    byId('folder-group').replaceChildren();
    byId('folder-group').disabled = false;
    byId('create-folder-button').disabled = false;
    byId('folder-name').value = '';
    byId('folder-count').textContent = '';
    message('');
  }
  function renderFolders(folders) {
    byId('folder-count').textContent = `${folders.length} ${folders.length === 1 ? 'folder' : 'folders'}`;
    byId('folder-list').replaceChildren();
    if (!folders.length) {
      const empty = document.createElement('div'); empty.className = 'folder-empty';
      empty.textContent = 'No folders in this study group yet.';
      byId('folder-list').append(empty);
    }
    for (const folder of folders) {
      const card = document.createElement('article'); card.className = 'folder-card';
      const icon = document.createElement('span'); icon.className = 'folder-icon'; icon.textContent = '▱';
      const title = document.createElement('h3'); title.textContent = folder.name;
      const note = document.createElement('p'); note.textContent = 'Study folder';
      card.append(icon, title, note); byId('folder-list').append(card);
    }
  }
  async function openGroup(groupId, token = revision) {
    const sequence = ++groupSequence;
    selectedGroup = groupId;
    byId('create-folder-form').hidden = true;
    byId('folder-list').replaceChildren();
    byId('folder-count').textContent = '';
    byId('folder-status').textContent = 'Loading folders…';
    message('');
    try {
      const data = await request(`/api/groups/${groupId}/folders`);
      if (token !== revision || sequence !== groupSequence) return;
      renderFolders(data.folders);
      byId('create-folder-form').hidden = !data.can_create;
      byId('folder-status').textContent = data.can_create
        ? 'Create a folder to organize this group’s study resources.'
        : 'You can view this group’s folders. Folder creation is available to its authorized managers.';
      return true;
    } catch (error) {
      if (token !== revision || sequence !== groupSequence) return;
      byId('folder-status').textContent = 'Folders could not be loaded.';
      message(error.message);
      return false;
    }
  }
  async function load(session) {
    reset(); current = session;
    const token = revision;
    byId('folders-panel').hidden = false;
    byId('folder-status').textContent = 'Loading study groups…';
    try {
      const data = await request('/api/groups');
      if (token !== revision) return;
      for (const group of data.groups) {
        const option = document.createElement('option');
        option.value = String(group.id); option.textContent = group.name;
        byId('folder-group').append(option);
      }
      if (!data.groups.length) {
        byId('folder-group').disabled = true;
        byId('folder-status').textContent = 'No study groups are available for this account yet.';
        return;
      }
      byId('folder-group').value = String(data.groups[0].id);
      await openGroup(data.groups[0].id, token);
    } catch (error) {
      if (token !== revision) return;
      byId('folder-status').textContent = 'Study groups could not be loaded.';
      message(error.message);
    }
  }
  byId('folder-group').addEventListener('change', () => {
    if (!current || saving) return;
    byId('folder-name').value = '';
    return openGroup(Number(byId('folder-group').value));
  });
  byId('create-folder-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!current || selectedGroup === null || saving || byId('create-folder-form').hidden) return;
    const token = revision; const groupId = selectedGroup;
    saving = true;
    byId('create-folder-button').disabled = true;
    byId('folder-group').disabled = true;
    message('');
    try {
      const data = await request(`/api/groups/${groupId}/folders`, {
        method: 'POST', body: JSON.stringify({name: byId('folder-name').value})
      });
      if (token !== revision) return;
      byId('folder-name').value = '';
      const refreshed = await openGroup(groupId, token);
      if (token !== revision) return;
      if (refreshed) message(`“${data.folder.name}” was created.`, true);
      else message(`“${data.folder.name}” was created, but the folder list could not be refreshed. Select the group again to retry.`);
    } catch (error) {
      if (token === revision) message(error.message);
    } finally {
      if (token === revision) {
        saving = false;
        byId('create-folder-button').disabled = false;
        byId('folder-group').disabled = false;
      }
    }
  });
  globalThis.StudyFolders = {load, reset};
})();
