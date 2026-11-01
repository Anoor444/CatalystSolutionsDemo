/*
 * schedule.js
 * Buff Bison Construction Management System - Schedule page (A11: tasks and due dates)
 *
 * How this file works:
 *   1. Read the demo data Flask placed in the page (<script id="sch-data">).
 *   2. Keep the tasks in a simple JavaScript array.
 *   3. "render" functions redraw the cards, table, and deadline list.
 *   4. Add / edit / complete / delete changes the array, then re-renders.
 *
 * IMPORTANT: Changes live only in memory. Reloading the page resets everything.
 * When MySQL is connected, saveTask(), markTaskComplete() and deleteTask()
 * will call Flask routes instead of only changing the array.
 */

// ---------- 1. Load data from Flask ----------
const scheduleData = JSON.parse(document.getElementById("sch-data").textContent);

const projects = scheduleData.projects;      // [{ id, name }]
const statuses = scheduleData.statuses;      // ["Not Started", "In Progress", "Completed"]
const priorities = scheduleData.priorities;  // ["Low", "Medium", "High"]
let tasks = scheduleData.tasks;              // [{ id, project_id, name, description, assigned_to, start_date, due_date, priority, status }]

// Demo-only id counter. A real database will create ids automatically.
let nextTaskId = tasks.reduce((highest, task) => Math.max(highest, task.id), 0) + 1;

// Id of the task being edited. null = adding a new task.
let editingTaskId = null;

// How many days ahead the "Upcoming Deadlines" list looks.
const UPCOMING_DAYS = 14;

// ---------- 2. Page elements ----------
const projectSelect = document.getElementById("sch-project-select");
const statusFilter = document.getElementById("sch-status-filter");
const sortOrder = document.getElementById("sch-sort-order");
const taskBody = document.getElementById("sch-task-body");
const deadlineList = document.getElementById("sch-deadline-list");
const messageArea = document.getElementById("sch-message");

const taskDialog = document.getElementById("sch-task-dialog");
const taskForm = document.getElementById("sch-task-form");
const dialogTitle = document.getElementById("sch-dialog-title");
const formErrors = document.getElementById("sch-form-errors");
const formName = document.getElementById("sch-form-name");
const formProject = document.getElementById("sch-form-project");
const formDescription = document.getElementById("sch-form-description");
const formAssigned = document.getElementById("sch-form-assigned");
const formStart = document.getElementById("sch-form-start");
const formDue = document.getElementById("sch-form-due");
const formPriority = document.getElementById("sch-form-priority");
const formStatus = document.getElementById("sch-form-status");

// ---------- 3. Date helpers ----------
// Dates are stored as "YYYY-MM-DD" text (the same format MySQL DATE columns use).

// Turns "2026-10-26" into a Date at local midnight (avoids time-zone "off by one day" bugs).
function parseLocalDate(isoDate) {
    const [year, month, day] = isoDate.split("-").map(Number);
    return new Date(year, month - 1, day);
}

// Today's date at midnight, taken from the user's computer every time it is called.
function getToday() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

// Whole days from today until the date (negative = in the past).
function daysFromToday(isoDate) {
    const millisecondsPerDay = 24 * 60 * 60 * 1000;
    return Math.round((parseLocalDate(isoDate) - getToday()) / millisecondsPerDay);
}

// "2026-10-26" -> "Oct 26, 2026". Empty dates show a dash.
function formatDate(isoDate) {
    if (!isoDate) {
        return "—";
    }
    return parseLocalDate(isoDate).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// OVERDUE = not completed AND the due date is before today.
function isOverdue(task) {
    return task.status !== "Completed" && daysFromToday(task.due_date) < 0;
}

// ---------- 4. Other helpers ----------
function getProjectName(projectId) {
    const project = projects.find((p) => p.id === projectId);
    return project ? project.name : "Unknown project";
}

// Creates an element with text. textContent (not innerHTML) keeps user-typed text safe.
function createElementWithText(tagName, text, className) {
    const element = document.createElement(tagName);
    element.textContent = text;
    if (className) {
        element.className = className;
    }
    return element;
}

// Turns a word into a CSS-friendly name, e.g. "High" -> "high"
function toClassName(text) {
    return text.toLowerCase().replace(/\s+/g, "-");
}

// Matches each task status to an existing badge style in style.css
// (.status.pending, .status.progress, .status.completed).
const STATUS_BADGE_CLASSES = {
    "Not Started": "pending",
    "In Progress": "progress",
    "Completed": "completed",
};

// Tasks for the project chosen in the dropdown ("all" = every project).
function getTasksForSelectedProject() {
    if (projectSelect.value === "all") {
        return tasks;
    }
    const projectId = Number(projectSelect.value);
    return tasks.filter((task) => task.project_id === projectId);
}

function showMessage(text) {
    messageArea.textContent = text;
}

// ---------- 5. Render (draw) the page ----------

function renderOptions() {
    projects.forEach((project) => {
        projectSelect.appendChild(new Option(project.name, project.id));
        formProject.appendChild(new Option(project.name, project.id));
    });
    priorities.forEach((priority) => formPriority.appendChild(new Option(priority, priority)));
    statuses.forEach((status) => formStatus.appendChild(new Option(status, status)));
}

// Summary cards count the tasks for the selected project (the status filter does not change them).
function renderSummaryCards() {
    const projectTasks = getTasksForSelectedProject();
    const completedCount = projectTasks.filter((t) => t.status === "Completed").length;
    const inProgressCount = projectTasks.filter((t) => t.status === "In Progress").length;
    const overdueCount = projectTasks.filter(isOverdue).length;

    document.getElementById("sch-total-count").textContent = projectTasks.length;
    document.getElementById("sch-completed-count").textContent = completedCount;
    document.getElementById("sch-progress-count").textContent = inProgressCount;
    document.getElementById("sch-overdue-count").textContent = overdueCount;
    document.getElementById("sch-overdue-card").classList.toggle("summary--over", overdueCount > 0);
}

function renderTaskTable() {
    taskBody.replaceChildren();

    // Step 1: filter by status
    let visibleTasks = getTasksForSelectedProject().filter((task) => {
        if (statusFilter.value === "all") {
            return true;
        }
        if (statusFilter.value === "overdue") {
            return isOverdue(task);
        }
        return task.status === statusFilter.value;
    });

    // Step 2: sort by due date. "YYYY-MM-DD" text sorts in date order.
    visibleTasks = visibleTasks.slice().sort((a, b) => {
        const comparison = a.due_date.localeCompare(b.due_date);
        return sortOrder.value === "soonest" ? comparison : -comparison;
    });

    if (visibleTasks.length === 0) {
        const emptyRow = document.createElement("tr");
        emptyRow.className = "empty-row";
        const emptyCell = createElementWithText("td", "No tasks match the selected project and filter.");
        emptyCell.colSpan = 8;
        emptyRow.appendChild(emptyCell);
        taskBody.appendChild(emptyRow);
        return;
    }

    visibleTasks.forEach((task) => {
        const overdue = isOverdue(task);
        const row = document.createElement("tr");
        if (overdue) {
            row.className = "row-over";
        }
        if (task.status === "Completed") {
            row.classList.add("sch-row--done");
        }

        // Task name (+ description underneath in smaller text)
        const nameCell = document.createElement("td");
        nameCell.appendChild(createElementWithText("span", task.name, "sch-task-name"));
        if (task.description) {
            nameCell.appendChild(createElementWithText("span", task.description, "sch-task-desc"));
        }
        row.appendChild(nameCell);

        row.appendChild(createElementWithText("td", getProjectName(task.project_id)));
        row.appendChild(createElementWithText("td", task.assigned_to || "Unassigned"));
        row.appendChild(createElementWithText("td", formatDate(task.start_date)));

        // Due date + an "Overdue" label (symbol + words, not color alone)
        const dueCell = document.createElement("td");
        dueCell.appendChild(createElementWithText("span", formatDate(task.due_date)));
        if (overdue) {
            dueCell.appendChild(createElementWithText("span", "⚠ Overdue", "status over sch-overdue-tag"));
        }
        row.appendChild(dueCell);

        const priorityCell = document.createElement("td");
        priorityCell.appendChild(createElementWithText("span", task.priority, "sch-priority sch-priority--" + toClassName(task.priority)));
        row.appendChild(priorityCell);

        const statusCell = document.createElement("td");
        statusCell.appendChild(createElementWithText("span", task.status, "status " + STATUS_BADGE_CLASSES[task.status]));
        row.appendChild(statusCell);

        // Action buttons
        const actionsCell = document.createElement("td");
        actionsCell.className = "actions-cell";
        if (task.status !== "Completed") {
            const completeButton = createElementWithText("button", "✓ Complete", "btn-outline btn-small btn-success");
            completeButton.type = "button";
            completeButton.setAttribute("aria-label", "Mark complete: " + task.name);
            completeButton.addEventListener("click", () => markTaskComplete(task.id));
            actionsCell.appendChild(completeButton);
        }
        const editButton = createElementWithText("button", "Edit", "btn-outline btn-small");
        editButton.type = "button";
        editButton.setAttribute("aria-label", "Edit task: " + task.name);
        editButton.addEventListener("click", () => openTaskForm(task));

        const deleteButton = createElementWithText("button", "Delete", "btn-outline btn-small btn-danger");
        deleteButton.type = "button";
        deleteButton.setAttribute("aria-label", "Delete task: " + task.name);
        deleteButton.addEventListener("click", () => deleteTask(task.id));

        actionsCell.append(editButton, deleteButton);
        row.appendChild(actionsCell);
        taskBody.appendChild(row);
    });
}

// Describes how far away a due date is, e.g. "Due today", "In 3 days", "2 days overdue".
function describeDueDate(isoDate) {
    const days = daysFromToday(isoDate);
    if (days < 0) {
        const daysLate = Math.abs(days);
        return daysLate + (daysLate === 1 ? " day overdue" : " days overdue");
    }
    if (days === 0) {
        return "Due today";
    }
    if (days === 1) {
        return "Due tomorrow";
    }
    return "In " + days + " days";
}

// Upcoming Deadlines: unfinished tasks that are overdue or due within UPCOMING_DAYS.
function renderDeadlineList() {
    deadlineList.replaceChildren();

    const upcomingTasks = getTasksForSelectedProject()
        .filter((task) => task.status !== "Completed" && daysFromToday(task.due_date) <= UPCOMING_DAYS)
        .sort((a, b) => a.due_date.localeCompare(b.due_date));

    if (upcomingTasks.length === 0) {
        deadlineList.appendChild(createElementWithText("p", "No deadlines in the next " + UPCOMING_DAYS + " days.", "empty-text"));
        return;
    }

    const list = document.createElement("ul");
    list.className = "sch-deadlines";
    upcomingTasks.forEach((task) => {
        const item = document.createElement("li");
        item.className = "sch-deadline";
        if (isOverdue(task)) {
            item.classList.add("sch-deadline--overdue");
        } else if (daysFromToday(task.due_date) <= 2) {
            item.classList.add("sch-deadline--soon");
        }

        // Left side: date box
        const dateBox = document.createElement("div");
        dateBox.className = "sch-deadline-date";
        const dueDate = parseLocalDate(task.due_date);
        dateBox.appendChild(createElementWithText("span", dueDate.toLocaleDateString("en-US", { month: "short" }), "sch-deadline-month"));
        dateBox.appendChild(createElementWithText("span", String(dueDate.getDate()), "sch-deadline-day"));

        // Right side: task details
        const details = document.createElement("div");
        details.appendChild(createElementWithText("span", task.name, "sch-deadline-name"));
        details.appendChild(createElementWithText("span", getProjectName(task.project_id), "sch-deadline-project"));
        const whenText = (isOverdue(task) ? "⚠ " : "") + describeDueDate(task.due_date) + " · " + task.priority + " priority";
        details.appendChild(createElementWithText("span", whenText, "sch-deadline-when"));

        item.append(dateBox, details);
        list.appendChild(item);
    });
    deadlineList.appendChild(list);
}

// Redraws everything.
function renderPage() {
    renderSummaryCards();
    renderTaskTable();
    renderDeadlineList();
}

// ---------- 6. Add / Edit task form ----------

// Opens the form. Pass a task to edit it, or nothing to add a new one.
function openTaskForm(task) {
    taskForm.reset();
    clearFormErrors();

    if (task) {
        editingTaskId = task.id;
        dialogTitle.textContent = "Edit Task";
        formName.value = task.name;
        formProject.value = task.project_id;
        formDescription.value = task.description || "";
        formAssigned.value = task.assigned_to || "";
        formStart.value = task.start_date || "";
        formDue.value = task.due_date;
        formPriority.value = task.priority;
        formStatus.value = task.status;
    } else {
        editingTaskId = null;
        dialogTitle.textContent = "Add Task";
        // Pre-select the project chosen on the page (if one is chosen).
        formProject.value = projectSelect.value === "all" ? "" : projectSelect.value;
        formPriority.value = "Medium";
        formStatus.value = "Not Started";
    }

    taskDialog.showModal();
    formName.focus();
}

function closeTaskForm() {
    taskDialog.close();
    editingTaskId = null;
}

function clearFormErrors() {
    formErrors.replaceChildren();
    taskForm.querySelectorAll("[aria-invalid]").forEach((field) => field.removeAttribute("aria-invalid"));
}

// Checks the form. Returns a list of error messages (empty list = valid).
function validateTaskForm() {
    const errors = [];

    function addError(field, message) {
        errors.push(message);
        field.setAttribute("aria-invalid", "true");
    }

    if (formName.value.trim() === "") {
        addError(formName, "Please enter a task name.");
    }
    if (!formProject.value) {
        addError(formProject, "Please select a project.");
    }
    if (!formDue.value) {
        addError(formDue, "Please enter a due date.");
    }
    // If a start date is given, the due date cannot be earlier than it.
    // "YYYY-MM-DD" text compares correctly with < and >.
    if (formStart.value && formDue.value && formDue.value < formStart.value) {
        addError(formDue, "The due date cannot be earlier than the start date.");
    }

    return errors;
}

function showFormErrors(errors) {
    const heading = createElementWithText("p", "Please fix the following:", "form-errors-title");
    const list = document.createElement("ul");
    errors.forEach((message) => list.appendChild(createElementWithText("li", message)));
    formErrors.replaceChildren(heading, list);
}

// Runs when "Save" is clicked.
function saveTask(event) {
    event.preventDefault();   // stop the browser from reloading the page
    clearFormErrors();

    const errors = validateTaskForm();
    if (errors.length > 0) {
        showFormErrors(errors);
        taskForm.querySelector("[aria-invalid='true']").focus();
        return;
    }

    const taskValues = {
        project_id: Number(formProject.value),
        name: formName.value.trim(),
        description: formDescription.value.trim(),
        assigned_to: formAssigned.value.trim(),
        start_date: formStart.value || null,
        due_date: formDue.value,
        priority: formPriority.value,
        status: formStatus.value,
    };

    // FUTURE MySQL: send taskValues to a Flask route (e.g. POST /api/tasks) here,
    // and only update the array after the server confirms it was saved.
    if (editingTaskId === null) {
        taskValues.id = nextTaskId;
        nextTaskId += 1;
        tasks.push(taskValues);
        showMessage("Task added: " + taskValues.name + ".");
    } else {
        const existing = tasks.find((t) => t.id === editingTaskId);
        Object.assign(existing, taskValues);
        showMessage("Task updated: " + existing.name + ".");
    }

    // If the page shows a different project, switch to "All Projects" so the task is visible.
    if (projectSelect.value !== "all" && Number(projectSelect.value) !== taskValues.project_id) {
        projectSelect.value = "all";
    }
    closeTaskForm();
    renderPage();
}

function markTaskComplete(taskId) {
    const task = tasks.find((t) => t.id === taskId);
    // FUTURE MySQL: call a Flask route (e.g. POST /api/tasks/<id>/complete) here.
    task.status = "Completed";
    showMessage("Marked complete: " + task.name + ".");
    renderPage();
}

function deleteTask(taskId) {
    const task = tasks.find((t) => t.id === taskId);
    // confirm() shows plain text, so the task name is displayed safely.
    if (!task || !window.confirm('Delete the task "' + task.name + '"?')) {
        return;
    }
    // FUTURE MySQL: call a Flask route (e.g. DELETE /api/tasks/<id>) here.
    tasks = tasks.filter((t) => t.id !== taskId);
    showMessage("Task deleted: " + task.name + ".");
    renderPage();
}

// ---------- 7. Connect controls and start the page ----------
projectSelect.addEventListener("change", () => {
    showMessage("");
    renderPage();
});
statusFilter.addEventListener("change", renderTaskTable);
sortOrder.addEventListener("change", renderTaskTable);
document.getElementById("sch-add-task-btn").addEventListener("click", () => openTaskForm(null));
document.getElementById("sch-cancel-btn").addEventListener("click", closeTaskForm);
taskForm.addEventListener("submit", saveTask);

renderOptions();
renderPage();
