"use strict";
const $ = (id) => document.getElementById(id);
let session = null;
async function request(path, options = {}) {
  const headers = {...options.headers};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (session) headers["X-CSRF-Token"] = session.csrf_token;
  const response = await fetch(path, {...options, headers, credentials:"same-origin"});
  const data = await response.json();
  if (!response.ok) throw new Error(`${response.status}: ${data.error}`);
  return data;
}
async function showAccess() {
  session = await request("/api/session");
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
}
$("accounts").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-user]");
  if (!button) return;
  const buttons = [...$("accounts").querySelectorAll("button")];
  buttons.forEach((b) => b.disabled = true);
  $("message").textContent = "";
  try {
    await request("/api/demo/session", {method:"POST", body:JSON.stringify({user_id:Number(button.dataset.user)})});
    await showAccess();
    buttons.forEach((b) => b.classList.toggle("selected", b === button));
  } catch (error) { $("message").textContent = error.message; }
  finally { buttons.forEach((b) => b.disabled = false); }
});
const checks = {
  instructor:"/api/access/instructor", admin:"/api/access/admin",
  "quiz-create":"/api/access/quiz-create", "group-1":"/api/access/groups/1",
  "group-3":"/api/access/groups/3", "manage-1":"/api/access/groups/1/manage"
};
$("access-panel").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-check]");
  if (!button) return;
  button.disabled = true;
  try {
    const result = await request(checks[button.dataset.check]);
    $("check-result").textContent = `Allowed: ${result.message}`;
    $("check-result").classList.add("allowed");
  } catch (error) {
    $("check-result").textContent = error.message;
    $("check-result").classList.remove("allowed");
  } finally { button.disabled = false; }
});
(async () => {
  try {
    const health = await request("/api/health");
    $("demo-notice").hidden = !health.demo;
    $("account-panel").hidden = !health.demo;
    try { await showAccess(); }
    catch (error) {
      $("access-panel").hidden = true;
      $("message").textContent = health.demo ? "Choose a sample account to check its permissions." : "Sign in through the authentication module to continue. Demo access is disabled.";
    }
  } catch (error) { $("message").textContent = "Cannot reach the application. Start the server and refresh."; }
})();
