/* =====================================================================
   Buff Bison – Invoices page
   Covers RTM A5: create invoices, track paid/unpaid, export as PDF.

   Field names follow the ERD (Invoice, InvoiceLineItem, Project, Client)
   so the mock data can be swapped for API calls. Every place that should
   talk to the Flask backend is inside `api` below, marked TODO(backend).

   Status values stored: Draft | Unpaid | Paid
   "Overdue" is not stored – it's shown when an Unpaid invoice is past its due date.
   ===================================================================== */

// ---------------------------------------------------------------------
// Mock data (replace with API responses)
// ---------------------------------------------------------------------
const clients = [
  { client_id: 1, contact_first_name: "Sarah",   contact_last_name: "Johnson" },
  { client_id: 2, contact_first_name: "Michael", contact_last_name: "Thompson" },
  { client_id: 3, contact_first_name: "Emily",   contact_last_name: "Davis" },
  { client_id: 4, contact_first_name: "Robert",  contact_last_name: "Garcia" },
];

const projects = [
  { project_id: 1, name: "Riverstone Kitchen Remodel",   client_id: 1 },
  { project_id: 2, name: "Sugar Land Roof Replacement",  client_id: 2 },
  { project_id: 3, name: "Memorial Bathroom Renovation", client_id: 3 },
  { project_id: 4, name: "Katy Home Addition",           client_id: 4 },
];

let nextLineId = 1;

let invoices = [
  inv(1040, 1, "Paid",   "2026-08-20", "2026-09-19", "2026-09-10", [["Deposit – 30% of contract", 1, 15000]]),
  inv(1041, 4, "Paid",   "2026-08-28", "2026-09-27", "2026-09-20", [["Foundation pour", 1, 14000], ["Site prep and grading", 1, 8000]]),
  inv(1042, 2, "Paid",   "2026-09-15", "2026-10-15", "2026-10-27", [["Tear-off and disposal", 1, 3800], ["Shingle installation – first half", 1, 6000]]),
  inv(1043, 4, "Paid",   "2026-09-30", "2026-10-30", "2026-10-20", [["Rough plumbing and electrical", 1, 14600]]),
  inv(1044, 3, "Paid",   "2026-10-01", "2026-10-31", "2026-10-08", [["Deposit – design and planning", 1, 2500]]),
  inv(1045, 1, "Unpaid", "2026-10-10", "2026-11-09", null,         [["Cabinet installation – progress billing", 1, 9500], ["Countertop templating", 1, 3000]]),
  inv(1046, 4, "Unpaid", "2026-09-15", "2026-10-15", null,         [["Framing labor (hours)", 75, 90], ["Lumber delivery", 1, 1500]]),
  inv(1047, 2, "Unpaid", "2026-10-20", "2026-11-19", null,         [["Final roof inspection and cleanup", 1, 4000]]),
  inv(1048, 3, "Draft",  "2026-10-28", "2026-11-27", null,         [["Design consultation", 1, 1000], ["Demo – bathroom fixtures", 1, 1500]]),
];

let nextInvoiceId = 1049;

function inv(id, projectId, status, issue, due, paidAt, lines) {
  const line_items = lines.map(([description, quantity, unit_price]) => ({
    invoice_line_item_id: nextLineId++, description, quantity, unit_price,
    line_total: round2(quantity * unit_price),
  }));
  return {
    invoice_id: id,
    invoice_number: `INV-${id}`,
    project_id: projectId,
    issue_date: issue,
    due_date: due,
    paid_at: paidAt,
    status,
    line_items,
    total_amount: round2(line_items.reduce((s, li) => s + li.line_total, 0)),
  };
}

// ---------------------------------------------------------------------
// API layer – swap each body for a fetch() call to Flask
// ---------------------------------------------------------------------
const api = {
  // TODO(backend): GET /api/invoices
  async list() { return invoices; },

  // TODO(backend): POST /api/invoices   body: { project_id, issue_date, due_date, status, line_items:[...] }
  async create(payload) {
    const id = nextInvoiceId++;
    const record = { invoice_id: id, invoice_number: `INV-${id}`, paid_at: null, ...payload };
    invoices.unshift(record);
    return record;
  },

  // TODO(backend): PUT /api/invoices/<id>   (Draft and Unpaid only)
  async update(id, payload) {
    const i = invoices.findIndex(x => x.invoice_id === id);
    invoices[i] = { ...invoices[i], ...payload };
    return invoices[i];
  },

  // TODO(backend): PATCH /api/invoices/<id>/status   body: { status }
  //   server sets paid_at when status becomes Paid, clears it otherwise
  async setStatus(id, status) {
    return api.update(id, { status, paid_at: status === "Paid" ? todayISO() : null });
  },

  // TODO(backend): DELETE /api/invoices/<id>   (Draft only)
  async remove(id) { invoices = invoices.filter(x => x.invoice_id !== id); },

  // TODO(backend): GET /api/invoices/<id>/pdf  could later return a server-made PDF.
  //   For now the browser's "Save as PDF" print option creates it.
};

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
  const c = p && clients.find(c => c.client_id === p.client_id);
  return c ? `${c.contact_first_name} ${c.contact_last_name}` : "—";
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
    const price = parseFloat(tr.querySelector(".li-price").value) || 0;
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
      invoice_line_item_id: nextLineId++,
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
  let x;
  if (editingId) {
    const wasDraft = findInvoice(editingId).status === "Draft";
    x = await api.update(editingId, { ...data, status });
    toast(`${x.invoice_number} ${wasDraft && status === "Unpaid" ? "sent" : "saved"}`);
  } else {
    x = await api.create({ ...data, status });
    toast(`${x.invoice_number} ${status === "Draft" ? "saved as draft" : "created and sent"}`);
  }
  closeModal($("#invoiceModal"));
  refresh();
}

async function changeStatus(id, status) {
  const x = await api.setStatus(id, status);
  toast(`${x.invoice_number} marked ${status.toLowerCase()}`);
  closeModal($("#invoiceModal"));
  refresh();
}

async function deleteDraft() {
  const x = findInvoice(editingId);
  if (!confirm(`Delete ${x.invoice_number}? This cannot be undone.`)) return;
  await api.remove(editingId);
  toast(`${x.invoice_number} deleted`);
  closeModal($("#invoiceModal"));
  refresh();
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
document.addEventListener("DOMContentLoaded", () => {
  refresh();

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
});
