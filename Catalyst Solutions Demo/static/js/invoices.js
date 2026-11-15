/* =====================================================================
   Buff Bison – Invoices page
   Covers RTM A5: create invoices, track paid/unpaid, export as PDF.

   Data comes from the Flask JSON API in api.py (via apiRequest in
   api-client.js). The server re-checks everything and recalculates totals.

   Status values stored: Draft | Unpaid | Paid
   "Overdue" is not stored – it's shown when an Unpaid invoice is past its due date.
   ===================================================================== */

// Filled from the server when the page loads (see loadData)
let projects = [];   // { project_id, name, client_name }
let invoices = [];

// ---------------------------------------------------------------------
// API calls (endpoints are in api.py)
// ---------------------------------------------------------------------
const api = {
  lookups:   ()            => apiRequest("GET", "/api/lookups"),
  list:      ()            => apiRequest("GET", "/api/invoices"),
  create:    (payload)     => apiRequest("POST", "/api/invoices", payload),
  update:    (id, payload) => apiRequest("PUT", `/api/invoices/${id}`, payload),
  setStatus: (id, status)  => apiRequest("PATCH", `/api/invoices/${id}/status`, { status }),
  remove:    (id)          => apiRequest("DELETE", `/api/invoices/${id}`),
  // PDF: the browser's "Save as PDF" print option creates it (see openPdf).
};

async function loadData() {
  const [lookups, list] = await Promise.all([api.lookups(), api.list()]);
  projects = lookups.projects;
  invoices = list;
}

async function reloadInvoices() {
  invoices = await api.list();
  refresh();
}

// Runs an API action; shows the server's message if it fails.
async function attempt(action, errorBox) {
  try {
    await action();
    return true;
  } catch (err) {
    if (errorBox && !errorBox.parentElement.closest("[hidden]")) { errorBox.textContent = err.message; errorBox.hidden = false; }
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
function isoLocal(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function todayISO() { return isoLocal(new Date()); }
function addDaysISO(iso, days) {
  const [y, m, d] = iso.split("-").map(Number);
  return isoLocal(new Date(y, m - 1, d + days));
}
function formatDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" });
}
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const findInvoice = (id) => invoices.find(x => x.invoice_id === id);
const findProject = (id) => projects.find(p => p.project_id === id);
function clientNameForProject(projectId) {
  const p = findProject(projectId);
  return p ? p.client_name : "—";
}
const projectName = (id) => (findProject(id) || {}).name || "—";

// Overdue = Unpaid and past the due date
const isOverdue = (x) => x.status === "Unpaid" && x.due_date < todayISO();
const displayStatus = (x) => (isOverdue(x) ? "Overdue" : x.status);

// Reuses badge colors from style.css / estimates.css
const STATUS_CLASS = { Draft: "draft", Unpaid: "progress", Overdue: "hold", Paid: "completed" };
const statusBadge = (label) => `<span class="status ${STATUS_CLASS[label]}">${label}</span>`;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

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
  const unpaid = invoices.filter(x => x.status === "Unpaid");
  const overdue = unpaid.filter(isOverdue);
  const paid = invoices.filter(x => x.status === "Paid");
  const drafts = invoices.filter(x => x.status === "Draft");
  const sum = (arr) => arr.reduce((s, x) => s + x.total_amount, 0);

  $("#statUnpaid").textContent = moneyShort(sum(unpaid));
  $("#statUnpaidCount").textContent = plural(unpaid.length, "invoice");
  $("#statOverdue").textContent = moneyShort(sum(overdue));
  $("#statOverdueCount").textContent = plural(overdue.length, "invoice");
  $("#statPaid").textContent = moneyShort(sum(paid));
  $("#statPaidCount").textContent = plural(paid.length, "invoice");
  $("#statTotal").textContent = invoices.length;
  $("#statDraftCount").textContent = `${plural(drafts.length, "draft")}`;
}

function renderTable() {
  const q = $("#searchInput").value.trim().toLowerCase();
  const filter = $("#statusFilter").value;

  const rows = invoices.filter(x => {
    if (filter !== "All" && displayStatus(x) !== filter) return false;
    if (!q) return true;
    return [x.invoice_number, projectName(x.project_id), clientNameForProject(x.project_id)]
      .some(v => v.toLowerCase().includes(q));
  }).sort((a, b) => b.invoice_id - a.invoice_id);   // newest first

  if (rows.length === 0) {
    $("#invoicesBody").innerHTML = `<tr class="empty-row"><td colspan="8">No invoices match your search.</td></tr>`;
    return;
  }

  $("#invoicesBody").innerHTML = rows.map(x => {
    const label = displayStatus(x);
    return `
    <tr>
      <td>${escapeHtml(x.invoice_number)}</td>
      <td>${escapeHtml(projectName(x.project_id))}</td>
      <td>${escapeHtml(clientNameForProject(x.project_id))}</td>
      <td>${formatDate(x.issue_date)}</td>
      <td class="${label === "Overdue" ? "overdue-date" : ""}">${formatDate(x.due_date)}</td>
      <td>${statusBadge(label)}</td>
      <td class="num">${money(x.total_amount)}</td>
      <td>
        <div class="row-actions">
          <button type="button" class="btn-outline" data-action="open" data-id="${x.invoice_id}">
            ${x.status === "Draft" ? "Edit" : "View"}
          </button>
          ${x.status === "Unpaid"
            ? `<button type="button" class="btn btn-sm" data-action="paid" data-id="${x.invoice_id}">Mark Paid</button>`
            : ""}
          ${x.status !== "Draft"
            ? `<button type="button" class="btn-outline" data-action="pdf" data-id="${x.invoice_id}">PDF</button>`
            : ""}
        </div>
      </td>
    </tr>`;
  }).join("");
}

function refresh() { renderStats(); renderTable(); }

// ---------------------------------------------------------------------
// Invoice modal (create / edit / view)
// ---------------------------------------------------------------------
let editingId = null;
let readOnly = false;

function openModal(el) { el.hidden = false; document.body.style.overflow = "hidden"; }
function closeModal(el) { el.hidden = true; document.body.style.overflow = ""; }

function openInvoice(id = null) {
  editingId = id;
  const x = id ? findInvoice(id) : null;
  readOnly = !!x && x.status === "Paid";

  $("#invoiceModalTitle").textContent = x ? x.invoice_number : "New Invoice";
  $("#invoiceModalSub").innerHTML = x
    ? `${statusBadge(displayStatus(x))} &nbsp;${escapeHtml(projectName(x.project_id))}` +
      (x.paid_at ? ` &nbsp;·&nbsp; Paid ${formatDate(x.paid_at)}` : "")
    : "Choose a project, set the dates, and add at least one line item.";

  $("#invProject").innerHTML = `<option value="">Select a project…</option>` +
    projects.map(p => `<option value="${p.project_id}">${escapeHtml(p.name)}</option>`).join("");
  $("#invProject").value = x ? x.project_id : "";
  $("#invClient").value = x ? clientNameForProject(x.project_id) : "";

  const today = todayISO();
  $("#invIssue").value = x ? x.issue_date : today;
  $("#invDue").value = x ? x.due_date : addDaysISO(today, 30);

  $("#lineItemsBody").innerHTML = "";
  const lines = x ? x.line_items : [{ description: "", quantity: 1, unit_price: 0 }];
  lines.forEach(addLineRow);

  ["#invProject", "#invIssue", "#invDue"].forEach(s => ($(s).disabled = readOnly));
  $("#addLineBtn").hidden = readOnly;
  $("#formError").hidden = true;
  document.querySelectorAll("#invoiceForm .invalid").forEach(el => el.classList.remove("invalid"));

  renderFooter(x);
  recalc();
  openModal($("#invoiceModal"));
  if (!readOnly) $("#invProject").focus();
}

function renderFooter(x) {
  const status = x ? x.status : "New";
  const buttons = {
    New: `
      <button type="button" class="btn-outline" data-close>Cancel</button>
      <button type="button" class="btn-outline" data-save="Draft">Save as Draft</button>
      <button type="button" class="btn" data-save="Unpaid">Save &amp; Send</button>`,
    Draft: `
      <button type="button" class="btn-danger" data-delete>Delete Draft</button>
      <span class="spacer"></span>
      <button type="button" class="btn-outline" data-close>Cancel</button>
      <button type="button" class="btn-outline" data-save="Draft">Save Draft</button>
      <button type="button" class="btn" data-save="Unpaid">Save &amp; Send</button>`,
    Unpaid: `
      <button type="button" class="btn-outline" data-pdf>PDF</button>
      <span class="spacer"></span>
      <button type="button" class="btn-outline" data-close>Close</button>
      <button type="button" class="btn-outline" data-save="Unpaid">Save Changes</button>
      <button type="button" class="btn" data-status="Paid">Mark Paid</button>`,
    Paid: `
      <button type="button" class="btn-outline" data-status="Unpaid">Mark Unpaid</button>
      <span class="spacer"></span>
      <button type="button" class="btn-outline" data-close>Close</button>
      <button type="button" class="btn" data-pdf>PDF</button>`,
  };
  $("#invoiceFooter").innerHTML = buttons[status];
}

function addLineRow(li = {}) {
  const tr = document.createElement("tr");
  const dis = readOnly ? "disabled" : "";
  tr.innerHTML = `
    <td><input class="li-desc" type="text" placeholder="Description" value="${escapeHtml(li.description ?? "")}" ${dis}></td>
    <td><input class="li-qty" type="number" min="0" step="any" value="${li.quantity ?? 1}" ${dis}></td>
    <td><input class="li-price" type="number" min="0" step="0.01" value="${li.unit_price ?? 0}" ${dis}></td>
    <td class="line-total">$0.00</td>
    <td>${readOnly ? "" : `<button type="button" class="remove-line" aria-label="Remove line">×</button>`}</td>`;
  $("#lineItemsBody").appendChild(tr);
}

// line_total = quantity × unit_price; total = sum of line totals
function recalc() {
  let total = 0, count = 0;
  document.querySelectorAll("#lineItemsBody tr").forEach(tr => {
    const qty = parseFloat(tr.querySelector(".li-qty").value) || 0;
    const price = round2(parseFloat(tr.querySelector(".li-price").value) || 0);  // cents, same as the server
    const lt = round2(qty * price);
    tr.querySelector(".line-total").textContent = money(lt);
    total += lt;
    count++;
  });
  $("#lineCount").textContent = count;
  $("#invoiceTotal").textContent = money(round2(total));
}

function collectForm() {
  const errors = [];
  document.querySelectorAll("#invoiceForm .invalid").forEach(el => el.classList.remove("invalid"));

  const project_id = Number($("#invProject").value);
  const issue_date = $("#invIssue").value;
  const due_date = $("#invDue").value;
  if (!project_id) { errors.push("Select a project."); $("#invProject").classList.add("invalid"); }
  if (!issue_date) { errors.push("Choose an issue date."); $("#invIssue").classList.add("invalid"); }
  if (!due_date) { errors.push("Choose a due date."); $("#invDue").classList.add("invalid"); }
  else if (issue_date && due_date < issue_date) { errors.push("Due date can't be before the issue date."); $("#invDue").classList.add("invalid"); }

  const line_items = [];
  document.querySelectorAll("#lineItemsBody tr").forEach(tr => {
    const desc = tr.querySelector(".li-desc"), qty = tr.querySelector(".li-qty"), price = tr.querySelector(".li-price");
    const q = parseFloat(qty.value), p = parseFloat(price.value);
    let bad = false;
    if (!desc.value.trim()) { desc.classList.add("invalid"); bad = true; }
    if (!(q > 0)) { qty.classList.add("invalid"); bad = true; }
    if (!(p >= 0) || price.value === "") { price.classList.add("invalid"); bad = true; }
    if (bad) return;
    line_items.push({
      description: desc.value.trim(),
      quantity: q,
      unit_price: round2(p),
      line_total: round2(q * p),
    });
  });

  const rowCount = document.querySelectorAll("#lineItemsBody tr").length;
  if (rowCount === 0) errors.push("Add at least one line item.");
  else if (line_items.length !== rowCount) errors.push("Fix the highlighted line items (description, quantity above 0, and unit price are required).");

  const err = $("#formError");
  err.hidden = errors.length === 0;
  err.textContent = errors.join(" ");
  if (errors.length) return null;

  return {
    project_id, issue_date, due_date, line_items,
    total_amount: round2(line_items.reduce((s, li) => s + li.line_total, 0)),
  };
}

async function saveInvoice(status) {
  const data = collectForm();
  if (!data) return;
  // The server works out line totals and the invoice total itself.
  const payload = {
    project_id: data.project_id,
    issue_date: data.issue_date,
    due_date: data.due_date,
    status,
    line_items: data.line_items.map(({ description, quantity, unit_price }) => ({ description, quantity, unit_price })),
  };
  const wasDraft = editingId && findInvoice(editingId).status === "Draft";
  let x;
  const ok = await attempt(async () => {
    x = editingId ? await api.update(editingId, payload) : await api.create(payload);
  }, $("#formError"));
  if (!ok) return;
  toast(editingId
    ? `${x.invoice_number} ${wasDraft && status === "Unpaid" ? "sent" : "saved"}`
    : `${x.invoice_number} ${status === "Draft" ? "saved as draft" : "created and sent"}`);
  closeModal($("#invoiceModal"));
  await reloadInvoices();
}

async function changeStatus(id, status) {
  let x;
  const ok = await attempt(async () => { x = await api.setStatus(id, status); }, $("#formError"));
  if (!ok) return;
  toast(`${x.invoice_number} marked ${status.toLowerCase()}`);
  closeModal($("#invoiceModal"));
  await reloadInvoices();
}

async function deleteDraft() {
  const x = findInvoice(editingId);
  if (!confirm(`Delete ${x.invoice_number}? This cannot be undone.`)) return;
  const ok = await attempt(() => api.remove(editingId), $("#formError"));
  if (!ok) return;
  toast(`${x.invoice_number} deleted`);
  closeModal($("#invoiceModal"));
  await reloadInvoices();
}

// ---------------------------------------------------------------------
// PDF / print preview
// ---------------------------------------------------------------------
function openPdf(id) {
  const x = findInvoice(id);
  const logo = document.body.dataset.logo;
  const label = displayStatus(x);

  $("#invoiceDoc").innerHTML = `
    <div class="doc-top">
      <div>
        ${logo ? `<img src="${escapeHtml(logo)}" alt="Buff Bison Construction" class="doc-logo">` : ""}
        <p style="margin-top:8px;font-weight:bold">Buff Bison Construction</p>
      </div>
      <div class="doc-title">
        <h2>INVOICE</h2>
        <p>${escapeHtml(x.invoice_number)}</p>
        ${x.status === "Paid" ? `<span class="paid-stamp">PAID</span>` : ""}
      </div>
    </div>

    <div class="doc-meta">
      <div><small>Bill To</small>${escapeHtml(clientNameForProject(x.project_id))}</div>
      <div><small>Project</small>${escapeHtml(projectName(x.project_id))}</div>
      <div><small>Issue Date</small>${formatDate(x.issue_date)}</div>
      <div><small>${x.status === "Paid" ? "Paid On" : "Due Date"}</small>${formatDate(x.status === "Paid" ? x.paid_at : x.due_date)}</div>
    </div>

    <table class="doc-table">
      <thead>
        <tr><th>Description</th><th class="num">Qty</th><th class="num">Unit Price</th><th class="num">Amount</th></tr>
      </thead>
      <tbody>
        ${x.line_items.map(li => `
          <tr>
            <td>${escapeHtml(li.description)}</td>
            <td class="num">${li.quantity}</td>
            <td class="num">${money(li.unit_price)}</td>
            <td class="num">${money(li.line_total)}</td>
          </tr>`).join("")}
      </tbody>
    </table>

    <div class="totals doc-total">
      <div class="totals-row grand"><span>${x.status === "Paid" ? "Total Paid" : "Amount Due"}</span><span>${money(x.total_amount)}</span></div>
    </div>

    <div class="doc-footer">
      ${label === "Overdue" ? "This invoice is past due. " : ""}Thank you for your business.
    </div>`;

  closeModal($("#invoiceModal"));
  openModal($("#pdfModal"));
}

// ---------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  $("#invoicesBody").innerHTML = `<tr class="empty-row"><td colspan="8">Loading invoices…</td></tr>`;
  try {
    await loadData();
    refresh();
  } catch (err) {
    $("#invoicesBody").innerHTML = `<tr class="empty-row"><td colspan="8">${escapeHtml(err.message)}</td></tr>`;
    if (err.status === 401) setTimeout(() => (window.location.href = "/login"), 1500);
  }

  $("#newInvoiceBtn").addEventListener("click", () => openInvoice());
  $("#searchInput").addEventListener("input", renderTable);
  $("#statusFilter").addEventListener("change", renderTable);

  $("#invoicesBody").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-action]");
    if (!btn) return;
    const id = Number(btn.dataset.id);
    if (btn.dataset.action === "open") openInvoice(id);
    if (btn.dataset.action === "paid") changeStatus(id, "Paid");
    if (btn.dataset.action === "pdf") openPdf(id);
  });

  // Client fills in automatically from the chosen project
  $("#invProject").addEventListener("change", () => {
    $("#invClient").value = $("#invProject").value ? clientNameForProject(Number($("#invProject").value)) : "";
  });

  $("#addLineBtn").addEventListener("click", () => {
    addLineRow({ description: "", quantity: 1, unit_price: 0 });
    recalc();
    const rows = document.querySelectorAll("#lineItemsBody tr");
    rows[rows.length - 1].querySelector(".li-desc").focus();
  });

  $("#invoiceForm").addEventListener("input", (ev) => ev.target.classList.remove("invalid"));
  $("#invoiceForm").addEventListener("change", (ev) => ev.target.classList.remove("invalid"));
  $("#lineItemsBody").addEventListener("input", () => { $("#formError").hidden = true; recalc(); });
  $("#lineItemsBody").addEventListener("click", (ev) => {
    if (ev.target.closest(".remove-line")) { ev.target.closest("tr").remove(); recalc(); }
  });

  $("#invoiceFooter").addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.save) saveInvoice(b.dataset.save);
    else if (b.dataset.status) changeStatus(editingId, b.dataset.status);
    else if (b.hasAttribute("data-delete")) deleteDraft();
    else if (b.hasAttribute("data-pdf")) openPdf(editingId);
  });
  $("#invoiceForm").addEventListener("submit", (ev) => ev.preventDefault());

  $("#printBtn").addEventListener("click", () => window.print());

  document.querySelectorAll(".modal-backdrop").forEach(bd => {
    bd.addEventListener("click", (ev) => {
      if (ev.target === bd || ev.target.closest("[data-close]")) closeModal(bd);
    });
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") document.querySelectorAll(".modal-backdrop:not([hidden])").forEach(closeModal);
  });

  // Links from a project page: /invoices?open=<invoice id> or /invoices?new=1&project=<project id>
  const params = new URLSearchParams(window.location.search);
  const openId = Number(params.get("open"));
  const projectId = Number(params.get("project"));
  if (openId && findInvoice(openId)) {
    openInvoice(openId);
  } else if (params.get("new")) {
    openInvoice();
    if (findProject(projectId)) {
      $("#invProject").value = projectId;
      $("#invClient").value = clientNameForProject(projectId);
    }
  }
  if (params.has("open") || params.has("new")) history.replaceState(null, "", window.location.pathname);
});
