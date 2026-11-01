/*
 * job_costs.js
 * Buff Bison Construction Management System - Job Costs page (A6: estimated vs. actual)
 *
 * How this file works:
 *   1. Read the demo data Flask placed in the page (<script id="jc-data">).
 *   2. Keep that data in simple JavaScript arrays.
 *   3. "render" functions redraw the cards and tables from those arrays.
 *   4. Adding / editing / deleting an expense changes the array, then re-renders.
 *
 * IMPORTANT: Changes live only in memory. Reloading the page resets everything.
 * When MySQL is connected, saveExpense() and deleteExpense() will call Flask
 * routes instead of only changing the array.
 */

// ---------- 1. Load data from Flask ----------
const jobCostData = JSON.parse(document.getElementById("jc-data").textContent);

const projects = jobCostData.projects;       // [{ id, name }]
const categories = jobCostData.categories;   // ["Materials", "Labor", ...]
const estimates = jobCostData.estimates;     // [{ project_id, category, estimated_amount }]
let expenses = jobCostData.expenses;         // [{ id, project_id, expense_date, description, category, amount, receipt_name }]

// Demo-only id counter. A real database will create ids automatically.
let nextExpenseId = expenses.reduce((highest, expense) => Math.max(highest, expense.id), 0) + 1;

// When editing, this holds the id of the expense being edited. null = adding a new one.
let editingExpenseId = null;

// ---------- 2. Page elements ----------
const projectSelect = document.getElementById("jc-project-select");
const breakdownBody = document.getElementById("jc-breakdown-body");
const breakdownFoot = document.getElementById("jc-breakdown-foot");
const expenseBody = document.getElementById("jc-expense-body");
const messageArea = document.getElementById("jc-message");

const expenseDialog = document.getElementById("jc-expense-dialog");
const expenseForm = document.getElementById("jc-expense-form");
const dialogTitle = document.getElementById("jc-dialog-title");
const formErrors = document.getElementById("jc-form-errors");
const formProject = document.getElementById("jc-form-project");
const formDate = document.getElementById("jc-form-date");
const formDescription = document.getElementById("jc-form-description");
const formCategory = document.getElementById("jc-form-category");
const formAmount = document.getElementById("jc-form-amount");
const formReceipt = document.getElementById("jc-form-receipt");
const currentReceiptText = document.getElementById("jc-current-receipt");

// ---------- 3. Small helper functions ----------

// Formats a number as US currency, e.g. 1234.5 -> "$1,234.50" and -50 -> "-$50.00"
const currencyFormatter = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
function formatCurrency(amount) {
    return currencyFormatter.format(amount);
}

// Variance gets a "+" sign when positive so "over budget" is obvious, e.g. "+$1,250.00"
function formatVariance(variance) {
    return (variance > 0 ? "+" : "") + formatCurrency(variance);
}

// Rounds to 2 decimal places so adding many prices does not create values like 0.30000000000000004
function roundToCents(amount) {
    return Math.round(amount * 100) / 100;
}

// Turns "2026-10-26" into "Oct 26, 2026". Built from parts so the date never shifts a day due to time zones.
function formatDate(isoDate) {
    const [year, month, day] = isoDate.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function getProjectName(projectId) {
    const project = projects.find((p) => p.id === projectId);
    return project ? project.name : "Unknown project";
}

function getSelectedProjectId() {
    return Number(projectSelect.value);
}

// Creates an element with text. Using textContent (not innerHTML) keeps user-typed text safe.
function createElementWithText(tagName, text, className) {
    const element = document.createElement(tagName);
    element.textContent = text;
    if (className) {
        element.className = className;
    }
    return element;
}

// ---------- 4. Calculations ----------

// Estimated cost of ONE category for a project (from the estimate rows).
function getEstimatedAmount(projectId, category) {
    const row = estimates.find((e) => e.project_id === projectId && e.category === category);
    return row ? row.estimated_amount : 0;
}

// Actual cost of ONE category = the sum of that project's expenses in that category.
function getActualAmount(projectId, category) {
    const total = expenses
        .filter((e) => e.project_id === projectId && e.category === category)
        .reduce((sum, e) => sum + e.amount, 0);
    return roundToCents(total);
}

// Status from the variance (Actual − Estimated):
//   variance > 0  -> Over Budget
//   variance = 0  -> On Budget
//   variance < 0  -> Under Budget
// Each status has a symbol + words so it does not depend on color alone.
function getBudgetStatus(variance) {
    if (variance > 0) {
        return { label: "Over Budget", symbol: "▲", cssClass: "over" };
    }
    if (variance === 0) {
        return { label: "On Budget", symbol: "●", cssClass: "on" };
    }
    return { label: "Under Budget", symbol: "▼", cssClass: "under" };
}

// Builds a status badge, e.g. <span class="status over">▲ Over Budget</span>
function createStatusBadge(status) {
    const badge = document.createElement("span");
    badge.className = "status " + status.cssClass;
    const symbol = createElementWithText("span", status.symbol + " ");
    symbol.setAttribute("aria-hidden", "true");   // screen readers read only the words
    badge.appendChild(symbol);
    badge.appendChild(document.createTextNode(status.label));
    return badge;
}

// Totals for the whole project. Category totals are added up, so the
// summary cards ALWAYS match the cost breakdown table.
function calculateProjectTotals(projectId) {
    let estimatedTotal = 0;
    let actualTotal = 0;
    categories.forEach((category) => {
        estimatedTotal += getEstimatedAmount(projectId, category);
        actualTotal += getActualAmount(projectId, category);
    });
    estimatedTotal = roundToCents(estimatedTotal);
    actualTotal = roundToCents(actualTotal);

    return {
        estimatedTotal: estimatedTotal,
        actualTotal: actualTotal,
        remaining: roundToCents(estimatedTotal - actualTotal),   // Remaining Budget = Estimated − Actual
        variance: roundToCents(actualTotal - estimatedTotal),    // Cost Variance = Actual − Estimated
    };
}

// ---------- 5. Render (draw) the page ----------

function renderProjectOptions() {
    projects.forEach((project) => {
        projectSelect.appendChild(new Option(project.name, project.id));
        formProject.appendChild(new Option(project.name, project.id));
    });
    formCategory.appendChild(new Option("Select a category", ""));
    categories.forEach((category) => {
        formCategory.appendChild(new Option(category, category));
    });
}

function renderSummaryCards(projectId) {
    const totals = calculateProjectTotals(projectId);
    const status = getBudgetStatus(totals.variance);
    const expenseCount = expenses.filter((e) => e.project_id === projectId).length;

    document.getElementById("jc-estimated-total").textContent = formatCurrency(totals.estimatedTotal);
    document.getElementById("jc-actual-total").textContent = formatCurrency(totals.actualTotal);
    document.getElementById("jc-expense-count").textContent =
        expenseCount + (expenseCount === 1 ? " expense recorded" : " expenses recorded");

    document.getElementById("jc-remaining-total").textContent = formatCurrency(totals.remaining);
    document.getElementById("jc-remaining-note").textContent = totals.remaining < 0
        ? "Over budget by " + formatCurrency(Math.abs(totals.remaining))
        : "Estimated − Actual";

    const statusText = document.getElementById("jc-status-text");
    statusText.textContent = status.symbol + " " + status.label;
    document.getElementById("jc-variance-note").textContent = "Variance: " + formatVariance(totals.variance);

    // Highlight cards when over budget (the text above also says so - not color alone).
    const isOver = totals.variance > 0;
    document.getElementById("jc-remaining-card").classList.toggle("summary--over", isOver);
    const statusCard = document.getElementById("jc-status-card");
    statusCard.classList.remove("summary--over", "summary--on", "summary--under");
    statusCard.classList.add("summary--" + status.cssClass);
}

function renderBreakdownTable(projectId) {
    breakdownBody.replaceChildren();   // clear old rows

    categories.forEach((category) => {
        const estimated = getEstimatedAmount(projectId, category);
        const actual = getActualAmount(projectId, category);
        const variance = roundToCents(actual - estimated);
        const status = getBudgetStatus(variance);

        const row = document.createElement("tr");
        if (variance > 0) {
            row.className = "row-over";
        }
        row.appendChild(createElementWithText("td", category));
        row.appendChild(createElementWithText("td", formatCurrency(estimated), "num"));
        row.appendChild(createElementWithText("td", formatCurrency(actual), "num"));
        row.appendChild(createElementWithText("td", formatVariance(variance), "num"));
        const statusCell = document.createElement("td");
        statusCell.appendChild(createStatusBadge(status));
        row.appendChild(statusCell);
        breakdownBody.appendChild(row);
    });

    // Totals row - uses the same calculation as the summary cards.
    const totals = calculateProjectTotals(projectId);
    const totalRow = document.createElement("tr");
    totalRow.className = "total-row";
    totalRow.appendChild(createElementWithText("td", "Total"));
    totalRow.appendChild(createElementWithText("td", formatCurrency(totals.estimatedTotal), "num"));
    totalRow.appendChild(createElementWithText("td", formatCurrency(totals.actualTotal), "num"));
    totalRow.appendChild(createElementWithText("td", formatVariance(totals.variance), "num"));
    const totalStatusCell = document.createElement("td");
    totalStatusCell.appendChild(createStatusBadge(getBudgetStatus(totals.variance)));
    totalRow.appendChild(totalStatusCell);
    breakdownFoot.replaceChildren(totalRow);
}

function renderExpenseTable(projectId) {
    expenseBody.replaceChildren();

    // Newest expenses first. ISO dates ("YYYY-MM-DD") sort correctly as text.
    const projectExpenses = expenses
        .filter((e) => e.project_id === projectId)
        .sort((a, b) => b.expense_date.localeCompare(a.expense_date));

    if (projectExpenses.length === 0) {
        const emptyRow = document.createElement("tr");
        emptyRow.className = "empty-row";
        const emptyCell = createElementWithText("td", "No expenses recorded for this project yet.");
        emptyCell.colSpan = 7;
        emptyRow.appendChild(emptyCell);
        expenseBody.appendChild(emptyRow);
        return;
    }

    projectExpenses.forEach((expense) => {
        const row = document.createElement("tr");
        row.appendChild(createElementWithText("td", formatDate(expense.expense_date)));
        row.appendChild(createElementWithText("td", expense.description));
        row.appendChild(createElementWithText("td", expense.category));
        row.appendChild(createElementWithText("td", getProjectName(expense.project_id)));
        row.appendChild(createElementWithText("td", formatCurrency(expense.amount), "num"));

        // Receipt: show the file name, and clearly say it is NOT actually uploaded.
        const receiptCell = document.createElement("td");
        if (expense.receipt_name) {
            receiptCell.appendChild(createElementWithText("span", expense.receipt_name, "jc-receipt-name"));
            receiptCell.appendChild(createElementWithText("span", "Not uploaded (demo)", "muted-tag"));
        } else {
            receiptCell.appendChild(createElementWithText("span", "None", "muted"));
        }
        row.appendChild(receiptCell);

        // Edit and Delete buttons. aria-label tells screen-reader users WHICH expense.
        const actionsCell = document.createElement("td");
        actionsCell.className = "actions-cell";
        const editButton = createElementWithText("button", "Edit", "btn-outline btn-small");
        editButton.type = "button";
        editButton.setAttribute("aria-label", "Edit expense: " + expense.description);
        editButton.addEventListener("click", () => openExpenseForm(expense));

        const deleteButton = createElementWithText("button", "Delete", "btn-outline btn-small btn-danger");
        deleteButton.type = "button";
        deleteButton.setAttribute("aria-label", "Delete expense: " + expense.description);
        deleteButton.addEventListener("click", () => deleteExpense(expense.id));

        actionsCell.append(editButton, deleteButton);
        row.appendChild(actionsCell);
        expenseBody.appendChild(row);
    });
}

// Redraws everything for the selected project.
function renderPage() {
    const projectId = getSelectedProjectId();
    renderSummaryCards(projectId);
    renderBreakdownTable(projectId);
    renderExpenseTable(projectId);
}

function showMessage(text) {
    messageArea.textContent = text;
}

// ---------- 6. Add / Edit expense form ----------

// Opens the form. Pass an expense to edit it, or nothing to add a new one.
function openExpenseForm(expense) {
    expenseForm.reset();
    clearFormErrors();

    if (expense) {
        editingExpenseId = expense.id;
        dialogTitle.textContent = "Edit Expense";
        formProject.value = expense.project_id;
        formDate.value = expense.expense_date;
        formDescription.value = expense.description;
        formCategory.value = expense.category;
        formAmount.value = expense.amount.toFixed(2);
        currentReceiptText.textContent = expense.receipt_name
            ? " Current receipt name: " + expense.receipt_name + " (choose a new file to replace it)."
            : "";
    } else {
        editingExpenseId = null;
        dialogTitle.textContent = "Add Expense";
        formProject.value = getSelectedProjectId();
        formDate.value = new Date().toLocaleDateString("en-CA");   // today's date as YYYY-MM-DD
        currentReceiptText.textContent = "";
    }

    expenseDialog.showModal();
    formDescription.focus();
}

function closeExpenseForm() {
    expenseDialog.close();
    editingExpenseId = null;
}

function clearFormErrors() {
    formErrors.replaceChildren();
    expenseForm.querySelectorAll("[aria-invalid]").forEach((field) => field.removeAttribute("aria-invalid"));
}

// Checks the form. Returns a list of error messages (empty list = valid).
function validateExpenseForm() {
    const errors = [];

    function addError(field, message) {
        errors.push(message);
        field.setAttribute("aria-invalid", "true");
    }

    if (!formProject.value) {
        addError(formProject, "Please choose a project.");
    }
    if (!formDate.value) {
        addError(formDate, "Please enter the expense date.");
    }
    if (formDescription.value.trim() === "") {
        addError(formDescription, "Please enter an expense description.");
    }
    if (!categories.includes(formCategory.value)) {
        addError(formCategory, "Please choose a cost category.");
    }
    // Amount must be a nonnegative number with at most 2 decimals, e.g. 250 or 1250.75.
    // (Number inputs give an empty value when the text is not a valid number.)
    const amountText = formAmount.value.trim();
    if (!/^\d+(\.\d{1,2})?$/.test(amountText)) {
        addError(formAmount, "Amount must be a number of $0.00 or more (up to 2 decimal places).");
    }

    return errors;
}

function showFormErrors(errors) {
    const heading = createElementWithText("p", "Please fix the following:", "form-errors-title");
    const list = document.createElement("ul");
    errors.forEach((message) => list.appendChild(createElementWithText("li", message)));
    formErrors.replaceChildren(heading, list);
}

// Runs when "Save Expense" is clicked.
function saveExpense(event) {
    event.preventDefault();   // stop the browser from reloading the page
    clearFormErrors();

    const errors = validateExpenseForm();
    if (errors.length > 0) {
        showFormErrors(errors);
        expenseForm.querySelector("[aria-invalid='true']").focus();
        return;
    }

    // Only the file NAME is kept. Nothing is uploaded in this demo.
    const chosenFile = formReceipt.files[0];

    const expenseValues = {
        project_id: Number(formProject.value),
        expense_date: formDate.value,
        description: formDescription.value.trim(),
        category: formCategory.value,
        amount: roundToCents(Number(formAmount.value)),
    };

    // FUTURE MySQL: send expenseValues to a Flask route (e.g. POST /api/expenses) here,
    // and only update the array after the server confirms it was saved.
    if (editingExpenseId === null) {
        expenseValues.id = nextExpenseId;
        nextExpenseId += 1;
        expenseValues.receipt_name = chosenFile ? chosenFile.name : null;
        expenses.push(expenseValues);
        showMessage("Expense added: " + expenseValues.description + " (" + formatCurrency(expenseValues.amount) + ").");
    } else {
        const existing = expenses.find((e) => e.id === editingExpenseId);
        Object.assign(existing, expenseValues);
        if (chosenFile) {
            existing.receipt_name = chosenFile.name;
        }
        showMessage("Expense updated: " + existing.description + ".");
    }

    // Switch the page to the expense's project so the user sees the change.
    projectSelect.value = expenseValues.project_id;
    closeExpenseForm();
    renderPage();
}

function deleteExpense(expenseId) {
    const expense = expenses.find((e) => e.id === expenseId);
    // confirm() shows plain text, so the description is displayed safely.
    if (!expense || !window.confirm('Delete the expense "' + expense.description + '"?')) {
        return;
    }
    // FUTURE MySQL: call a Flask route (e.g. DELETE /api/expenses/<id>) here.
    expenses = expenses.filter((e) => e.id !== expenseId);
    showMessage("Expense deleted: " + expense.description + ".");
    renderPage();
}

// ---------- 7. Connect buttons and start the page ----------
projectSelect.addEventListener("change", () => {
    showMessage("");
    renderPage();
});
document.getElementById("jc-add-expense-btn").addEventListener("click", () => openExpenseForm(null));
document.getElementById("jc-cancel-btn").addEventListener("click", closeExpenseForm);
expenseForm.addEventListener("submit", saveExpense);

renderProjectOptions();
renderPage();
