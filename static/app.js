"use strict";
const $ = (id) => document.getElementById(id);
let session = null;
let initialized = false;
let selectingAccount = false;
let accountRevision = 0;
let probeSequence = 0;
async function request(path, options = {}) {
  const headers = {...options.headers};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (session) headers["X-CSRF-Token"] = session.csrf_token;
  const response = await fetch(path, {...options, headers, credentials:"same-origin"});
  const data = await response.json();
  if (!response.ok) throw new Error(`${response.status}: ${data.error}`);
  return data;
}
async function showAccess(revision) {
  const current = await request("/api/session");
  if (revision !== accountRevision) return;
  session = current;
  $("access-panel").hidden = false;
  $("account-name").textContent = session.user.name;
  $("role-badge").textContent = session.user.role;
  $("permissions").replaceChildren();
  for (const permission of session.permissions) {
    const item = document.createElement("li");
    item.textContent = permission;
    $("permissions").append(item);
  }
  $("check-result").textContent = "";
  $("check-result").classList.remove("allowed");
  await globalThis.StudyFolders?.load(session);
}
$("accounts").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-user]");
  if (!button || !initialized || selectingAccount) return;
  selectingAccount = true;
  globalThis.StudyFolders?.reset();
  const revision = ++accountRevision;
  ++probeSequence;
  const buttons = [...$("accounts").querySelectorAll("button")];
  buttons.forEach((b) => b.disabled = true);
  $("access-panel").hidden = true;
  $("check-result").textContent = "";
  $("message").textContent = "";
  try {
    await request("/api/demo/session", {method:"POST", body:JSON.stringify({user_id:Number(button.dataset.user)})});
    await showAccess(revision);
    buttons.forEach((b) => b.classList.toggle("selected", b === button));
  } catch (error) { $("message").textContent = error.message; }
  finally {
    selectingAccount = false;
    buttons.forEach((b) => b.disabled = false);
  }
});
const checks = {
  instructor:"/api/access/instructor", admin:"/api/access/admin",
  "quiz-create":"/api/access/quiz-create", "group-1":"/api/access/groups/1",
  "group-3":"/api/access/groups/3", "manage-1":"/api/access/groups/1/manage"
};
$("access-panel").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-check]");
  if (!button || selectingAccount || !session) return;
  const sequence = ++probeSequence;
  const revision = accountRevision;
  button.disabled = true;
  try {
    const result = await request(checks[button.dataset.check]);
    if (sequence !== probeSequence || revision !== accountRevision) return;
    $("check-result").textContent = `Allowed: ${result.message}`;
    $("check-result").classList.add("allowed");
  } catch (error) {
    if (sequence !== probeSequence || revision !== accountRevision) return;
    $("check-result").textContent = error.message;
    $("check-result").classList.remove("allowed");
  } finally { button.disabled = false; }
});
(async () => {
  try {
    const health = await request("/api/health");
    $("demo-notice").hidden = !health.demo;
    try { await showAccess(accountRevision); }
    catch (error) {
      $("access-panel").hidden = true;
      $("message").textContent = health.demo ? "Choose a sample account to check its permissions." : "Sign in through the authentication module to continue. Demo access is disabled.";
    }
    // Make account selection available only after initial session detection settles.
    initialized = true;
    $("account-panel").hidden = !health.demo;
  } catch (error) { $("message").textContent = "Cannot reach the application. Start the server and refresh."; }
})();
