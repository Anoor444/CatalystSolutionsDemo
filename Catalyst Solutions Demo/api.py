"""
JSON API used by the Estimates and Invoices pages (their JavaScript calls these).

Every endpoint:
- requires a logged-in employee (returns 401/403 JSON otherwise),
- is CSRF-protected for POST/PUT/PATCH/DELETE (the page sends the token in an
  X-CSRF-Token header; see protect_state_changing_requests in app.py),
- re-checks every value on the server and recalculates totals; nothing the
  browser sends is trusted as-is.

Business rules (which statuses can change to which, what can be edited or
deleted) live in database.py.
"""
from datetime import date
from functools import wraps

from flask import Blueprint, jsonify, request, session

import database
from database import RuleError

api = Blueprint("api", __name__, url_prefix="/api")

MAX_TEXT = 200
MAX_LINE_ITEMS = 100
MAX_AMOUNT = 100_000_000


# ---------------------------------------------------------------------
# Access control and errors
# ---------------------------------------------------------------------
def employee_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Please log in again."), 401
        if session.get("role") != "employee":
            return jsonify(error="You don't have access to this."), 403
        return view(*args, **kwargs)
    return wrapped


@api.errorhandler(RuleError)
def handle_rule_error(error):
    return jsonify(error=error.message), error.status_code


class ValidationError(Exception):
    def __init__(self, messages):
        super().__init__("; ".join(messages))
        self.messages = messages


@api.errorhandler(ValidationError)
def handle_validation_error(error):
    return jsonify(error=" ".join(error.messages), errors=error.messages), 400


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError(["Request body must be JSON."])
    return data


# ---------------------------------------------------------------------
# Field checks
# ---------------------------------------------------------------------
def text(data, key, label, errors, required=True):
    value = str(data.get(key) or "").strip()
    if required and not value:
        errors.append(f"{label} is required.")
    elif len(value) > MAX_TEXT:
        errors.append(f"{label} must be {MAX_TEXT} characters or fewer.")
    return value


def number(value, label, errors, minimum=0, allow_equal=True):
    try:
        result = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be a number.")
        return 0
    if result != result or result > MAX_AMOUNT:  # NaN or absurdly large
        errors.append(f"{label} is not a valid amount.")
    elif result < minimum or (not allow_equal and result == minimum):
        errors.append(f"{label} must be {'more than' if not allow_equal else 'at least'} {minimum}.")
    return round(result, 2)


def iso_date(data, key, label, errors, required=True):
    value = str(data.get(key) or "").strip()
    if not value:
        if required:
            errors.append(f"{label} is required.")
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} is not a valid date.")
    return value


def record_id(data, key, label, errors, table, column):
    try:
        value = int(data.get(key))
    except (TypeError, ValueError):
        errors.append(f"Choose a {label}.")
        return None
    exists = database.get_db().execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (value,)).fetchone()
    if not exists:
        errors.append(f"That {label} doesn't exist.")
    return value


def line_items(data, errors, price_key, with_category):
    raw = data.get("line_items")
    if not isinstance(raw, list) or not raw:
        errors.append("Add at least one line item.")
        return []
    if len(raw) > MAX_LINE_ITEMS:
        errors.append(f"An invoice or estimate can have at most {MAX_LINE_ITEMS} line items.")
        return []
    category_ids = {row[0] for row in database.get_db().execute("SELECT category_id FROM cost_categories")}
    clean = []
    for n, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            errors.append(f"Line {n} is not valid.")
            continue
        row_errors = []
        line = {
            "description": text(item, "description", f"Line {n} description", row_errors),
            "quantity": number(item.get("quantity"), f"Line {n} quantity", row_errors, 0, allow_equal=False),
            price_key: number(item.get(price_key), f"Line {n} price", row_errors),
        }
        if with_category:
            try:
                line["category_id"] = int(item.get("category_id"))
                if line["category_id"] not in category_ids:
                    raise ValueError
            except (TypeError, ValueError):
                row_errors.append(f"Line {n} needs a category.")
        errors.extend(row_errors)
        clean.append(line)
    return clean


def check(errors):
    if errors:
        raise ValidationError(errors)


# ---------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------
@api.get("/lookups")
@employee_required
def lookups():
    return jsonify(database.get_lookups())


# ---------------------------------------------------------------------
# Estimates
# ---------------------------------------------------------------------
def estimate_payload(allowed_statuses):
    data, errors = body(), []
    clean = {
        "title": text(data, "title", "Job title", errors),
        "client_id": record_id(data, "client_id", "client", errors, "clients", "client_id"),
        "status": data.get("status"),
        "line_items": line_items(data, errors, "unit_cost", with_category=True),
    }
    if clean["status"] not in allowed_statuses:
        errors.append("Status must be Draft or Sent.")
    check(errors)
    return clean


@api.get("/estimates")
@employee_required
def list_estimates():
    return jsonify(database.get_estimates())


@api.post("/estimates")
@employee_required
def create_estimate():
    estimate = database.create_estimate(estimate_payload(("Draft", "Sent")), session["user_id"])
    return jsonify(estimate), 201


@api.put("/estimates/<int:estimate_id>")
@employee_required
def update_estimate(estimate_id):
    return jsonify(database.update_estimate(estimate_id, estimate_payload(("Draft", "Sent"))))


@api.patch("/estimates/<int:estimate_id>/status")
@employee_required
def estimate_status(estimate_id):
    new_status = body().get("status")
    if new_status not in ("Approved", "Rejected", "Draft"):
        raise ValidationError(["Status must be Approved, Rejected or Draft."])
    return jsonify(database.set_estimate_status(estimate_id, new_status))


@api.delete("/estimates/<int:estimate_id>")
@employee_required
def delete_estimate(estimate_id):
    database.delete_estimate(estimate_id)
    return "", 204


@api.post("/estimates/<int:estimate_id>/convert")
@employee_required
def convert_estimate(estimate_id):
    data, errors = body(), []
    clean = {
        "name": text(data, "name", "Project name", errors),
        "project_manager_id": None,
        "budget_amount": number(data.get("budget_amount"), "Budget", errors),
        "start_date": iso_date(data, "start_date", "Start date", errors, required=False),
        "due_date": iso_date(data, "due_date", "Due date", errors),
    }
    manager = data.get("project_manager_id")
    row = database.get_db().execute(
        "SELECT id FROM users WHERE id = ? AND role = 'employee'", (manager,)
    ).fetchone()
    if row is None:
        errors.append("Choose a project manager.")
    else:
        clean["project_manager_id"] = row["id"]
    if clean["start_date"] and clean["due_date"] and clean["due_date"] < clean["start_date"]:
        errors.append("Due date must be after the start date.")
    check(errors)
    return jsonify(database.convert_estimate(estimate_id, clean)), 201


# ---------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------
def invoice_payload():
    data, errors = body(), []
    clean = {
        "project_id": record_id(data, "project_id", "project", errors, "projects", "project_id"),
        "issue_date": iso_date(data, "issue_date", "Issue date", errors),
        "due_date": iso_date(data, "due_date", "Due date", errors),
        "status": data.get("status"),
        "line_items": line_items(data, errors, "unit_price", with_category=False),
    }
    if clean["status"] not in ("Draft", "Unpaid"):
        errors.append("Status must be Draft or Unpaid.")
    if clean["issue_date"] and clean["due_date"] and clean["due_date"] < clean["issue_date"]:
        errors.append("Due date can't be before the issue date.")
    check(errors)
    return clean


@api.get("/invoices")
@employee_required
def list_invoices():
    return jsonify(database.get_invoices())


@api.post("/invoices")
@employee_required
def create_invoice():
    return jsonify(database.create_invoice(invoice_payload())), 201


@api.put("/invoices/<int:invoice_id>")
@employee_required
def update_invoice(invoice_id):
    return jsonify(database.update_invoice(invoice_id, invoice_payload()))


@api.patch("/invoices/<int:invoice_id>/status")
@employee_required
def invoice_status(invoice_id):
    new_status = body().get("status")
    if new_status not in ("Paid", "Unpaid"):
        raise ValidationError(["Status must be Paid or Unpaid."])
    return jsonify(database.set_invoice_status(invoice_id, new_status))


@api.delete("/invoices/<int:invoice_id>")
@employee_required
def delete_invoice(invoice_id):
    database.delete_invoice(invoice_id)
    return "", 204


# ---------------------------------------------------------------------
# Tasks (Schedule page, RTM A11)
# ---------------------------------------------------------------------
def task_payload():
    data, errors = body(), []
    clean = {
        "name": text(data, "name", "Task name", errors),
        "project_id": record_id(data, "project_id", "project", errors, "projects", "project_id"),
        "description": str(data.get("description") or "").strip(),
        "assigned_to": str(data.get("assigned_to") or "").strip(),
        "start_date": iso_date(data, "start_date", "Start date", errors, required=False),
        "due_date": iso_date(data, "due_date", "Due date", errors),
        "priority": data.get("priority"),
        "status": data.get("status"),
    }
    if len(clean["name"]) > 150:
        errors.append("Task name must be 150 characters or fewer.")
    if len(clean["assigned_to"]) > 100:
        errors.append("Assigned to must be 100 characters or fewer.")
    if len(clean["description"]) > 500:
        errors.append("Description must be 500 characters or fewer.")
    if clean["priority"] not in database.TASK_PRIORITIES:
        errors.append("Choose a priority.")
    if clean["status"] not in database.TASK_STATUSES:
        errors.append("Choose a status.")
    if clean["start_date"] and clean["due_date"] and clean["due_date"] < clean["start_date"]:
        errors.append("The due date cannot be earlier than the start date.")
    check(errors)
    return clean


@api.get("/tasks")
@employee_required
def list_tasks():
    return jsonify(database.get_tasks())


@api.post("/tasks")
@employee_required
def create_task():
    return jsonify(database.create_task(task_payload())), 201


@api.put("/tasks/<int:task_id>")
@employee_required
def update_task(task_id):
    return jsonify(database.update_task(task_id, task_payload()))


@api.patch("/tasks/<int:task_id>/status")
@employee_required
def task_status(task_id):
    status = body().get("status")
    if status not in database.TASK_STATUSES:
        raise ValidationError(["Choose a valid status."])
    return jsonify(database.set_task_status(task_id, status))


@api.delete("/tasks/<int:task_id>")
@employee_required
def delete_task(task_id):
    database.delete_task(task_id)
    return "", 204
