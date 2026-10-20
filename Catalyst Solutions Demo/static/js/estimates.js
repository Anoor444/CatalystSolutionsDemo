/* =====================================================================
   Buff Bison – Estimates page
   Covers RTM A3 (estimates with line items + auto-calculation)
   and A4 (convert approved estimate -> project).

   Field names follow the ERD (Estimate, EstimateLineItem, CostCategory,
   Client, User, Project) so the mock data can be swapped for API calls.
   Every place that should talk to the Flask backend is inside `api`
   below and marked with TODO(backend).
   ===================================================================== */

// ---------------------------------------------------------------------
// Mock data (replace with API responses)
// ---------------------------------------------------------------------
const CURRENT_USER = { user_id: 1, first_name: "Daniel", last_name: "Carter", role: "admin" };

const users = [
  { user_id: 1, first_name: "Daniel", last_name: "Carter", role: "admin" },
  { user_id: 2, first_name: "Carlos", last_name: "Reyes",  role: "project_manager" },
  { user_id: 3, first_name: "James",  last_name: "Wilson", role: "project_manager" },
];

const clients = [
  { client_id: 1, contact_first_name: "Maria",   contact_last_name: "Hernandez" },
  { client_id: 2, contact_first_name: "James",   contact_last_name: "Thompson" },
  { client_id: 3, contact_first_name: "Angela",  contact_last_name: "Brooks" },
  { client_id: 4, contact_first_name: "Robert",  contact_last_name: "Nguyen" },
  { client_id: 5, contact_first_name: "Sarah",   contact_last_name: "Johnson" },
  { client_id: 6, contact_first_name: "Emily",   contact_last_name: "Davis" },
  { client_id: 7, contact_first_name: "Michael", contact_last_name: "Thompson" },
];

const costCategories = [
  { category_id: 1, name: "Labor" },
  { category_id: 2, name: "Materials" },
  { category_id: 3, name: "Equipment" },
  { category_id: 4, name: "Subcontractor" },
  { category_id: 5, name: "Permits & Fees" },
  { category_id: 6, name: "Disposal" },
];

let nextLineIdSeed = 1;

// status: Draft | Sent | Approved | Rejected | Converted
let estimates = [
  est(1001, "Kitchen Remodel – Oak Forest",      1, 1, "Converted", "2026-08-18", [[2,"Cabinets and countertops",1,28500],[1,"Demo and install labor",120,85],[4,"Plumbing and electrical",1,18500],[5,"City permit",1,1300]]),
  est(1002, "Roof Replacement – Katy",           2, 2, "Converted", "2026-08-25", [[2,"Architectural shingles (squares)",32,310],[1,"Tear-off and install labor",1,10500],[6,"Dumpster and haul-off",1,1780]]),
  est(1003, "Storm Damage Repair – Cypress",     4, 2, "Approved",  "2026-09-22", [[1,"Framing and drywall repair",96,80],[2,"Lumber, drywall, and paint",1,9400],[4,"Window replacement",1,14200],[6,"Debris removal",1,1470]]),
  est(1004, "Master Bath Addition – Sugar Land", 3, 1, "Sent",      "2026-09-29", [[4,"Plumbing rough-in and finish",1,12500],[2,"Tile, vanity, and fixtures",1,16800],[1,"General labor",110,85],[5,"Permit and inspection",1,2350]]),
  est(1005, "Patio Cover – Pearland",            5, 1, "Sent",      "2026-10-01", [[2,"Cedar posts and beams",1,6200],[1,"Framing labor",60,80],[3,"Post-hole auger rental",2,175]]),
  est(1006, "Garage Conversion – Spring",        6, 3, "Sent",      "2026-10-03", [[1,"Framing and insulation",140,82],[4,"HVAC mini-split install",1,5800],[2,"Drywall, flooring, trim",1,8900],[5,"Permit",1,950]]),
  est(1007, "Fence Replacement – Humble",        7, 2, "Sent",      "2026-10-06", [[2,"Pressure-treated pickets and rails",210,14.5],[1,"Install labor",48,70],[6,"Old fence haul-off",1,650]]),
  est(1008, "Laundry Room Refresh – Bellaire",   5, 1, "Draft",     "2026-10-09", [[2,"Cabinets and shelving",1,3400],[1,"Install labor",24,80]]),
  est(1009, "Deck Repair – The Woodlands",       2, 3, "Draft",     "2026-10-11", [[2,"Composite decking boards",45,62],[1,"Demo and install",36,80]]),
  est(1010, "Driveway Extension – Tomball",      4, 2, "Rejected",  "2026-09-12", [[4,"Concrete pour and finish",1,9800],[3,"Skid steer rental",2,420]]),
];

let nextEstimateId = 1011;
let nextLineId = 500;

function est(id, title, clientId, createdBy, status, date, lines) {
  const line_items = lines.map(([category_id, description, quantity, unit_cost]) => ({
    line_item_id: nextLineIdSeed++, category_id, description, quantity, unit_cost,
    line_total: round2(quantity * unit_cost),
  }));
  return {
    estimate_id: id,
    estimate_number: `EST-${id}`,
    title,
    client_id: clientId,
    created_by: createdBy,
    created_at: date,
    status,
    line_items,
    total_amount: round2(line_items.reduce((s, li) => s + li.line_total, 0)),
  };
}

// ---------------------------------------------------------------------
// API layer – swap each body for a fetch() call to Flask
// ---------------------------------------------------------------------
const api = {
  // TODO(backend): GET /api/estimates
  async list() { return estimates; },

  // TODO(backend): POST /api/estimates   body: { client_id, title, status, line_items:[...] }
  async create(payload) {
    const id = nextEstimateId++;
    const record = {
      estimate_id: id,
      estimate_number: `EST-${id}`,
      created_by: CURRENT_USER.user_id,
      created_at: todayISO(),
      ...payload,
    };
    estimates.unshift(record);
    return record;
  },

  // TODO(backend): PUT /api/estimates/<id>
  async update(id, payload) {
    const i = estimates.findIndex(e => e.estimate_id === id);
    estimates[i] = { ...estimates[i], ...payload };
    return estimates[i];
  },

  // TODO(backend): PATCH /api/estimates/<id>/status   body: { status }
  async setStatus(id, status) { return api.update(id, { status }); },

  // TODO(backend): DELETE /api/estimates/<id>   (drafts only)
  async remove(id) { estimates = estimates.filter(e => e.estimate_id !== id); },

  // TODO(backend): POST /api/estimates/<id>/convert
  //   body: { name, project_manager_id, budget_amount, start_date, due_date }
  //   server creates Project (client_id + estimate_id carried over) and sets estimate status = Converted
  async convert(id, projectData) {
    const project_id = 2000 + id - 1000;
    await api.update(id, { status: "Converted", project_id });
    return { project_id, project_number: `PRJ-${project_id}`, ...projectData };
  },
};

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const money = (n) => Number(n || 0).toLocaleString("en-US", { style: "currency", currency: "USD" });
const moneyShort = (n) => Number(n || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
function round2(n) { return Math.round((Number(n) + Number.EPSILON) * 100) / 100; }
function todayISO() { return new Date().toISOString().slice(0, 10); }
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function formatDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
}
const clientName = (id) => { const c = clients.find(c => c.client_id === id); return c ? `${c.contact_first_name} ${c.contact_last_name}` : "—"; };
const userName = (id) => { const u = users.find(u => u.user_id === id); return u ? `${u.first_name} ${u.last_name}` : "—"; };
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

  $("#estimatesBody").innerHTML = rows.map(e => `
    <tr>
      <td class="est-number">${escapeHtml(e.estimate_number)}</td>
      <td class="job-title">${escapeHtml(e.title)}</td>
      <td>${escapeHtml(clientName(e.client_id))}</td>
      <td>${escapeHtml(userName(e.created_by))}</td>
      <td class="nowrap">${formatDate(e.created_at)}</td>
      <td><span class="badge badge-${e.status.toLowerCase()}">${e.status}</span></td>
      <td class="num">${money(e.total_amount)}</td>
      <td>
        <div class="row-actions">
          <button class="btn btn-outline btn-sm" data-action="open" data-id="${e.estimate_id}">
            ${e.status === "Draft" ? "Edit" : "View"}
          </button>
          ${e.status === "Approved"
            ? `<button class="btn btn-primary btn-sm" data-action="convert" data-id="${e.estimate_id}">Convert</button>`
            : ""}
        </div>
      </td>
    </tr>`).join("");

  $("#emptyState").hidden = rows.length > 0;
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
    ? `<span class="badge badge-${e.status.toLowerCase()}">${e.status}</span> &nbsp;Created ${formatDate(e.created_at)} by ${escapeHtml(userName(e.created_by))}`
    : "Add a client, job title, and at least one line item.";

  fillSelect($("#estClient"), clients, "client_id", c => `${c.contact_first_name} ${c.contact_last_name}`, "Select a client…");
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
      <button type="button" class="btn btn-ghost" data-close>Cancel</button>
      <button type="button" class="btn btn-outline" data-save="Draft">Save as Draft</button>
      <button type="button" class="btn btn-primary" data-save="Sent">Save &amp; Send</button>`,
    Draft: `
      <button type="button" class="btn btn-danger" data-delete>Delete Draft</button>
      <span class="spacer"></span>
      <button type="button" class="btn btn-ghost" data-close>Cancel</button>
      <button type="button" class="btn btn-outline" data-save="Draft">Save Draft</button>
      <button type="button" class="btn btn-primary" data-save="Sent">Save &amp; Send</button>`,
    Sent: `
      <button type="button" class="btn btn-danger" data-status="Rejected">Mark Rejected</button>
      <span class="spacer"></span>
      <button type="button" class="btn btn-ghost" data-close>Close</button>
      <button type="button" class="btn btn-outline" data-save="Sent">Save Changes</button>
      <button type="button" class="btn btn-primary" data-status="Approved">Mark Approved</button>`,
    Approved: `
      <button type="button" class="btn btn-ghost" data-close>Close</button>
      <button type="button" class="btn btn-primary" data-convert>Convert to Project</button>`,
    Rejected: `
      <button type="button" class="btn btn-ghost" data-close>Close</button>
      <button type="button" class="btn btn-outline" data-status="Draft">Reopen as Draft</button>`,
    Converted: `
      <span class="modal-sub" style="margin-right:auto">Converted to project ${e && e.project_id ? "PRJ-" + e.project_id : ""}</span>
      <button type="button" class="btn btn-ghost" data-close>Close</button>`,
  };
  f.innerHTML = buttons[status];
}

function addLineRow(li = {}) {
  const tr = document.createElement("tr");
  const dis = readOnly ? "disabled" : "";
  tr.innerHTML = `
    <td><select class="input select li-cat" ${dis}>
      <option value="">Category…</option>
      ${costCategories.map(c => `<option value="${c.category_id}">${escapeHtml(c.name)}</option>`).join("")}
    </select></td>
    <td><input class="input li-desc" type="text" placeholder="Description" value="${escapeHtml(li.description ?? "")}" ${dis}></td>
    <td><input class="input li-qty" type="number" min="0" step="any" value="${li.quantity ?? 1}" ${dis}></td>
    <td><input class="input li-cost" type="number" min="0" step="0.01" value="${li.unit_cost ?? 0}" ${dis}></td>
    <td class="line-total">$0.00</td>
    <td>${readOnly ? "" : `<button type="button" class="icon-btn remove-line" aria-label="Remove line">×</button>`}</td>`;
  tr.querySelector(".li-cat").value = li.category_id ?? "";
  $("#lineItemsBody").appendChild(tr);
}

// Auto-calculation (A3): line_total = quantity × unit_cost, total = Σ line_total
function recalc() {
  let total = 0, count = 0;
  document.querySelectorAll("#lineItemsBody tr").forEach(tr => {
    const qty = parseFloat(tr.querySelector(".li-qty").value) || 0;
    const cost = parseFloat(tr.querySelector(".li-cost").value) || 0;
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
      line_item_id: nextLineId++,
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
  if (editingId) {
    const e = await api.update(editingId, { ...data, status });
    toast(`${e.estimate_number} saved${status === "Sent" ? " and sent" : ""}`);
  } else {
    const e = await api.create({ ...data, status });
    toast(`${e.estimate_number} created${status === "Sent" ? " and sent" : " as draft"}`);
  }
  closeModal($("#estimateModal"));
  refresh();
}

async function changeStatus(status) {
  const e = await api.setStatus(editingId, status);
  toast(`${e.estimate_number} marked ${status}`);
  closeModal($("#estimateModal"));
  refresh();
}

async function deleteDraft() {
  const e = findEstimate(editingId);
  if (!confirm(`Delete ${e.estimate_number}? This cannot be undone.`)) return;
  await api.remove(editingId);
  toast(`${e.estimate_number} deleted`);
  closeModal($("#estimateModal"));
  refresh();
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
    <strong>Line items:</strong> ${e.line_items.length} (carried over as the project's estimated costs)`;
  $("#projName").value = e.title;
  fillSelect($("#projManager"), users.filter(u => ["admin", "project_manager"].includes(u.role)), "user_id", u => `${u.first_name} ${u.last_name}`, "Select a project manager…");
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

  const project = await api.convert(convertingId, {
    name: name.value.trim(),
    project_manager_id: Number(pm.value),
    budget_amount: round2(parseFloat(budget.value)),
    start_date: start.value || null,
    due_date: due.value,
  });
  closeModal($("#convertModal"));
  refresh();
  toast(`Project ${project.project_number} created from ${findEstimate(convertingId).estimate_number}`);
}

// ---------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  refresh();

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
});
