/* =====================================================================
   Buff Bison – Estimates page
   Covers RTM A3 (estimates with line items + auto-calculation)
   and A4 (convert approved estimate -> project).

   Data comes from the Flask JSON API in api.py (via apiRequest in
   api-client.js). The server re-checks everything and recalculates totals.
   ===================================================================== */

// Filled from the server when the page loads (see loadData)
let clients = [];
let costCategories = [];
let managers = [];
let estimates = [];

// ---------------------------------------------------------------------
// API calls (endpoints are in api.py)
// ---------------------------------------------------------------------
const api = {
  lookups:   ()                 => apiRequest("GET", "/api/lookups"),
  list:      ()                 => apiRequest("GET", "/api/estimates"),
  create:    (payload)          => apiRequest("POST", "/api/estimates", payload),
  update:    (id, payload)      => apiRequest("PUT", `/api/estimates/${id}`, payload),
  setStatus: (id, status)       => apiRequest("PATCH", `/api/estimates/${id}/status`, { status }),
  remove:    (id)               => apiRequest("DELETE", `/api/estimates/${id}`),
  convert:   (id, projectData)  => apiRequest("POST", `/api/estimates/${id}/convert`, projectData),
};

async function loadData() {
  const [lookups, list] = await Promise.all([api.lookups(), api.list()]);
  clients = lookups.clients;
  costCategories = lookups.categories;
  managers = lookups.managers;
  estimates = list;
}

async function reloadEstimates() {
  estimates = await api.list();
  refresh();
}

// Runs an API action; shows the server's message if it fails.
// Returns true on success so callers can close the modal.
async function attempt(action, errorBox) {
  try {
    await action();
    return true;
  } catch (err) {
    if (errorBox) { errorBox.textContent = err.message; errorBox.hidden = false; }
    else toast(err.message);
    if (err.status === 401) setTimeout(() => (window.location.href = "/login"), 1500);
    return false;
  }
}

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const money = (n) => Number(n || 0).toLocaleString("en-US", { style: "currency", currency: "USD" });
const moneyShort = (n) => Number(n || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
function round2(n) { return Math.round((Number(n) + Number.EPSILON) * 100) / 100; }
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function formatDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
}
const clientName = (id) => { const c = clients.find(c => c.client_id === id); return c ? c.name : "—"; };
const findEstimate = (id) => estimates.find(e => e.estimate_id === id);

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => (t.hidden = true), 3200);
}

// ---------------------------------------------------------------------
// List view
// ---------------------------------------------------------------------
function renderStats() {
  const pending = estimates.filter(e => e.status === "Sent");
  $("#statTotal").textContent = estimates.length;
  $("#statPending").textContent = pending.length;
  $("#statApproved").textContent = estimates.filter(e => e.status === "Approved").length;
  $("#statPendingValue").textContent = moneyShort(pending.reduce((s, e) => s + e.total_amount, 0));
}

function renderTable() {
  const q = $("#searchInput").value.trim().toLowerCase();
  const status = $("#statusFilter").value;

  const rows = estimates.filter(e => {
    if (status !== "All" && e.status !== status) return false;
    if (!q) return true;
    return [e.estimate_number, e.title, clientName(e.client_id)].some(v => v.toLowerCase().includes(q));
  });

  if (rows.length === 0) {
    $("#estimatesBody").innerHTML = `<tr class="empty-row"><td colspan="8">No estimates match your search.</td></tr>`;
    return;
  }

  $("#estimatesBody").innerHTML = rows.map(e => `
    <tr>
      <td>${escapeHtml(e.title)}</td>
      <td>${escapeHtml(e.estimate_number)}</td>
      <td>${escapeHtml(clientName(e.client_id))}</td>
      <td>${escapeHtml(e.created_by_name || "—")}</td>
      <td>${formatDate(e.created_at)}</td>
      <td>${statusBadge(e.status)}</td>
      <td class="num">${money(e.total_amount)}</td>
      <td>
        <div class="row-actions">
          <button type="button" class="btn-outline" data-action="open" data-id="${e.estimate_id}">
            ${e.status === "Draft" ? "Edit" : "View"}
          </button>
          ${e.status === "Approved"
            ? `<button type="button" class="btn btn-sm" data-action="convert" data-id="${e.estimate_id}">Convert</button>`
            : ""}
        </div>
      </td>
    </tr>`).join("");
}

// Reuses the badge colors already in style.css (.status.progress, .completed, .hold, .near)
const STATUS_CLASS = { Draft: "draft", Sent: "progress", Approved: "completed", Rejected: "hold", Converted: "near" };
function statusBadge(status) {
  return `<span class="status ${STATUS_CLASS[status]}">${status}</span>`;
}

function refresh() { renderStats(); renderTable(); }

// ---------------------------------------------------------------------
// Estimate modal (create / edit / view)
// ---------------------------------------------------------------------
let editingId = null;   // null = new estimate
let readOnly = false;

function openModal(el) { el.hidden = false; document.body.style.overflow = "hidden"; }
function closeModal(el) { el.hidden = true; document.body.style.overflow = ""; }

function fillSelect(select, items, valueKey, labelFn, placeholder) {
  select.innerHTML = (placeholder ? `<option value="">${placeholder}</option>` : "") +
    items.map(i => `<option value="${i[valueKey]}">${escapeHtml(labelFn(i))}</option>`).join("");
}

function openEstimate(id = null) {
  editingId = id;
  const e = id ? findEstimate(id) : null;
  // Only Draft and Sent estimates can be edited; everything else is a record.
  readOnly = !!e && !["Draft", "Sent"].includes(e.status);

  $("#estimateModalTitle").textContent = e ? `${e.estimate_number}` : "New Estimate";
  $("#estimateModalSub").innerHTML = e
    ? `${statusBadge(e.status)} &nbsp;Created ${formatDate(e.created_at)} by ${escapeHtml(e.created_by_name || "—")}`
    : "Add a client, job title, and at least one line item.";

  fillSelect($("#estClient"), clients, "client_id", c => c.name, "Select a client…");
  $("#estClient").value = e ? e.client_id : "";
  $("#estTitle").value = e ? e.title : "";

  $("#lineItemsBody").innerHTML = "";
  const lines = e ? e.line_items : [{ category_id: "", description: "", quantity: 1, unit_cost: 0 }];
  lines.forEach(addLineRow);

  $("#estClient").disabled = readOnly;
  $("#estTitle").disabled = readOnly;
  $("#addLineBtn").hidden = readOnly;
  $("#formError").hidden = true;

  renderFooter(e);
  recalc();
  openModal($("#estimateModal"));
  if (!readOnly) $("#estClient").focus();
}

function renderFooter(e) {
  const f = $("#estimateFooter");
  const status = e ? e.status : "New";
  const buttons = {
    New: `
      <button type="button" class="btn-outline" data-close>Cancel</button>
      <button type="button" class="btn-outline" data-save="Draft">Save as Draft</button>
      <button type="button" class="btn" data-save="Sent">Save &amp; Send</button>`,
    Draft: `
      <button type="button" class="btn-danger" data-delete>Delete Draft</button>
      <span class="spacer"></span>
      <button type="button" class="btn-outline" data-close>Cancel</button>
      <button type="button" class="btn-outline" data-save="Draft">Save Draft</button>
      <button type="button" class="btn" data-save="Sent">Save &amp; Send</button>`,
    Sent: `
      <button type="button" class="btn-danger" data-status="Rejected">Mark Rejected</button>
      <span class="spacer"></span>
      <button type="button" class="btn-outline" data-close>Close</button>
      <button type="button" class="btn-outline" data-save="Sent">Save Changes</button>
      <button type="button" class="btn" data-status="Approved">Mark Approved</button>`,
    Approved: `
      <button type="button" class="btn-outline" data-close>Close</button>
      <button type="button" class="btn" data-convert>Convert to Project</button>`,
    Rejected: `
      <button type="button" class="btn-outline" data-close>Close</button>
      <button type="button" class="btn-outline" data-status="Draft">Reopen as Draft</button>`,
    Converted: `
      <span class="modal-sub" style="margin-right:auto">Converted to project ${e && e.project_number ? escapeHtml(e.project_number) : ""}</span>
      <button type="button" class="btn-outline" data-close>Close</button>`,
  };
  f.innerHTML = buttons[status];
}

function addLineRow(li = {}) {
  const tr = document.createElement("tr");
  const dis = readOnly ? "disabled" : "";
  tr.innerHTML = `
    <td><select class="li-cat" ${dis}>
      <option value="">Category…</option>
      ${costCategories.map(c => `<option value="${c.category_id}">${escapeHtml(c.name)}</option>`).join("")}
    </select></td>
    <td><input class="li-desc" type="text" placeholder="Description" value="${escapeHtml(li.description ?? "")}" ${dis}></td>
    <td><input class="li-qty" type="number" min="0" step="any" value="${li.quantity ?? 1}" ${dis}></td>
    <td><input class="li-cost" type="number" min="0" step="0.01" value="${li.unit_cost ?? 0}" ${dis}></td>
    <td class="line-total">$0.00</td>
    <td>${readOnly ? "" : `<button type="button" class="remove-line" aria-label="Remove line">×</button>`}</td>`;
  tr.querySelector(".li-cat").value = li.category_id ?? "";
  $("#lineItemsBody").appendChild(tr);
}

// Auto-calculation (A3): line_total = quantity × unit_cost, total = Σ line_total
function recalc() {
  let total = 0, count = 0;
  document.querySelectorAll("#lineItemsBody tr").forEach(tr => {
    const qty = parseFloat(tr.querySelector(".li-qty").value) || 0;
    const cost = round2(parseFloat(tr.querySelector(".li-cost").value) || 0);  // cents, same as the server
    const lineTotal = round2(qty * cost);
    tr.querySelector(".line-total").textContent = money(lineTotal);
    total += lineTotal;
    count++;
  });
  $("#lineCount").textContent = count;
  $("#estimateTotal").textContent = money(round2(total));
}

function collectForm() {
  const errors = [];
  document.querySelectorAll("#estimateForm .invalid").forEach(el => el.classList.remove("invalid"));

  const client_id = Number($("#estClient").value);
  const title = $("#estTitle").value.trim();
  if (!client_id) { errors.push("Select a client."); $("#estClient").classList.add("invalid"); }
  if (!title) { errors.push("Enter a job title."); $("#estTitle").classList.add("invalid"); }

  const line_items = [];
  document.querySelectorAll("#lineItemsBody tr").forEach(tr => {
    const cat = tr.querySelector(".li-cat"), desc = tr.querySelector(".li-desc");
    const qty = tr.querySelector(".li-qty"), cost = tr.querySelector(".li-cost");
    const q = parseFloat(qty.value), c = parseFloat(cost.value);
    let bad = false;
    if (!cat.value) { cat.classList.add("invalid"); bad = true; }
    if (!desc.value.trim()) { desc.classList.add("invalid"); bad = true; }
    if (!(q > 0)) { qty.classList.add("invalid"); bad = true; }
    if (!(c >= 0) || cost.value === "") { cost.classList.add("invalid"); bad = true; }
    if (bad) return;
    line_items.push({
      category_id: Number(cat.value),
      description: desc.value.trim(),
      quantity: q,
      unit_cost: round2(c),
      line_total: round2(q * c),
    });
  });

  const rowCount = document.querySelectorAll("#lineItemsBody tr").length;
  if (rowCount === 0) errors.push("Add at least one line item.");
  else if (line_items.length !== rowCount) errors.push("Fix the highlighted line items (category, description, quantity above 0, and unit cost are required).");

  const err = $("#formError");
  err.hidden = errors.length === 0;
  err.textContent = errors.join(" ");
  if (errors.length) return null;

  return {
    client_id, title, line_items,
    total_amount: round2(line_items.reduce((s, li) => s + li.line_total, 0)),
  };
}

async function saveEstimate(status) {
  const data = collectForm();
  if (!data) return;
  // The server works out line totals and the estimate total itself.
  const payload = {
    client_id: data.client_id,
    title: data.title,
    status,
    line_items: data.line_items.map(({ category_id, description, quantity, unit_cost }) =>
      ({ category_id, description, quantity, unit_cost })),
  };
  let saved;
  const ok = await attempt(async () => {
    saved = editingId ? await api.update(editingId, payload) : await api.create(payload);
  }, $("#formError"));
  if (!ok) return;
  toast(editingId
    ? `${saved.estimate_number} saved${status === "Sent" ? " and sent" : ""}`
    : `${saved.estimate_number} created${status === "Sent" ? " and sent" : " as draft"}`);
  closeModal($("#estimateModal"));
  await reloadEstimates();
}

async function changeStatus(status) {
  let saved;
  const ok = await attempt(async () => { saved = await api.setStatus(editingId, status); }, $("#formError"));
  if (!ok) return;
  toast(`${saved.estimate_number} marked ${status}`);
  closeModal($("#estimateModal"));
  await reloadEstimates();
}

async function deleteDraft() {
  const e = findEstimate(editingId);
  if (!confirm(`Delete ${e.estimate_number}? This cannot be undone.`)) return;
  const ok = await attempt(() => api.remove(editingId), $("#formError"));
  if (!ok) return;
  toast(`${e.estimate_number} deleted`);
  closeModal($("#estimateModal"));
  await reloadEstimates();
}

// ---------------------------------------------------------------------
// Convert to project (A4)
// ---------------------------------------------------------------------
let convertingId = null;

function openConvert(id) {
  convertingId = id;
  const e = findEstimate(id);
  $("#convertSub").textContent = `From ${e.estimate_number}`;
  $("#convertSummary").innerHTML = `
    <strong>Client:</strong> ${escapeHtml(clientName(e.client_id))}<br>
    <strong>Approved total:</strong> ${money(e.total_amount)}<br>
    <strong>Line items:</strong> ${e.line_items.length} (the estimate stays linked to the new project)`;
  $("#projName").value = e.title;
  fillSelect($("#projManager"), managers, "user_id", u => u.name, "Select a project manager…");
  $("#projBudget").value = e.total_amount;
  $("#projStart").value = todayISO();
  $("#projDue").value = "";
  $("#convertError").hidden = true;
  document.querySelectorAll("#convertForm .invalid").forEach(el => el.classList.remove("invalid"));
  closeModal($("#estimateModal"));
  openModal($("#convertModal"));
  $("#projName").focus();
}

async function submitConvert(ev) {
  ev.preventDefault();
  const errors = [];
  const name = $("#projName"), pm = $("#projManager"), budget = $("#projBudget");
  const start = $("#projStart"), due = $("#projDue");
  [name, pm, budget, due].forEach(el => el.classList.remove("invalid"));

  if (!name.value.trim()) { errors.push("Enter a project name."); name.classList.add("invalid"); }
  if (!pm.value) { errors.push("Select a project manager."); pm.classList.add("invalid"); }
  if (!(parseFloat(budget.value) >= 0) || budget.value === "") { errors.push("Enter a budget."); budget.classList.add("invalid"); }
  if (!due.value) { errors.push("Choose a due date."); due.classList.add("invalid"); }
  else if (start.value && due.value < start.value) { errors.push("Due date must be after the start date."); due.classList.add("invalid"); }

  const err = $("#convertError");
  err.hidden = errors.length === 0;
  err.textContent = errors.join(" ");
  if (errors.length) return;

  let result;
  const ok = await attempt(async () => {
    result = await api.convert(convertingId, {
      name: name.value.trim(),
      project_manager_id: Number(pm.value),
      budget_amount: round2(parseFloat(budget.value)),
      start_date: start.value || null,
      due_date: due.value,
    });
  }, err);
  if (!ok) return;
  closeModal($("#convertModal"));
  await reloadEstimates();
  toast(`Project ${result.project_number} created from ${result.estimate.estimate_number}. It's now on the Projects page.`);
}

// ---------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  $("#estimatesBody").innerHTML = `<tr class="empty-row"><td colspan="8">Loading estimates…</td></tr>`;
  try {
    await loadData();
    refresh();
  } catch (err) {
    $("#estimatesBody").innerHTML = `<tr class="empty-row"><td colspan="8">${escapeHtml(err.message)}</td></tr>`;
    if (err.status === 401) setTimeout(() => (window.location.href = "/login"), 1500);
  }

  $("#newEstimateBtn").addEventListener("click", () => openEstimate());
  $("#searchInput").addEventListener("input", renderTable);
  $("#statusFilter").addEventListener("change", renderTable);

  $("#estimatesBody").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-action]");
    if (!btn) return;
    const id = Number(btn.dataset.id);
    if (btn.dataset.action === "open") openEstimate(id);
    if (btn.dataset.action === "convert") openConvert(id);
  });

  $("#addLineBtn").addEventListener("click", () => {
    addLineRow({ category_id: "", description: "", quantity: 1, unit_cost: 0 });
    recalc();
    const rows = document.querySelectorAll("#lineItemsBody tr");
    rows[rows.length - 1].querySelector(".li-cat").focus();
  });

  // Clear validation styling as soon as the user fixes a field
  ["#estimateForm", "#convertForm"].forEach(sel => {
    $(sel).addEventListener("input", (ev) => ev.target.classList.remove("invalid"));
    $(sel).addEventListener("change", (ev) => ev.target.classList.remove("invalid"));
  });
  $("#lineItemsBody").addEventListener("input", () => {
    $("#formError").hidden = true;
    recalc();
  });
  $("#lineItemsBody").addEventListener("click", (ev) => {
    if (ev.target.closest(".remove-line")) {
      ev.target.closest("tr").remove();
      recalc();
    }
  });

  $("#estimateFooter").addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.save) saveEstimate(b.dataset.save);
    else if (b.dataset.status) changeStatus(b.dataset.status);
    else if (b.hasAttribute("data-delete")) deleteDraft();
    else if (b.hasAttribute("data-convert")) openConvert(editingId);
  });
  $("#estimateForm").addEventListener("submit", (ev) => ev.preventDefault());
  $("#convertForm").addEventListener("submit", submitConvert);

  // Close buttons + backdrop click + Escape
  document.querySelectorAll(".modal-backdrop").forEach(bd => {
    bd.addEventListener("click", (ev) => {
      if (ev.target === bd || ev.target.closest("[data-close]")) closeModal(bd);
    });
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") document.querySelectorAll(".modal-backdrop:not([hidden])").forEach(closeModal);
  });

  // Links from search results: /estimates?open=<estimate id>
  const params = new URLSearchParams(window.location.search);
  const openId = Number(params.get("open"));
  if (openId && findEstimate(openId)) openEstimate(openId);
  if (params.has("open")) history.replaceState(null, "", window.location.pathname);
});
