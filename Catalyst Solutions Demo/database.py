"""
Database helpers for the Buff Bison Construction Portal.

- One SQLite file (the same one the login system already uses).
- get_db() gives each request its own connection; it closes automatically.
- init_app(app) creates the tables from schema.sql and loads the sample
  data the first time the app runs.
- `flask --app app reset-demo-data` wipes the business tables and reloads
  the sample data (user accounts are kept).

Query functions for each page live at the bottom of this file, so app.py
routes stay short.
"""
import os
import sqlite3

import click
from flask import g

DATABASE_FILE = None  # set by init_app()
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

# Tables cleared by reset-demo-data, children first so foreign keys are happy.
BUSINESS_TABLES = (
    "documents", "photos", "tasks", "subcontractor_invoices", "project_assignments", "project_budget_items",
    "receipts", "invoice_line_items", "invoices", "projects",
    "estimate_line_items", "estimates", "subcontractors", "clients", "cost_categories",
)

PROJECT_STATUSES = ("Planning", "In Progress", "On Hold", "Completed")


# ---------------------------------------------------------------------
# Connection handling
# ---------------------------------------------------------------------
def connect(path=None):
    connection = sqlite3.connect(path or DATABASE_FILE)
    connection.row_factory = sqlite3.Row          # rows behave like dicts: row["name"]
    connection.execute("PRAGMA foreign_keys = ON")  # SQLite needs this to enforce FKs
    return connection


def get_db():
    """Connection for the current request (opened once, reused, closed at the end)."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_app(app, database_file):
    global DATABASE_FILE
    DATABASE_FILE = database_file
    app.teardown_appcontext(close_db)
    app.cli.add_command(reset_demo_data_command)

    with connect() as connection:
        # Step 4 replaced the original (never used) tasks table with a fuller one.
        columns = [row[1] for row in connection.execute("PRAGMA table_info(tasks)")]
        if columns and "priority" not in columns and \
                connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            connection.execute("DROP TABLE tasks")
            columns = []
        tasks_table_is_new = not columns

        # Step 5 rebuilt receipts (it only held placeholder "costs to date" rows) and
        # added project_budget_items. Both are refilled with sample costs below.
        receipt_columns = [row[1] for row in connection.execute("PRAGMA table_info(receipts)")]
        if receipt_columns and "description" not in receipt_columns:
            connection.execute("DROP TABLE receipts")
        costs_are_new = not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'project_budget_items'").fetchone()

        create_tables(connection)

        # Step 6 added contact/status columns to clients and subcontractors.
        # (SQLite can add columns to an existing table; the CHECK lives in schema.sql for new databases.)
        directory_upgraded = False
        for table, new_columns in (
            ("clients", (("company", "TEXT"), ("address", "TEXT"),
                         ("status", "TEXT NOT NULL DEFAULT 'Active'"), ("notes", "TEXT"))),
            ("subcontractors", (("address", "TEXT"), ("license_number", "TEXT"),
                                ("status", "TEXT NOT NULL DEFAULT 'Active'"), ("notes", "TEXT"))),
        ):
            existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for column, definition in new_columns:
                if column not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    directory_upgraded = True

        from seed_data import (load_billing_samples, load_cost_samples, load_directory_samples,
                               load_sample_data, load_task_samples)

        def count(table):
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        if count("projects") == 0:
            load_sample_data(connection)          # brand-new database: everything
        else:
            if count("estimates") == 0 and count("invoices") == 0:
                load_billing_samples(connection)  # database from step 1: add sample estimates/invoices
            if tasks_table_is_new:
                load_task_samples(connection)     # database from before step 4: add sample tasks
            if costs_are_new:
                load_cost_samples(connection)     # database from before step 5: add sample job costs
            if directory_upgraded:
                load_directory_samples(connection)  # database from before step 6: client details, subcontractors

        # Databases created before step 3 stamped the sample projects with their creation time,
        # which would fill "Recent Activity" with 12 "project created" entries. Backdate them once.
        from seed_data import PROJECTS, SAMPLE_PROJECT_CREATED_AT
        names = [p[0] for p in PROJECTS]
        connection.execute(
            f"UPDATE projects SET created_at = ? WHERE description IS NULL "
            f"AND created_at > ? AND name IN ({','.join('?' * len(names))})",
            (SAMPLE_PROJECT_CREATED_AT, SAMPLE_PROJECT_CREATED_AT, *names),
        )


def create_tables(connection):
    with open(SCHEMA_FILE, encoding="utf-8") as schema:
        connection.executescript(schema.read())


@click.command("reset-demo-data")
def reset_demo_data_command():
    """Delete all business data and reload the sample data (keeps user accounts)."""
    from seed_data import load_sample_data

    with connect() as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in BUSINESS_TABLES:
            connection.execute(f"DELETE FROM {table}")
        connection.execute("PRAGMA foreign_keys = ON")
        load_sample_data(connection)
    click.echo("Sample data reloaded.")


# ---------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------
# Actual cost = receipts + subcontractor invoices that were approved or paid.
_PROJECT_SELECT = """
    SELECT p.*,
           c.name  AS client_name,
           u.name  AS manager_name,
           COALESCE(r.total, 0) + COALESCE(s.total, 0) AS actual_cost
    FROM projects p
    JOIN clients c      ON c.client_id = p.client_id
    LEFT JOIN users u   ON u.id = p.project_manager_id
    LEFT JOIN (SELECT project_id, SUM(amount) AS total
               FROM receipts GROUP BY project_id) r
           ON r.project_id = p.project_id
    LEFT JOIN (SELECT pa.project_id, SUM(si.amount) AS total
               FROM subcontractor_invoices si
               JOIN project_assignments pa ON pa.assignment_id = si.assignment_id
               WHERE si.status IN ('Approved', 'Paid')
               GROUP BY pa.project_id) s
           ON s.project_id = p.project_id
"""


def get_projects():
    return get_db().execute(_PROJECT_SELECT + " ORDER BY p.project_id").fetchall()


def get_project(project_id):
    return get_db().execute(_PROJECT_SELECT + " WHERE p.project_id = ?", (project_id,)).fetchone()


def get_project_counts():
    rows = get_db().execute("SELECT status, COUNT(*) AS n FROM projects GROUP BY status").fetchall()
    by_status = {row["status"]: row["n"] for row in rows}
    return {
        "total": sum(by_status.values()),
        "active": by_status.get("In Progress", 0),
        "planning": by_status.get("Planning", 0),
        "on_hold": by_status.get("On Hold", 0),
        "completed": by_status.get("Completed", 0),
    }


def get_project_managers():
    return get_db().execute(
        "SELECT id, name FROM users WHERE role = 'employee' ORDER BY name"
    ).fetchall()


def find_or_create_client(connection, name, email=None, phone=None):
    """Reuse an existing client with the same name (case-insensitive), otherwise add one."""
    row = connection.execute(
        "SELECT client_id FROM clients WHERE lower(name) = lower(?)", (name,)
    ).fetchone()
    if row:
        if email or phone:
            connection.execute(
                "UPDATE clients SET email = COALESCE(?, email), phone = COALESCE(?, phone) WHERE client_id = ?",
                (email or None, phone or None, row["client_id"]),
            )
        return row["client_id"]
    cursor = connection.execute(
        "INSERT INTO clients (name, email, phone) VALUES (?, ?, ?)",
        (name, email or None, phone or None),
    )
    return cursor.lastrowid


def create_project(data):
    """Insert a project from already-validated form data. Returns the new project_id."""
    connection = get_db()
    with connection:  # one transaction: client + project together, or neither
        client_id = find_or_create_client(
            connection, data["client_name"], data.get("client_email"), data.get("client_phone")
        )
        cursor = connection.execute(
            """
            INSERT INTO projects (project_number, name, project_type, description, address,
                                  client_id, project_manager_id, status, budget_amount,
                                  progress_percent, start_date, due_date)
            VALUES ('pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"], data["project_type"], data.get("description") or None, data["address"],
                client_id, data["manager_id"], data["status"], data["budget"],
                100 if data["status"] == "Completed" else 0,
                data.get("start_date") or None, data.get("due_date") or None,
            ),
        )
        project_id = cursor.lastrowid
        connection.execute(
            "UPDATE projects SET project_number = ? WHERE project_id = ?",
            (f"BB-{project_id:04d}", project_id),
        )
    return project_id


# ---------------------------------------------------------------------
# Shared helpers for estimates and invoices
# ---------------------------------------------------------------------
class RuleError(Exception):
    """Raised when a request breaks a business rule (wrong status, missing record...).
    The API turns it into a 400/404/409 JSON error with this message."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _money(value):
    return round(float(value or 0), 2)


def get_lookups():
    """Dropdown data for the Estimates and Invoices pages."""
    db = get_db()
    return {
        "clients": [dict(r) for r in db.execute("SELECT client_id, name FROM clients ORDER BY name")],
        "categories": [dict(r) for r in db.execute(
            "SELECT category_id, name FROM cost_categories WHERE is_active = 1 ORDER BY category_id")],
        "managers": [dict(r) for r in db.execute(
            "SELECT id AS user_id, name FROM users WHERE role = 'employee' ORDER BY name")],
        "projects": [dict(r) for r in db.execute(
            """SELECT p.project_id, p.name, c.name AS client_name
               FROM projects p JOIN clients c ON c.client_id = p.client_id ORDER BY p.name""")],
    }


# ---------------------------------------------------------------------
# Estimates (RTM A3, A4)
# ---------------------------------------------------------------------
ESTIMATE_EDITABLE = ("Draft", "Sent")
# status a user can move an estimate to, from its current status
ESTIMATE_TRANSITIONS = {
    "Sent": ("Approved", "Rejected"),
    "Rejected": ("Draft",),
}


def get_estimates(estimate_id=None):
    db = get_db()
    where, params = ("WHERE e.estimate_id = ?", (estimate_id,)) if estimate_id else ("", ())
    rows = db.execute(
        f"""SELECT e.*, date(e.created_at) AS created_date, c.name AS client_name,
                   u.name AS created_by_name, p.project_id, p.project_number
            FROM estimates e
            JOIN clients c        ON c.client_id = e.client_id
            LEFT JOIN users u     ON u.id = e.created_by
            LEFT JOIN projects p  ON p.estimate_id = e.estimate_id
            {where}
            ORDER BY e.estimate_id DESC""",
        params,
    ).fetchall()
    items = {}
    for li in db.execute("SELECT * FROM estimate_line_items ORDER BY line_item_id"):
        items.setdefault(li["estimate_id"], []).append(dict(li))
    result = []
    for row in rows:
        estimate = dict(row)
        estimate["created_at"] = estimate.pop("created_date")
        estimate["line_items"] = items.get(row["estimate_id"], [])
        result.append(estimate)
    return result


def get_estimate(estimate_id):
    found = get_estimates(estimate_id)
    if not found:
        raise RuleError("Estimate not found.", 404)
    return found[0]


def _save_estimate_lines(db, estimate_id, line_items):
    db.execute("DELETE FROM estimate_line_items WHERE estimate_id = ?", (estimate_id,))
    total = 0
    for li in line_items:
        line_total = _money(li["quantity"] * li["unit_cost"])
        total += line_total
        db.execute(
            """INSERT INTO estimate_line_items (estimate_id, category_id, description, quantity, unit_cost, line_total)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (estimate_id, li["category_id"], li["description"], li["quantity"], li["unit_cost"], line_total),
        )
    db.execute("UPDATE estimates SET total_amount = ? WHERE estimate_id = ?", (_money(total), estimate_id))


def create_estimate(data, user_id):
    db = get_db()
    with db:
        cursor = db.execute(
            "INSERT INTO estimates (estimate_number, title, client_id, created_by, status, created_at) "
            "VALUES ('pending', ?, ?, ?, ?, datetime('now', 'localtime'))",
            (data["title"], data["client_id"], user_id, data["status"]),
        )
        estimate_id = cursor.lastrowid
        db.execute("UPDATE estimates SET estimate_number = ? WHERE estimate_id = ?", (f"EST-{estimate_id}", estimate_id))
        _save_estimate_lines(db, estimate_id, data["line_items"])
    return get_estimate(estimate_id)


def update_estimate(estimate_id, data):
    current = get_estimate(estimate_id)
    if current["status"] not in ESTIMATE_EDITABLE:
        raise RuleError(f"A {current['status'].lower()} estimate can't be edited.", 409)
    if current["status"] == "Sent" and data["status"] == "Draft":
        raise RuleError("A sent estimate can't go back to draft.", 409)
    db = get_db()
    with db:
        db.execute(
            "UPDATE estimates SET title = ?, client_id = ?, status = ? WHERE estimate_id = ?",
            (data["title"], data["client_id"], data["status"], estimate_id),
        )
        _save_estimate_lines(db, estimate_id, data["line_items"])
    return get_estimate(estimate_id)


def set_estimate_status(estimate_id, new_status):
    current = get_estimate(estimate_id)
    allowed = ESTIMATE_TRANSITIONS.get(current["status"], ())
    if new_status not in allowed:
        raise RuleError(f"Can't change a {current['status'].lower()} estimate to {new_status.lower()}.", 409)
    db = get_db()
    with db:
        db.execute("UPDATE estimates SET status = ? WHERE estimate_id = ?", (new_status, estimate_id))
    return get_estimate(estimate_id)


def delete_estimate(estimate_id):
    current = get_estimate(estimate_id)
    if current["status"] != "Draft":
        raise RuleError("Only draft estimates can be deleted.", 409)
    db = get_db()
    with db:
        db.execute("DELETE FROM estimates WHERE estimate_id = ?", (estimate_id,))


def convert_estimate(estimate_id, data):
    """Create a project from an approved estimate (RTM A4)."""
    current = get_estimate(estimate_id)
    if current["status"] != "Approved":
        raise RuleError("Only approved estimates can be converted.", 409)
    db = get_db()
    with db:
        cursor = db.execute(
            """INSERT INTO projects (project_number, name, description, client_id, estimate_id,
                                     project_manager_id, status, budget_amount, start_date, due_date)
               VALUES ('pending', ?, ?, ?, ?, ?, 'Planning', ?, ?, ?)""",
            (data["name"], f"Created from {current['estimate_number']}", current["client_id"], estimate_id,
             data["project_manager_id"], data["budget_amount"], data["start_date"], data["due_date"]),
        )
        project_id = cursor.lastrowid
        project_number = f"BB-{project_id:04d}"
        db.execute("UPDATE projects SET project_number = ? WHERE project_id = ?", (project_number, project_id))
        db.execute("UPDATE estimates SET status = 'Converted' WHERE estimate_id = ?", (estimate_id,))
        from seed_data import copy_estimate_budget
        copy_estimate_budget(db, project_id)   # Job Costs "Estimated" column comes from the estimate
    return {"project_id": project_id, "project_number": project_number, "estimate": get_estimate(estimate_id)}


# ---------------------------------------------------------------------
# Invoices (RTM A5)
# ---------------------------------------------------------------------
INVOICE_EDITABLE = ("Draft", "Unpaid")
INVOICE_TRANSITIONS = {
    "Unpaid": ("Paid",),
    "Paid": ("Unpaid",),   # undo a mistaken "Mark Paid"
}


def get_invoices(invoice_id=None):
    db = get_db()
    where, params = ("WHERE i.invoice_id = ?", (invoice_id,)) if invoice_id else ("", ())
    rows = db.execute(
        f"""SELECT i.*, p.name AS project_name, c.name AS client_name
            FROM invoices i
            JOIN projects p ON p.project_id = i.project_id
            JOIN clients c  ON c.client_id = p.client_id
            {where}
            ORDER BY i.invoice_id DESC""",
        params,
    ).fetchall()
    items = {}
    for li in db.execute("SELECT * FROM invoice_line_items ORDER BY invoice_line_item_id"):
        items.setdefault(li["invoice_id"], []).append(dict(li))
    return [dict(row, line_items=items.get(row["invoice_id"], [])) for row in rows]


def get_invoice(invoice_id):
    found = get_invoices(invoice_id)
    if not found:
        raise RuleError("Invoice not found.", 404)
    return found[0]


def _save_invoice_lines(db, invoice_id, line_items):
    db.execute("DELETE FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
    total = 0
    for li in line_items:
        line_total = _money(li["quantity"] * li["unit_price"])
        total += line_total
        db.execute(
            """INSERT INTO invoice_line_items (invoice_id, description, quantity, unit_price, line_total)
               VALUES (?, ?, ?, ?, ?)""",
            (invoice_id, li["description"], li["quantity"], li["unit_price"], line_total),
        )
    db.execute("UPDATE invoices SET total_amount = ? WHERE invoice_id = ?", (_money(total), invoice_id))


def create_invoice(data):
    db = get_db()
    with db:
        cursor = db.execute(
            """INSERT INTO invoices (invoice_number, project_id, issue_date, due_date, status)
               VALUES ('pending', ?, ?, ?, ?)""",
            (data["project_id"], data["issue_date"], data["due_date"], data["status"]),
        )
        invoice_id = cursor.lastrowid
        db.execute("UPDATE invoices SET invoice_number = ? WHERE invoice_id = ?", (f"INV-{invoice_id}", invoice_id))
        _save_invoice_lines(db, invoice_id, data["line_items"])
    return get_invoice(invoice_id)


def update_invoice(invoice_id, data):
    current = get_invoice(invoice_id)
    if current["status"] not in INVOICE_EDITABLE:
        raise RuleError("A paid invoice can't be edited. Mark it unpaid first.", 409)
    if current["status"] == "Unpaid" and data["status"] == "Draft":
        raise RuleError("A sent invoice can't go back to draft.", 409)
    db = get_db()
    with db:
        db.execute(
            "UPDATE invoices SET project_id = ?, issue_date = ?, due_date = ?, status = ? WHERE invoice_id = ?",
            (data["project_id"], data["issue_date"], data["due_date"], data["status"], invoice_id),
        )
        _save_invoice_lines(db, invoice_id, data["line_items"])
    return get_invoice(invoice_id)


def set_invoice_status(invoice_id, new_status):
    current = get_invoice(invoice_id)
    if new_status not in INVOICE_TRANSITIONS.get(current["status"], ()):
        raise RuleError(f"Can't change a {current['status'].lower()} invoice to {new_status.lower()}.", 409)
    db = get_db()
    with db:
        db.execute(
            "UPDATE invoices SET status = ?, paid_at = CASE WHEN ? = 'Paid' THEN date('now', 'localtime') END "
            "WHERE invoice_id = ?",
            (new_status, new_status, invoice_id),
        )
    return get_invoice(invoice_id)


def delete_invoice(invoice_id):
    current = get_invoice(invoice_id)
    if current["status"] != "Draft":
        raise RuleError("Only draft invoices can be deleted.", 409)
    db = get_db()
    with db:
        db.execute("DELETE FROM invoices WHERE invoice_id = ?", (invoice_id,))


# ---------------------------------------------------------------------
# Dashboard (employee)
# ---------------------------------------------------------------------
def get_dashboard():
    db = get_db()
    one = lambda sql: db.execute(sql).fetchone()[0]
    stats = {
        "active_projects": one("SELECT COUNT(*) FROM projects WHERE status = 'In Progress'"),
        "pending_estimates": one("SELECT COUNT(*) FROM estimates WHERE status = 'Sent'"),
        "unpaid_total": one("SELECT COALESCE(SUM(total_amount), 0) FROM invoices WHERE status = 'Unpaid'"),
        "unpaid_count": one("SELECT COUNT(*) FROM invoices WHERE status = 'Unpaid'"),
        "overdue_count": one(
            "SELECT COUNT(*) FROM invoices WHERE status = 'Unpaid' AND due_date < date('now', 'localtime')"),
    }
    open_projects = db.execute(
        _PROJECT_SELECT + " WHERE p.status != 'Completed' "
        "ORDER BY CASE p.status WHEN 'In Progress' THEN 0 WHEN 'Planning' THEN 1 ELSE 2 END, "
        "p.due_date IS NULL, p.due_date"
    ).fetchall()

    # Recent activity is built from the timestamps already stored on each record.
    events = db.execute(
        """
        SELECT created_at AS at, 'Estimate ' || estimate_number || ' created: ' || title AS text
          FROM estimates
        UNION ALL
        SELECT issue_date, 'Invoice ' || i.invoice_number || ' sent: ' || p.name
          FROM invoices i JOIN projects p ON p.project_id = i.project_id WHERE i.status != 'Draft'
        UNION ALL
        SELECT paid_at, 'Invoice ' || invoice_number || ' paid ($' || printf('%,.2f', total_amount) || ')'
          FROM invoices WHERE paid_at IS NOT NULL
        UNION ALL
        SELECT created_at, 'Project ' || name || ' created'
               || CASE WHEN estimate_id IS NOT NULL THEN ' from an estimate' ELSE '' END
          FROM projects
        ORDER BY at DESC
        LIMIT 6
        """
    ).fetchall()
    return {"stats": stats, "projects": open_projects, "activity": events}


# ---------------------------------------------------------------------
# Tasks / Schedule (RTM A11)
# ---------------------------------------------------------------------
TASK_STATUSES = ("Not Started", "In Progress", "Completed")
TASK_PRIORITIES = ("Low", "Medium", "High")

# Same field names the Schedule page's JavaScript already uses.
_TASK_SELECT = """
    SELECT t.task_id AS id, t.project_id, p.name AS project_name, t.title AS name,
           COALESCE(t.description, '') AS description, COALESCE(t.assigned_to, '') AS assigned_to,
           t.start_date, t.due_date, t.priority, t.status
    FROM tasks t JOIN projects p ON p.project_id = t.project_id
"""


def get_tasks(project_id=None):
    if project_id is None:
        rows = get_db().execute(_TASK_SELECT + " ORDER BY t.due_date, t.task_id")
    else:
        rows = get_db().execute(_TASK_SELECT + " WHERE t.project_id = ? ORDER BY t.due_date, t.task_id", (project_id,))
    return [dict(row) for row in rows]


def get_task(task_id):
    row = get_db().execute(_TASK_SELECT + " WHERE t.task_id = ?", (task_id,)).fetchone()
    if row is None:
        raise RuleError("Task not found.", 404)
    return dict(row)


def get_schedule_data():
    projects = get_db().execute("SELECT project_id AS id, name FROM projects ORDER BY name").fetchall()
    return {
        "projects": [dict(p) for p in projects],
        "statuses": list(TASK_STATUSES),
        "priorities": list(TASK_PRIORITIES),
        "tasks": get_tasks(),
    }


def get_open_tasks():
    return [task for task in get_tasks() if task["status"] != "Completed"]


def create_task(data):
    db = get_db()
    with db:
        cursor = db.execute(
            """INSERT INTO tasks (project_id, title, description, assigned_to, start_date, due_date, priority, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["project_id"], data["name"], data["description"] or None, data["assigned_to"] or None,
             data["start_date"], data["due_date"], data["priority"], data["status"]),
        )
    return get_task(cursor.lastrowid)


def update_task(task_id, data):
    get_task(task_id)
    db = get_db()
    with db:
        db.execute(
            """UPDATE tasks SET project_id = ?, title = ?, description = ?, assigned_to = ?,
                                start_date = ?, due_date = ?, priority = ?, status = ?
               WHERE task_id = ?""",
            (data["project_id"], data["name"], data["description"] or None, data["assigned_to"] or None,
             data["start_date"], data["due_date"], data["priority"], data["status"], task_id),
        )
    return get_task(task_id)


def set_task_status(task_id, status):
    get_task(task_id)
    db = get_db()
    with db:
        db.execute("UPDATE tasks SET status = ? WHERE task_id = ?", (status, task_id))
    return get_task(task_id)


def delete_task(task_id):
    get_task(task_id)
    db = get_db()
    with db:
        db.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))


# ---------------------------------------------------------------------
# Job costs (RTM A6, A7)
# ---------------------------------------------------------------------
_EXPENSE_SELECT = """
    SELECT r.receipt_id AS id, r.project_id, r.expense_date, r.description, c.name AS category,
           CAST(r.amount AS REAL) AS amount, r.receipt_filename AS receipt_name,
           (r.file_path IS NOT NULL) AS has_receipt
    FROM receipts r JOIN cost_categories c ON c.category_id = r.category_id
"""


def get_expenses(project_id=None):
    sql, params = _EXPENSE_SELECT, ()
    if project_id is not None:
        sql, params = sql + " WHERE r.project_id = ?", (project_id,)
    rows = get_db().execute(sql + " ORDER BY r.expense_date DESC, r.receipt_id DESC", params)
    return [dict(row, has_receipt=bool(row["has_receipt"])) for row in rows]


def get_expense(expense_id):
    row = get_db().execute(_EXPENSE_SELECT + " WHERE r.receipt_id = ?", (expense_id,)).fetchone()
    if row is None:
        raise RuleError("Expense not found.", 404)
    return dict(row, has_receipt=bool(row["has_receipt"]))


def get_receipt_file(expense_id):
    row = get_db().execute(
        "SELECT file_path, receipt_filename FROM receipts WHERE receipt_id = ?", (expense_id,)).fetchone()
    if row is None or row["file_path"] is None:
        raise RuleError("No receipt file is on record for this expense.", 404)
    return row["file_path"], row["receipt_filename"]


def get_job_cost_data():
    db = get_db()
    return {
        "projects": [dict(r) for r in db.execute(
            "SELECT project_id AS id, name, CAST(budget_amount AS REAL) AS budget FROM projects ORDER BY name")],
        "categories": [r[0] for r in db.execute(
            "SELECT name FROM cost_categories WHERE is_active = 1 ORDER BY category_id")],
        "estimates": [dict(r) for r in db.execute(
            """SELECT b.project_id, c.name AS category, CAST(b.estimated_amount AS REAL) AS estimated_amount
               FROM project_budget_items b JOIN cost_categories c ON c.category_id = b.category_id""")],
        "expenses": get_expenses(),
    }


def category_id_for(name):
    row = get_db().execute(
        "SELECT category_id FROM cost_categories WHERE name = ? AND is_active = 1", (name,)).fetchone()
    return row["category_id"] if row else None


def create_expense(data, user_id):
    db = get_db()
    with db:
        cursor = db.execute(
            """INSERT INTO receipts (project_id, category_id, uploaded_by, description, amount, expense_date,
                                     receipt_filename, file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["project_id"], data["category_id"], user_id, data["description"], data["amount"],
             data["expense_date"], data.get("receipt_filename"), data.get("file_path")),
        )
    return get_expense(cursor.lastrowid)


def update_expense(expense_id, data):
    """Returns (updated expense, stored file name that is no longer used or None)."""
    old_file = get_db().execute("SELECT file_path FROM receipts WHERE receipt_id = ?", (expense_id,)).fetchone()
    if old_file is None:
        raise RuleError("Expense not found.", 404)
    replaced = None
    db = get_db()
    with db:
        db.execute(
            """UPDATE receipts SET project_id = ?, category_id = ?, description = ?, amount = ?, expense_date = ?
               WHERE receipt_id = ?""",
            (data["project_id"], data["category_id"], data["description"], data["amount"],
             data["expense_date"], expense_id),
        )
        if data.get("file_path"):
            db.execute("UPDATE receipts SET receipt_filename = ?, file_path = ? WHERE receipt_id = ?",
                       (data["receipt_filename"], data["file_path"], expense_id))
            replaced = old_file["file_path"]
    return get_expense(expense_id), replaced


def delete_expense(expense_id):
    """Returns the stored file name to remove from disk (or None)."""
    row = get_db().execute("SELECT file_path FROM receipts WHERE receipt_id = ?", (expense_id,)).fetchone()
    if row is None:
        raise RuleError("Expense not found.", 404)
    db = get_db()
    with db:
        db.execute("DELETE FROM receipts WHERE receipt_id = ?", (expense_id,))
    return row["file_path"]


# ---------------------------------------------------------------------
# Clients and subcontractors (employee directory)
# ---------------------------------------------------------------------
DIRECTORY_STATUSES = ("Active", "Inactive")


def _link_login(db, table, key, record_id, email, role):
    """If a login account with this email exists for the role, link it (used by the portals)."""
    if not email:
        return
    user = db.execute("SELECT id FROM users WHERE lower(email) = lower(?) AND role = ?", (email, role)).fetchone()
    if user and not db.execute(f"SELECT 1 FROM {table} WHERE user_id = ? AND {key} != ?", (user["id"], record_id)).fetchone():
        db.execute(f"UPDATE {table} SET user_id = ? WHERE {key} = ? AND user_id IS NULL", (user["id"], record_id))


def get_clients():
    return get_db().execute(
        """SELECT c.*, COUNT(p.project_id) AS project_count,
                  SUM(CASE WHEN p.status != 'Completed' THEN 1 ELSE 0 END) AS open_projects
           FROM clients c LEFT JOIN projects p ON p.client_id = c.client_id
           GROUP BY c.client_id ORDER BY c.name"""
    ).fetchall()


def get_client(client_id):
    return get_db().execute("SELECT * FROM clients WHERE client_id = ?", (client_id,)).fetchone()


def client_name_taken(name, exclude_id=None):
    return get_db().execute(
        "SELECT 1 FROM clients WHERE lower(name) = lower(?) AND client_id != ?", (name, exclude_id or 0)
    ).fetchone() is not None


def save_client(data, client_id=None):
    db = get_db()
    values = (data["name"], data["company"] or None, data["email"] or None, data["phone"] or None,
              data["address"] or None, data["status"], data["notes"] or None)
    with db:
        if client_id is None:
            client_id = db.execute(
                """INSERT INTO clients (name, company, email, phone, address, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""", values).lastrowid
        else:
            db.execute(
                """UPDATE clients SET name = ?, company = ?, email = ?, phone = ?, address = ?, status = ?, notes = ?
                   WHERE client_id = ?""", (*values, client_id))
        _link_login(db, "clients", "client_id", client_id, data["email"], "client")
    return client_id


def get_subcontractors():
    rows = get_db().execute(
        """SELECT s.*, COUNT(pa.assignment_id) AS project_count, GROUP_CONCAT(p.name, ', ') AS project_names
           FROM subcontractors s
           LEFT JOIN project_assignments pa ON pa.subcontractor_id = s.subcontractor_id
           LEFT JOIN projects p ON p.project_id = pa.project_id
           GROUP BY s.subcontractor_id ORDER BY s.contact_name"""
    ).fetchall()
    return rows


def get_subcontractor(subcontractor_id):
    return get_db().execute("SELECT * FROM subcontractors WHERE subcontractor_id = ?", (subcontractor_id,)).fetchone()


def get_subcontractor_project_ids(subcontractor_id):
    return [row[0] for row in get_db().execute(
        "SELECT project_id FROM project_assignments WHERE subcontractor_id = ?", (subcontractor_id,))]


def subcontractor_email_taken(email, exclude_id=None):
    return get_db().execute(
        "SELECT 1 FROM subcontractors WHERE lower(email) = lower(?) AND subcontractor_id != ?", (email, exclude_id or 0)
    ).fetchone() is not None


def save_subcontractor(data, project_ids, subcontractor_id=None):
    db = get_db()
    values = (data["company"], data["name"], data["trade"], data["email"], data["phone"] or None,
              data["address"] or None, data["license_number"] or None, data["status"], data["notes"] or None)
    with db:
        if subcontractor_id is None:
            subcontractor_id = db.execute(
                """INSERT INTO subcontractors (company_name, contact_name, trade, email, phone, address,
                                               license_number, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", values).lastrowid
        else:
            db.execute(
                """UPDATE subcontractors SET company_name = ?, contact_name = ?, trade = ?, email = ?, phone = ?,
                          address = ?, license_number = ?, status = ?, notes = ? WHERE subcontractor_id = ?""",
                (*values, subcontractor_id))
        # Assignments: keep existing rows that are still checked, add new ones, remove unchecked.
        current = set(get_subcontractor_project_ids(subcontractor_id))
        wanted = set(project_ids)
        for project_id in current - wanted:
            db.execute("DELETE FROM project_assignments WHERE subcontractor_id = ? AND project_id = ?",
                       (subcontractor_id, project_id))
        for project_id in wanted - current:
            db.execute(
                """INSERT INTO project_assignments (project_id, subcontractor_id, status, assigned_date)
                   VALUES (?, ?, 'Active', date('now', 'localtime'))""", (project_id, subcontractor_id))
        _link_login(db, "subcontractors", "subcontractor_id", subcontractor_id, data["email"], "subcontractor")
    return subcontractor_id


def get_project_choices():
    return get_db().execute("SELECT project_id, name, status FROM projects ORDER BY name").fetchall()
